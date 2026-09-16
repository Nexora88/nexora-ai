"""
Nexora AI — Smart multi-model router
Ürün: soruya göre model seçimi + failover + token maliyeti
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from litellm import acompletion
from loguru import logger

from app.core.config import get_settings

settings = get_settings()


# ---------- Sorgu sınıfları ----------
class QueryType:
    FAST = "fast"          # kısa sohbet → 1 token
    CODE = "code"          # kod / hata → 2 token
    FINANCE = "finance"    # borsa / kripto → 3 token
    DEEP = "deep"          # uzun muhakeme → 2-3 token


TOKEN_COST = {
    QueryType.FAST: 1,
    QueryType.CODE: 2,
    QueryType.FINANCE: 3,
    QueryType.DEEP: 2,
}

# Plan → hangi havuzlar açık
PLAN_POOLS = {
    "free": ["fast", "code", "finance"],
    "pro": ["fast", "code", "finance", "deep"],
    "elite": ["fast", "code", "finance", "deep"],
}

# Model havuzları (önce ücretsiz / ucuz)
# Format: LiteLLM model id
MODEL_POOLS: Dict[str, List[str]] = {
    "fast": [
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

FINANCE_RE = re.compile(
    r"\b(btc|eth|bitcoin|ethereum|borsa|hisse|kripto|coin|forex|"
    r"altın|gümüş|dolar|euro|bist|thyao|aselsan|aapl|tsla|"
    r"analiz|portföy|candle|rsi|macd)\b",
    re.I,
)
CODE_RE = re.compile(
    r"\b(code|kod|python|javascript|typescript|bug|error|hata|"
    r"function|class|api|sql|debug|compile|stack\s*trace)\b",
    re.I,
)


def classify_query(text: str) -> str:
    t = (text or "").strip()
    if not t:
        return QueryType.FAST
    if FINANCE_RE.search(t):
        return QueryType.FINANCE
    if CODE_RE.search(t):
        return QueryType.CODE
    # uzun / karmaşık
    if len(t) > 600 or t.count("?") >= 3:
        return QueryType.DEEP
    return QueryType.FAST


@dataclass
class RouterResult:
    response: Any
    model_used: str
    query_type: str
    token_cost: int
    latency_ms: int
    attempts: List[str]


class LLMRouter:
    def __init__(self) -> None:
        self.settings = get_settings()

    def _pools_for_plan(self, plan: str) -> Dict[str, List[str]]:
        plan = (plan or "free").lower()
        allowed = PLAN_POOLS.get(plan, PLAN_POOLS["free"])
        return {k: v for k, v in MODEL_POOLS.items() if k in allowed}

    def resolve(self, user_text: str, plan: str = "free") -> tuple[str, List[str], int]:
        """query_type, model listesi (öncelik sırası), token cost"""
        qtype = classify_query(user_text)
        pools = self._pools_for_plan(plan)
        # deep free'de yoksa fast'e düş
        if qtype not in pools:
            qtype = QueryType.FAST
        models = list(pools.get(qtype) or pools.get("fast") or [])
        cost = TOKEN_COST.get(qtype, 1)
        # elite deep biraz daha pahalı hissedilsin
        if plan == "elite" and qtype == QueryType.DEEP:
            cost = 3
        return qtype, models, cost

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

        qtype, models, cost = self.resolve(user_text, plan)
        if not models:
            raise RuntimeError("No models available for this plan")

        attempts: List[str] = []
        last_error: Optional[Exception] = None

        for model in models:
            attempts.append(model)
            t0 = time.perf_counter()
            try:
                logger.info(f"Nexora router → type={qtype} model={model} cost={cost}")
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
                )
            except Exception as e:
                last_error = e
                logger.warning(f"Model failed {model}: {e}")
                continue

        raise RuntimeError(
            f"All models failed for type={qtype}. Last: {last_error}"
        )


llm_router = LLMRouter()
