"use client";

import { useEffect, useState, useRef, useCallback } from "react";
import { useParams, useRouter } from "next/navigation";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Send, Bot, User, Code2, Loader2, ArrowLeft,
  Copy, Check, Download, X, ChevronRight, ChevronDown,
  RotateCcw, Folder, FolderOpen, FileCode, FileText, File,
} from "lucide-react";
import axios from "axios";
import Link from "next/link";
import ReactMarkdown from "react-markdown";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import { vscDarkPlus } from "react-syntax-highlighter/dist/esm/styles/prism";

type Message = { role: "user" | "assistant"; content: string; sources?: string[] };

// Suggested questions mapped to tech stack keywords
const SUGGESTED_QUESTIONS: Record<string, string[]> = {
  fastapi:   ["How is authentication handled?", "What API endpoints are defined?", "How is error handling implemented?"],
  django:    ["How are models structured?", "Where is user auth handled?", "What middleware is configured?"],
  next:      ["How is routing structured?", "Where is state management handled?", "How are API routes defined?"],
  react:     ["What components exist?", "How is global state managed?", "Where are API calls made?"],
  python:    ["What is the main entry point?", "How are dependencies managed?", "Where is configuration stored?"],
  typescript:["What are the key interfaces?", "How is the project structured?", "Where are types defined?"],
  default:   ["What does this codebase do?", "What is the folder structure?", "What dependencies does it use?"],
};

function getSuggestedQuestions(techStack: any): string[] {
  if (!techStack) return SUGGESTED_QUESTIONS.default;
  const all = [
    ...(techStack.frameworks || []),
    ...(techStack.languages || []),
  ].map((s: string) => s.toLowerCase());

  for (const key of Object.keys(SUGGESTED_QUESTIONS)) {
    if (all.some((s) => s.includes(key))) return SUGGESTED_QUESTIONS[key];
  }
  return SUGGESTED_QUESTIONS.default;
}

// Copy button component
function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  const handleCopy = async () => {
    await navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };
  return (
    <button
      onClick={handleCopy}
      className="p-1.5 rounded transition-all"
      style={{
        color: "var(--ra-muted)",
        background: "transparent",
      }}
      onMouseEnter={(e) => {
        (e.currentTarget as HTMLElement).style.color = "var(--ra-accent)";
        (e.currentTarget as HTMLElement).style.background = "var(--ra-accent-dim)";
      }}
      onMouseLeave={(e) => {
        (e.currentTarget as HTMLElement).style.color = "var(--ra-muted)";
        (e.currentTarget as HTMLElement).style.background = "transparent";
      }}
      title="Copy message"
    >
      {copied ? <Check className="w-3.5 h-3.5" /> : <Copy className="w-3.5 h-3.5" />}
    </button>
  );
}

// Markdown renderer with syntax highlighting
function MarkdownContent({ content }: { content: string }) {
  return (
    <ReactMarkdown
      components={{
        code({ node, inline, className, children, ...props }: any) {
          const match = /language-(\w+)/.exec(className || "");
          return !inline && match ? (
            <SyntaxHighlighter
              style={vscDarkPlus as any}
              language={match[1]}
              PreTag="div"
              className="!rounded-lg !text-xs !my-2"
              {...props}
            >
              {String(children).replace(/\n$/, "")}
            </SyntaxHighlighter>
          ) : (
            <code
              className={className}
              style={{
                fontFamily: "var(--font-mono)",
                background: "var(--ra-elevated)",
                color: "var(--ra-code)",
                padding: "0.15em 0.4em",
                borderRadius: "4px",
                fontSize: "0.85em",
              }}
              {...props}
            >
              {children}
            </code>
          );
        },
        p: ({ children }) => <p className="mb-2 last:mb-0 leading-relaxed text-sm">{children}</p>,
        ul: ({ children }) => <ul className="list-disc pl-4 mb-2 space-y-0.5 text-sm">{children}</ul>,
        ol: ({ children }) => <ol className="list-decimal pl-4 mb-2 space-y-0.5 text-sm">{children}</ol>,
        li: ({ children }) => <li className="leading-relaxed">{children}</li>,
        strong: ({ children }) => <strong className="font-semibold" style={{ color: "var(--ra-text)" }}>{children}</strong>,
        h1: ({ children }) => <h1 className="text-base font-bold mb-2 mt-3" style={{ color: "var(--ra-text)" }}>{children}</h1>,
        h2: ({ children }) => <h2 className="text-sm font-bold mb-1.5 mt-3" style={{ color: "var(--ra-text)" }}>{children}</h2>,
        h3: ({ children }) => <h3 className="text-sm font-semibold mb-1 mt-2" style={{ color: "var(--ra-text)" }}>{children}</h3>,
      }}
    >
      {content}
    </ReactMarkdown>
  );
}

export default function Dashboard() {
  const { snapshot_id } = useParams();
  const router = useRouter();
  const [data, setData] = useState<any>(null);

  // Chat state
  const [messages, setMessages] = useState<Message[]>([
    { role: "assistant", content: "Hi! I've analyzed this repository. Ask me any technical questions about the codebase!" },
  ]);
  const [inputVal, setInputVal] = useState("");
  const [chatLoading, setChatLoading] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Source drawer
  const [drawerSource, setDrawerSource] = useState<string | null>(null);
  const [drawerContent, setDrawerContent] = useState<string | null>(null);
  const [drawerLoading, setDrawerLoading] = useState(false);
  const [routesOpen, setRoutesOpen] = useState(true);
  const [filesOpen, setFilesOpen] = useState(true);
  const [modelName, setModelName] = useState("llama3");

  // Fetch active model name from backend config
  useEffect(() => {
    axios
      .get("http://127.0.0.1:8000/api/config")
      .then((res) => setModelName(res.data.ollama_model || "llama3"))
      .catch(() => { /* fallback already set */ });
  }, []);

  useEffect(() => {
    if (!snapshot_id) return;
    axios
      .get(`http://127.0.0.1:8000/api/snapshots/${snapshot_id}`)
      .then((res) => {
        setData(res.data);
        // Save to recent repos
        try {
          const meta = res.data.meta || res.data;
          const owner = meta.owner || res.data.owner;
          const repo = meta.repo || res.data.repo;
          const repoUrl = meta.repo_url || res.data.repo_url || "";
          const name = `${owner}/${repo}`;
          const entry = { url: repoUrl, snapshotId: snapshot_id as string, name };
          const stored = localStorage.getItem("ra_recent_repos");
          const list = stored ? JSON.parse(stored) : [];
          const filtered = list.filter((r: any) => r.snapshotId !== snapshot_id);
          localStorage.setItem("ra_recent_repos", JSON.stringify([entry, ...filtered].slice(0, 8)));
        } catch { /* ignore */ }
      })
      .catch((err) => console.error("Error fetching snapshot data", err));
  }, [snapshot_id]);

  // Fetch file content when drawer opens
  useEffect(() => {
    if (!drawerSource || !snapshot_id) {
      setDrawerContent(null);
      return;
    }
    setDrawerLoading(true);
    setDrawerContent(null);
    const encoded = encodeURIComponent(drawerSource).replace(/%2F/g, "/");
    axios
      .get(`http://127.0.0.1:8000/api/snapshots/${snapshot_id}/files/${encoded}`, {
        responseType: "text",
        transformResponse: [(data) => data], // prevent axios from JSON-parsing
      })
      .then((res) => setDrawerContent(res.data as unknown as string))
      .catch(() => setDrawerContent("// Could not load file content."))
      .finally(() => setDrawerLoading(false));
  }, [drawerSource, snapshot_id]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, chatLoading]);

  const handleSend = useCallback(async (question?: string) => {
    const userQuery = question || inputVal.trim();
    if (!userQuery || chatLoading) return;
    setInputVal("");

    const newMessages: Message[] = [...messages, { role: "user", content: userQuery }];
    setMessages(newMessages);
    setChatLoading(true);

    try {
      const historyPayload = newMessages
        .slice(1, -1)
        .map((m) => ({ role: m.role, content: m.content }));

      const res = await fetch(`http://127.0.0.1:8000/api/chat/${snapshot_id}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: userQuery, history: historyPayload }),
      });

      if (!res.body) throw new Error("No response body");

      const reader = res.body.getReader();
      const decoder = new TextDecoder("utf-8");
      let currentAnswer = "";
      let currentSources: string[] = [];

      setMessages((prev) => [...prev, { role: "assistant", content: "", sources: [] }]);

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        const chunk = decoder.decode(value, { stream: true });
        for (const line of chunk.split("\n").filter((l) => l.trim())) {
          try {
            const parsed = JSON.parse(line);
            if (parsed.type === "sources") currentSources = parsed.sources;
            else if (parsed.type === "token") currentAnswer += parsed.content;
            setMessages((prev) => {
              const arr = [...prev];
              arr[arr.length - 1] = { role: "assistant", content: currentAnswer, sources: currentSources };
              return arr;
            });
          } catch { /* partial JSON */ }
        }
      }
    } catch {
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: "Sorry, I encountered an error. Is Ollama running?" },
      ]);
    } finally {
      setChatLoading(false);
    }
  }, [inputVal, messages, chatLoading, snapshot_id]);

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const exportMarkdown = () => {
    if (!data) return;
    const lines = [
      `# ${data.meta.owner}/${data.meta.repo} — Analysis Report`,
      "",
      `**Snapshot ID:** \`${snapshot_id}\``,
      "",
      "## Tech Stack",
      "",
      ...(data.results?.tech_stack?.languages || []).map((l: string) => `- ${l}`),
      ...(data.results?.tech_stack?.frameworks || []).map((f: string) => `- ${f}`),
      "",
      "## API Endpoints",
      "",
      ...(data.results?.routes?.fastapi || []).map(
        (r: any) => `- \`${r.methods.join(", ")} ${r.path}\``
      ),
      "",
      "## Chat History",
      "",
      ...messages.slice(1).map((m) => `**${m.role === "user" ? "You" : "Assistant"}:** ${m.content}`),
    ].join("\n");

    const blob = new Blob([lines], { type: "text/markdown" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `${data.meta.repo}-analysis.md`;
    a.click();
  };

  // Loading state
  if (!data) {
    return (
      <div className="min-h-screen flex items-center justify-center" style={{ background: "var(--ra-bg)" }}>
        <div
          className="w-6 h-6 rounded-full border-2 border-t-transparent animate-spin"
          style={{ borderColor: "var(--ra-accent) var(--ra-accent) var(--ra-accent) transparent" }}
        />
      </div>
    );
  }

  const routes = data.results?.routes?.fastapi || [];
  const techStack = data.results?.tech_stack || {};
  const scannedFiles: string[] = data.results?.scanned_files || [];
  const allTech = [
    ...(techStack.languages || []),
    ...(techStack.frameworks || []),
    ...(techStack.databases || []),
  ];
  const suggested = getSuggestedQuestions(techStack);
  const showSuggested = messages.length === 1; // only show before user starts chatting

  // Helper to pick a file icon based on extension
  function FileIcon({ path }: { path: string }) {
    const ext = path.split(".").pop()?.toLowerCase() || "";
    if (["py","ts","tsx","js","jsx","go","rs","java","cpp","rb","php"].includes(ext))
      return <FileCode className="w-3 h-3 flex-shrink-0" style={{ color: "var(--ra-accent)" }} />;
    if (["md","txt","rst","yaml","yml","json","toml"].includes(ext))
      return <FileText className="w-3 h-3 flex-shrink-0" style={{ color: "var(--ra-blue)" }} />;
    return <File className="w-3 h-3 flex-shrink-0" style={{ color: "var(--ra-muted)" }} />;
  }

  return (
    <div className="min-h-screen flex flex-col" style={{ background: "var(--ra-bg)" }}>
      {/* Header */}
      <header
        className="border-b sticky top-0 z-40 h-14 flex items-center px-4 gap-4"
        style={{
          borderColor: "var(--ra-border)",
          background: "rgba(10,10,15,0.85)",
          backdropFilter: "blur(12px)",
        }}
      >
        <Link href="/">
          <button
            className="flex items-center gap-1.5 text-sm font-mono transition-colors"
            style={{ color: "var(--ra-muted)" }}
            onMouseEnter={(e) => (e.currentTarget.style.color = "var(--ra-accent)")}
            onMouseLeave={(e) => (e.currentTarget.style.color = "var(--ra-muted)")}
          >
            <ArrowLeft className="w-4 h-4" />
            Home
          </button>
        </Link>

        <div className="h-4 w-px" style={{ background: "var(--ra-border)" }} />

        <span className="text-sm font-mono" style={{ color: "var(--ra-muted)" }}>
          <span style={{ color: "var(--ra-text)" }}>{data.meta.owner}/{data.meta.repo}</span>
        </span>

        {/* Tech stack in header */}
        <div className="flex gap-1.5 ml-2 overflow-x-auto flex-1">
          {allTech.slice(0, 6).map((t: string) => (
            <span
              key={t}
              className="text-[10px] font-mono px-2 py-0.5 rounded-full whitespace-nowrap flex-shrink-0"
              style={{
                background: "var(--ra-accent-dim)",
                color: "var(--ra-accent)",
                border: "1px solid rgba(0,229,160,0.2)",
              }}
            >
              {t}
            </span>
          ))}
        </div>

        {/* Header actions */}
        <div className="flex items-center gap-2 ml-auto flex-shrink-0">
          <button
            onClick={() => router.push("/")}
            className="flex items-center gap-1.5 text-xs font-mono px-3 py-1.5 rounded-lg transition-colors"
            style={{ color: "var(--ra-muted)", border: "1px solid var(--ra-border)" }}
            onMouseEnter={(e) => {
              (e.currentTarget as HTMLElement).style.color = "var(--ra-text)";
              (e.currentTarget as HTMLElement).style.borderColor = "var(--ra-accent)";
            }}
            onMouseLeave={(e) => {
              (e.currentTarget as HTMLElement).style.color = "var(--ra-muted)";
              (e.currentTarget as HTMLElement).style.borderColor = "var(--ra-border)";
            }}
            title="Re-analyze"
          >
            <RotateCcw className="w-3.5 h-3.5" /> Re-analyze
          </button>
          <button
            onClick={exportMarkdown}
            className="flex items-center gap-1.5 text-xs font-mono px-3 py-1.5 rounded-lg transition-colors"
            style={{ color: "var(--ra-muted)", border: "1px solid var(--ra-border)" }}
            onMouseEnter={(e) => {
              (e.currentTarget as HTMLElement).style.color = "var(--ra-text)";
              (e.currentTarget as HTMLElement).style.borderColor = "var(--ra-accent)";
            }}
            onMouseLeave={(e) => {
              (e.currentTarget as HTMLElement).style.color = "var(--ra-muted)";
              (e.currentTarget as HTMLElement).style.borderColor = "var(--ra-border)";
            }}
          >
            <Download className="w-3.5 h-3.5" /> Export
          </button>
        </div>
      </header>

      {/* 3-panel layout */}
      <div className="flex flex-1 overflow-hidden h-[calc(100vh-3.5rem)]">

        {/* LEFT PANEL — API routes & info */}
        <aside
          className="w-60 flex-shrink-0 border-r flex flex-col overflow-hidden hidden md:flex"
          style={{ borderColor: "var(--ra-border)", background: "var(--ra-surface)" }}
        >
          <ScrollArea className="flex-1">
            <div className="p-3 space-y-4">
              {/* Snapshot ID */}
              <div>
                <p className="text-[10px] font-mono uppercase tracking-widest mb-1" style={{ color: "var(--ra-muted)" }}>
                  Snapshot
                </p>
                <p className="text-xs font-mono truncate" style={{ color: "var(--ra-muted)" }}>{snapshot_id}</p>
              </div>

              {/* API Endpoints */}
              {routes.length > 0 && (
                <div>
                  <button
                    className="flex items-center justify-between w-full text-[10px] font-mono uppercase tracking-widest mb-2"
                    style={{ color: "var(--ra-muted)" }}
                    onClick={() => setRoutesOpen(!routesOpen)}
                  >
                    Endpoints ({routes.length})
                    {routesOpen ? <ChevronDown className="w-3 h-3" /> : <ChevronRight className="w-3 h-3" />}
                  </button>
                  {routesOpen && (
                    <div className="space-y-1">
                      {routes.map((route: any, i: number) => (
                        <div
                          key={i}
                          className="px-2 py-1.5 rounded-md"
                          style={{ background: "var(--ra-elevated)" }}
                        >
                          <div className="flex items-center gap-1.5 flex-wrap">
                            <span
                              className="text-[9px] font-mono font-bold px-1 py-0.5 rounded"
                              style={{
                                background: route.methods.includes("GET")
                                  ? "rgba(77,158,255,0.15)"
                                  : route.methods.includes("POST")
                                  ? "var(--ra-accent-dim)"
                                  : "rgba(245,158,11,0.15)",
                                color: route.methods.includes("GET")
                                  ? "var(--ra-blue)"
                                  : route.methods.includes("POST")
                                  ? "var(--ra-accent)"
                                  : "#f59e0b",
                              }}
                            >
                              {route.methods.join(",")}
                            </span>
                            <span className="text-[11px] font-mono break-all" style={{ color: "var(--ra-text)" }}>
                              {route.path}
                            </span>
                          </div>
                          {route.handler && (
                            <span className="text-[10px] font-mono mt-0.5 block" style={{ color: "var(--ra-muted)" }}>
                              → {route.handler}()
                            </span>
                          )}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>
          </ScrollArea>

          {/* File tree */}
          {scannedFiles.length > 0 && (
            <div className="border-t" style={{ borderColor: "var(--ra-border)" }}>
              <ScrollArea style={{ maxHeight: "40vh" }}>
                <div className="p-3">
                  <button
                    className="flex items-center justify-between w-full text-[10px] font-mono uppercase tracking-widest mb-2"
                    style={{ color: "var(--ra-muted)" }}
                    onClick={() => setFilesOpen(!filesOpen)}
                  >
                    Files ({scannedFiles.length})
                    {filesOpen ? <ChevronDown className="w-3 h-3" /> : <ChevronRight className="w-3 h-3" />}
                  </button>
                  {filesOpen && (
                    <div className="space-y-0.5">
                      {scannedFiles.slice(0, 200).map((f, i) => (
                        <button
                          key={i}
                          onClick={() => setDrawerSource(f)}
                          className="flex items-center gap-1.5 w-full rounded px-1 py-1 text-left transition-colors"
                          style={{
                            background: drawerSource === f ? "var(--ra-accent-dim)" : "transparent",
                            color: drawerSource === f ? "var(--ra-accent)" : "var(--ra-muted)",
                          }}
                          onMouseEnter={(e) => {
                            if (drawerSource !== f) {
                              (e.currentTarget as HTMLElement).style.background = "var(--ra-elevated)";
                              (e.currentTarget as HTMLElement).style.color = "var(--ra-text)";
                            }
                          }}
                          onMouseLeave={(e) => {
                            if (drawerSource !== f) {
                              (e.currentTarget as HTMLElement).style.background = "transparent";
                              (e.currentTarget as HTMLElement).style.color = "var(--ra-muted)";
                            }
                          }}
                          title={f}
                        >
                          <FileIcon path={f} />
                          <span className="text-[10px] font-mono truncate flex-1 text-left">{f}</span>
                        </button>
                      ))}
                      {scannedFiles.length > 200 && (
                        <p className="text-[10px] font-mono px-1 mt-1" style={{ color: "var(--ra-muted)" }}>
                          + {scannedFiles.length - 200} more files
                        </p>
                      )}
                    </div>
                  )}
                </div>
              </ScrollArea>
            </div>
          )}
        </aside>

        {/* CENTER PANEL — AI Chat */}
        <main className="flex-1 flex flex-col overflow-hidden">
          {/* Chat header */}
          <div
            className="flex items-center justify-between px-4 py-2.5 border-b"
            style={{ borderColor: "var(--ra-border)", background: "var(--ra-surface)" }}
          >
            <div className="flex items-center gap-2">
              <div
                className="w-2 h-2 rounded-full"
                style={{ background: "var(--ra-accent)", boxShadow: "0 0 4px var(--ra-accent)" }}
              />
              <span className="text-sm font-semibold" style={{ color: "var(--ra-text)" }}>AI Chat</span>
            </div>
            <span className="text-xs font-mono" style={{ color: "var(--ra-muted)" }}>
              {modelName} · local
            </span>
          </div>

          {/* Messages */}
          <ScrollArea className="flex-1 min-h-0">
            <div className="max-w-2xl mx-auto px-4 py-6 space-y-6">
              {messages.map((m, i) => (
                <div key={i} className={`flex gap-3 ${m.role === "user" ? "flex-row-reverse" : "flex-row"}`}>
                  {/* Avatar */}
                  <div
                    className="w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0"
                    style={{
                      background: m.role === "user" ? "var(--ra-elevated)" : "var(--ra-accent-dim)",
                      border: `1px solid ${m.role === "user" ? "var(--ra-border)" : "rgba(0,229,160,0.3)"}`,
                    }}
                  >
                    {m.role === "user"
                      ? <User className="w-4 h-4" style={{ color: "var(--ra-muted)" }} />
                      : <Bot className="w-4 h-4" style={{ color: "var(--ra-accent)" }} />
                    }
                  </div>

                  {/* Bubble */}
                  <div className={`flex flex-col gap-2 min-w-0 flex-1 ${m.role === "user" ? "items-end" : "items-start"}`}>
                    <div
                      className="relative group px-4 py-3 rounded-2xl max-w-full"
                      style={{
                        background: m.role === "user" ? "var(--ra-elevated)" : "var(--ra-surface)",
                        border: "1px solid",
                        borderColor: m.role === "user" ? "var(--ra-border)" : "var(--ra-border)",
                        borderRadius: m.role === "user" ? "1rem 0.25rem 1rem 1rem" : "0.25rem 1rem 1rem 1rem",
                        color: "var(--ra-text)",
                      }}
                    >
                      {/* Copy button overlay */}
                      {m.content && (
                        <div className="absolute top-2 right-2 opacity-0 group-hover:opacity-100 transition-opacity">
                          <CopyButton text={m.content} />
                        </div>
                      )}
                      {m.role === "assistant" ? (
                        <MarkdownContent content={m.content || "…"} />
                      ) : (
                        <p className="text-sm leading-relaxed">{m.content}</p>
                      )}
                    </div>

                    {/* Source citations */}
                    {m.sources && m.sources.length > 0 && (
                      <div className="flex flex-wrap gap-1.5">
                        {m.sources.map((src, idx) => (
                          <button
                            key={idx}
                            onClick={() => setDrawerSource(src)}
                            className="flex items-center gap-1 text-[10px] font-mono px-2 py-1 rounded-md transition-all"
                            style={{
                              background: "var(--ra-accent-dim)",
                              color: "var(--ra-accent)",
                              border: "1px solid rgba(0,229,160,0.2)",
                            }}
                            onMouseEnter={(e) => {
                              (e.currentTarget as HTMLElement).style.background = "rgba(0,229,160,0.2)";
                            }}
                            onMouseLeave={(e) => {
                              (e.currentTarget as HTMLElement).style.background = "var(--ra-accent-dim)";
                            }}
                          >
                            <Code2 className="w-3 h-3" />
                            {src}
                          </button>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              ))}

              {/* Typing indicator */}
              {chatLoading && (
                <div className="flex gap-3">
                  <div
                    className="w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0"
                    style={{ background: "var(--ra-accent-dim)", border: "1px solid rgba(0,229,160,0.3)" }}
                  >
                    <Loader2 className="w-4 h-4 animate-spin" style={{ color: "var(--ra-accent)" }} />
                  </div>
                  <div
                    className="px-4 py-3 rounded-2xl flex items-center gap-1"
                    style={{
                      background: "var(--ra-surface)",
                      border: "1px solid var(--ra-border)",
                      borderRadius: "0.25rem 1rem 1rem 1rem",
                    }}
                  >
                    {[75, 150, 300].map((d, i) => (
                      <span
                        key={i}
                        className="w-1.5 h-1.5 rounded-full animate-bounce"
                        style={{ background: "var(--ra-muted)", animationDelay: `${d}ms` }}
                      />
                    ))}
                  </div>
                </div>
              )}

              {/* Suggested questions — show before user starts chatting */}
              {showSuggested && !chatLoading && (
                <div className="space-y-2">
                  <p className="text-xs font-mono" style={{ color: "var(--ra-muted)" }}>Suggested questions</p>
                  <div className="flex flex-wrap gap-2">
                    {suggested.map((q, i) => (
                      <button
                        key={i}
                        onClick={() => handleSend(q)}
                        className="text-xs font-mono px-3 py-2 rounded-lg transition-colors text-left"
                        style={{
                          background: "var(--ra-elevated)",
                          color: "var(--ra-muted)",
                          border: "1px solid var(--ra-border)",
                        }}
                        onMouseEnter={(e) => {
                          (e.currentTarget as HTMLElement).style.color = "var(--ra-accent)";
                          (e.currentTarget as HTMLElement).style.borderColor = "rgba(0,229,160,0.3)";
                        }}
                        onMouseLeave={(e) => {
                          (e.currentTarget as HTMLElement).style.color = "var(--ra-muted)";
                          (e.currentTarget as HTMLElement).style.borderColor = "var(--ra-border)";
                        }}
                      >
                        {q}
                      </button>
                    ))}
                  </div>
                </div>
              )}

              <div ref={messagesEndRef} />
            </div>
          </ScrollArea>

          {/* Chat input */}
          <div
            className="px-4 py-3 border-t"
            style={{ borderColor: "var(--ra-border)", background: "var(--ra-surface)" }}
          >
            <form
              onSubmit={(e) => { e.preventDefault(); handleSend(); }}
              className="max-w-2xl mx-auto relative flex items-center gap-2"
            >
              <Input
                value={inputVal}
                onChange={(e) => setInputVal(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="Ask anything about the codebase…"
                className="flex-1 h-11 text-sm font-mono rounded-xl border-2 pr-12"
                style={{
                  background: "var(--ra-bg)",
                  borderColor: "var(--ra-border)",
                  color: "var(--ra-text)",
                  fontFamily: "var(--font-mono)",
                }}
                disabled={chatLoading}
                onFocus={(e) => (e.currentTarget.style.borderColor = "var(--ra-accent)")}
                onBlur={(e) => (e.currentTarget.style.borderColor = "var(--ra-border)")}
              />
              <Button
                type="submit"
                size="icon"
                className="absolute right-1 w-9 h-9 rounded-lg transition-all"
                style={{
                  background: inputVal.trim() && !chatLoading ? "var(--ra-accent)" : "var(--ra-elevated)",
                  color: inputVal.trim() && !chatLoading ? "#0a0a0f" : "var(--ra-muted)",
                }}
                disabled={!inputVal.trim() || chatLoading}
              >
                <Send className="w-4 h-4" />
              </Button>
            </form>
          </div>
        </main>

        {/* RIGHT PANEL — Source drawer */}
        {drawerSource && (
          <aside
            className="w-80 flex-shrink-0 border-l flex flex-col overflow-hidden"
            style={{ borderColor: "var(--ra-border)", background: "var(--ra-surface)" }}
          >
            <div
              className="flex items-center justify-between px-4 py-3 border-b"
              style={{ borderColor: "var(--ra-border)" }}
            >
              <div className="flex items-center gap-2 min-w-0">
                <Code2 className="w-4 h-4 flex-shrink-0" style={{ color: "var(--ra-accent)" }} />
                <span className="text-xs font-mono truncate" style={{ color: "var(--ra-text)" }}>
                  {drawerSource}
                </span>
              </div>
              <button
                onClick={() => setDrawerSource(null)}
                className="p-1 rounded transition-colors flex-shrink-0"
                style={{ color: "var(--ra-muted)" }}
                onMouseEnter={(e) => (e.currentTarget.style.color = "var(--ra-text)")}
                onMouseLeave={(e) => (e.currentTarget.style.color = "var(--ra-muted)")}
              >
                <X className="w-4 h-4" />
              </button>
            </div>
            <ScrollArea className="flex-1">
              {drawerLoading ? (
                <div className="flex items-center justify-center h-32">
                  <Loader2
                    className="w-5 h-5 animate-spin"
                    style={{ color: "var(--ra-accent)" }}
                  />
                </div>
              ) : (
                <>
                  <SyntaxHighlighter
                    style={vscDarkPlus as any}
                    language={
                      drawerSource.endsWith(".py") ? "python" :
                      drawerSource.endsWith(".ts") || drawerSource.endsWith(".tsx") ? "typescript" :
                      drawerSource.endsWith(".js") || drawerSource.endsWith(".jsx") ? "javascript" :
                      drawerSource.endsWith(".go") ? "go" :
                      drawerSource.endsWith(".rs") ? "rust" :
                      drawerSource.endsWith(".java") ? "java" :
                      drawerSource.endsWith(".md") ? "markdown" :
                      drawerSource.endsWith(".json") ? "json" :
                      drawerSource.endsWith(".yaml") || drawerSource.endsWith(".yml") ? "yaml" :
                      drawerSource.endsWith(".toml") ? "toml" :
                      drawerSource.endsWith(".sh") ? "bash" : "text"
                    }
                    customStyle={{
                      margin: 0,
                      borderRadius: 0,
                      background: "var(--ra-bg)",
                      fontSize: "0.7rem",
                      lineHeight: 1.6,
                      minHeight: "100%",
                    }}
                    showLineNumbers
                    lineNumberStyle={{ color: "var(--ra-muted)", minWidth: "2.5em" }}
                    wrapLines
                    wrapLongLines
                  >
                    {drawerContent || ""}
                  </SyntaxHighlighter>
                  <p className="text-[10px] font-mono px-3 py-2" style={{ color: "var(--ra-muted)" }}>
                    {drawerContent && drawerContent.split("\n").length} lines · {drawerSource}
                  </p>
                </>
              )}
            </ScrollArea>
          </aside>
        )}
      </div>
    </div>
  );
}
