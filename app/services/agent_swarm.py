"""
Nexora AI — Multi-agent ship pipeline (iskelet)
PM → Coder → Security → (Test sonra) → PR body
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from app.services.llm_router import llm_router
from app.services.secret_guard import scan_files


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


def _event(events: List[AgentEvent], agent: str, step: str, status: str, detail: str = ""):
    events.append(AgentEvent(agent=agent, step=step, status=status, detail=detail))


async def _llm_json(system: str, user: str, plan: str = "pro") -> Dict[str, Any]:
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
    result = await llm_router.chat(messages=messages, plan=plan, temperature=0.2, max_tokens=3000)
    text = result.response.choices[0].message.content or ""
    # ```json ... ``` temizle
    m = re.search(r"\{[\s\S]*\}", text)
    if not m:
        raise ValueError("Ajan JSON üretmedi")
    return json.loads(m.group(0))


async def run_ship_swarm(
    instruction: str,
    repo_context: str = "",
    plan_tier: str = "pro",
) -> SwarmResult:
    events: List[AgentEvent] = []
    out = SwarmResult(ok=False, events=events)

    try:
        # --- PM ---
        _event(events, "pm", "task_breakdown", "running", "İstek analiz ediliyor")
        pm = await _llm_json(
            system=(
                "Sen Nexora Ürün Müdürü ajanısın. Sadece JSON döndür.\n"
                '{"plan": ["adım1", "adım2"], "pr_title": "...", "summary": "..."}\n'
                "plan en fazla 6 madde, kısa."
            ),
            user=f"İstek:\n{instruction}\n\nRepo bağlamı (özet):\n{repo_context[:3000]}",
            plan=plan_tier,
        )
        out.plan = list(pm.get("plan") or [])
        out.pr_title = (pm.get("pr_title") or "Nexora Ship")[:72]
        _event(events, "pm", "task_breakdown", "done", f"{len(out.plan)} madde")

        # --- Coder ---
        _event(events, "coder", "write_files", "running", "Kod üretiliyor")
        coder = await _llm_json(
            system=(
                "Sen Nexora Yazılımcı ajanısın. Sadece JSON döndür.\n"
                '{"files": [{"path": "relative/path", "content": "full file content"}]}\n'
                "1-5 dosya. path repo köküne göre. content tam dosya."
            ),
            user=(
                f"İstek:\n{instruction}\n\nPlan:\n"
                + "\n".join(f"- {p}" for p in out.plan)
                + f"\n\nBağlam:\n{repo_context[:2500]}"
            ),
            plan=plan_tier,
        )
        files = coder.get("files") or []
        if not files:
            raise ValueError("Coder dosya üretmedi")
        out.files = [
            {"path": str(f.get("path", "")).lstrip("/"), "content": str(f.get("content", ""))}
            for f in files
            if f.get("path")
        ]
        _event(events, "coder", "write_files", "done", f"{len(out.files)} dosya")

        # --- Security ---
        _event(events, "security", "secret_scan", "running", "Secret Guard")
        hits = scan_files(out.files)
        if hits:
            msg = "; ".join(f"{h.path}:{h.line} [{h.kind}]" for h in hits[:5])
            _event(events, "security", "secret_scan", "error", msg)
            out.error = f"Secret Guard: {msg}"
            return out
        _event(events, "security", "secret_scan", "done", "temiz")

        # --- PR raporu ---
        _event(events, "pm", "pr_report", "running", "PR açıklaması")
        file_list = "\n".join(f"- `{f['path']}`" for f in out.files)
        plan_md = "\n".join(f"1. {p}" if False else f"- {p}" for p in out.plan)
        out.pr_body = (
            "## Nexora Ship\n\n"
            f"**Özet:** {pm.get('summary') or instruction[:200]}\n\n"
            "### Plan\n"
            f"{plan_md}\n\n"
            "### Dosyalar\n"
            f"{file_list}\n\n"
            "### Not\n"
            "Bu PR Nexora çoklu-ajan hattı ile oluşturuldu. "
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
