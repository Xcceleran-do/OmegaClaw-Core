import asyncio
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from uagents import Model
    from uagents.query import send_sync_message
except ModuleNotFoundError:
    class Model:
        def __init__(self, **kwargs):
            for key, value in kwargs.items():
                setattr(self, key, value)

    send_sync_message = None

TECHNICAL_ANALYSIS_AGENT_ADDRESS = os.environ.get(
    "TECHNICAL_ANALYSIS_AGENT_ADDRESS",
    "agent1q085746wlr3u2uh4fmwqplude8e0w6fhrmqgsnlp49weawef3ahlutypvu6",
)
TAVILY_SEARCH_AGENT_ADDRESS = os.environ.get(
    "TAVILY_SEARCH_AGENT_ADDRESS",
    "agent1qt5uffgp0l3h9mqed8zh8vy5vs374jl2f8y0mjjvqm44axqseejqzmzx9v8",
)
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_EDITORIAL_PROVIDER = "Bedrock"
DEFAULT_EDITORIAL_MAX_TOKENS = 1800


class WebSearchRequest(Model):
    query: str


class TechAnalysisRequest(Model):
    ticker: str


def _truncate_text(value: Any, limit: int) -> str:
    text = " ".join(str(value).split())
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."


def _format_tavily_results(response: str, max_results: int = 5) -> str:
    try:
        data = json.loads(response)
    except json.JSONDecodeError:
        return response

    if not isinstance(data, dict):
        return response

    results = data.get("results")
    if not isinstance(results, list):
        return response

    formatted = []
    for result in results[:max_results]:
        if not isinstance(result, dict):
            continue

        title = _truncate_text(result.get("title", ""), 160)
        url = _truncate_text(result.get("url", ""), 240)
        snippet = _truncate_text(result.get("content", ""), 400)

        parts = []
        if title:
            parts.append(f"TITLE: {title}")
        if url:
            parts.append(f"URL: {url}")
        if snippet:
            parts.append(f"SNIPPET: {snippet}")

        if parts:
            formatted.append(f"({' '.join(parts)})")

    return f"({' '.join(formatted)})" if formatted else response

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


def tavily_search(search_query: str, timeout: int = 60) -> str:
    try:
        request = WebSearchRequest(query=search_query)
        response = asyncio.run(
            _ask_agent(TAVILY_SEARCH_AGENT_ADDRESS, request, int(timeout))
        )
        return _format_tavily_results(response)
    except Exception as e:
        return f"error: {e}"



def load_editorial_context():
    with open(PROJECT_ROOT / "memory" / "topic_config.json") as f:
        topic = json.load(f)

    # with open("configs/methodology_config.json") as f:
    #     methodology = json.load(f)

    # with open("configs/engagement_config.json") as f:
    #     engagement = json.load(f)

    return topic


def search_mindplex(beat: str):
    sources_by_topic = {
        "AI": [
            {
                "title": "What is AI?",
                "url": "https://example.com/ai",
                "content": "AI stands for Artificial Intelligence, which refers to the simulation of human intelligence in machines that are programmed to think and learn like humans.",
            },
            {
                "title": "Applications of AI",
                "url": "https://example.com/ai-applications",
                "content": "AI is used in various applications such as natural language processing, computer vision, autonomous vehicles, and recommendation systems.",
            },
        ],
        "AGI": [
            {
                "title": "What is AGI?",
                "url": "https://example.com/agi",
                "content": "AGI stands for Artificial General Intelligence, which refers to a type of artificial intelligence that can understand, learn, and apply knowledge across a wide range of tasks at a level comparable to human intelligence.",
            }
        ],
        "BGI": [
            {
                "title": "What is BGI?",
                "url": "https://example.com/bgi",
                "content": "BGI stands for Beneficial General Intelligence, which refers to the development of artificial general intelligence that is designed and aligned to be beneficial to humanity, ensuring that its actions and decisions promote human well-being and safety.",
            }
        ],

         "Biology": [
            {
                "title": "What is Biology?",
                "url": "https://example.com/biology",
                "content": "Biology is the scientific study of living organisms, including their structure, function, growth, evolution, and distribution.",
            }
        ],
    }

    topic_aliases = {
        "AI Agents": "AI",
        "Open Source AI": "AI",
        "AGI": "AGI",
        "BGI": "BGI",
    }
    return sources_by_topic.get(topic_aliases.get(beat, beat), [])


def fetch_sources(context):
    collected = []


    for beat in context["beats"]:

        results = search_mindplex(beat)

        for result in results:
            collected.append({
                "topic": beat,
                **result,
            })
    

    return collected

