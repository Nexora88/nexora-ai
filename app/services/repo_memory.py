"""
Nexora AI — Repo Memory
GitHub'dan README + ağaç özeti (sohbet bağlamı için).
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import httpx

from app.services.github_ship import github_get, parse_repo


async def fetch_readme(token: str, full_name: str) -> str:
    owner, repo = parse_repo(full_name)
    try:
        data = await github_get(token, f"/repos/{owner}/{repo}/readme")
        import base64

        content = data.get("content") or ""
        return base64.b64decode(content).decode("utf-8", errors="ignore")[:8000]
    except Exception:
        return ""


async def fetch_tree_paths(token: str, full_name: str, limit: int = 80) -> List[str]:
    owner, repo = parse_repo(full_name)
    repo_info = await github_get(token, f"/repos/{owner}/{repo}")
    branch = repo_info.get("default_branch") or "main"
    ref = await github_get(token, f"/repos/{owner}/{repo}/git/ref/heads/{branch}")
    sha = ref["object"]["sha"]
    tree = await github_get(
        token,
        f"/repos/{owner}/{repo}/git/trees/{sha}",
        params={"recursive": "1"},
    )
    paths = []
    for item in tree.get("tree") or []:
        if item.get("type") == "blob":
            paths.append(item.get("path"))
            if len(paths) >= limit:
                break
    return paths


async def build_repo_summary(token: str, full_name: str) -> Dict[str, Any]:
    readme = await fetch_readme(token, full_name)
    paths = await fetch_tree_paths(token, full_name)
    summary = {
        "repo": full_name,
        "file_count_sampled": len(paths),
        "sample_paths": paths[:40],
        "readme_excerpt": readme[:4000],
        "context_blob": (
            f"Repo: {full_name}\n"
            f"Dosya örnekleri:\n" + "\n".join(f"- {p}" for p in paths[:30]) + "\n\n"
            f"README excerpt:\n{readme[:2000]}"
        ),
    }
    return summary
