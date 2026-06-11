"""FastClinic chat assistant — a LangGraph ReAct agent over the cockpit data.

Slash commands (/due, /lapsed, …) answer structured data directly and instantly.
This module handles free-form questions: a LangGraph agent with tools that read
the clinic database, backed by a **configurable model provider**.

Provider selection (env):
    MODEL_PROVIDER   xai | openai | anthropic | google   (default: auto-detect)
    MODEL_NAME       e.g. grok-4-1-fast-reasoning, gpt-4o-mini
    XAI_API_KEY / OPENAI_API_KEY / ANTHROPIC_API_KEY / GOOGLE_API_KEY

xAI (Grok) is OpenAI-API-compatible, so it runs through ChatOpenAI with the
x.ai base URL — no extra dependency. If no provider/key is configured, the agent
degrades gracefully to a friendly nudge toward the shortcut commands so the
cockpit (and the eval suite) work offline.
"""
from __future__ import annotations

import os

SYSTEM_PROMPT = """You are the FastClinic GP-clinic data assistant — a concise,
practical operations assistant for a general-practice (GP) clinic's marketing and
operations team. Tagline: "Modern primary care, made personal."

Your job is to help the team understand patient and revenue data and, above all,
bring patients back (patient activation): immunisations and health-check renewals
due, lapsed patients to win back, and post-visit follow-ups.

Use the provided tools to fetch real numbers from the clinic database before
answering — do not invent figures. Keep answers short and practical; use markdown
tables for lists. You are not a substitute for a clinician's judgement — refer
individual patient care decisions to the attending GP. Reply in the language the
user writes in."""

X_AI_BASE_URL = "https://api.x.ai/v1"

_DEFAULT_NAMES = {
    "xai": "grok-4-1-fast-reasoning",
    "openai": "gpt-4o-mini",
    "anthropic": "claude-3-5-sonnet-latest",
    "google": "gemini-1.5-flash",
}


# --------------------------------------------------------------- model factory --
def _resolve_provider() -> str | None:
    provider = (os.getenv("MODEL_PROVIDER") or "").strip().lower()
    if provider:
        return provider
    # auto-detect from whichever key is present
    if os.getenv("XAI_API_KEY"):
        return "xai"
    if os.getenv("OPENAI_API_KEY"):
        return "openai"
    if os.getenv("ANTHROPIC_API_KEY"):
        return "anthropic"
    if os.getenv("GOOGLE_API_KEY"):
        return "google"
    return None


def make_model():
    """Build a LangChain chat model from env, or return None if unconfigured."""
    provider = _resolve_provider()
    if not provider:
        return None
    name = (os.getenv("MODEL_NAME") or "").strip() or _DEFAULT_NAMES.get(provider, "")
    temperature = float(os.getenv("MODEL_TEMPERATURE", "0.2"))

    if provider in ("xai", "grok"):
        key = os.getenv("XAI_API_KEY")
        if not key:
            return None
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(model=name, api_key=key, base_url=X_AI_BASE_URL,
                          temperature=temperature, timeout=60, max_retries=2)
    if provider == "openai":
        key = os.getenv("OPENAI_API_KEY")
        if not key:
            return None
        from langchain_openai import ChatOpenAI
        base = os.getenv("OPENAI_BASE_URL")
        kwargs = {"base_url": base} if base else {}
        return ChatOpenAI(model=name, api_key=key, temperature=temperature, **kwargs)
    if provider == "anthropic":
        key = os.getenv("ANTHROPIC_API_KEY")
        if not key:
            return None
        from langchain_anthropic import ChatAnthropic
        return ChatAnthropic(model=name, api_key=key, temperature=temperature)
    if provider in ("google", "gemini"):
        key = os.getenv("GOOGLE_API_KEY")
        if not key:
            return None
        from langchain_google_genai import ChatGoogleGenerativeAI
        return ChatGoogleGenerativeAI(model=name, google_api_key=key, temperature=temperature)
    return None


# ----------------------------------------------------------------------- tools --
def _build_tools():
    """Wrap the cockpit's read-only command functions as agent tools."""
    from langchain_core.tools import tool
    from web import commands as c

    @tool
    def clinic_kpis() -> str:
        """Get clinic KPIs: active/total patients, recent visits, revenue, patients."""
        return c.cmd_kpi("")

    @tool
    def services_due(category: str = "all") -> str:
        """List patients due/overdue for a recurring service.
        category: 'all', 'vaccine', 'health_plan', or 'repeat_prescription'."""
        return c.cmd_due(category or "all")

    @tool
    def lapsed_clients(months: int = 12) -> str:
        """List patients with no visit in the last `months` months (win-back targets),
        highest lifetime value first."""
        return c.cmd_lapsed(str(months))

    @tool
    def recent_visits(days: int = 14) -> str:
        """List recent visits within the last `days` days, for post-visit follow-up."""
        return c.cmd_followup(str(days))

    @tool
    def revenue_breakdown() -> str:
        """Get revenue broken down by service category (vaccine, lab, procedure, etc.)."""
        return c.cmd_revenue("")

    @tool
    def find_patients(search: str = "") -> str:
        """Search patients by id or name. Empty = most recent."""
        return c.cmd_patients(search or "")

    @tool
    def patient_summary(patient_id: int) -> str:
        """Get a single patient's profile, lifetime value, and consultation history."""
        return c.cmd_patient(str(patient_id))

    return [clinic_kpis, services_due, lapsed_clients, recent_visits,
            revenue_breakdown, find_patients, patient_summary]


# --------------------------------------------------------------------- agent ----
_agent = None
_agent_signature: tuple | None = None


def _get_agent():
    """Build (and cache) the LangGraph ReAct agent for the current provider config."""
    global _agent, _agent_signature
    sig = (os.getenv("MODEL_PROVIDER"), os.getenv("MODEL_NAME"))
    if _agent is not None and _agent_signature == sig:
        return _agent
    model = make_model()
    if model is None:
        _agent, _agent_signature = None, sig
        return None
    from langgraph.prebuilt import create_react_agent
    _agent = create_react_agent(model, _build_tools(), prompt=SYSTEM_PROMPT)
    _agent_signature = sig
    return _agent


def _fallback() -> str:
    return (
        "I can answer questions about the clinic, but no AI provider is configured "
        "yet. Meanwhile, try a shortcut command:\n\n"
        "- `/kpi` — clinic KPIs\n"
        "- `/due` — immunisations & health checks due\n"
        "- `/lapsed` — patients to win back\n"
        "- `/followup` — recent visits\n"
        "- `/revenue` — revenue by category\n"
        "- `/patient ID` — a patient summary\n\n"
        "_Set `MODEL_PROVIDER` + the matching API key to enable free-form answers._"
    )


def answer(message: str, thread_id: str | None = None) -> str:
    """Answer a free-form question via the LangGraph agent (or the fallback)."""
    if not (message or "").strip():
        return _fallback()
    try:
        agent = _get_agent()
    except Exception as e:  # model/agent construction failed
        return f"⚠ assistant unavailable: `{e}`\n\n" + _fallback()
    if agent is None:
        return _fallback()
    try:
        result = agent.invoke({"messages": [{"role": "user", "content": message}]})
        msgs = result.get("messages", []) if isinstance(result, dict) else []
        if msgs:
            content = getattr(msgs[-1], "content", None)
            if isinstance(content, list):  # some providers return content blocks
                content = "".join(b.get("text", "") if isinstance(b, dict) else str(b)
                                  for b in content)
            if content and content.strip():
                return content
        return "*(no response)*"
    except Exception as e:
        return f"⚠ assistant error: `{e}`\n\n" + _fallback()


async def answer_stream(message: str):
    """Async generator of (kind, data) events for the streaming chat endpoint.

    kinds: ('token', str) | ('tool_start', {name,args}) | ('tool_end', {name})
           | ('error', str). Falls back to a single token when no provider is set.
    """
    if not (message or "").strip():
        yield ("token", _fallback())
        return
    try:
        agent = _get_agent()
    except Exception as e:
        yield ("token", f"⚠ assistant unavailable: `{e}`\n\n" + _fallback())
        return
    if agent is None:
        yield ("token", _fallback())
        return
    try:
        async for ev in agent.astream_events(
            {"messages": [{"role": "user", "content": message}]}, version="v2"
        ):
            kind = ev.get("event")
            if kind == "on_chat_model_stream":
                chunk = ev["data"].get("chunk")
                content = getattr(chunk, "content", None)
                # skip the tool-deciding turn (chunks that carry tool_call_chunks)
                if content and isinstance(content, str) and not getattr(chunk, "tool_call_chunks", None):
                    yield ("token", content)
            elif kind == "on_tool_start":
                yield ("tool_start", {"name": ev.get("name", "tool"),
                                      "args": ev["data"].get("input", {})})
            elif kind == "on_tool_end":
                yield ("tool_end", {"name": ev.get("name", "tool")})
    except Exception as e:
        yield ("error", str(e))
