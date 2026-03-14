import os
from pathlib import Path

from langchain_community.document_loaders import TextLoader
from langchain_community.embeddings import OllamaEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter, Language
from langchain_postgres.vectorstores import PGVector
from agent.app.database import engine
from agent.app.config import settings
from agent.app.services.repo_filters import collect_analyzable_files

def get_embeddings():
    return OllamaEmbeddings(
        model=settings.ollama_embed_model,
        base_url=settings.ollama_base_url,
    )

def process_single_file(snapshot_id: str, repo_dir: Path, rel_path: str) -> int:
    """Chunks and embeds a single file into the remote ChromaDB server."""
    docs = []
    from langchain_community.document_loaders import PyPDFLoader, NotebookLoader

    abs_path = repo_dir / rel_path
    ext = abs_path.suffix.lower()
    
    # Determine the multi-agent category
    if ext in {".pdf", ".md", ".txt", ".rst"}:
        category = "document"
    elif ext in {".py", ".ts", ".js", ".tsx", ".jsx", ".java", ".cpp", ".go", ".html", ".css", ".scss", ".rb", ".php", ".rs"}:
        category = "code"
    else:
        category = "other"

    try:
        if ext == ".pdf":
            loader = PyPDFLoader(str(abs_path))
            pdf_docs = loader.load()
            for pdoc in pdf_docs:
                docs.append({
                    "page_content": pdoc.page_content,
                    "metadata": {"source": str(rel_path), "category": category}
                })
        elif ext == ".ipynb":
            loader = NotebookLoader(
                str(abs_path),
                include_outputs=False,
                remove_newline=True
            )
            nb_docs = loader.load()
            for ndoc in nb_docs:
                docs.append({
                    "page_content": ndoc.page_content,
                    "metadata": {"source": str(rel_path), "category": category}
                })
        else:
            with open(abs_path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
            docs.append({"page_content": content, "metadata": {"source": str(rel_path), "category": category}})
    except Exception:
        pass

    if not docs:
        return 0

    from langchain_core.documents import Document
    lc_docs = [Document(page_content=d["page_content"], metadata=d["metadata"]) for d in docs]

    # Map extensions to specific LangChain AST chunking strategies
    EXTENSION_TO_LANGUAGE = {
        ".py": Language.PYTHON,
        ".js": Language.JS,
        ".ts": Language.TS,
        ".tsx": Language.TS,
        ".jsx": Language.JS,
        ".html": Language.HTML,
        ".md": Language.MARKDOWN,
        ".cpp": Language.CPP,
        ".java": Language.JAVA,
        ".go": Language.GO,
        ".rs": Language.RUST,
        ".rb": Language.RUBY,
        ".php": Language.PHP,
    }

    # Chunk intelligently based on the file's programming language
    splits = []
    # Optimized chunk sizes (3000 chars) for faster ingestion and broader semantic context
    default_splitter = RecursiveCharacterTextSplitter(chunk_size=3000, chunk_overlap=300)

    for doc in lc_docs:
        ext = Path(doc.metadata["source"]).suffix.lower()
        if ext in EXTENSION_TO_LANGUAGE:
            splitter = RecursiveCharacterTextSplitter.from_language(
                language=EXTENSION_TO_LANGUAGE[ext],
                chunk_size=3000,
                chunk_overlap=300
            )
            splits.extend(splitter.split_documents([doc]))
        else:
            splits.extend(default_splitter.split_documents([doc]))
    
    # Removed artificial 150-chunk limit.
    # The optimized chunk sizes (3000 chars) ensures we can index the full repository efficiently
    # without catastrophically freezing local CPU/RAM resources.

    collection_name = f"snapshot_{snapshot_id}"
    
    db = PGVector(
        embeddings=get_embeddings(),
        collection_name=collection_name,
        connection=engine,
        use_jsonb=True,
    )
    db.add_documents(splits)
    
    return len(splits)

def ingest_snapshot(snapshot_id: str, repo_dir: Path) -> int:
    """Fallback dispatcher to chunk sequentially if not using celery grouping."""
    candidates = collect_analyzable_files(repo_dir, collect_paths=True)
    paths = candidates.get("paths", [])
    total_chunks = 0
    for p in paths:
        total_chunks += process_single_file(snapshot_id, repo_dir, p)
    return total_chunks


async def stream_question(snapshot_id: str, question: str, history: list[dict[str, str]] | None = None):
    """Runs a RAG query against the snapshot's code and streams the LLM response chunks as NDJSON."""
    collection_name = f"snapshot_{snapshot_id}"
    
    db = PGVector(
        embeddings=get_embeddings(),
        collection_name=collection_name,
        connection=engine,
        use_jsonb=True,
    )
    
    # Multi-Agent Metadata Retrieval
    import asyncio
    try:
        # We can run these concurrently to speed up the retrieval phase
        docs_code, docs_doc, docs_other = await asyncio.gather(
            db.asimilarity_search(question, k=4, filter={"category": "code"}),
            db.asimilarity_search(question, k=4, filter={"category": "document"}),
            db.asimilarity_search(question, k=3, filter={"category": "other"})
        )
        docs = docs_code + docs_doc + docs_other
    except Exception:
        docs = []

    # Fallback to general search if metadata filtering failed (e.g., old snaphot)
    if not docs:
        docs = await db.asimilarity_search(question, k=8)
        
    context = "\n\n".join(d.page_content for d in docs)
    
    # Extract unique source file paths from metadata
    sources = list({d.metadata.get("source", "unknown") for d in docs})
    
    import json
    
    # Pre-yield the sources so the frontend has them instantly
    yield json.dumps({"type": "sources", "sources": list(sources)}) + "\n"

    # Build System message with Context
    system_prompt = (
        "You are an expert coding assistant analyzing a specific codebase.\n"
        "Use the provided [Codebase Context] below to answer the user's questions in detail.\n"
        "If you are asked a general question about the repository (e.g. 'what is this repo about?'), "
        "synthesize a summary based on whatever files, documentation, or code snippets happen to be provided in the context below.\n"
        "If the specific answer cannot be found at all, explain what you DO see in the context instead of rejecting the question.\n\n"
        f"--- [Codebase Context] ---\n{context}\n--------------------------"
    )
    
    messages = [{"role": "system", "content": system_prompt}]
    if history:
        for msg in history:
            messages.append({"role": msg.get("role", "user"), "content": msg.get("content", "")})
            
    messages.append({"role": "user", "content": question})
    
    # Stream the local Ollama API processing back to the client directly
    import httpx
    url = f"{settings.ollama_base_url}/api/chat"
    data = {
        "model": settings.ollama_model,
        "messages": messages,
        "stream": True,
    }
    
    async with httpx.AsyncClient() as client:
        try:
            async with client.stream("POST", url, json=data) as response:
                async for chunk in response.aiter_lines():
                    if chunk:
                        try:
                            # Ollama streams complete json objects per line when streaming
                            obj = json.loads(chunk)
                            if "message" in obj:
                                content = obj["message"].get("content", "")
                                yield json.dumps({"type": "token", "content": content}) + "\n"
                        except Exception:
                            pass
        except Exception as e:
            yield json.dumps({"type": "token", "content": f"\nError communicating with Local LLM: {str(e)}"}) + "\n"
