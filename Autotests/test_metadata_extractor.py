import json

from src import metadata_extractor


ARTICLE_TEXT = (
    "Climate Policy Cuts Industrial Emissions. According to a 2025 agency report, "
    "carbon emissions from heavy industry fell 12 percent after factories adopted "
    "renewable energy contracts. The article argues that targeted regulation can "
    "reduce pollution without lowering output. However, the report notes uncertainty "
    "about whether smaller firms can afford the transition by 2030."
)


def test_article_metadata_accepts_dspy_json(monkeypatch):
    llm_output = {
        "schema": "omegaclaw.article_metadata.v1",
        "input_length": 0,
        "article": {
            "title": "Climate Policy Cuts Industrial Emissions",
            "domain": "climate_environment",
            "primary_topic": "industrial emissions policy",
            "topics": [
                {"label": "industrial emissions", "score": 0.93},
                {"label": "renewable energy contracts", "score": 0.68},
            ],
            "sentiment": {"label": "mixed", "score": -0.12, "rationale": "Benefits plus affordability risk."},
            "tone": [{"label": "analytical", "score": 0.82}],
            "style": "policy_brief",
            "scope": "organization",
            "temporal_framing": {"frame": "mixed", "years": ["2025", "2030"]},
            "main_claim": "Targeted regulation can reduce pollution without lowering output.",
            "claim_type": "causal",
            "evidence_quality": {
                "label": "high",
                "score": 0.83,
                "evidence_types": ["agency report", "statistics", "uncertainty note"],
                "rationale": "Uses dated report, quantitative reduction, and caveat.",
            },
            "suggested_truth_confidence": 0.82,
        },
    }
    monkeypatch.setattr(metadata_extractor, "_run_metadata_dspy", lambda text: json.dumps(llm_output))

    parsed = metadata_extractor.article_metadata(ARTICLE_TEXT)

    assert parsed["schema"] == "omegaclaw.article_metadata.v1"
    assert parsed["input_length"] == len(ARTICLE_TEXT)
    assert parsed["article"]["domain"] == "climate_environment"
    assert parsed["article"]["evidence_quality"]["label"] == "high"
    assert parsed["article"]["suggested_truth_confidence"] == 0.82


def test_extract_metadata_returns_pretty_json(monkeypatch):
    monkeypatch.setattr(
        metadata_extractor,
        "_run_metadata_dspy",
        lambda text: json.dumps({
            "article": {
                "title": "Opinion",
                "domain": "policy_governance",
                "primary_topic": "urban policy",
                "topics": [{"label": "urban policy", "score": 0.9}],
                "sentiment": {"label": "negative", "score": -0.3, "rationale": "Risk-focused."},
                "tone": [{"label": "persuasive", "score": 0.8}],
                "style": "opinion",
                "scope": "local",
                "temporal_framing": {"frame": "current", "years": []},
                "main_claim": "Cities should ban private cars downtown.",
                "claim_type": "prescriptive",
                "evidence_quality": {
                    "label": "moderate",
                    "score": 0.58,
                    "evidence_types": ["examples"],
                    "rationale": "Examples, not controlled evidence.",
                },
                "suggested_truth_confidence": 0.62,
            }
        }),
    )

    parsed = json.loads(metadata_extractor.extract_metadata(ARTICLE_TEXT))

    assert parsed["article"]["style"] == "opinion"
    assert parsed["article"]["scope"] == "local"
    assert parsed["article"]["claim_type"] == "prescriptive"


def test_extract_metadata_returns_error_json_when_dspy_fails(monkeypatch):
    def fail(text):
        raise RuntimeError("Gemini API key is required; set GEMINI_API_KEY.")

    monkeypatch.setattr(metadata_extractor, "_run_metadata_dspy", fail)

    parsed = json.loads(metadata_extractor.extract_metadata(ARTICLE_TEXT))

    assert parsed["reason"] == "metadata_extraction_failed"
    assert parsed["error"]["type"] == "RuntimeError"
    assert "Gemini API key" in parsed["error"]["message"]


def test_article_metadata_rejects_bad_confidence(monkeypatch):
    monkeypatch.setattr(
        metadata_extractor,
        "_run_metadata_dspy",
        lambda text: json.dumps({
            "article": {
                "sentiment": {"label": "neutral", "score": 0.0},
                "tone": [{"label": "neutral", "score": 0.0}],
                "topics": [],
                "evidence_quality": {"label": "low", "score": 0.2},
                "suggested_truth_confidence": 1.5,
            }
        }),
    )

    try:
        metadata_extractor.article_metadata(ARTICLE_TEXT)
    except ValueError as exc:
        assert "suggested_truth_confidence" in str(exc)
    else:
        raise AssertionError("Expected bad confidence to fail")


def test_article_metadata_skips_small_inputs_without_dspy(monkeypatch):
    def fail_if_called(text):
        raise AssertionError("DSPy should not run for tiny metadata input")

    monkeypatch.setattr(metadata_extractor, "_run_metadata_dspy", fail_if_called)

    parsed = metadata_extractor.article_metadata("short claim")

    assert parsed["skipped"] is True
    assert parsed["reason"] == "input_too_short_for_article_metadata"
    assert parsed["article"]["evidence_quality"]["score"] == 0.0
