"""
Nexora AI — İzinler API
Eklentiler: always | ask | deny + ship öncesi karar
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_user_by_email
from app.core.database import get_db
from app.core.security import decode_access_token
from app.models.db_models import PluginGrant, User
from app.services.plugin_permissions import (
    PluginId,
    decide,
    grant_key,
    parse_mode,
)

router = APIRouter(prefix="/permissions", tags=["permissions"])

KNOWN_PLUGINS = [
    {
        "id": PluginId.GITHUB_SHIP.value,
        "name": "GitHub Ship",
        "description": "Seçili repoya branch, commit ve PR açar.",
    },
    {
        "id": PluginId.DIFF_PREVIEW.value,
        "name": "Diff Preview",
        "description": "Push öncesi dosya farkını gösterir.",
    },
    {
        "id": PluginId.SECRET_GUARD.value,
        "name": "Secret Guard",
        "description": "Commit içinde gizli anahtar sızıntısını engeller.",
    },
    {
        "id": PluginId.REPO_MEMORY.value,
        "name": "Repo Memory",
        "description": "Seçili repoyu sohbet bağlamına özetler.",
    },
]


class GrantUpsert(BaseModel):
    plugin: str
    scope: str = "*"
    mode: str = Field(..., description="always | ask | deny")


class CheckBody(BaseModel):
    plugin: str
    scope: str = "*"
    once: bool = False  # tek seferlik onay verildi


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


async def _get_grant(
    db: AsyncSession, user_id: str, plugin: str, scope: str
) -> Optional[PluginGrant]:
    scope = scope or "*"
    q = await db.execute(
        select(PluginGrant).where(
            PluginGrant.user_id == user_id,
            PluginGrant.plugin == plugin,
            PluginGrant.scope == scope,
        )
    )
    grant = q.scalar_one_or_none()
    if grant:
        return grant
    # repo özel yoksa * dene
    if scope != "*":
        q2 = await db.execute(
            select(PluginGrant).where(
                PluginGrant.user_id == user_id,
                PluginGrant.plugin == plugin,
                PluginGrant.scope == "*",
            )
        )
        return q2.scalar_one_or_none()
    return None


@router.get("/catalog")
async def catalog():
    """Eklenti listesi (UI)."""
    return {"plugins": KNOWN_PLUGINS}


@router.get("")
async def list_grants(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    q = await db.execute(select(PluginGrant).where(PluginGrant.user_id == user.id))
    rows = q.scalars().all()
    return {
        "grants": [
            {
                "id": g.id,
                "plugin": g.plugin,
                "scope": g.scope,
                "mode": g.mode,
                "updated_at": g.updated_at.isoformat() if g.updated_at else None,
            }
            for g in rows
        ]
    }


@router.put("")
async def upsert_grant(
    body: GrantUpsert,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    mode = parse_mode(body.mode)
    if mode == "once":
        # once saklanmaz; ask olarak tut
        mode = "ask"
    plugin = body.plugin.strip()
    scope = (body.scope or "*").strip() or "*"

    existing = await _get_grant(db, user.id, plugin, scope)
    # _get_grant * fallback yapabilir; tam eşleşme iste
    q = await db.execute(
        select(PluginGrant).where(
            PluginGrant.user_id == user.id,
            PluginGrant.plugin == plugin,
            PluginGrant.scope == scope,
        )
    )
    row = q.scalar_one_or_none()

    if row:
        row.mode = mode
        row.updated_at = datetime.now(timezone.utc)
    else:
        row = PluginGrant(
            id=str(uuid.uuid4()),
            user_id=user.id,
            plugin=plugin,
            scope=scope,
            mode=mode,
        )
        db.add(row)

    await db.commit()
    await db.refresh(row)
    return {
        "plugin": row.plugin,
        "scope": row.scope,
        "mode": row.mode,
        "grant_key": grant_key(row.plugin, row.scope),
    }


@router.post("/check")
async def check_permission(
    body: CheckBody,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Ship / eklenti öncesi çağır.
    needs_prompt=true → UI: Bir kez / Her zaman / Reddet
    """
    grant = await _get_grant(db, user.id, body.plugin, body.scope or "*")
    stored = grant.mode if grant else None
    decision = decide(
        stored_mode=stored,
        plugin=body.plugin,
        scope=body.scope or "*",
        once_token_valid=body.once,
    )
    return {
        "allowed": decision.allowed,
        "mode": decision.mode,
        "needs_prompt": decision.needs_prompt,
        "message": decision.message,
        "grant_key": decision.grant_key,
        "plugin": body.plugin,
        "scope": body.scope or "*",
  }
