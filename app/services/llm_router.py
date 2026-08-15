from typing import AsyncGenerator, List, Dict, Any
from loguru import logger
from litellm import acompletion
from app.core.config import get_settings

settings = get_settings()

FREE_MODELS = [
    "groq/llama-3.3-70b-versatile",
    "groq/llama-3.1-8b-instant",
    "gemini/gemini-2.0-flash",
    "gemini/gemini-1.5-flash",
    "openrouter/meta-llama/llama-3.3-70b-instruct:free",
    "openrouter/google/gemma-2-9b-it:free",
    "openrouter/microsoft/phi-3-mini-128k-instruct:free",
    "openrouter/qwen/qwen-2-7b-instruct:free",
]

PRO_MODELS = [
    "xai/grok-4",
    "anthropic/claude-3-5-sonnet-20241022",
    "openai/gpt-4o",
    "gemini/gemini-1.5-pro",
    "groq/llama-3.3-70b-versatile",
]

ELITE_MODELS = [
    "xai/grok-4",
    "anthropic/claude-3-5-sonnet-20241022",
    "openai/o1-preview",
    "openai/gpt-4o",
    "gemini/gemini-1.5-pro",
]


class LLMRouter:
    def get_model_list(self, plan: str = "free") -> List[str]:
        if plan == "elite":
            return ELITE_MODELS + FREE_MODELS
        if plan == "pro":
            return PRO_MODELS + FREE_MODELS
        return FREE_MODELS

    async def chat(
        self,
        messages: List[Dict[str, str]],
        plan: str = "free",
        temperature: float = 0.7,
        max_tokens: int = 2048,
        stream: bool = False,
    ) -> Any:
        models = self.get_model_list(plan)
        last_error = None

        for model in models:
            try:
                logger.info(f"Trying model: {model}")
                response = await acompletion(
                    model=model,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    stream=stream,
                    timeout=30,
                )
                logger.success(f"Success with model: {model}")
                return response
            except Exception as e:
                logger.warning(f"Model {model} failed: {str(e)[:120]}")
                last_error = e
                continue

        raise Exception(f"All models failed. Last error: {last_error}")

    async def stream_chat(
        self,
        messages: List[Dict[str, str]],
        plan: str = "free",
        temperature: float = 0.7,
        max_tokens: int = 2048,
    ) -> AsyncGenerator[str, None]:
        models = self.get_model_list(plan)
        last_error = None

        for model in models:
            try:
                logger.info(f"Streaming with model: {model}")
                response = await acompletion(
                    model=model,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    stream=True,
                    timeout=45,
                )
                async for chunk in response:
                    if chunk.choices and chunk.choices[0].delta.content:
                        yield chunk.choices[0].delta.content
                return
            except Exception as e:
                logger.warning(f"Stream model {model} failed: {str(e)[:120]}")
                last_error = e
                continue

        raise Exception(f"All streaming models failed. Last error: {last_error}")


llm_router = LLMRouter()
