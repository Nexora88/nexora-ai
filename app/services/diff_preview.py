"""
Nexora AI — Diff Preview
Basit satır diff (push öncesi UI).
"""
from __future__ import annotations

import difflib
from typing import List, Optional


def unified_diff(
    path: str,
    old: Optional[str],
    new: str,
    context: int = 3,
) -> str:
    old_lines = (old or "").splitlines(keepends=True)
    new_lines = (new or "").splitlines(keepends=True)
    if not old_lines and not new_lines:
        return ""
    diff = difflib.unified_diff(
        old_lines,
        new_lines,
        fromfile=f"a/{path}",
        tofile=f"b/{path}",
        n=context,
    )
    return "".join(diff)


def preview_files(items: List[dict]) -> List[dict]:
    """
    items: [{path, old_content?, content}]
    """
    out = []
    for it in items:
        path = it.get("path") or "file"
        old = it.get("old_content")
        new = it.get("content") or ""
        text = unified_diff(path, old, new)
        out.append(
            {
                "path": path,
                "diff": text,
                "is_new": old is None or old == "",
                "lines_added": sum(1 for ln in text.splitlines() if ln.startswith("+") and not ln.startswith("+++")),
                "lines_removed": sum(1 for ln in text.splitlines() if ln.startswith("-") and not ln.startswith("---")),
            }
        )
    return out
