"""
Nexora AI — Plugins hub
diff, secret-scan, repo-memory, code-index
"""
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_user_by_email
from app.api.permissions import _get_grant
from app.core.database import get_db
from app.core.security import decode_access_token
from app.models.db_models import User
from app.services.code_index import (
    build_index,
    get_cached,
    index_to_context,
    search_index,
    set_cached,
)
from app.services.diff_preview import preview_files
from app.services.plugin_permissions import PluginId, decide
from app.services.repo_memory import build_repo_summary
from app.services.secret_guard import scan_files

router = APIRouter(prefix="/plugins", tags=["plugins"])


class FileIn(BaseModel):
    path: str
    content: str
    old_content: Optional[str] = None


class DiffBody(BaseModel):
    files: List[FileIn]


class ScanBody(BaseModel):
    files: List[FileIn]


async def get_current_user(
    authorization: Optional[str] = Header(None),
    db: AsyncSession = Depends(get_db),
) -> User:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Token gerekli")
    payload = decode_access_token(authorization.replace("Bearer ", ""))
    if not payload:
        raise HTTPException(status_code=401, detail="Geçersiz oturum")
    user = await get_user_by_email(payload.get("email"), db)
    if not user:
        raise HTTPException(status_code=404, detail="Kullanıcı bulunamadı")
    return user


def _require_github(user: User) -> tuple[str, str]:
    token = getattr(user, "github_access_token", None)
    repo = getattr(user, "github_default_repo", None)
    if not token:
        raise HTTPException(status_code=400, detail="GitHub bağlı değil")
    if not repo:
        raise HTTPException(status_code=400, detail="Varsayılan repo seç")
    return token, repo


@router.post("/diff")
async def plugin_diff(body: DiffBody, user: User = Depends(get_current_user)):
    items = [f.model_dump() for f in body.files]
    return {"previews": preview_files(items)}


@router.post("/secret-scan")
async def plugin_secret_scan(body: ScanBody, user: User = Depends(get_current_user)):
    items = [{"path": f.path, "content": f.content} for f in body.files]
    hits = scan_files(items)
    return {
        "clean": len(hits) == 0,
        "hits": [
            {"path": h.path, "line": h.line, "kind": h.kind, "snippet": h.snippet}
            for h in hits
        ],
    }


@router.get("/repo-memory")
async def plugin_repo_memory(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    token, repo = _require_github(user)
    grant = await _get_grant(db, user.id, PluginId.REPO_MEMORY.value, repo)
    decision = decide(grant.mode if grant else None, PluginId.REPO_MEMORY.value, repo)
    if decision.needs_prompt:
        return {
            "needs_prompt": True,
            "message": decision.message,
            "plugin": PluginId.REPO_MEMORY.value,
            "scope": repo,
        }
    if not decision.allowed:
        raise HTTPException(status_code=403, detail=decision.message)
    summary = await build_repo_summary(token, repo)
    return {"needs_prompt": False, "summary": summary}


@router.post("/index")
async def plugin_build_index(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Dinamik code index oluştur / yenile (cache)."""
    token, repo = _require_github(user)
    grant = await _get_grant(db, user.id, PluginId.REPO_MEMORY.value, repo)
    decision = decide(grant.mode if grant else None, PluginId.REPO_MEMORY.value, repo)
    if decision.needs_prompt:
        return {
            "needs_prompt": True,
            "message": decision.message,
            "plugin": PluginId.REPO_MEMORY.value,
            "scope": repo,
        }
    if not decision.allowed:
        raise HTTPException(status_code=403, detail=decision.message)

    index = await build_index(token, repo)
    set_cached(user.id, repo, index)
    return {
        "needs_prompt": False,
        "ok": True,
        "stats": index.stats(),
        "sample_paths": [f.path for f in index.files[:30]],
    }


@router.get("/index")
async def plugin_index_status(user: User = Depends(get_current_user)):
    token, repo = _require_github(user)
    index = get_cached(user.id, repo)
    if not index:
        return {"ok": False, "cached": False, "repo": repo, "stats": None}
    return {"ok": True, "cached": True, "repo": repo, "stats": index.stats()}


@router.get("/index/search")
async def plugin_index_search(
    q: str = Query(..., min_length=1),
    user: User = Depends(get_current_user),
):
    _, repo = _require_github(user)
    index = get_cached(user.id, repo)
    if not index:
        raise HTTPException(
            status_code=400,
            detail="Önce POST /plugins/index ile indeksle",
        )
    hits = search_index(index, q, limit=15)
    context = index_to_context(index, query=q, max_chars=2500)
    return {"query": q, "hits": hits, "context_preview": context}
