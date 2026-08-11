"""DeepEval judge adapter with configuration isolated from the app model.

The evaluated assistant uses ``MODEL_PROVIDER`` / ``MODEL_NAME``.  The judge
always uses ``EVAL_LLM_PROVIDER`` / ``EVAL_LLM_MODEL`` so an evaluation cannot
silently judge a model with whichever application defaults happen to be active.
API credentials are shared with the corresponding provider's normal key.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True)
class JudgeConfig:
    provider: str
    model: str


_KEY_BY_PROVIDER = {
    "xai": "XAI_API_KEY",
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "google": "GOOGLE_API_KEY",
}


def resolve_judge_config(env: Mapping[str, str] | None = None) -> JudgeConfig:
    """Validate and return the explicitly configured LLM judge."""
    values = os.environ if env is None else env
    provider = values.get("EVAL_LLM_PROVIDER", "").strip().lower()
    model = values.get("EVAL_LLM_MODEL", "").strip()
    if provider in {"grok"}:
        provider = "xai"
    if provider in {"gemini"}:
        provider = "google"
    if not provider or not model:
        raise ValueError(
            "Set both EVAL_LLM_PROVIDER and EVAL_LLM_MODEL for the DeepEval judge. "
            "They may name the same provider/model as MODEL_PROVIDER and MODEL_NAME."
        )
    if provider not in _KEY_BY_PROVIDER:
        supported = ", ".join(sorted(_KEY_BY_PROVIDER))
        raise ValueError(f"Unsupported EVAL_LLM_PROVIDER={provider!r}; choose {supported}.")
    key_name = _KEY_BY_PROVIDER[provider]
    if not values.get(key_name, "").strip():
        raise ValueError(f"{key_name} is required for the {provider} evaluation judge.")
    return JudgeConfig(provider=provider, model=model)


def _chat_model(config: JudgeConfig):
    temperature = 0
    timeout = float(os.getenv("EVAL_LLM_TIMEOUT", "90"))
    if config.provider in {"xai", "openai"}:
        from langchain_openai import ChatOpenAI

        kwargs = {
            "model": config.model,
            "temperature": temperature,
            "timeout": timeout,
            "max_retries": 2,
        }
        if config.provider == "xai":
            kwargs.update(api_key=os.environ["XAI_API_KEY"], base_url="https://api.x.ai/v1")
        else:
            kwargs["api_key"] = os.environ["OPENAI_API_KEY"]
            if os.getenv("OPENAI_BASE_URL"):
                kwargs["base_url"] = os.environ["OPENAI_BASE_URL"]
        return ChatOpenAI(**kwargs)
    if config.provider == "anthropic":
        try:
            from langchain_anthropic import ChatAnthropic
        except ImportError as exc:  # pragma: no cover - optional provider
            raise RuntimeError("Install langchain-anthropic to use the Anthropic judge.") from exc
        return ChatAnthropic(
            model=config.model,
            api_key=os.environ["ANTHROPIC_API_KEY"],
            temperature=temperature,
            timeout=timeout,
            max_retries=2,
        )
    try:
        from langchain_google_genai import ChatGoogleGenerativeAI
    except ImportError as exc:  # pragma: no cover - optional provider
        raise RuntimeError("Install langchain-google-genai to use the Google judge.") from exc
    return ChatGoogleGenerativeAI(
        model=config.model,
        google_api_key=os.environ["GOOGLE_API_KEY"],
        temperature=temperature,
        timeout=timeout,
        max_retries=2,
    )


def _content_text(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            block.get("text", "") if isinstance(block, dict) else str(block)
            for block in content
        )
    return str(content or "")


def _coerce_schema(content, schema=None):
    text = _content_text(content).strip()
    if schema is None:
        return text
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.I)
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < start:
        raise ValueError(f"Judge did not return a JSON object: {text[:200]!r}")
    payload = json.loads(text[start:end + 1])
    return schema.model_validate(payload)


def build_deepeval_judge(config: JudgeConfig | None = None):
    """Return a DeepEvalBaseLLM backed by the explicitly selected provider."""
    from deepeval.models import DeepEvalBaseLLM

    resolved = config or resolve_judge_config()

    class FastClinicJudge(DeepEvalBaseLLM):
        def load_model(self):
            return _chat_model(resolved)

        def generate(self, prompt: str, schema=None, **_kwargs):
            return _coerce_schema(self.model.invoke(prompt).content, schema)

        async def a_generate(self, prompt: str, schema=None, **_kwargs):
            response = await self.model.ainvoke(prompt)
            return _coerce_schema(response.content, schema)

        def get_model_name(self):
            return f"{resolved.provider}:{resolved.model}"

        def supports_json_mode(self):
            return True

        def supports_structured_outputs(self):
            return True

    return FastClinicJudge(model=resolved.model)
