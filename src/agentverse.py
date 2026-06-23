import asyncio
import json
import os
from typing import Any
from uagents import Model
from uagents.query import send_sync_message

# ── OmegaPlex direct import (in-process, no network) ──────────────────────────
# from omegaplex.search_spider import raw_execute_query, EngineConfig

try:
    from omegaplex.search_spider import raw_execute_query, EngineConfig
    print("[agentverse] omegaplex imported OK")
except Exception as e:
    print(f"[agentverse] omegaplex IMPORT FAILED: {e}")
    raw_execute_query = None
    EngineConfig = None


TECHNICAL_ANALYSIS_AGENT_ADDRESS = os.environ.get(
    "TECHNICAL_ANALYSIS_AGENT_ADDRESS",
    "agent1q085746wlr3u2uh4fmwqplude8e0w6fhrmqgsnlp49weawef3ahlutypvu6",
)


class WebSearchRequest(Model):
    query: str


class TechAnalysisRequest(Model):
    ticker: str


def _truncate_text(value: Any, limit: int) -> str:
    text = " ".join(str(value).split())
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."


def _format_source_documents(docs, max_results: int = 5) -> str:
    """Format list[SourceDocument] into the (TITLE: ... URL: ... SNIPPET: ...) string OmegaClaw expects."""
    formatted = []
    for doc in docs[:max_results]:
        title   = _truncate_text(doc.title, 160)
        url     = _truncate_text(doc.canonical_url, 240)
        snippet = _truncate_text(doc.abstract_or_snippet, 400)
        parts = []
        if title:   parts.append(f"TITLE: {title}")
        if url:     parts.append(f"URL: {url}")
        if snippet: parts.append(f"SNIPPET: {snippet}")
        if parts:
            formatted.append(f"({' '.join(parts)})")
    return f"({' '.join(formatted)})" if formatted else "(no results)"


async def _ask_agent(destination: str, request: Model, timeout: int = 60) -> str:
    envelope_or_status = await send_sync_message(
        destination=destination,
        message=request,
        timeout=timeout,
    )
    return str(envelope_or_status)


def technical_analysis(ticker: str, timeout: int = 60) -> str:
    try:
        request = TechAnalysisRequest(ticker=ticker)
        return asyncio.run(
            _ask_agent(TECHNICAL_ANALYSIS_AGENT_ADDRESS, request, int(timeout))
        )
    except Exception as e:
        return f"error: {e}"


def _clean_result(text: str) -> str:
    return text.replace("_quote_", '"').replace("_apostrophe_", "'")

def tavily_search(search_query: str, timeout: int = 60) -> str:
    """
    Replaced Tavily with OmegaPlex — direct in-process call.
    No network hop, no uAgent, no Agentverse. Function name kept
    the same so skills.metta and all other callers work unchanged.
    """
    try:
        config = EngineConfig.from_env()
        docs = raw_execute_query(search_query, limit=5, config=config)
        return _clean_result(_format_source_documents(docs))
    except Exception as e:
        return f"error: {e}"

def ai_research(topic: str, timeout: int = 60) -> str:
    if raw_execute_query is None:
        return "error: omegaplex not available"
    try:
        config = EngineConfig.from_env()
        docs = raw_execute_query(topic, limit=5, config=config)
        print(f"[agentverse.ai_research] got {len(docs)} docs")
        return _clean_result(_format_source_documents(docs))
    except Exception as e:
        print(f"[agentverse.ai_research] ERROR: {e}")
        return f"error: {e}"