try:
    from src.dspy_gemini import dumps, parse_json_output, predict_json
except ImportError:
    from dspy_gemini import dumps, parse_json_output, predict_json
import re


SCHEMA = "omegaclaw.article_metadata.v1"
MIN_METADATA_CHARS = 320
MIN_METADATA_SENTENCES = 3


def extract_metadata(text):
    try:
        return dumps(article_metadata(text))
    except Exception as exc:
        return dumps(_error_response(str(text), exc))


def article_metadata(text):
    text = str(text)
    if _should_skip_metadata(text):
        return _skipped_metadata(text)

    raw = _run_metadata_dspy(text)
    parsed = parse_json_output(raw)
    return _validate_article_metadata(parsed, text)


def _run_metadata_dspy(text):
    import dspy

    class ArticleMetadataSignature(dspy.Signature):
        """
        Extract one article-level metadata profile for logical inference.

        Return one JSON object only. Do not include markdown.
        Do not extract page numbers, footers, headers, layout, or OCR artifacts.

        Required schema:
        {
          "schema": "omegaclaw.article_metadata.v1",
          "input_length": 0,
          "article": {
            "title": "",
            "domain": "general | artificial_intelligence | technology | health | climate_environment | finance_economics | policy_governance | science_research | education | other",
            "primary_topic": "",
            "topics": [{"label": "", "score": 0.0}],
            "sentiment": {"label": "positive | negative | neutral | mixed", "score": 0.0, "rationale": ""},
            "tone": [{"label": "analytical | critical | optimistic | urgent | speculative | persuasive | neutral | other", "score": 0.0}],
            "style": "academic | news_report | opinion | technical | policy_brief | marketing | expository | narrative | other",
            "scope": "global | national | local | organization | individual_or_named_entity | general",
            "temporal_framing": {"frame": "past_oriented | current | future_oriented | mixed | timeless_or_unspecified", "years": []},
            "main_claim": "",
            "claim_type": "descriptive | causal | predictive | prescriptive | evaluative | mixed",
            "evidence_quality": {"label": "high | moderate | low", "score": 0.0, "evidence_types": [], "rationale": ""},
            "suggested_truth_confidence": 0.0
          }
        }

        Interpret the text as a whole article. The fields describe the article overall:
        this article's topic, this article's sentiment, this article's evidence quality, and so on.
        Only profile the complete supplied article/corpus, not isolated phrases or chat messages.
        Evidence quality should reflect source citation, data, methodology, balance, uncertainty,
        and whether claims are mostly asserted without support. suggested_truth_confidence should be
        a conservative prior for atomizing this article's claims into NAL/PLN truth values.
        """

        text = dspy.InputField(desc="Article text to profile.")
        output_json = dspy.OutputField(desc="JSON object matching the article metadata schema exactly.")

    return predict_json(ArticleMetadataSignature, text=text)


def _should_skip_metadata(text):
    stripped = text.strip()
    if len(stripped) < MIN_METADATA_CHARS:
        return True
    sentence_count = sum(1 for part in re.split(r"[.!?]+", stripped) if part.strip())
    return sentence_count < MIN_METADATA_SENTENCES


def _skipped_metadata(text):
    return {
        "schema": SCHEMA,
        "input_length": len(text),
        "skipped": True,
        "reason": "input_too_short_for_article_metadata",
        "minimum": {
            "characters": MIN_METADATA_CHARS,
            "sentences": MIN_METADATA_SENTENCES,
        },
        "article": {
            "title": "",
            "domain": "general",
            "primary_topic": "",
            "topics": [],
            "sentiment": {"label": "neutral", "score": 0.0, "rationale": "Skipped: input is not article-length."},
            "tone": [{"label": "neutral", "score": 0.0}],
            "style": "other",
            "scope": "general",
            "temporal_framing": {"frame": "timeless_or_unspecified", "years": []},
            "main_claim": "",
            "claim_type": "descriptive",
            "evidence_quality": {
                "label": "low",
                "score": 0.0,
                "evidence_types": [],
                "rationale": "Skipped: metadata extraction is only useful for article-length text.",
            },
            "suggested_truth_confidence": 0.0,
        },
    }


def _validate_article_metadata(data, original_text):
    if not isinstance(data, dict):
        raise ValueError("Metadata extractor returned non-object JSON.")

    data["schema"] = SCHEMA
    data["input_length"] = len(original_text)
    article = data.get("article")
    if not isinstance(article, dict):
        raise ValueError("Metadata output must contain an article object.")

    article.setdefault("title", "")
    article.setdefault("domain", "general")
    article.setdefault("primary_topic", "general")
    article.setdefault("topics", [])
    article.setdefault("sentiment", {"label": "neutral", "score": 0.0, "rationale": ""})
    article.setdefault("tone", [{"label": "neutral", "score": 0.0}])
    article.setdefault("style", "expository")
    article.setdefault("scope", "general")
    article.setdefault("temporal_framing", {"frame": "timeless_or_unspecified", "years": []})
    article.setdefault("main_claim", "")
    article.setdefault("claim_type", "descriptive")
    article.setdefault(
        "evidence_quality",
        {"label": "low", "score": 0.0, "evidence_types": [], "rationale": ""},
    )
    article.setdefault("suggested_truth_confidence", 0.0)

    _validate_score(article["sentiment"], "sentiment")
    for tone in article["tone"]:
        if not isinstance(tone, dict):
            raise ValueError("Each tone entry must be an object.")
        _validate_score(tone, "tone")
    for topic in article["topics"]:
        if not isinstance(topic, dict):
            raise ValueError("Each topic entry must be an object.")
        _validate_score(topic, "topic")
    _validate_score(article["evidence_quality"], "evidence_quality")

    confidence = article["suggested_truth_confidence"]
    if not isinstance(confidence, (int, float)) or confidence < 0.0 or confidence > 1.0:
        raise ValueError("suggested_truth_confidence must be numeric between 0 and 1.")

    return data


def _validate_score(obj, name):
    score = obj.get("score", 0.0)
    if not isinstance(score, (int, float)):
        raise ValueError(f"{name} score must be numeric.")


def _error_response(text, exc):
    data = _skipped_metadata(text)
    data["skipped"] = False
    data["error"] = {
        "type": type(exc).__name__,
        "message": str(exc),
    }
    data["reason"] = "metadata_extraction_failed"
    return data
