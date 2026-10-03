"""
Nexora AI — Dynamic code index (Faz 1)
GitHub tree + dosya içeriği özeti + sembol haritası + keyword arama.
Vektör DB olmadan global bağlam; Ship / chat için context üretir.
"""
from __future__ import annotations

import base64
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from app.services.github_ship import github_get, parse_repo

# Basit dil ipuçları
SYMBOL_PATTERNS = [
    ("python", re.compile(
        r"^(?:async\s+)?(?:def|class)\s+(\w+)", re.M
    )),
    ("js", re.compile(
        r"^(?:export\s+)?(?:async\s+)?(?:function|class)\s+(\w+)|"
        r"^(?:export\s+)?const\s+(\w+)\s*=\s*(?:async\s*)?\(",
        re.M,
    )),
    ("go", re.compile(r"^func\s+(?:\([^)]+\)\s+)?(\w+)", re.M)),
]

SKIP_DIRS = {
    "node_modules", ".git", "dist", "build", ".next", "venv",
    "__pycache__", ".venv", "coverage", "vendor",
}
SKIP_EXT = {
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".pdf",
    ".zip", ".tar", ".gz", ".woff", ".woff2", ".exe", ".dll",
    ".lock", ".map", ".min.js", ".min.css",
}
TEXT_EXT = {
    ".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".rs", ".java",
    ".kt", ".md", ".json", ".yml", ".yaml", ".toml", ".css",
    ".html", ".sql", ".sh", ".env.example", ".txt", ".vue", ".svelte",
}


@dataclass
class FileEntry:
    path: str
    size: int = 0
    language: str = ""
    symbols: List[str] = field(default_factory=list)
    preview: str = ""  # ilk satırlar


@dataclass
class CodeIndex:
    repo: str
    default_branch: str
    files: List[FileEntry] = field(default_factory=list)
    symbol_to_files: Dict[str, List[str]] = field(default_factory=dict)
    indexed_at_sha: str = ""

    def stats(self) -> Dict[str, Any]:
        return {
            "repo": self.repo,
            "branch": self.default_branch,
            "file_count": len(self.files),
            "symbol_count": len(self.symbol_to_files),
            "sha": self.indexed_at_sha[:12] if self.indexed_at_sha else "",
        }


def _lang_for(path: str) -> str:
    p = path.lower()
    if p.endswith(".py"):
        return "python"
    if p.endswith((".ts", ".tsx")):
        return "typescript"
    if p.endswith((".js", ".jsx")):
        return "javascript"
    if p.endswith(".go"):
        return "go"
    if p.endswith(".rs"):
        return "rust"
    if p.endswith(".md"):
        return "markdown"
    return "other"


def _should_skip_path(path: str) -> bool:
    parts = path.replace("\\", "/").split("/")
    if any(p in SKIP_DIRS for p in parts):
        return True
    lower = path.lower()
    for ext in SKIP_EXT:
        if lower.endswith(ext):
            return True
    return False


def _is_text_path(path: str) -> bool:
    lower = path.lower()
    if any(lower.endswith(ext) for ext in TEXT_EXT):
        return True
    # uzantısız önemli dosyalar
    name = lower.split("/")[-1]
    return name in {"dockerfile", "makefile", "license", "readme"}


def extract_symbols(path: str, content: str, limit: int = 40) -> List[str]:
    found: List[str] = []
    for _name, pat in SYMBOL_PATTERNS:
        for m in pat.finditer(content):
            sym = next((g for g in m.groups() if g), None)
            if sym and sym not in found:
                found.append(sym)
            if len(found) >= limit:
                return found
    return found


async def fetch_tree(
    token: str, owner: str, repo: str, sha: str
) -> List[Dict[str, Any]]:
    tree = await github_get(
        token,
        f"/repos/{owner}/{repo}/git/trees/{sha}",
        params={"recursive": "1"},
    )
    return tree.get("tree") or []


async def fetch_file_text(
    token: str, owner: str, repo: str, path: str, ref: str, max_bytes: int = 80_000
) -> str:
    try:
        data = await github_get(
            token,
            f"/repos/{owner}/{repo}/contents/{path}",
            params={"ref": ref},
        )
        if isinstance(data, list):
            return ""
        if data.get("encoding") == "base64" and data.get("content"):
            raw = base64.b64decode(data["content"])
            if len(raw) > max_bytes:
                raw = raw[:max_bytes]
            return raw.decode("utf-8", errors="ignore")
        return ""
    except Exception:
        return ""


async def build_index(
    token: str,
    repo_full_name: str,
    max_files: int = 120,
    max_read: int = 40,
) -> CodeIndex:
    """
    max_files: tree'den alınacak blob sayısı
    max_read: içerik + sembol için okunacak dosya (rate limit)
    """
    owner, repo = parse_repo(repo_full_name)
    info = await github_get(token, f"/repos/{owner}/{repo}")
    branch = info.get("default_branch") or "main"
    ref = await github_get(token, f"/repos/{owner}/{repo}/git/ref/heads/{branch}")
    sha = ref["object"]["sha"]

    blobs = await fetch_tree(token, owner, repo, sha)
    paths: List[Tuple[str, int]] = []
    for item in blobs:
        if item.get("type") != "blob":
            continue
        path = item.get("path") or ""
        if _should_skip_path(path) or not _is_text_path(path):
            continue
        paths.append((path, int(item.get("size") or 0)))
        if len(paths) >= max_files:
            break

    # Öncelik: app/, src/, lib/, kısa path
    def rank(p: str) -> tuple:
        pl = p.lower()
        score = 0
        if pl.startswith(("app/", "src/", "lib/", "frontend/")):
            score -= 10
        if pl.endswith((".py", ".ts", ".tsx")):
            score -= 5
        return (score, len(p))

    paths.sort(key=lambda x: rank(x[0]))

    index = CodeIndex(
        repo=repo_full_name,
        default_branch=branch,
        indexed_at_sha=sha,
    )

    read_count = 0
    for path, size in paths:
        entry = FileEntry(path=path, size=size, language=_lang_for(path))
        if read_count < max_read:
            content = await fetch_file_text(token, owner, repo, path, branch)
            read_count += 1
            if content:
                entry.preview = "\n".join(content.splitlines()[:30])[:1500]
                entry.symbols = extract_symbols(path, content)
                for sym in entry.symbols:
                    index.symbol_to_files.setdefault(sym, [])
                    if path not in index.symbol_to_files[sym]:
                        index.symbol_to_files[sym].append(path)
        index.files.append(entry)

    return index


def search_index(index: CodeIndex, query: str, limit: int = 15) -> List[Dict[str, Any]]:
    """Dinamik arama: path + sembol + preview."""
    q = (query or "").strip().lower()
    if not q or not index.files:
        return []

    tokens = [t for t in re.split(r"\W+", q) if len(t) > 1]
    scored: List[Tuple[int, Dict[str, Any]]] = []

    for f in index.files:
        score = 0
        pl = f.path.lower()
        for t in tokens:
            if t in pl:
                score += 5
            for sym in f.symbols:
                if t in sym.lower():
                    score += 8
            if t in (f.preview or "").lower():
                score += 2
        # sembol tam eşleşme
        for sym, paths in index.symbol_to_files.items():
            if sym.lower() == q and f.path in paths:
                score += 15
        if score > 0:
            scored.append(
                (
                    score,
                    {
                        "path": f.path,
                        "language": f.language,
                        "symbols": f.symbols[:12],
                        "score": score,
                        "preview": (f.preview or "")[:400],
                    },
                )
            )

    scored.sort(key=lambda x: -x[0])
    return [item for _, item in scored[:limit]]


def index_to_context(
    index: CodeIndex,
    query: Optional[str] = None,
    max_chars: int = 4000,
) -> str:
    """Ship / chat system context."""
    lines = [
        f"Repo: {index.repo} @ {index.default_branch}",
        f"Indexed files: {len(index.files)} | symbols: {len(index.symbol_to_files)}",
        "",
    ]
    if query:
        hits = search_index(index, query, limit=10)
        lines.append(f"Search '{query}':")
        for h in hits:
            lines.append(f"- {h['path']} (score={h['score']}) sym={h['symbols'][:5]}")
        lines.append("")

    lines.append("Tree sample:")
    for f in index.files[:50]:
        sym = ",".join(f.symbols[:4])
        lines.append(f"- {f.path}" + (f" [{sym}]" if sym else ""))

    text = "\n".join(lines)
    return text[:max_chars]


# Basit process-içi cache (kullanıcı başına genişletilebilir)
_CACHE: Dict[str, CodeIndex] = {}


def cache_key(user_id: str, repo: str) -> str:
    return f"{user_id}:{repo}"


def get_cached(user_id: str, repo: str) -> Optional[CodeIndex]:
    return _CACHE.get(cache_key(user_id, repo))


def set_cached(user_id: str, repo: str, index: CodeIndex) -> None:
    _CACHE[cache_key(user_id, repo)] = index
