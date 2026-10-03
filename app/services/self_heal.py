"""
Nexora AI — Self-heal loop
Test kırmızı → log → coder düzelt → tekrar test (max N).
Yeşil olmadan PR yok (çağıran taraf kontrol eder).
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from app.services.llm_router import llm_router
from app.services.secret_guard import scan_files
from app.services.test_runner import (
    WorkspaceResult,
    failure_blob,
    run_tests_on_files,
)


@dataclass
class HealEvent:
    agent: str
    step: str
    status: str
    detail: str = ""


@dataclass
class HealResult:
    ok: bool
    files: List[Dict[str, str]] = field(default_factory=list)
    events: List[HealEvent] = field(default_factory=list)
    attempts: int = 0
    last_test_ok: bool = False
    error: str = ""
    skipped_tests: bool = False


def _ev(events: List[HealEvent], agent: str, step: str, status: str, detail: str = ""):
    events.append(HealEvent(agent=agent, step=step, status=status, detail=detail))


async def _llm_fix(system: str, user: str, plan: str = "pro") -> Dict[str, Any]:
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
    result = await llm_router.chat(
        messages=messages,
        plan=plan,
        temperature=0.15,
        max_tokens=4000,
    )
    text = result.response.choices[0].message.content or ""
    m = re.search(r"\{[\s\S]*\}", text)
    if not m:
        raise ValueError("Heal ajanı JSON üretmedi")
    return json.loads(m.group(0))


def _merge_files(
    base: List[Dict[str, str]], updates: List[Dict[str, str]]
) -> List[Dict[str, str]]:
    by_path = {f["path"]: f["content"] for f in base if f.get("path")}
    for u in updates:
        p = (u.get("path") or "").lstrip("/")
        if not p:
            continue
        by_path[p] = u.get("content") or ""
    return [{"path": p, "content": c} for p, c in by_path.items()]


async def heal_until_green(
    files: List[Dict[str, str]],
    instruction: str = "",
    max_attempts: int = 3,
    plan_tier: str = "pro",
    run_tests: bool = True,
) -> HealResult:
    """
    files: [{path, content}]
    Dönüş: ok=True ve last_test_ok=True ise ship güvenli.
    Test yoksa (framework none) skipped_tests=True, ok dosya + secret temizse True.
    """
    events: List[HealEvent] = []
    current = [
        {"path": str(f.get("path", "")).lstrip("/"), "content": str(f.get("content", ""))}
        for f in files
        if f.get("path")
    ]
    if not current:
        return HealResult(ok=False, error="Heal: dosya yok", events=events)

    # İlk secret taraması
    _ev(events, "security", "secret_scan", "running")
    hits = scan_files(current)
    if hits:
        msg = "; ".join(f"{h.path}:{h.line} [{h.kind}]" for h in hits[:5])
        _ev(events, "security", "secret_scan", "error", msg)
        return HealResult(ok=False, files=current, events=events, error=f"Secret: {msg}")
    _ev(events, "security", "secret_scan", "done", "temiz")

    if not run_tests:
        return HealResult(
            ok=True,
            files=current,
            events=events,
            last_test_ok=True,
            skipped_tests=True,
        )

    attempt = 0
    last_ws: Optional[WorkspaceResult] = None

    while attempt < max_attempts:
        attempt += 1
        _ev(events, "qa", "test", "running", f"deneme {attempt}/{max_attempts}")
        ws = await run_tests_on_files(current)
        last_ws = ws
        for e in ws.events:
            _ev(events, e.get("agent", "qa"), e.get("step", "test"), e.get("status", "done"), e.get("detail", ""))

        if ws.test.framework == "none":
            _ev(events, "qa", "test", "done", "test yok — atlandı")
            return HealResult(
                ok=True,
                files=current,
                events=events,
                attempts=attempt,
                last_test_ok=True,
                skipped_tests=True,
            )

        if ws.ok:
            _ev(events, "qa", "test", "done", "yeşil")
            return HealResult(
                ok=True,
                files=current,
                events=events,
                attempts=attempt,
                last_test_ok=True,
            )

        # Kırmızı → heal
        blob = failure_blob(ws.test)
        _ev(events, "coder", "heal", "running", f"düzeltme #{attempt}")
        try:
            fixed = await _llm_json(
                system=(
                    "Sen Nexora Self-Heal yazılımcı ajanısın. Sadece JSON döndür.\n"
                    '{"files": [{"path": "...", "content": "tam dosya içeriği"}]}\n'
                    "Test hatalarını düzelt. Sadece gerekli dosyaları güncelle."
                ),
                user=(
                    f"Orijinal istek:\n{instruction}\n\n"
                    f"Test çıktısı:\n{blob}\n\n"
                    "Mevcut dosyalar:\n"
                    + "\n\n".join(
                        f"### {f['path']}\n```\n{f['content'][:3000]}\n```"
                        for f in current[:8]
                    )
                ),
                plan=plan_tier,
            )
            updates = fixed.get("files") or []
            if not updates:
                _ev(events, "coder", "heal", "error", "boş düzeltme")
                break
            current = _merge_files(
                current,
                [
                    {
                        "path": str(u.get("path", "")).lstrip("/"),
                        "content": str(u.get("content", "")),
                    }
                    for u in updates
                ],
            )
            # secret tekrar
            hits = scan_files(current)
            if hits:
                msg = "; ".join(f"{h.path}:{h.line}" for h in hits[:3])
                _ev(events, "security", "secret_scan", "error", msg)
                return HealResult(
                    ok=False,
                    files=current,
                    events=events,
                    attempts=attempt,
                    error=f"Secret after heal: {msg}",
                )
            _ev(events, "coder", "heal", "done", f"{len(updates)} dosya")
        except Exception as e:
            _ev(events, "coder", "heal", "error", str(e)[:150])
            return HealResult(
                ok=False,
                files=current,
                events=events,
                attempts=attempt,
                error=str(e)[:300],
            )

    err = "Testler yeşile dönmedi"
    if last_ws and not last_ws.ok:
        err = (last_ws.test.stderr or last_ws.test.stdout or err)[:400]
    _ev(events, "qa", "test", "error", "max deneme")
    return HealResult(
        ok=False,
        files=current,
        events=events,
        attempts=attempt,
        last_test_ok=False,
        error=err,
  )
