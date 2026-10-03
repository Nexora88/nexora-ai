"""
Nexora AI — Multi-agent ship pipeline
PM → Coder → Security → Self-heal (test) → PR body
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List

from app.services.llm_router import llm_router
from app.services.secret_guard import scan_files
from app.services.self_heal import heal_until_green


@dataclass
class AgentEvent:
    agent: str
    step: str
    status: str  # running | done | error
    detail: str = ""


@dataclass
class SwarmResult:
    ok: bool
    events: List[AgentEvent] = field(default_factory=list)
    plan: List[str] = field(default_factory=list)
    files: List[Dict[str, str]] = field(default_factory=list)
    pr_title: str = ""
    pr_body: str = ""
    error: str = ""
    heal_attempts: int = 0
    tests_skipped: bool = False


def _event(
    events: List[AgentEvent],
    agent: str,
    step: str,
    status: str,
    detail: str = "",
):
    events.append(AgentEvent(agent=agent, step=step, status=status, detail=detail))


async def _llm_json(system: str, user: str, plan: str = "pro") -> Dict[str, Any]:
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
    result = await llm_router.chat(
        messages=messages,
        plan=plan,
        temperature=0.2,
        max_tokens=3500,
    )
    text = result.response.choices[0].message.content or ""
    m = re.search(r"\{[\s\S]*\}", text)
    if not m:
        raise ValueError("Ajan JSON üretmedi")
    return json.loads(m.group(0))


async def run_ship_swarm(
    instruction: str,
    repo_context: str = "",
    plan_tier: str = "pro",
    run_tests: bool = True,
    max_heal_attempts: int = 3,
) -> SwarmResult:
    events: List[AgentEvent] = []
    out = SwarmResult(ok=False, events=events)

    try:
        # ----- PM -----
        _event(events, "pm", "task_breakdown", "running", "İstek analiz ediliyor")
        pm = await _llm_json(
            system=(
                "Sen Nexora Ürün Müdürü ajanısın. Sadece JSON döndür.\n"
                '{"plan": ["adım1", "adım2"], "pr_title": "...", "summary": "..."}\n'
                "plan en fazla 6 kısa madde."
            ),
            user=(
                f"İstek:\n{instruction}\n\n"
                f"Repo bağlamı (özet):\n{repo_context[:3000]}"
            ),
            plan=plan_tier,
        )
        out.plan = list(pm.get("plan") or [])
        out.pr_title = (pm.get("pr_title") or "Nexora Ship")[:72]
        summary = pm.get("summary") or instruction[:200]
        _event(events, "pm", "task_breakdown", "done", f"{len(out.plan)} madde")

        # ----- Coder -----
        _event(events, "coder", "write_files", "running", "Kod üretiliyor")
        coder = await _llm_json(
            system=(
                "Sen Nexora Yazılımcı ajanısın. Sadece JSON döndür.\n"
                '{"files": [{"path": "relative/path", "content": "full file content"}]}\n'
                "1-5 dosya. path repo köküne göre. content tam dosya metni."
            ),
            user=(
                f"İstek:\n{instruction}\n\nPlan:\n"
                + "\n".join(f"- {p}" for p in out.plan)
                + f"\n\nBağlam:\n{repo_context[:2500]}"
            ),
            plan=plan_tier,
        )
        raw_files = coder.get("files") or []
        if not raw_files:
            raise ValueError("Coder dosya üretmedi")
        files = [
            {
                "path": str(f.get("path", "")).lstrip("/"),
                "content": str(f.get("content", "")),
            }
            for f in raw_files
            if f.get("path")
        ]
        if not files:
            raise ValueError("Coder geçerli path üretmedi")
        _event(events, "coder", "write_files", "done", f"{len(files)} dosya")

        # ----- Security (ön tarama) -----
        _event(events, "security", "secret_scan", "running", "Secret Guard")
        hits = scan_files(files)
        if hits:
            msg = "; ".join(f"{h.path}:{h.line} [{h.kind}]" for h in hits[:5])
            _event(events, "security", "secret_scan", "error", msg)
            out.error = f"Secret Guard: {msg}"
            out.files = files
            return out
        _event(events, "security", "secret_scan", "done", "temiz")

        # ----- QA + Self-heal -----
        _event(events, "qa", "self_heal", "running", "Test / heal")
        heal = await heal_until_green(
            files=files,
            instruction=instruction,
            max_attempts=max_heal_attempts,
            plan_tier=plan_tier,
            run_tests=run_tests,
        )
        for he in heal.events:
            _event(events, he.agent, he.step, he.status, he.detail)

        out.files = heal.files or files
        out.heal_attempts = heal.attempts
        out.tests_skipped = heal.skipped_tests

        if not heal.ok:
            _event(events, "qa", "self_heal", "error", heal.error or "heal başarısız")
            out.error = heal.error or "Self-heal: testler yeşile dönmedi"
            return out

        _event(
            events,
            "qa",
            "self_heal",
            "done",
            "atlandı" if heal.skipped_tests else f"yeşil ({heal.attempts} deneme)",
        )

        # ----- PR raporu -----
        _event(events, "pm", "pr_report", "running", "PR açıklaması")
        file_list = "\n".join(f"- `{f['path']}`" for f in out.files)
        plan_md = "\n".join(f"- {p}" for p in out.plan)
        heal_note = (
            "Test komutu bulunamadı; doğrulama atlandı."
            if out.tests_skipped
            else f"Self-heal denemesi: {out.heal_attempts}"
        )
        out.pr_body = (
            "## Nexora Ship\n\n"
            f"**Özet:** {summary}\n\n"
            "### Plan\n"
            f"{plan_md}\n\n"
            "### Dosyalar\n"
            f"{file_list}\n\n"
            "### Kalite\n"
            f"- Secret Guard: geçti\n"
            f"- {heal_note}\n\n"
            "### Not\n"
            "Bu PR Nexora çoklu-ajan hattı (PM → Coder → Security → QA) ile üretildi. "
            "Merge öncesi inceleyin.\n\n"
            "— Data · Intelligence · Future\n"
        )
        _event(events, "pm", "pr_report", "done", out.pr_title)

        out.ok = True
        return out

    except Exception as e:
        _event(events, "system", "error", "error", str(e)[:200])
        out.error = str(e)[:300]
        return out
