"""
engine/search_spider.py
────────────────────────
Phase 1 — Core Search Engine Library.

This module is intentionally zero-dependency on MCP, LLMs, or any agent
framework.  It is a plain Python library that:

  1. Accepts a query string + source config
  2. Fans out concurrently across configured source tiers
  3. Deduplicates by canonical URL
  4. Validates and normalises every record into a strict SourceDocument schema
  5. Returns a clean list[SourceDocument] — nothing else reaches the caller

Source tiers (all configurable via SourceConfig):
  - BRAVE_WEB    : Brave Search API  (primary web search)
  - RSS_FEED     : Arbitrary RSS/Atom feeds (news, blogs)
  - ARXIV        : arXiv API  (academic papers)
  - DIRECT_URL   : Specific URLs you always want included

Anti-pollution mandate (from spec §1):
  Raw HTML, scraped blobs, or raw API payloads NEVER leave this module.
  Everything is cleaned, truncated, and validated through SourceDocument
  before being returned.

Usage (standalone test):
    python -m engine.search_spider "OmegaClaw MeTTa agents"
"""

import asyncio
import hashlib
import logging
import os
import re
import sys
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional
from urllib.parse import urlparse, urlunparse

import feedparser
import httpx
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from pydantic import BaseModel, Field, field_validator, model_validator

load_dotenv()

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

brave_key = os.getenv("BRAVE_API_KEY")
if brave_key:
    print(f"✅ BRAVE_API_KEY loaded: {brave_key[:8]}...")  # Show first 8 chars only
else:
    print("❌ BRAVE_API_KEY not found")

# ── Output schema (spec §1 "Output Constraint") ───────────────────────────────

class SourceTier(str, Enum):
    BRAVE_WEB  = "brave_web"
    RSS_FEED   = "rss_feed"
    ARXIV      = "arxiv"
    DIRECT_URL = "direct_url"


class SourceDocument(BaseModel):
    """
    Canonical record returned by every source tier.
    This is the only data structure that ever leaves the engine layer.
    All fields are sanitised strings — no raw HTML, no binary blobs.
    """
    id:                  str        = Field(..., description="SHA-256 of canonical_url, hex-encoded")
    url:                 str        = Field(..., description="Original URL as fetched")
    canonical_url:       str        = Field(..., description="Normalised URL (scheme+host+path, no tracking params)")
    title:               str        = Field(default="", description="Page or article title, plain text")
    abstract_or_snippet: str        = Field(default="", description="Short plain-text excerpt, max 500 chars")
    source_tier:         SourceTier = Field(..., description="Which source tier produced this record")
    published_at:        str        = Field(default="", description="ISO-8601 date string or empty")
    authors:             list[str]  = Field(default_factory=list, description="Author names if available")
    tags:                list[str]  = Field(default_factory=list, description="Topic tags if available")

    @field_validator("title", "abstract_or_snippet", mode="before")
    @classmethod
    def strip_and_clean(cls, v: Any) -> str:
        if not v:
            return ""
        text = str(v)
        # Strip script/style blocks including their content first (anti-injection)
        text = re.sub(r"<(script|style)[^>]*>.*?</(script|style)>", "", text, flags=re.DOTALL | re.IGNORECASE)
        # Strip remaining HTML tags
        text = re.sub(r"<[^>]+>", "", text)
        # Collapse whitespace
        text = re.sub(r"\s+", " ", text).strip()
        return text

    @field_validator("abstract_or_snippet", mode="after")
    @classmethod
    def truncate_snippet(cls, v: str) -> str:
        limit = 500
        if len(v) <= limit:
            return v
        return v[:limit].rsplit(" ", 1)[0] + "…"

    @field_validator("canonical_url", mode="before")
    @classmethod
    def validate_url(cls, v: Any) -> str:
        s = str(v).strip()
        if not re.match(r"^https?://", s):
            raise ValueError(f"canonical_url must start with http(s)://: {s!r}")
        return s

    @model_validator(mode="after")
    def set_id(self) -> "SourceDocument":
        if not self.id:
            self.id = hashlib.sha256(self.canonical_url.encode()).hexdigest()[:16]
        return self


# ── Source configuration ──────────────────────────────────────────────────────

@dataclass
class RSSSourceConfig:
    name: str
    url:  str
    tags: list[str] = field(default_factory=list)


@dataclass
class EngineConfig:
    """
    All source tiers and limits.  Pass this to raw_execute_query().
    Every field has a safe default so it works out-of-the-box with
    only BRAVE_API_KEY set.
    """
    brave_api_key:      str   = field(default_factory=lambda: os.environ.get("BRAVE_API_KEY", ""))
    brave_result_count: int   = 5
    brave_enabled:      bool  = True
    brave_freshness:    Optional[str] = None   # 'pd','pw','pm','py' or None

    arxiv_enabled:      bool  = False
    arxiv_max_results:  int   = 3

    rss_feeds:          list[RSSSourceConfig] = field(default_factory=list)

    direct_urls:        list[str] = field(default_factory=list)

    max_concurrent:     int   = 8    # concurrent HTTP connections
    request_timeout:    float = 12.0
    crawl_max_chars:    int   = 6000

    @classmethod
    def from_env(cls) -> "EngineConfig":
        """Build a default config purely from environment variables."""
        return cls(
            brave_api_key=os.environ.get("BRAVE_API_KEY", ""),
            brave_enabled=bool(os.environ.get("BRAVE_API_KEY", "")),
            arxiv_enabled=os.environ.get("ARXIV_ENABLED", "false").lower() == "true",
        )

# ── URL canonicalisation ──────────────────────────────────────────────────────

_TRACKING_PARAMS = frozenset({
    "utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term",
    "ref", "referrer", "fbclid", "gclid", "msclkid", "yclid",
    "mc_cid", "mc_eid", "_ga",
})


def _canonicalise(url: str) -> str:
    """
    Strip tracking query parameters and fragments; lowercase scheme+host.
    Produces a stable key for deduplication.
    """
    try:
        p = urlparse(url)
        from urllib.parse import parse_qs, urlencode
        qs = {k: v for k, v in parse_qs(p.query).items() if k not in _TRACKING_PARAMS}
        clean_query = urlencode(qs, doseq=True)
        return urlunparse((
            p.scheme.lower(),
            p.netloc.lower(),
            p.path.rstrip("/") or "/",
            p.params,
            clean_query,
            "",   # strip fragment
        ))
    except Exception:
        return url


def _make_id(canonical_url: str) -> str:
    return hashlib.sha256(canonical_url.encode()).hexdigest()[:16]


# ── HTML cleaning ─────────────────────────────────────────────────────────────

def _clean_html_to_text(html: str, max_chars: int = 6000) -> str:
    """
    Strip tags, nav, footer, scripts.  Return plain text up to max_chars.
    Anti-pollution: raw HTML never leaves this function.
    """
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "aside", "header", "form"]):
        tag.decompose()
    node = soup.find("article") or soup.find("main") or soup.body or soup
    text = node.get_text(separator=" ")
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > max_chars:
        text = text[:max_chars].rsplit(" ", 1)[0] + "…"
    return text


# ── Tier 1: Brave Search ──────────────────────────────────────────────────────

async def _fetch_brave(
    query: str,
    config: EngineConfig,
    client: httpx.AsyncClient,
) -> list[SourceDocument]:
    if not config.brave_enabled or not config.brave_api_key:
        logger.debug("Brave Search disabled or no API key — skipping")
        return []

    params: dict[str, Any] = {
        "q":               query,
        "count":           min(config.brave_result_count, 10),
        "text_decorations": False,
        "spellcheck":      True,
    }
    if config.brave_freshness:
        params["freshness"] = config.brave_freshness

    headers = {
        "Accept":              "application/json",
        "Accept-Encoding":     "gzip",
        "X-Subscription-Token": config.brave_api_key,
    }

    logger.info("Brave Search: q=%r count=%d", query, params["count"])
    try:
        resp = await client.get(
            "https://api.search.brave.com/res/v1/web/search",
            params=params,
            headers=headers,
        )
        resp.raise_for_status()
        data = resp.json()
    except httpx.HTTPStatusError as exc:
        logger.error("Brave HTTP %d: %s", exc.response.status_code, exc.response.text[:200])
        return []
    except Exception as exc:
        logger.error("Brave fetch failed: %s", exc)
        return []

    results = []
    for r in data.get("web", {}).get("results", []):
        raw_url = r.get("url", "")
        if not raw_url:
            continue
        canonical = _canonicalise(raw_url)
        snippet = r.get("description", "")
        if not snippet and r.get("extra_snippets"):
            snippet = r["extra_snippets"][0]
        try:
            doc = SourceDocument(
                id=_make_id(canonical),
                url=raw_url,
                canonical_url=canonical,
                title=r.get("title", ""),
                abstract_or_snippet=snippet,
                source_tier=SourceTier.BRAVE_WEB,
                published_at=r.get("page_age", ""),
                tags=[],
            )
            results.append(doc)
        except Exception as exc:
            logger.warning("Brave result validation error: %s", exc)
            continue

    logger.info("Brave Search: returned %d valid records", len(results))
    return results


# ── Tier 2: RSS/Atom Feeds ────────────────────────────────────────────────────

async def _fetch_rss(
    query: str,
    feed_config: RSSSourceConfig,
    client: httpx.AsyncClient,
) -> list[SourceDocument]:
    logger.info("RSS fetch: %s (%s)", feed_config.name, feed_config.url)
    try:
        resp = await client.get(feed_config.url)
        resp.raise_for_status()
        raw_feed = resp.text
    except Exception as exc:
        logger.warning("RSS fetch failed for %s: %s", feed_config.url, exc)
        return []

    parsed = feedparser.parse(raw_feed)
    query_lower = query.lower()
    results = []

    for entry in parsed.entries[:20]:  # cap per feed
        title   = entry.get("title", "")
        summary = entry.get("summary", entry.get("description", ""))
        link    = entry.get("link", "")

        if not link:
            continue

        # Relevance filter: title or summary must contain at least one query token
        query_tokens = query_lower.split()
        combined = (title + " " + summary).lower()
        if not any(tok in combined for tok in query_tokens):
            continue

        canonical = _canonicalise(link)
        published = ""
        if hasattr(entry, "published"):
            published = str(entry.published)
        elif hasattr(entry, "updated"):
            published = str(entry.updated)

        try:
            doc = SourceDocument(
                id=_make_id(canonical),
                url=link,
                canonical_url=canonical,
                title=title,
                abstract_or_snippet=summary,
                source_tier=SourceTier.RSS_FEED,
                published_at=published,
                tags=feed_config.tags,
            )
            results.append(doc)
        except Exception as exc:
            logger.warning("RSS entry validation error: %s", exc)
            continue

    logger.info("RSS %s: %d relevant entries", feed_config.name, len(results))
    return results


async def _fetch_all_rss(
    query: str,
    config: EngineConfig,
    client: httpx.AsyncClient,
) -> list[SourceDocument]:
    if not config.rss_feeds:
        return []
    tasks = [_fetch_rss(query, feed, client) for feed in config.rss_feeds]
    results_nested = await asyncio.gather(*tasks, return_exceptions=True)
    out: list[SourceDocument] = []
    for r in results_nested:
        if isinstance(r, Exception):
            logger.error("RSS gather error: %s", r)
        else:
            out.extend(r)
    return out


# ── Tier 3: arXiv ─────────────────────────────────────────────────────────────

async def _fetch_arxiv(
    query: str,
    config: EngineConfig,
) -> list[SourceDocument]:
    if not config.arxiv_enabled:
        return []

    logger.info("arXiv fetch: q=%r max=%d", query, config.arxiv_max_results)
    try:
        import arxiv  # optional dependency

        # arxiv SDK is sync — run in thread pool to avoid blocking event loop
        loop = asyncio.get_event_loop()

        def _sync_search():
            search = arxiv.Search(
                query=query,
                max_results=config.arxiv_max_results,
                sort_by=arxiv.SortCriterion.Relevance,
            )
            client_arxiv = arxiv.Client()
            return list(client_arxiv.results(search))

        papers = await loop.run_in_executor(None, _sync_search)
    except ImportError:
        logger.warning("arxiv package not installed — skipping arXiv tier")
        return []
    except Exception as exc:
        logger.error("arXiv fetch failed: %s", exc)
        return []

    results = []
    for paper in papers:
        url = paper.entry_id
        canonical = _canonicalise(url)
        try:
            doc = SourceDocument(
                id=_make_id(canonical),
                url=url,
                canonical_url=canonical,
                title=paper.title,
                abstract_or_snippet=paper.summary,
                source_tier=SourceTier.ARXIV,
                published_at=paper.published.isoformat() if paper.published else "",
                authors=[str(a) for a in paper.authors[:5]],
                tags=paper.categories,
            )
            results.append(doc)
        except Exception as exc:
            logger.warning("arXiv record validation error: %s", exc)
            continue

    logger.info("arXiv: returned %d valid records", len(results))
    return results


# ── Tier 4: Direct URL crawl ──────────────────────────────────────────────────

async def _crawl_direct_url(
    url: str,
    config: EngineConfig,
    client: httpx.AsyncClient,
) -> Optional[SourceDocument]:
    logger.info("Direct URL crawl: %s", url)
    try:
        resp = await client.get(
            url,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (compatible; OmegaPlex-Spider/1.0; "
                    "+https://github.com/asi-alliance/OmegaClaw-Core)"
                )
            },
        )
        resp.raise_for_status()
    except Exception as exc:
        logger.warning("Direct URL crawl failed for %s: %s", url, exc)
        return None

    content_type = resp.headers.get("content-type", "")
    if "text/html" not in content_type and "text/plain" not in content_type:
        logger.debug("Skipping non-HTML direct URL: %s (%s)", url, content_type)
        return None

    soup = BeautifulSoup(resp.text, "html.parser")
    title_tag = soup.find("title")
    title = title_tag.get_text().strip() if title_tag else ""
    snippet = _clean_html_to_text(resp.text, config.crawl_max_chars)[:500]
    canonical = _canonicalise(str(resp.url))

    try:
        return SourceDocument(
            id=_make_id(canonical),
            url=url,
            canonical_url=canonical,
            title=title,
            abstract_or_snippet=snippet,
            source_tier=SourceTier.DIRECT_URL,
        )
    except Exception as exc:
        logger.warning("Direct URL validation error for %s: %s", url, exc)
        return None


async def _fetch_all_direct(
    config: EngineConfig,
    client: httpx.AsyncClient,
) -> list[SourceDocument]:
    if not config.direct_urls:
        return []
    tasks = [_crawl_direct_url(u, config, client) for u in config.direct_urls]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    out = []
    for r in results:
        if isinstance(r, Exception):
            logger.error("Direct URL gather error: %s", r)
        elif r is not None:
            out.append(r)
    return out


# ── Deduplication ─────────────────────────────────────────────────────────────

def _deduplicate(docs: list[SourceDocument]) -> list[SourceDocument]:
    """
    Remove documents with duplicate canonical_url, preferring the record
    from a higher-priority tier (BRAVE_WEB > RSS_FEED > ARXIV > DIRECT_URL).
    """
    tier_priority = {
        SourceTier.BRAVE_WEB:  0,
        SourceTier.RSS_FEED:   1,
        SourceTier.ARXIV:      2,
        SourceTier.DIRECT_URL: 3,
    }
    seen: dict[str, SourceDocument] = {}
    for doc in docs:
        key = doc.canonical_url
        if key not in seen:
            seen[key] = doc
        else:
            if tier_priority[doc.source_tier] < tier_priority[seen[key].source_tier]:
                seen[key] = doc  # keep the higher-priority tier's version

    return list(seen.values())


# ── Public API (spec §1: raw_execute_query) ───────────────────────────────────

async def _async_execute_query(
    query: str,
    limit: int,
    config: EngineConfig,
) -> list[SourceDocument]:
    """Internal async implementation."""
    if not query or not query.strip():
        raise ValueError("query must be a non-empty string")
    limit = max(1, min(limit, 50))

    async with httpx.AsyncClient(
        timeout=httpx.Timeout(config.request_timeout),
        follow_redirects=True,
        limits=httpx.Limits(max_connections=config.max_concurrent),
    ) as client:
        # Fan out across all tiers concurrently
        brave_task  = _fetch_brave(query, config, client)
        rss_task    = _fetch_all_rss(query, config, client)
        direct_task = _fetch_all_direct(config, client)
        arxiv_task  = _fetch_arxiv(query, config)   # uses own client

        brave_results, rss_results, direct_results, arxiv_results = await asyncio.gather(
            brave_task, rss_task, direct_task, arxiv_task,
            return_exceptions=True,
        )

    all_docs: list[SourceDocument] = []
    for result in [brave_results, rss_results, direct_results, arxiv_results]:
        if isinstance(result, Exception):
            logger.error("Tier gather exception: %s", result)
        else:
            all_docs.extend(result)

    logger.info("Total raw records across all tiers: %d", len(all_docs))

    deduped = _deduplicate(all_docs)
    logger.info("After deduplication: %d unique records", len(deduped))

    return deduped[:limit]


def raw_execute_query(
    query: str,
    limit: int = 5,
    config: Optional[EngineConfig] = None,
) -> list[SourceDocument]:
    """
    Synchronous public API.  This is what the MCP server and tests call.

    Args:
        query:  Search query string. Must be non-empty.
        limit:  Maximum records to return (1–50).
        config: EngineConfig instance.  If None, uses EngineConfig.from_env().

    Returns:
        list[SourceDocument] — clean, validated, deduplicated records.
        NEVER returns raw HTML, raw API payloads, or unparsed text.

    Raises:
        ValueError: if query is empty.
    """
    if config is None:
        config = EngineConfig.from_env()

    return asyncio.run(_async_execute_query(query, limit, config))


# ── CLI test (spec §1: Verification) ─────────────────────────────────────────

if __name__ == "__main__":
    query = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "Mindplex AI platform"
    print(f"\n🕷  OmegaPlex Search Engine — query: {query!r}\n")

    cfg = EngineConfig.from_env()
    if not cfg.brave_api_key:
        print("⚠  BRAVE_API_KEY not set — Brave tier disabled")

    start = time.perf_counter()
    results = raw_execute_query(query, limit=5, config=cfg)
    elapsed = time.perf_counter() - start

    print(f"  {len(results)} results in {elapsed:.2f}s\n")
    for i, doc in enumerate(results, 1):
        print(f"  {i}. [{doc.source_tier.value}] {doc.title}")
        print(f"     {doc.canonical_url}")
        print(f"     {doc.abstract_or_snippet[:120]}")
        print()
