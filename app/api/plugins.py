"""
Nexora AI — Plugins hub
Diff preview, secret scan, repo memory (Ship ayrı router'da).
"""
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_user_by_email
from app.core.database import get_db
from app.core.security import decode_access_token
from app.models.db_models import User
from app.services.diff_preview import preview_files
from app.services.repo_memory import build_repo_summary
from app.services.secret_guard import assert_clean, scan_files
from app.services.plugin_permissions import PluginId, decide
from app.api.permissions import _get_grant

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
    token = getattr(user, "github_access_token", None)
    repo = getattr(user, "github_default_repo", None)
    if not token or not repo:
        raise HTTPException(status_code=400, detail="GitHub + varsayılan repo gerekli")

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
