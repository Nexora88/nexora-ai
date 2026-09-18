"""
Nexora AI — Smart multi-model router
Ürün: kullanıcının ne istediğini anla → doğru motor → failover → token
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from litellm import acompletion
from loguru import logger

from app.core.config import get_settings

settings = get_settings()


class QueryType:
    FAST = "fast"
    CODE = "code"
    FINANCE = "finance"
    DEEP = "deep"
    IDENTITY = "identity"  # kimlik soruları — hızlı + ucuz


TOKEN_COST = {
    QueryType.FAST: 1,
    QueryType.IDENTITY: 1,
    QueryType.CODE: 2,
    QueryType.DEEP: 2,
    QueryType.FINANCE: 3,
}

PLAN_POOLS = {
    "free": ["fast", "identity", "code", "finance"],
    "pro": ["fast", "identity", "code", "finance", "deep"],
    "elite": ["fast", "identity", "code", "finance", "deep"],
}

MODEL_POOLS: Dict[str, List[str]] = {
    "fast": [
        "groq/llama-3.1-8b-instant",
        "groq/openai/gpt-oss-20b",
    ],
    "identity": [
        "groq/llama-3.1-8b-instant",
        "groq/openai/gpt-oss-20b",
    ],
    "code": [
        "groq/llama-3.1-8b-instant",
        "groq/openai/gpt-oss-20b",
        "groq/openai/gpt-oss-120b",
    ],
    "finance": [
        "groq/openai/gpt-oss-120b",
        "groq/llama-3.1-8b-instant",
    ],
    "deep": [
        "groq/openai/gpt-oss-120b",
        "groq/openai/gpt-oss-20b",
    ],
}

# --- Sinyal sözlükleri (TR + EN) ---
FINANCE_RE = re.compile(
    r"\b("
    r"btc|eth|bitcoin|ethereum|sol|xrp|borsa|hisse|kripto|coin|token|forex|"
    r"altın|gumus|gümüş|dolar|euro|sterlin|bist|xu100|thyao|aselsan|garanti|"
    r"aapl|tsla|nvda|nasdaq|s&p|portföy|portfoy|candle|mum|rsi|macd|stop[\s-]?loss|"
    r"analiz|yükseliş|yukselis|düşüş|dusuş|volati?lite|likidite|emir|lot|"
    r"faiz|enflasyon|cds|tahvil|dividant|temettü"
    r")\b",
    re.I,
)

CODE_RE = re.compile(
    r"\b("
    r"code|kod|python|javascript|typescript|react|next\.?js|fastapi|sql|html|css|"
    r"bug|error|hata|exception|stack\s*trace|debug|compile|function|fonksiyon|"
    r"class|api|endpoint|regex|json|docker|git|algorithm|algoritma|"
    r"yazılım|program|script|refactor|unit\s*test"
    r")\b",
    re.I,
)

IDENTITY_RE = re.compile(
    r"("
    r"sen kimsin|seni kim (yaptı|geliştirdi|yazdı|üretti)|kurucun kim|"
    r"hangi modelsin|chatgpt misin|grok musun|claude musun|gemini misin|"
    r"nerelisin|sahibin kim|kimin ürünüsün|nexora (nedir|kim)|"
    r"who (are|made|built) you|what model are you"
    r")",
    re.I,
)

DEEP_RE = re.compile(
    r"("
    r"neden|niçin|nasıl çalışır|karşılaştır|farkı ne|avantaj|dezavantaj|"
    r"adım adım|detaylı|derinlemesine|strateji|planla|mimarisi|"
    r"why |how does|compare|pros and cons|step by step|in detail"
    r")",
    re.I,
)


def classify_query(text: str) -> Tuple[str, str]:
    """
    Döner: (query_type, reason)
    reason = kullanıcıya/log'a gösterilecek kısa açıklama
    """
    t = (text or "").strip()
    if not t:
        return QueryType.FAST, "boş_girdi"

    # 1) Kimlik — önce (kısa ve net)
    if IDENTITY_RE.search(t) or len(t) < 80 and re.search(
        r"\b(kimsin|kurucu|modelsin)\b", t, re.I
    ):
        return QueryType.IDENTITY, "kimlik_sorgusu"

    # 2) Finans sinyali güçlüyse
    fin_hits = len(FINANCE_RE.findall(t))
    code_hits = len(CODE_RE.findall(t))

    if fin_hits >= 1 and fin_hits >= code_hits:
        return QueryType.FINANCE, f"finans_sinyali:{fin_hits}"

    # 3) Kod
    if code_hits >= 1:
        return QueryType.CODE, f"kod_sinyali:{code_hits}"

    # 4) Uzun / çok sorulu / derin kelimeler
    if len(t) > 500 or t.count("?") >= 3 or DEEP_RE.search(t):
        return QueryType.DEEP, "derin_muhakeme"

    # 5) Varsayılan: hızlı sohbet
    return QueryType.FAST, "genel_sohbet"


@dataclass
class RouterResult:
    response: Any
    model_used: str
    query_type: str
    token_cost: int
    latency_ms: int
    attempts: List[str]
    reason: str = ""


class LLMRouter:
    def __init__(self) -> None:
        self.settings = get_settings()

    def _pools_for_plan(self, plan: str) -> Dict[str, List[str]]:
        plan = (plan or "free").lower()
        allowed = PLAN_POOLS.get(plan, PLAN_POOLS["free"])
        return {k: v for k, v in MODEL_POOLS.items() if k in allowed}

    def resolve(self, user_text: str, plan: str = "free") -> Tuple[str, List[str], int, str]:
        qtype, reason = classify_query(user_text)
        pools = self._pools_for_plan(plan)
        if qtype not in pools:
            # free'de deep yoksa
            qtype = QueryType.FAST if qtype == QueryType.DEEP else qtype
            if qtype not in pools:
                qtype = QueryType.FAST
            reason = reason + "|plan_downgrade"
        models = list(pools.get(qtype) or pools.get("fast") or [])
        cost = TOKEN_COST.get(qtype, 1)
        if plan == "elite" and qtype == QueryType.DEEP:
            cost = 3
        return qtype, models, cost, reason

    async def chat(
        self,
        messages: List[Dict[str, str]],
        plan: str = "free",
        temperature: float = 0.7,
        max_tokens: int = 2048,
        stream: bool = False,
    ) -> RouterResult:
        user_text = ""
        for m in reversed(messages):
            if m.get("role") == "user":
                user_text = m.get("content") or ""
                break

        qtype, models, cost, reason = self.resolve(user_text, plan)
        if not models:
            raise RuntimeError("No models available for this plan")

        attempts: List[str] = []
        last_error: Optional[Exception] = None

        for model in models:
            attempts.append(model)
            t0 = time.perf_counter()
            try:
                logger.info(
                    f"Nexora router type={qtype} reason={reason} model={model} cost={cost}"
                )
                resp = await acompletion(
                    model=model,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    stream=False,
                )
                latency_ms = int((time.perf_counter() - t0) * 1000)
                return RouterResult(
                    response=resp,
                    model_used=model,
                    query_type=qtype,
                    token_cost=cost,
                    latency_ms=latency_ms,
                    attempts=attempts,
                    reason=reason,
                )
            except Exception as e:
                last_error = e
                logger.warning(f"Model failed {model}: {e}")
                continue

        raise RuntimeError(f"All models failed type={qtype}. Last: {last_error}")


llm_router = LLMRouter()
