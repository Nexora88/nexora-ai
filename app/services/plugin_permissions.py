"""
Nexora AI — Plugin permission engine
always | once | ask | deny
Tüm eklentiler (Ship, Deploy, …) bu katmandan geçer.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Optional


class GrantMode(str, Enum):
    ALWAYS = "always"   # bir daha sorma
    ASK = "ask"         # her seferinde sor
    DENY = "deny"       # engelle
    ONCE = "once"       # tek kullanımlık onay (bellekte / kısa ömürlü)


class PluginId(str, Enum):
    GITHUB_SHIP = "github_ship"
    DIFF_PREVIEW = "diff_preview"
    SECRET_GUARD = "secret_guard"
    REPO_MEMORY = "repo_memory"
    DEPLOY = "deploy"


@dataclass
class PermissionDecision:
    allowed: bool
    mode: str
    needs_prompt: bool
    message: str = ""
    grant_key: str = ""


def grant_key(plugin: str, scope: str = "*") -> str:
    """örn. github_ship:Nexora88/nexora-ai"""
    scope = (scope or "*").strip() or "*"
    return f"{plugin}:{scope}"


def decide(
    stored_mode: Optional[str],
    plugin: str,
    scope: str = "*",
    once_token_valid: bool = False,
) -> PermissionDecision:
    """
    stored_mode: DB'den gelen always | ask | deny | None
    once_token_valid: bu istek için tek seferlik onay verildi mi
    """
    key = grant_key(plugin, scope)
    mode = (stored_mode or GrantMode.ASK.value).lower()

    if mode == GrantMode.DENY.value:
        return PermissionDecision(
            allowed=False,
            mode=mode,
            needs_prompt=False,
            message="Bu eklenti için izin reddedilmiş. İzinler sayfasından değiştirebilirsin.",
            grant_key=key,
        )

    if mode == GrantMode.ALWAYS.value:
        return PermissionDecision(
            allowed=True,
            mode=mode,
            needs_prompt=False,
            message="Kayıtlı izin: her zaman",
            grant_key=key,
        )

    # ask (varsayılan) veya once
    if once_token_valid:
        return PermissionDecision(
            allowed=True,
            mode=GrantMode.ONCE.value,
            needs_prompt=False,
            message="Tek seferlik izin",
            grant_key=key,
        )

    return PermissionDecision(
        allowed=False,
        mode=GrantMode.ASK.value,
        needs_prompt=True,
        message="Bu işlem için izin gerekli: Bir kez / Her zaman / Reddet",
        grant_key=key,
    )


def parse_mode(value: str) -> str:
    v = (value or "").strip().lower()
    allowed = {m.value for m in GrantMode}
    if v not in allowed:
        return GrantMode.ASK.value
    return v


def utcnow():
    return datetime.now(timezone.utc)
