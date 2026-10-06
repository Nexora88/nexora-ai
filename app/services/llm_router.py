"""
Nexora AI — provider-aware multi-model router.
Keys stay in environment variables; LiteLLM handles provider normalization/fallback.
"""
from __future__ import annotations
import os
import re
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple
from litellm import acompletion
from loguru import logger
from app.core.config import get_settings

settings = get_settings()
# Normalize provider key aliases expected by LiteLLM.
if settings.GOOGLE_API_KEY:
    os.environ.setdefault("GEMINI_API_KEY", settings.GOOGLE_API_KEY)
if settings.TOGETHER_API_KEY:
    os.environ.setdefault("TOGETHERAI_API_KEY", settings.TOGETHER_API_KEY)

class QueryType:
    FAST="fast"; CODE="code"; FINANCE="finance"; DEEP="deep"; IDENTITY="identity"

TOKEN_COST={QueryType.FAST:1,QueryType.IDENTITY:1,QueryType.CODE:2,QueryType.DEEP:2,QueryType.FINANCE:3}

FINANCE_RE=re.compile(r"\b(btc|eth|bitcoin|ethereum|sol|xrp|borsa|hisse|kripto|coin|token|forex|altın|gümüş|dolar|euro|sterlin|bist|xu100|thyao|aselsan|garanti|aapl|tsla|nvda|nasdaq|s&p|portföy|portfoy|candle|mum|rsi|macd|stop[\s-]?loss|analiz|yükseliş|düşüş|volatilite|likidite|emir|lot|faiz|enflasyon|temettü)\b",re.I)
CODE_RE=re.compile(r"\b(code|kod|python|javascript|typescript|react|next\.?js|fastapi|sql|html|css|bug|error|hata|exception|stack\s*trace|debug|compile|function|fonksiyon|class|api|endpoint|regex|json|docker|git|algorithm|algoritma|yazılım|program|script|refactor|unit\s*test)\b",re.I)
IDENTITY_RE=re.compile(r"(sen kimsin|seni kim (yaptı|geliştirdi|yazdı|üretti)|kurucun kim|hangi modelsin|chatgpt misin|grok musun|claude musun|gemini misin|nexora (nedir|kim)|who (are|made|built) you|what model are you)",re.I)
DEEP_RE=re.compile(r"(neden|niçin|nasıl çalışır|karşılaştır|farkı ne|avantaj|dezavantaj|adım adım|detaylı|derinlemesine|strateji|planla|mimarisi|why |how does|compare|pros and cons|step by step|in detail)",re.I)

def classify_query(text:str)->Tuple[str,str]:
    t=(text or "").strip()
    if not t: return QueryType.FAST,"boş_girdi"
    if IDENTITY_RE.search(t) or (len(t)<80 and re.search(r"\b(kimsin|kurucu|modelsin)\b",t,re.I)): return QueryType.IDENTITY,"kimlik_sorgusu"
    fh=len(FINANCE_RE.findall(t)); ch=len(CODE_RE.findall(t))
    if fh>=1 and fh>=ch: return QueryType.FINANCE,f"finans_sinyali:{fh}"
    if ch>=1: return QueryType.CODE,f"kod_sinyali:{ch}"
    if len(t)>500 or t.count("?")>=3 or DEEP_RE.search(t): return QueryType.DEEP,"derin_muhakeme"
    return QueryType.FAST,"genel_sohbet"

def _available_models():
    # Ordered by practical preference. Only providers with configured keys are enabled.
    pools={
      "groq": (settings.GROQ_API_KEY, [
        "groq/openai/gpt-oss-120b",
        "groq/openai/gpt-oss-20b",
        "groq/llama-3.1-8b-instant"]),
      "openrouter": (settings.OPENROUTER_API_KEY, [
        "openrouter/openai/gpt-oss-120b",
        "openrouter/anthropic/claude-sonnet-4-5",
        "openrouter/google/gemini-2.5-pro",
        "openrouter/deepseek/deepseek-chat",
        "openrouter/qwen/qwen3-235b-a22b"]),
      "openai": (settings.OPENAI_API_KEY, ["openai/gpt-5.6-terra"]),
      "anthropic": (settings.ANTHROPIC_API_KEY, ["anthropic/claude-sonnet-4-5"]),
      "google": (settings.GOOGLE_API_KEY, ["gemini/gemini-2.5-flash","gemini/gemini-2.5-pro"]),
      "mistral": (settings.MISTRAL_API_KEY, ["mistral/mistral-large-latest","mistral/codestral-latest"]),
      "deepseek": (settings.DEEPSEEK_API_KEY, ["deepseek/deepseek-chat"]),
      "cerebras": (settings.CEREBRAS_API_KEY, ["cerebras/llama-4-scout-17b-16e-instruct"]),
      "together": (settings.TOGETHER_API_KEY, ["together_ai/meta-llama/Llama-4-Scout-17B-16E-Instruct-Turbo"]),
    }
    out=[]
    for key, (present, models) in pools.items():
        if present:
            out.extend(models)
    return out

def model_pools()->Dict[str,List[str]]:
    available=_available_models()
    # Prefer fast Groq/Gemini; deeper routes prefer strong models.
    fast=[m for m in available if m.startswith(("groq/","gemini/","openrouter/"))]
    code=[m for m in available if any(x in m.lower() for x in ("codestral","gpt-oss-120","claude-sonnet","deepseek","llama-4","openai/"))] or fast
    finance=[m for m in available if any(x in m.lower() for x in ("gpt-oss-120","claude","gemini-2.5-pro","openai/"))] or fast
    deep=[m for m in available if any(x in m.lower() for x in ("claude","gemini-2.5-pro","gpt-5.6","gpt-oss-120","deepseek"))] or fast
    identity=fast or available
    return {"fast":fast or available,"identity":identity,"code":code,"finance":finance,"deep":deep}

@dataclass
class RouterResult:
    response:Any
    model_used:str
    query_type:str
    token_cost:int
    latency_ms:int
    attempts:List[str]
    reason:str=""

class LLMRouter:
    def __init__(self): self.settings=get_settings()
    def resolve(self,user_text:str,plan:str="free"):
        qtype,reason=classify_query(user_text); pools=model_pools()
        if qtype=="deep" and plan=="free":
            qtype="fast"; reason += "|free_downgrade"
        models=pools.get(qtype) or pools["fast"]
        return qtype,models,TOKEN_COST.get(qtype,1),reason
    async def chat(self,messages,plan="free",temperature=.7,max_tokens=2048,stream=False):
        user_text=next((m.get("content","") for m in reversed(messages) if m.get("role")=="user"),"")
        qtype,models,cost,reason=self.resolve(user_text,plan)
        if not models: raise RuntimeError("No configured LLM providers")
        attempts=[]; last=None
        for model in models:
            attempts.append(model); started=time.perf_counter()
            try:
                resp=await acompletion(model=model,messages=messages,temperature=temperature,max_tokens=max_tokens,stream=stream)
                return RouterResult(resp,model,qtype,cost,int((time.perf_counter()-started)*1000),attempts,reason)
            except Exception as exc:
                last=exc
                logger.warning(f"LLM fallback: {model} failed: {exc}")
        raise RuntimeError(f"All configured models failed. Last: {last}")

llm_router=LLMRouter()
