"""
Nexora AI — Ship API
GitHub bağlama + varsayılan repo + ship çalıştır (adımlı sonuç)
"""
from __future__ import annotations

import re
import secrets
from datetime import datetime, timezone
from typing import List, Optional
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import deduct_tokens, get_user_by_email
from app.core.config import get_settings
from app.core.database import get_db
from app.core.security import decode_access_token
from app.models.db_models import User
from app.services.github_ship import (
    ShipFile,
    get_authenticated_user,
    list_user_repos,
    run_ship,
    steps_as_dict,
)

router = APIRouter(prefix="/ship", tags=["ship"])
settings = get_settings()

SHIP_TOKEN_COST = int(getattr(settings, "SHIP_TOKEN_COST", 10) or 10)


class DefaultRepoBody(BaseModel):
    repo: str = Field(..., description="owner/name")


class ShipFileIn(BaseModel):
    path: str
    content: str


class ShipRunBody(BaseModel):
    instruction: str = ""
    files: List[ShipFileIn]
    commit_message: str = "feat: nexora ship"
    branch: Optional[str] = None
    create_pr: bool = True
    pr_title: Optional[str] = None
    pr_body: Optional[str] = None


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


def _oauth_configured() -> bool:
    return bool(
        getattr(settings, "GITHUB_CLIENT_ID", None)
        and getattr(settings, "GITHUB_CLIENT_SECRET", None)
    )


@router.get("/status")
async def ship_status(user: User = Depends(get_current_user)):
    connected = bool(getattr(user, "github_access_token", None))
    return {
        "connected": connected,
        "github_username": getattr(user, "github_username", None),
        "default_repo": getattr(user, "github_default_repo", None),
        "ship_token_cost": SHIP_TOKEN_COST,
        "oauth_ready": _oauth_configured(),
    }


@router.get("/connect")
async def ship_connect(user: User = Depends(get_current_user)):
    """Tarayıcıda açılır — GitHub OAuth."""
    if not _oauth_configured():
        raise HTTPException(
            status_code=503,
            detail="GITHUB_CLIENT_ID / SECRET .env içinde yok",
        )
    state = f"{user.id}:{secrets.token_urlsafe(16)}"
    # state'i basit tutuyoruz; production'da redis/db'ye yaz
    params = {
        "client_id": settings.GITHUB_CLIENT_ID,
        "redirect_uri": settings.GITHUB_REDIRECT_URI,
        "scope": "repo read:user",
        "state": state,
    }
    url = "https://github.com/login/oauth/authorize?" + urlencode(params)
    return {"authorize_url": url, "state": state}


@router.get("/callback")
async def ship_callback(
    code: str = Query(...),
    state: str = Query(""),
    db: AsyncSession = Depends(get_db),
):
    if not _oauth_configured():
        raise HTTPException(status_code=503, detail="OAuth yapılandırılmamış")

    user_id = state.split(":")[0] if state else ""
    if not user_id:
        raise HTTPException(status_code=400, detail="Geçersiz state")

    async with httpx.AsyncClient(timeout=30.0) as client:
        token_res = await client.post(
            "https://github.com/login/oauth/access_token",
            headers={"Accept": "application/json"},
            data={
                "client_id": settings.GITHUB_CLIENT_ID,
                "client_secret": settings.GITHUB_CLIENT_SECRET,
                "code": code,
                "redirect_uri": settings.GITHUB_REDIRECT_URI,
            },
        )
        token_data = token_res.json()
        access = token_data.get("access_token")
        if not access:
            raise HTTPException(
                status_code=400,
                detail=token_data.get("error_description") or "Token alınamadı",
            )

    gh_user = await get_authenticated_user(access)
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Kullanıcı bulunamadı")

    user.github_access_token = access
    user.github_username = gh_user.get("login")
    user.github_connected_at = datetime.now(timezone.utc)
    await db.commit()

    # Frontend eklentiler sayfasına dön
    front = getattr(settings, "FRONTEND_URL", "http://localhost:3000") or "http://localhost:3000"
    return RedirectResponse(f"{front}/extensions?github=connected")


@router.get("/repos")
async def ship_repos(user: User = Depends(get_current_user)):
    token = getattr(user, "github_access_token", None)
    if not token:
        raise HTTPException(status_code=400, detail="Önce GitHub bağla (Eklentiler)")
    repos = await list_user_repos(token)
    return {"repos": repos, "default_repo": getattr(user, "github_default_repo", None)}


@router.post("/default-repo")
async def set_default_repo(
    body: DefaultRepoBody,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not re.match(r"^[\w.-]+/[\w.-]+$", body.repo.strip()):
        raise HTTPException(status_code=400, detail="Format: owner/name")
    if not getattr(user, "github_access_token", None):
        raise HTTPException(status_code=400, detail="GitHub bağlı değil")
    user.github_default_repo = body.repo.strip()
    await db.commit()
    return {"default_repo": user.github_default_repo}


@router.delete("/disconnect")
async def disconnect(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    user.github_access_token = None
    user.github_username = None
    user.github_default_repo = None
    user.github_connected_at = None
    await db.commit()
    return {"ok": True}


@router.post("/run")
async def ship_run(
    body: ShipRunBody,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    token = getattr(user, "github_access_token", None)
    repo = getattr(user, "github_default_repo", None)
    if not token:
        raise HTTPException(status_code=400, detail="GitHub bağlı değil — Eklentiler → Kur")
    if not repo:
        raise HTTPException(status_code=400, detail="Varsayılan repo seç — Eklentiler")

    if user.tokens < SHIP_TOKEN_COST:
        raise HTTPException(
            status_code=402,
            detail=f"Ship {SHIP_TOKEN_COST} token. Kalan: {user.tokens}",
        )

    branch = body.branch or f"nexora/ship-{secrets.token_hex(3)}"
    files = [ShipFile(path=f.path, content=f.content) for f in body.files]

    result = await run_ship(
        token=token,
        repo_full_name=repo,
        files=files,
        commit_message=body.commit_message,
        branch=branch,
        create_pr=body.create_pr,
        pr_title=body.pr_title,
        pr_body=body.pr_body
        or (
            f"## Nexora Ship\n\n{body.instruction}\n\n"
            "Otomatik PR · Data · Intelligence · Future"
        ),
    )

    remaining = user.tokens
    if result.ok:
        remaining = await deduct_tokens(user.email, SHIP_TOKEN_COST, db)

    return {
        "ok": result.ok,
        "steps": steps_as_dict(result),
        "branch": result.branch,
        "commit_sha": result.commit_sha,
        "pr_url": result.pr_url,
        "pr_number": result.pr_number,
        "html_url": result.html_url,
        "error": result.error,
        "token_cost": SHIP_TOKEN_COST if result.ok else 0,
        "tokens": remaining,
        "repo": repo,
  }
