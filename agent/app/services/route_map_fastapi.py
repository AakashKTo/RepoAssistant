from __future__ import annotations

import ast
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

IGNORE_DIRS = {
    ".git",
    "node_modules",
    "dist",
    "build",
    ".next",
    ".venv",
    "venv",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    ".mypy_cache",
}

HTTP_ATTRS = {"get", "post", "put", "delete", "patch", "options", "head", "api_route"}

MAX_PY_BYTES = 700_000  # avoid huge generated files


def _safe_read_text(path: Path, max_bytes: int = MAX_PY_BYTES) -> str:
    data = path.read_bytes()
    if len(data) > max_bytes:
        data = data[:max_bytes]
    return data.decode("utf-8", errors="replace")


def _module_from_relpath(rel: Path) -> str:
    # "api/users.py" -> "api.users"
    return ".".join(rel.with_suffix("").parts)


def _expr_str(node: ast.AST) -> str:
    try:
        return ast.unparse(node)
    except Exception:
        return node.__class__.__name__


def _kw_str(call: ast.Call, name: str) -> Optional[str]:
    for kw in call.keywords or []:
        if kw.arg == name and isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
            return kw.value.value
    return None


def _const_str(node: ast.AST) -> Optional[str]:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _const_str_list(node: ast.AST) -> Optional[list[str]]:
    # methods=["GET","POST"]
    if isinstance(node, (ast.List, ast.Tuple)):
        out: list[str] = []
        for el in node.elts:
            s = _const_str(el)
            if s is None:
                return None
            out.append(s)
        return out
    return None


def _join_url(*parts: Optional[str]) -> str:
    cleaned: list[str] = []
    for p in parts:
        if not p:
            continue
        p = str(p)
        if p == "/":
            # special case: root path
            cleaned.append("")
            continue
        cleaned.append(p.strip("/"))
    if not cleaned:
        return "/"
    return "/" + "/".join([c for c in cleaned if c != ""])


@dataclass
class FileContext:
    repo_dir: Path
    file_path: Path
    rel_path: Path
    module_name: str
    imported_symbols: Dict[str, str]  # local_name -> "module:symbol"
    module_aliases: Dict[str, str]  # local_name -> "module"


def _collect_import_context(tree: ast.AST, module_name: str) -> Tuple[Dict[str, str], Dict[str, str], bool]:
    imported_symbols: Dict[str, str] = {}
    module_aliases: Dict[str, str] = {}
    uses_fastapi = False

    for node in getattr(tree, "body", []):
        if isinstance(node, ast.Import):
            for a in node.names:
                name = a.name  # e.g. fastapi, api.users
                asname = a.asname or name.split(".")[-1]
                module_aliases[asname] = name
                if name.startswith("fastapi"):
                    uses_fastapi = True

        elif isinstance(node, ast.ImportFrom):
            if node.module:
                if node.module.startswith("fastapi"):
                    uses_fastapi = True
                for a in node.names:
                    local = a.asname or a.name
                    imported_symbols[local] = f"{node.module}:{a.name}"

    return imported_symbols, module_aliases, uses_fastapi


def _resolve_symbol(expr: ast.AST, ctx: FileContext) -> str:
    """
    Return a stable symbol id for router/app references.
    Prefer "module:symbol" when we can resolve imports.
    Otherwise fall back to "this_module:name" for local vars.
    """
    # Name: local var or imported symbol alias
    if isinstance(expr, ast.Name):
        n = expr.id
        if n in ctx.imported_symbols:
            return ctx.imported_symbols[n]
        # local name in this module
        return f"{ctx.module_name}:{n}"

    # Attribute: could be module alias like users.router
    if isinstance(expr, ast.Attribute):
        if isinstance(expr.value, ast.Name) and expr.value.id in ctx.module_aliases:
            mod = ctx.module_aliases[expr.value.id]  # e.g. api.users
            return f"{mod}:{expr.attr}"
        # Otherwise, best-effort stringify
        return _expr_str(expr)

    return _expr_str(expr)


def extract_fastapi_route_map(repo_dir: Path, max_files: int = 2500) -> dict[str, Any]:
    """
    Best-effort static FastAPI route map extraction.
    Works well when:
    - routes are declared with literal strings in decorators
    - routers use APIRouter(prefix="...")
    - include_router(prefix="...") is used with imported routers
    """
    router_prefixes: Dict[str, str] = {}  # router_symbol -> prefix
    include_prefixes: Dict[str, List[str]] = {}  # router_symbol -> [prefixes]
    routes: List[dict[str, Any]] = []

    stats = {
        "py_files_seen": 0,
        "py_files_parsed": 0,
        "parse_errors": 0,
        "routes_found": 0,
    }

    def iter_py_files() -> List[Path]:
        out: List[Path] = []
        for root, dirs, files in os.walk(repo_dir):
            dirs[:] = [d for d in dirs if d not in IGNORE_DIRS]
            for f in files:
                if not f.endswith(".py"):
                    continue
                p = Path(root) / f
                stats["py_files_seen"] += 1
                try:
                    if p.stat().st_size > MAX_PY_BYTES:
                        continue
                except Exception:
                    continue
                out.append(p)
                if len(out) >= max_files:
                    return out
        return out

    files = iter_py_files()

    for path in files:
        rel = path.relative_to(repo_dir)
        module_name = _module_from_relpath(rel)

        try:
            src = _safe_read_text(path)
            tree = ast.parse(src)
            stats["py_files_parsed"] += 1
        except Exception:
            stats["parse_errors"] += 1
            continue

        imported_symbols, module_aliases, uses_fastapi = _collect_import_context(tree, module_name)
        if not uses_fastapi:
            # avoid false positives on non-FastAPI repos
            continue

        ctx = FileContext(
            repo_dir=repo_dir,
            file_path=path,
            rel_path=rel,
            module_name=module_name,
            imported_symbols=imported_symbols,
            module_aliases=module_aliases,
        )

        # 1) Find APIRouter(prefix="...") assignments
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
                call = node.value
                func = call.func
                is_apirouter = False

                if isinstance(func, ast.Name) and func.id == "APIRouter":
                    is_apirouter = True
                elif isinstance(func, ast.Attribute) and func.attr == "APIRouter":
                    is_apirouter = True

                if not is_apirouter:
                    continue

                prefix = _kw_str(call, "prefix")
                for t in node.targets:
                    if isinstance(t, ast.Name):
                        router_symbol = f"{module_name}:{t.id}"
                        if prefix:
                            router_prefixes[router_symbol] = prefix

        # 2) Find include_router(router, prefix="...")
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "include_router":
                if not node.args:
                    continue
                router_sym = _resolve_symbol(node.args[0], ctx)
                pref = _kw_str(node, "prefix") or ""
                include_prefixes.setdefault(router_sym, [])
                # avoid duplicates
                if pref not in include_prefixes[router_sym]:
                    include_prefixes[router_sym].append(pref)

        # 3) Find route decorators on functions
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue

            for dec in node.decorator_list or []:
                if not isinstance(dec, ast.Call):
                    continue
                if not isinstance(dec.func, ast.Attribute):
                    continue

                attr = dec.func.attr
                if attr not in HTTP_ATTRS:
                    continue

                router_sym = _resolve_symbol(dec.func.value, ctx)

                # path
                raw_path: Optional[str] = None
                confidence = "low"
                if dec.args:
                    raw_path = _const_str(dec.args[0])
                    if raw_path is not None:
                        confidence = "high"
                if raw_path is None and dec.args:
                    raw_path = _expr_str(dec.args[0])

                # methods
                methods: list[str] = []
                if attr == "api_route":
                    # methods keyword
                    mnode = None
                    for kw in dec.keywords or []:
                        if kw.arg == "methods":
                            mnode = kw.value
                    mlist = _const_str_list(mnode) if mnode is not None else None
                    if mlist:
                        methods = [m.upper() for m in mlist]
                    else:
                        methods = ["<UNKNOWN>"]
                else:
                    methods = [attr.upper()]

                router_pref = router_prefixes.get(router_sym, "")
                inc_prefs = include_prefixes.get(router_sym, [""]) or [""]

                full_paths = []
                # if decorator base is app local var, don't apply include prefixes
                if router_sym.endswith(":app"):
                    full_paths = [_join_url(raw_path)]
                else:
                    for ip in inc_prefs:
                        full_paths.append(_join_url(ip, router_pref, raw_path))

                start_line = getattr(node, "lineno", None)
                end_line = getattr(node, "end_lineno", start_line)

                routes.append(
                    {
                        "methods": methods,
                        "path": raw_path,
                        "full_paths": full_paths,
                        "handler": {"module": module_name, "function": node.name},
                        "router": {"symbol": router_sym, "prefix": router_pref or None},
                        "source": {
                            "file": rel.as_posix(),
                            "start_line": start_line,
                            "end_line": end_line,
                        },
                        "confidence": confidence,
                    }
                )
                stats["routes_found"] += 1

    present = stats["routes_found"] > 0

    return {
        "present": present,
        "routes": routes,
        "router_prefixes": router_prefixes,
        "include_prefixes": include_prefixes,
        "stats": stats,
        "notes": [
            "Best-effort static route mapping for FastAPI.",
            "High confidence requires literal string paths and prefixes.",
            "Dynamic route construction may appear with confidence=low.",
        ],
    }