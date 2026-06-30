import asyncio
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import urllib.request as _urlreq


def _load_env_file():
    for candidate in [Path(__file__).resolve().parent.parent.parent.parent / ".env",
                      Path(__file__).resolve().parent.parent.parent / ".env"]:
        if candidate.exists():
            for line in candidate.read_text().splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, _, v = line.partition("=")
                    os.environ.setdefault(k.strip(), v.strip())
            break

_load_env_file()

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
EDITORIAL_ATOMSPACE_MEMORY = PROJECT_ROOT / "memory" / "editorial_memory.metta"


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
        "Chemistry": "Chemistry",
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


def extract_themes(raw_sources):
    theme_dictionary = {

        "AI Agents": [
            "agent",
            "agents",
            "autonomous"
        ],

        "Open Source AI": [
            "open source",
            "github"
        ],

        "AGI": [
            "agi",
            "general intelligence"
        ], 
         "Biology": [
            "humans",
            "biology",
            "living organisms"
        ]
    }

    scores = {}

    for source in raw_sources:

        text = source["content"].lower()

        for theme, keywords in theme_dictionary.items():

            count = 0

            for keyword in keywords:

                count += text.count(keyword)

            scores[theme] = (
                scores.get(theme, 0) + count
            )


    return scores


def extract_entities(raw_sources):
    entities = {}

    known_entities = [
        "AGI",
        "ASI",
        "OpenAI",
        "Anthropic",
        "Claude",
        "GitHub",
        "Google"
    ]


    for source in raw_sources:

        text = source["content"]

        for entity in known_entities:

            if entity.lower() in text.lower():

                entities[entity] = (
                    entities.get(entity, 0) + 1
                )


    return entities



def _selected_editorial_provider() -> str:
    return (
        os.environ.get("EDITORIAL_PROVIDER")
        or os.environ.get("OMEGACLAW_PROVIDER")
        or _read_metta_config_value("provider", DEFAULT_EDITORIAL_PROVIDER)
    )


def _selected_editorial_max_tokens() -> int:
    raw_value = (
        os.environ.get("EDITORIAL_MAX_TOKENS")
        or _read_metta_config_value("maxOutputToken", str(DEFAULT_EDITORIAL_MAX_TOKENS))
    )
    try:
        return int(raw_value)
    except (TypeError, ValueError):
        return DEFAULT_EDITORIAL_MAX_TOKENS


def _call_selected_provider(prompt: str) -> str:
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))

    import lib_llm_ext

    provider = _selected_editorial_provider()
    max_tokens = _selected_editorial_max_tokens()
    return lib_llm_ext.callProvider(provider, prompt, max_tokens)




def cross_reference(themes):


    with open(PROJECT_ROOT / "memory" / "editorial_memory.json") as f:
        memory = json.load(f)

    candidates = []


    for theme, score in themes.items():

        previous_mentions = (
            memory["themes"]
            .get(theme, {})
            .get("mentions", 0)
        )

        candidates.append({
            "theme": theme,
            "signal_strength": score,
            "historical_mentions":
                previous_mentions
        })


    return candidates


def rank_stories(candidates):
    ranked = []

    for candidate in candidates:

        signal = (
            candidate["signal_strength"]
        )

        continuity = (
            candidate["historical_mentions"]
        )

        score = (
            signal * 0.7
            +
            continuity * 0.3
        )

        candidate["score"] = score

        ranked.append(candidate)


    ranked.sort(
        key=lambda x: x["score"],
        reverse=True
    )
    return ranked







def _fallback_article(story, sources, context):
    publication = context.get("publication", "AI Futures")
    theme = story["theme"]
    score = story["score"]
    source_titles = [
        source.get("title", "Untitled source")
        for source in sources
        if source.get("topic") == theme
    ][:3] or [source.get("title", "Untitled source") for source in sources][:3]
    evidence = "; ".join(source_titles) or "the collected editorial source summaries"

    content = (
        f"{publication} is tracking {theme} as today's strongest editorial candidate, "
        f"with a signal score of {score}. According to {evidence}, the topic is showing "
        f"enough activity to merit a focused draft.\n\n"
        f"The central story is that {theme} is moving from abstract promise into practical "
        f"systems, tools, and public debate. The available source material points to recurring "
        f"questions about capability, reliability, and how quickly organizations can turn "
        f"research ideas into usable infrastructure.\n\n"
        f"A publishable version should bring in concrete examples, named projects, dates, "
        f"and links to original reports or papers."
    )
    return {
        "theme": theme,
        "score": score,
        "title": f"{theme}: Today's Editorial Candidate",
        "content": content,
        "excerpt": f"{publication} examines {theme} as today's lead editorial theme.",
    }


def draft_article(story, sources=None, context=None, entities=None):
    sources = sources or []
    context = context or {}
    entities = entities or {}

    prompt = f"""You are the editorial drafting module for {context.get("publication", "AI Futures")}.

Write a publication-ready article from the selected story and source summaries.
Respond with ONLY a valid JSON object — no markdown fences, no extra text.

JSON schema:
{{
  "theme": "<the selected theme>",
  "score": <numeric signal score>,
  "title": "<compelling article headline, 8-12 words>",
  "content": "<full article body, 500-800 words, paragraphs separated by \\n\\n>",
  "excerpt": "<1-2 sentence summary for previews, max 200 chars>"
}}

Requirements:
- Write 500-800 words in the content field.
- Make the article specific, analytical, and readable.
- Use only the provided source summaries.
- Do not invent URLs, quotes, dates, or facts.
- Mention evidence with phrases such as "According to the source summaries" when exact citations are unavailable.
- Avoid placeholder language like "continues an ongoing trend".

Selected story:
{json.dumps(story, indent=2)}

Editorial context:
{json.dumps(context, indent=2)}

Detected entities:
{json.dumps(entities, indent=2)}

Source summaries:
{json.dumps(sources, indent=2)}
"""

    try:
        raw = _call_selected_provider(prompt)
        raw = str(raw).strip()
        raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.IGNORECASE)
        raw = re.sub(r"\s*```$", "", raw)
        article = json.loads(raw)
        if not isinstance(article, dict) or not article.get("content"):
            raise ValueError("Invalid structure")
        return article
    except Exception as e:
        print(f"LLM draft generation failed: {e}")
        return _fallback_article(story, sources, context)

def critique_article(article):
    if not isinstance(article, dict):
        return {
            "publication": {"success": False, "status": "needs-revision"},
            "critique": {"approved": False, "issues": [{"severity": "major", "message": "Article is not structured JSON."}]},
            "followups": ["Return a valid JSON article object."],
        }

    content = str(article.get("content", "")).strip()
    issues = []
    recommendations = []

    required_keys = ["title", "content", "theme"]
    missing_keys = [k for k in required_keys if not article.get(k)]
    if missing_keys:
        issues.append({
            "severity": "major",
            "message": f"Article is missing required fields: {', '.join(missing_keys)}",
        })
        recommendations.append("Ensure title, content, and theme fields are present and non-empty.")

    words = re.findall(r"\b[\w'-]+\b", content)
    word_count = len(words)
    if word_count < 120:
        issues.append({"severity": "major", "message": "Draft is too short for publication."})
        recommendations.append("Expand the draft with a clear lead, context, evidence, and implications.")

    source_signals = ["http://", "https://", "source:", "according to", "reported", "study", "paper"]
    if content and not any(signal in content.lower() for signal in source_signals):
        issues.append({"severity": "major", "message": "Draft does not cite or mention supporting sources."})
        recommendations.append("Add source-backed evidence before publication.")

    if "example.com" in content.lower():
        issues.append({"severity": "critical", "message": "Draft contains placeholder source material."})
        recommendations.append("Replace placeholder sources with real source references.")

    if "continues an ongoing trend" in content.lower():
        issues.append({"severity": "minor", "message": "Draft uses generic placeholder language."})
        recommendations.append("Replace generic phrasing with specific developments and concrete stakes.")

    approved = not any(issue["severity"] in {"critical", "major"} for issue in issues)
    critique = {"approved": approved, "word_count": word_count, "issues": issues, "recommendations": recommendations}

    if approved:
        return None

    return {
        "publication": {"success": False, "status": "needs-revision", "content": content},
        "critique": critique,
        "followups": recommendations,
    }



def parse_article_for_mindplex(article):

    title = article.get("title", "Untitled")
    content = article.get("content", "")
    excerpt = article.get("excerpt", title)[:300]
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    word_count = len(re.findall(r"\b\w+\b", content))
    reading_minutes = max(1, round(word_count / 200))

    payload = {
        "title": title,
        "slug": slug,
        "content": content,
        "excerpt": excerpt,
        "status": "published",
        "type": "article",
        "estimatedReadingMinutes": reading_minutes,
        "publishedAt": datetime.now(timezone.utc).isoformat(),
    }

    return payload


def publish_article(article):

    payload= parse_article_for_mindplex(article)
    
    api_url = os.environ.get("MINDPLEX_API_URL", "http://localhost:3000/v1/posts")

    def _do_publish(token: str) -> dict:
        body = json.dumps(payload).encode()
        req = _urlreq.Request(
            api_url,
            data=body,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {token}",
            },
            method="POST",
        )
        with _urlreq.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read().decode())
            d = result.get("data", result)
            return {
                "success": True,
                "status": "published",
                "article_id": d.get("id") or d.get("slug") or payload.get("slug"),
                "title": payload.get("title"),
                "response": result,
            }

    try:
        return _do_publish(os.environ.get("MINDPLEX_API_TOKEN", ""))
    except _urlreq.HTTPError as e:
        if e.code == 401:
            print("[publish_article] 401 — refreshing token and retrying")
            new_token = _refresh_mindplex_token()
            if new_token:
                try:
                    return _do_publish(new_token)
                except _urlreq.HTTPError as e2:
                    error_body = e2.read().decode(errors="replace")
                    print(f"[publish_article] HTTP {e2.code} after refresh: {error_body}")
                    return {"success": False, "status": "publish-failed", "error": f"HTTP {e2.code}", "api_message": error_body}
        error_body = e.read().decode(errors="replace")
        print(f"[publish_article] HTTP {e.code}: {error_body}")
        return {"success": False, "status": "publish-failed", "error": f"HTTP {e.code}", "api_message": error_body}
    except Exception as e:
        print(f"[publish_article] publish failed: {e}")
        return {"success": False, "status": "publish-failed", "error": str(e)}


def create_followups(story):
    return []


def update_memory(story):
    theme = story.get("theme")
    if not theme:
        return "MEMORY_UPDATE_SKIPPED"

    mentions = _read_theme_mentions_from_metta()
    next_count = mentions.get(theme, 0) + 1
    timestamp = datetime.now(timezone.utc).isoformat()
    _append_atomspace_facts([
        _metta_atom("ThemeMention", theme, next_count),
        _metta_atom("ThemeLastSelected", theme, timestamp),
    ])
    return "MEMORY_UPDATE_SUCCESS"

def editorial_agent():
    
  
    context = load_editorial_context()
    
  
    raw_sources = fetch_sources(
        context
    )

    entities = extract_entities(
        raw_sources
    )

    reasoning_mode = context.get("reasoning_mode", "python")
    
    if reasoning_mode == "atomspace":
        selected_story, reasoning_trace = atomspace_select_story(
            raw_sources,
            context,
        )
    else:
        themes = extract_themes(
            raw_sources
        )
        candidates = cross_reference(
            themes
        )

        ranked = rank_stories(
            candidates
        )

        selected_story = ranked[0]
        reasoning_trace = {
            "themes": themes,
            "candidates": candidates,
            "ranked": ranked,
        }

    article = draft_article(
        selected_story,
        sources=raw_sources,
        context=context,
        entities=entities,
    )

    critique = critique_article(
        article
    )

    if critique:
        
        return critique

    publication = publish_article(
        article
    )

    update_memory(
        selected_story
    )

    followups = create_followups(
        selected_story
    )

    return {
        "publication": publication,
        "selected_story": selected_story,
        "reasoning_mode": reasoning_mode,
        "reasoning_trace": reasoning_trace,
    }




def _metta_string(value: Any) -> str:
    text = str(value)
    text = text.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
    return f'"{text}"'


def _metta_atom(name: str, *args: Any) -> str:
    return f"({name} {' '.join(_metta_string(arg) for arg in args)})"


def _source_id(index: int, source: dict) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", source.get("topic", "source").lower()).strip("-")
    return f"{slug or 'source'}-{index + 1}"



def _extract_source_keywords(source: dict, theme_keywords: dict[str, list[str]]) -> list[str]:
    text = f"{source.get('title', '')} {source.get('content', '')}".lower()
    keywords = set()
    for keyword_list in theme_keywords.values():
        for keyword in keyword_list:
            if keyword.lower() in text:
                keywords.add(keyword)
    return sorted(keywords)


def _default_theme_keywords(context=None):
    configured_beats = (context or {}).get("beats") or []
    keywords = {
        "AI Agents": ["agent", "agents", "autonomous"],
        "Open Source AI": ["open source", "github"],
        "AGI": ["agi", "general intelligence"],
        "Biology": ["biology", "living organisms"],
    }
    for beat in configured_beats:
        keywords.setdefault(beat, [beat.lower()])
    return keywords





def _read_theme_mentions_from_json():
    path = PROJECT_ROOT / "memory" / "editorial_memory.json"
    try:
        with open(path) as f:
            memory = json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}

    mentions = {}
    for theme, data in memory.get("themes", {}).items():
        if isinstance(data, dict):
            mentions[theme] = int(data.get("mentions", 0))
    return mentions


def _read_theme_mentions_from_metta():
    if not EDITORIAL_ATOMSPACE_MEMORY.exists():
        return {}

    text = EDITORIAL_ATOMSPACE_MEMORY.read_text()
    mentions = {}
    for theme, count in re.findall(
        r'\(ThemeMention\s+"((?:\\.|[^"])*)"\s+"?([0-9]+)"?\)',
        text,
    ):
        mentions[theme.replace('\\"', '"')] = int(count)
    return mentions


def _read_comment_thread_signals() -> dict:
    """Returns {theme: total_signal_count} from CommentThreadSignal atoms."""
    if not EDITORIAL_ATOMSPACE_MEMORY.exists():
        return {}
    text = EDITORIAL_ATOMSPACE_MEMORY.read_text()
    signals: dict = {}
    for theme, count in re.findall(r'\(CommentThreadSignal\s+"((?:\\.|[^"])*)"\s+"?([0-9]+)"?\)', text):
        signals[theme] = signals.get(theme, 0) + int(count)
    return signals


def _read_comment_replied_from_metta() -> set:
    if not EDITORIAL_ATOMSPACE_MEMORY.exists():
        return set()
    text = EDITORIAL_ATOMSPACE_MEMORY.read_text()
    return set(re.findall(r'\(CommentReplied\s+"((?:\\.|[^"])*)"', text))



def _read_theme_keywords_from_metta(context=None):
    keywords = _default_theme_keywords(context)
    if not EDITORIAL_ATOMSPACE_MEMORY.exists():
        return keywords

    text = EDITORIAL_ATOMSPACE_MEMORY.read_text()
    for theme, keyword in re.findall(
        r'\(ThemeKeyword\s+"((?:\\.|[^"])*)"\s+"((?:\\.|[^"])*)"\)',
        text,
    ):
        clean_theme = theme.replace('\\"', '"')
        clean_keyword = keyword.replace('\\"', '"')
        keywords.setdefault(clean_theme, [])
        if clean_keyword not in keywords[clean_theme]:
            keywords[clean_theme].append(clean_keyword)
    return keywords



def _append_atomspace_facts(facts: list[str]):
    if not facts:
        return

    existing = set()
    if EDITORIAL_ATOMSPACE_MEMORY.exists():
        existing = {
            line.strip()
            for line in EDITORIAL_ATOMSPACE_MEMORY.read_text().splitlines()
            if line.strip() and not line.strip().startswith(";")
        }

    new_facts = [fact for fact in facts if fact not in existing]
    if not new_facts:
        return

    with open(EDITORIAL_ATOMSPACE_MEMORY, "a") as f:
        f.write("\n")
        for fact in new_facts:
            f.write(f"{fact}\n")


def assert_sources_to_atomspace(raw_sources, context):
    theme_keywords = _read_theme_keywords_from_metta(context)
    facts = []

    for index, source in enumerate(raw_sources):
        source_id = _source_id(index, source)
        facts.extend([
            _metta_atom("Source", source_id),
            _metta_atom("SourceTopic", source_id, source.get("topic", "")),
            _metta_atom("SourceTitle", source_id, source.get("title", "")),
            _metta_atom("SourceContent", source_id, source.get("content", "")),
        ])
        for keyword in _extract_source_keywords(source, theme_keywords):
            facts.append(_metta_atom("SourceKeyword", source_id, keyword))

    
    _append_atomspace_facts(facts)
    return facts


def atomspace_extract_themes(raw_sources, context):
    theme_keywords = _read_theme_keywords_from_metta(context)
    scores = {theme: 0 for theme in theme_keywords}

    for source in raw_sources:
        text = f"{source.get('title', '')} {source.get('content', '')}".lower()
        for theme, keywords in theme_keywords.items():
            scores[theme] += sum(text.count(keyword.lower()) for keyword in keywords)

    return {
        theme: score
        for theme, score in scores.items()
        if theme in context.get("beats", scores.keys())
    }



def atomspace_cross_reference(themes):
    mentions = _read_theme_mentions_from_metta()
    json_mentions = _read_theme_mentions_from_json()
    candidates = []

    for theme, score in themes.items():
        historical_mentions = max(
            mentions.get(theme, 0),
            json_mentions.get(theme, 0),
        )
        candidates.append({
            "theme": theme,
            "signal_strength": score,
            "historical_mentions": historical_mentions,
            "memory_backend": "atomspace",
        })

    return candidates


_NAL_CYCLE_CACHE: dict[str, Any] = {}


def gather_theme_candidates() -> str:
    """Fetch sources, extract themes/entities, and hand evidence counts to
    the NAL reasoner as a MeTTa string of (ThemeSignal "<theme>" <signal>
    <history>) facts. Caches the cycle's context/sources/entities/candidates
    so finish_nal_article can pick up where this left off."""
    context = load_editorial_context()
    raw_sources = fetch_sources(context)
    entities = extract_entities(raw_sources)

    assert_sources_to_atomspace(raw_sources, context)
    themes = atomspace_extract_themes(raw_sources, context)
    candidates = atomspace_cross_reference(themes)

    _NAL_CYCLE_CACHE["context"] = context
    _NAL_CYCLE_CACHE["raw_sources"] = raw_sources
    _NAL_CYCLE_CACHE["entities"] = entities
    _NAL_CYCLE_CACHE["candidates"] = candidates

    # Boost signal_strength for themes that had active comment threads
    thread_signals = _read_comment_thread_signals()
    boosted = []
    for c in candidates:
        boost = thread_signals.get(c["theme"], 0)
        boosted.append({**c, "signal_strength": c["signal_strength"] + boost})

    facts = " ".join(
        f"(ThemeSignal {_metta_string(c['theme'])} "
        f"{c['signal_strength']} {c['historical_mentions']})"
        for c in boosted
    )
    return f"({facts})"


_NAL_RESULT_RE = re.compile(
    r'^\(\(\s*(?:"((?:\\.|[^"])*)"|(\S+))\s+(-?[0-9.]+)\s+'
    r'\(stv\s+(-?[0-9.]+)\s+(-?[0-9.]+)\)\)\s*\((.*)\)\)\s*$',
    re.DOTALL,
)

_NAL_EXPLANATION_RE = re.compile(
    r'\(ThemeReasoning\s+"((?:\\.|[^"])*)"\s+'
    r'\(StrongSignalEvidence\s+([0-9]+)\)\s+'
    r'\(RecurringEvidence\s+([0-9]+)\)\s+'
    r'\(LeadCandidateBelief\s+\(stv\s+(-?[0-9.]+)\s+(-?[0-9.]+)\)\)\s+'
    r'\(Expectation\s+(-?[0-9.]+)\)\)'
)


def _parse_nal_result(result_str: str):
    """Parse the (repr ...) of (select-and-explain $candidates):
    ((WinnerTheme WinnerExpectation (stv f c)) (ThemeReasoning ...)*)"""
    match = _NAL_RESULT_RE.match(result_str.strip())
    if not match:
        raise ValueError(f"Could not parse NAL selection result: {result_str!r}")

    quoted_theme, bare_theme, expectation, freq, conf, explanations_blob = match.groups()
    theme = (quoted_theme or bare_theme or "").replace('\\"', '"')
    winner = {
        "theme": theme,
        "expectation": float(expectation),
        "lead_candidate_tv": (float(freq), float(conf)),
    }

    explanations = []
    for m in _NAL_EXPLANATION_RE.finditer(explanations_blob):
        e_theme, signal, history, e_freq, e_conf, e_exp = m.groups()
        explanations.append({
            "theme": e_theme.replace('\\"', '"'),
            "signal_strength": int(signal),
            "historical_mentions": int(history),
            "lead_candidate_tv": (float(e_freq), float(e_conf)),
            "expectation": float(e_exp),
        })

    return winner, explanations


def finish_nal_article(result_str: str):
    """Take the NAL selection result computed by lib_editorial_reasoning's
    select-and-explain, draft/critique/publish the winning theme, and
    record it in memory - mirroring the tail end of editorial_agent()."""
    context = _NAL_CYCLE_CACHE.get("context") or load_editorial_context()
    raw_sources = _NAL_CYCLE_CACHE.get("raw_sources", [])
    entities = _NAL_CYCLE_CACHE.get("entities", {})
    candidates = _NAL_CYCLE_CACHE.get("candidates", [])

    winner, explanations = _parse_nal_result(result_str)

    candidate_lookup = {c["theme"]: c for c in candidates}
    selected_story = dict(candidate_lookup.get(winner["theme"], {"theme": winner["theme"]}))
    selected_story["score"] = winner["expectation"]
    selected_story["lead_candidate_tv"] = winner["lead_candidate_tv"]

    article = draft_article(selected_story, sources=raw_sources, context=context, entities=entities)

    critique = critique_article(article)
    if critique:
        return critique

    publication = publish_article(article)
    update_memory(selected_story)

    return {
        "publication": publication,
        "selected_story": selected_story,
        "reasoning_mode": "nal",
        "reasoning_trace": {
            "winner": winner,
            "candidates": explanations,
        },
    }


def atomspace_select_story(raw_sources, context):
    assert_sources_to_atomspace(raw_sources, context)
    themes = atomspace_extract_themes(raw_sources, context)
    candidates = atomspace_cross_reference(themes)
    ranked = rank_stories(candidates)
    if not ranked:
        raise ValueError("AtomSpace story selection found no candidates")
    return ranked[0], {
        "themes": themes,
        "candidates": candidates,
        "ranked": ranked,
    }


def _read_metta_config_value(name: str, default: str) -> str:
    loop_path = PROJECT_ROOT / "src" / "loop.metta"
    try:
        text = loop_path.read_text()
    except OSError:
        return default

    match = re.search(rf"\(configure\s+{re.escape(name)}\s+([^\s\)]+)\)", text)
    if not match:
        return default
    return match.group(1)


def gateway_ping():
    return "PONG from AgentVerse editorial agent!"


def _mindplex_base() -> str:
    url = os.environ.get("MINDPLEX_API_URL", "https://api-dev.mindplex.ai/v1/posts")
    return url.rstrip("/").rsplit("/v1/", 1)[0] + "/v1"


def _mindplex_token() -> str:
    return os.environ.get("MINDPLEX_API_TOKEN", "")


def _refresh_mindplex_token() -> str:
    email = os.environ.get("MINDPLEX_EMAIL", "")
    password = os.environ.get("MINDPLEX_PASSWORD", "")
    if not email or not password:
        print("[_refresh_mindplex_token] no credentials configured")
        return ""
    try:
        body = json.dumps({"email": email, "password": password}).encode()
        req = _urlreq.Request(
            f"{_mindplex_base().rsplit('/v1', 1)[0]}/v1/auth/login",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with _urlreq.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())
            token = (data.get("data") or {}).get("access_token") or data.get("access_token", "")
            if token:
                os.environ["MINDPLEX_API_TOKEN"] = token
                print("[_refresh_mindplex_token] token refreshed")
            return token
    except Exception as e:
        print(f"[_refresh_mindplex_token] failed: {e}")
        return ""


def _fetch_mindplex(path: str) -> dict:
    req = _urlreq.Request(
        f"{_mindplex_base()}{path}",
        headers={"Authorization": f"Bearer {_mindplex_token()}",
                 "Content-Type": "application/json"},
    )
    with _urlreq.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode())


def _post_mindplex(path: str, body: dict) -> dict:
    def _do_post(token: str) -> dict:
        data = json.dumps(body).encode()
        req = _urlreq.Request(
            f"{_mindplex_base()}{path}",
            data=data,
            headers={"Authorization": f"Bearer {token}",
                     "Content-Type": "application/json"},
            method="POST",
        )
        with _urlreq.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode())

    try:
        return _do_post(_mindplex_token())
    except _urlreq.HTTPError as e:
        if e.code == 401:
            print("[_post_mindplex] 401 — refreshing token and retrying")
            new_token = _refresh_mindplex_token()
            if new_token:
                return _do_post(new_token)
        raise


def _engagement_prompt() -> str:
    path = PROJECT_ROOT / "memory" / "engagement_prompt.txt"
    if path.exists():
        return path.read_text().strip()
    return "Reply thoughtfully and concisely to the reader comment in 2-3 sentences."


def _classify_comment(comment_text: str) -> str:
    """Returns 'reply' | 'escalate' | 'skip'"""
    prompt = f"""Classify this reader comment. Reply with exactly one word.

escalate — if it contains: legal claims, accusations against named individuals,
           emotionally hostile language, or signs of coordinated manipulation
skip     — if it is spam, gibberish, or entirely off-topic
reply    — for everything else (questions, opinions, critiques, praise)

Comment: {comment_text}

Classification:"""
    try:
        result = _call_selected_provider(prompt).strip().lower().split()[0]
        return result if result in {"reply", "escalate", "skip"} else "reply"
    except Exception:
        return "reply"


def _build_thread_context(comments: list, comment_id) -> list:
    """Walk parentId chain to build the full conversation thread."""
    index = {str(c.get("id")): c for c in comments}
    thread = []
    current = index.get(str(comment_id))
    while current:
        thread.insert(0, current)
        parent_id = current.get("parentId")
        current = index.get(str(parent_id)) if parent_id else None
    return thread


def _extract_theme_from_comment(article_title: str, comment_text: str) -> str:
    """Ask the LLM for the main theme this comment discussion points to."""
    prompt = f"""Article: {article_title}
Comment: {comment_text}
In 3 words or less, what topic does this comment most want to explore further?
Reply with the topic only, no explanation:"""
    try:
        return _call_selected_provider(prompt).strip()[:60]
    except Exception:
        return ""


def draft_reply(article_title: str, article_content: str, thread: list) -> str:
    thread_text = "\n".join(
        f"[{'Agent' if c.get('authorId') == int(os.environ.get('MINDPLEX_AUTHOR_ID', '4')) else 'Reader'}] {c.get('content', '')}"
        for c in thread
    )
    prompt = f"""{_engagement_prompt()}

Article title: {article_title}
Article excerpt: {article_content[:600]}

Comment thread (oldest first):
{thread_text}

Write your reply to the last reader comment now:"""
    try:
        return _call_selected_provider(prompt).strip()
    except Exception as e:
        print(f"[draft_reply] LLM failed: {e}")
        return ""


def handle_comment(post_id, comment_id) -> dict:
    print(f"[handle_comment] post_id={post_id} comment_id={comment_id}")

    reply_key = f"{post_id}_{comment_id}"
    if reply_key in _read_comment_replied_from_metta():
        print(f"[handle_comment] skipped: already-replied {reply_key}")
        return {"status": "skipped", "reason": "already-replied"}

    print(f"[handle_comment] fetching article={post_id} token_set={bool(_mindplex_token())}")

    try:
        article_resp = _fetch_mindplex(f"/posts/{post_id}")
        article_data = article_resp.get("data", article_resp)
        article_title = article_data.get("title", "")
        article_content = article_data.get("excerpt") or article_data.get("content", "")[:600]
        post_identifier = article_data.get("slug") or str(post_id)

        comments_resp = _fetch_mindplex(f"/posts/{post_identifier}/comments")
        comments = comments_resp.get("data", [])
        comment = next((c for c in comments if str(c.get("id")) == str(comment_id)), None)
        print(f"[handle_comment] found comment={comment is not None} available_ids={[c.get('id') for c in comments]}")
        if not comment:
            raise RuntimeError(f"comment {comment_id} not visible yet — will retry")
        comment_text = comment.get("content", "")
    except RuntimeError:
        raise
    except Exception as e:
        print(f"[handle_comment] fetch failed: {e}")
        return {"status": "error", "reason": f"fetch failed: {e}"}

    if not comment_text:
        print(f"[handle_comment] skipped: empty comment")
        return {"status": "skipped", "reason": "empty comment"}

    # Step 2 — Escalation: classify before drafting
    action = _classify_comment(comment_text)
    print(f"[handle_comment] classification={action}")
    if action == "escalate":
        _append_atomspace_facts([
            _metta_atom("ThreadEscalated", reply_key, comment_text[:120]),
        ])
        print(f"[handle_comment] ESCALATED to human editor: {reply_key}")
        return {"status": "escalated", "reason": "routed to human editor", "comment": comment_text}
    if action == "skip":
        return {"status": "skipped", "reason": "spam or off-topic"}

    # Step 4 — Thread memory: build full conversation context
    thread = _build_thread_context(comments, comment_id)
    print(f"[handle_comment] thread_depth={len(thread)}")

    reply_text = draft_reply(article_title, article_content, thread)
    if not reply_text:
        print(f"[handle_comment] LLM reply generation failed")
        return {"status": "error", "reason": "LLM reply generation failed"}

    print(f"[handle_comment] identifier={post_identifier} reply: {reply_text[:120]}")

    try:
        result = _post_mindplex(f"/posts/{post_identifier}/comments", {
            "content": reply_text,
            "parentId": int(comment_id),
        })
        print(f"[handle_comment] posted: {result}")
    except Exception as e:
        print(f"[handle_comment] post reply failed: {e}")
        return {"status": "error", "reason": f"post reply failed: {e}", "draft": reply_text}

    # Step 3 — Reader influence: write theme signal for tomorrow's article selection
    thread_theme = _extract_theme_from_comment(article_title, comment_text)
    facts = [_metta_atom("CommentReplied", reply_key, datetime.now(timezone.utc).isoformat())]
    if thread_theme:
        facts.append(_metta_atom("CommentThreadSignal", thread_theme, "1"))
        print(f"[handle_comment] thread theme signal: {thread_theme}")
    _append_atomspace_facts(facts)

    return {"status": "replied", "post_id": post_id, "comment_id": comment_id, "reply": reply_text}





