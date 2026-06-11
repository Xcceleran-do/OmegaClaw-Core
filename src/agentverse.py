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
    ][:3]
    if not source_titles:
        source_titles = [
            source.get("title", "Untitled source")
            for source in sources
        ][:3]

    evidence = "; ".join(source_titles) or "the collected editorial source summaries"

    return f"""
Theme:
{theme}

Score:
{score}

Article Draft:

{publication} is tracking {theme} as today's strongest editorial candidate, with a signal score of {score}. According to the collected source summaries, especially {evidence}, the topic is showing enough activity to merit a focused draft rather than a generic trend note.

The central story is that {theme} is moving from abstract promise into practical systems, tools, and public debate. The available source material points to recurring questions about capability, reliability, and how quickly organizations can turn research ideas into usable infrastructure. That makes the topic useful for readers who want to understand not only what changed, but why it matters.

The strongest angle is the tension between momentum and evidence. There is clear interest around {theme}, but the article should avoid overclaiming until stronger primary sources are added. A publishable version should bring in concrete examples, named projects, dates, and links to original reports or papers.

For now, the draft conclusion is cautious: {theme} remains a live and important beat, but it needs better sourcing before publication. The next editorial step is to replace the placeholder summaries with real references and sharpen the argument around one specific development.
"""


def draft_article(story, sources=None, context=None, entities=None):
    sources = sources or []
    context = context or {}
    entities = entities or {}

    prompt = f"""You are the editorial drafting module for {context.get("publication", "AI Futures")}.

Write a publication-ready article from the selected story and source summaries.

Requirements:
- Use the exact section labels: Theme:, Score:, Article Draft:
- Write 500-800 words.
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
        article = _call_selected_provider(prompt)
    except Exception as e:
        print(f"LLM draft generation failed: {e}")
        return _fallback_article(story, sources, context)

    article = str(article).strip()
    if not article:
        return _fallback_article(story, sources, context)

    return article

def critique_article(article):
    article_text = str(article).strip()
    issues = []
    recommendations = []

    words = re.findall(r"\b[\w'-]+\b", article_text)
    word_count = len(words)

    if word_count < 120:
        issues.append({
            "severity": "major",
            "message": "Draft is too short for publication.",
        })
        recommendations.append("Expand the draft with a clear lead, context, evidence, and implications.")

    required_sections = [
        "Theme:",
        "Score:",
        "Article Draft:",
    ]
    missing_sections = [
        section for section in required_sections
        if section.lower() not in article_text.lower()
    ]
    if missing_sections:
        issues.append({
            "severity": "major",
            "message": f"Draft is missing required sections: {', '.join(missing_sections)}",
        })
        recommendations.append("Keep the generated article structured with theme, score, and article body sections.")

    source_signals = [
        "http://",
        "https://",
        "source:",
        "according to",
        "reported",
        "study",
        "paper",
    ]
    if not any(signal in article_text.lower() for signal in source_signals):
        issues.append({
            "severity": "major",
            "message": "Draft does not cite or mention supporting sources.",
        })
        recommendations.append("Add source-backed evidence before publication.")

    if "example.com" in article_text.lower():
        issues.append({
            "severity": "critical",
            "message": "Draft contains placeholder source material.",
        })
        recommendations.append("Replace placeholder sources with real source references.")

    if "continues an ongoing trend" in article_text.lower():
        issues.append({
            "severity": "minor",
            "message": "Draft uses generic placeholder language.",
        })
        recommendations.append("Replace generic phrasing with specific developments and concrete stakes.")

    approved = not any(
        issue["severity"] in {"critical", "major"}
        for issue in issues
    )

    critique = {
        "approved": approved,
        "word_count": word_count,
        "issues": issues,
        "recommendations": recommendations,
    }

    if approved:
        return None

    return {
        "publication": {
            "success": False,
            "status": "needs-revision",
            "content": article_text,
        },
        "critique": critique,
        "followups": recommendations,
    }

def publish_article(article):
    return {
        "success": True,
        "status": "draft-only",
        "content": article,
    }


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
