import json

from src import semantic_parser


def test_semantic_parse_accepts_dspy_json(monkeypatch):
    llm_output = {
        "schema": "omegaclaw.semantic_parser.v3",
        "input": "Pingu has feathers. All feathered things are birds. Is Pingu a bird?",
        "workspace": {
            "architecture": "seven_stage_elaboration_workspace",
            "stages": [
                {
                    "name": "normalization",
                    "status": "selected",
                    "hypotheses": [
                        {
                            "value": "Pingu has feathers. All feathered things are birds. Is Pingu a bird?",
                            "confidence": 0.99,
                            "evidence": "input is already normalized",
                        }
                    ],
                    "selected": "input is already normalized",
                },
                {
                    "name": "semantic_binding",
                    "status": "selected",
                    "hypotheses": [
                        {
                            "value": "Bind feathered as an IntSet property and bird as an inheritance target.",
                            "confidence": 0.86,
                            "evidence": "matches property rule plus fact plus query",
                            "depends_on": ["logical_form"],
                        }
                    ],
                    "selected": "PLN property modus ponens",
                },
            ],
        },
        "items": [
            {
                "kind": "fact",
                "source": "Pingu has feathers.",
                "logic": "property",
                "slots": {"subject": "pingu", "property": "feathered"},
                "truth": {"frequency": 1.0, "confidence": 0.78},
                "nal": "((--> pingu ([] feathered)) (stv 1.0 0.78))",
                "pln": "((Inheritance pingu (IntSet feathered)) (stv 1.0 0.78))",
            },
            {
                "kind": "rule",
                "source": "All feathered things are birds.",
                "logic": "implication",
                "premise": {"subject": "$1", "property": "feathered"},
                "conclusion": {"subject": "$1", "object": "bird"},
                "truth": {"frequency": 1.0, "confidence": 0.74},
                "nal": "((==> (--> $1 ([] feathered)) (--> $1 bird)) (stv 1.0 0.74))",
                "pln": "((Implication (Inheritance $1 (IntSet feathered)) (Inheritance $1 bird)) (stv 1.0 0.74))",
            },
            {
                "kind": "query",
                "source": "Is Pingu a bird?",
                "logic": "inheritance",
                "target": {"subject": "pingu", "object": "bird"},
                "nal": "(--> pingu bird)",
                "pln": "(Inheritance pingu bird)",
            },
            {
                "kind": "fact",
                "source": "Anna is Bob's friend.",
                "logic": "relation",
                "slots": {"subject": "anna", "object": "bob", "predicate": "friend"},
                "truth": {"frequency": 1.0, "confidence": 0.78},
                "nal": "((--> (× anna bob) friend) (stv 1.0 0.78))",
                "pln": "((Inheritance (Product anna bob) friend) (stv 1.0 0.78))",
            },
        ],
    }
    monkeypatch.setattr(semantic_parser, "_run_semantic_dspy", lambda text: json.dumps(llm_output))

    parsed = semantic_parser.semantic_parse(llm_output["input"])

    assert parsed["schema"] == "omegaclaw.semantic_parser.v3"
    assert parsed["workspace"]["architecture"] == "seven_stage_elaboration_workspace"
    assert parsed["workspace"]["trace_mode"] == "compact"
    assert parsed["workspace"]["stages"] == [
        "normalization",
        "pos_tagging",
        "pos_coherence",
        "logical_form",
        "reference_resolution",
        "time_modality",
        "semantic_binding",
    ]
    assert parsed["workspace"]["reported"][0]["status"] == "selected"
    assert parsed["workspace"]["reported"][-1]["selected"] == "PLN property modus ponens"
    assert parsed["summary"] == {"facts": 2, "rules": 1, "queries": 1}
    assert parsed["items"][1]["premise"] == {"subject": "$1", "property": "feathered"}
    assert parsed["items"][2]["pln"] == "(Inheritance pingu bird)"
    assert "metta" not in parsed
    assert "skill_calls" not in parsed


def test_atomize_returns_pretty_json(monkeypatch):
    monkeypatch.setattr(
        semantic_parser,
        "_run_semantic_dspy",
        lambda text: json.dumps({
            "items": [
                {
                    "kind": "fact",
                    "source": text,
                    "logic": "inheritance",
                    "truth": {"frequency": 1.0, "confidence": 0.7},
                    "nal": "((--> socrates human) (stv 1.0 0.7))",
                    "pln": "((Inheritance socrates human) (stv 1.0 0.7))",
                }
            ]
        }),
    )

    parsed = json.loads(semantic_parser.atomize("Socrates is human."))

    assert parsed["summary"] == {"facts": 1, "rules": 0, "queries": 0}
    assert parsed["items"][0]["truth"]["confidence"] == 0.7
    assert parsed["schema"] == "omegaclaw.semantic_parser.v3"
    assert len(parsed["workspace"]["stages"]) == 7
    assert parsed["workspace"]["reported"] == []
    assert "metta" not in parsed
    assert "skill_calls" not in parsed


def test_atomize_returns_error_json_when_dspy_fails(monkeypatch):
    def fail(text):
        raise RuntimeError("Gemini API key is required; set GEMINI_API_KEY.")

    monkeypatch.setattr(semantic_parser, "_run_semantic_dspy", fail)

    parsed = json.loads(semantic_parser.atomize("If an article has small length it has high engagement."))

    assert parsed["items"] == []
    assert parsed["schema"] == "omegaclaw.semantic_parser.v3"
    assert len(parsed["workspace"]["stages"]) == 7
    assert parsed["workspace"]["reported"] == []
    assert "metta" not in parsed
    assert "skill_calls" not in parsed
    assert parsed["error"]["type"] == "RuntimeError"
    assert "Gemini API key" in parsed["error"]["message"]


def test_semantic_parse_rejects_invalid_item_kind(monkeypatch):
    monkeypatch.setattr(
        semantic_parser,
        "_run_semantic_dspy",
        lambda text: json.dumps({"items": [{"kind": "note"}]}),
    )

    try:
        semantic_parser.semantic_parse("bad")
    except ValueError as exc:
        assert "Invalid semantic parser item kind" in str(exc)
    else:
        raise AssertionError("Expected invalid item kind to fail")


def test_semantic_parse_uses_workspace_for_stage_reports(monkeypatch):
    monkeypatch.setattr(
        semantic_parser,
        "_run_semantic_dspy",
        lambda text: json.dumps({
            "stages": [
                {
                    "name": "logical_form",
                    "status": "ambiguous",
                    "hypotheses": ["exists x human(x)"],
                    "selected": "exists x human(x)",
                }
            ],
            "items": [
                {
                    "kind": "fact",
                    "source": text,
                    "logic": "inheritance",
                    "truth": {"frequency": 1.0, "confidence": 0.7},
                    "nal": "((--> socrates human) (stv 1.0 0.7))",
                    "pln": "((Inheritance socrates human) (stv 1.0 0.7))",
                }
            ],
        }),
    )

    parsed = semantic_parser.semantic_parse("Socrates is human.")

    assert "stages" not in parsed
    assert parsed["workspace"]["reported"] == []


def test_semantic_parse_accepts_lib_nal_conjunction_and_lib_pln_nested_implication(monkeypatch):
    monkeypatch.setattr(
        semantic_parser,
        "_run_semantic_dspy",
        lambda text: json.dumps({
            "items": [
                {
                    "kind": "rule",
                    "source": "If an article has small length and has AI topic it will have high engagement.",
                    "logic": "implication",
                    "truth": {"frequency": 1.0, "confidence": 0.75},
                    "nal": "((==> (∧ (--> $art ([] short_length)) (--> $art ([] ai_topic))) (--> $art ([] high_engagement))) (stv 1.0 0.75))",
                    "pln": "((Implication (Inheritance $art (IntSet short_length)) (Implication (Inheritance $art (IntSet ai_topic)) (Inheritance $art (IntSet high_engagement)))) (stv 1.0 0.75))",
                },
                {
                    "kind": "fact",
                    "source": "article with small length",
                    "logic": "property",
                    "truth": {"frequency": 1.0, "confidence": 0.75},
                    "nal": "((--> planned_article ([] short_length)) (stv 1.0 0.75))",
                    "pln": "((Inheritance planned_article (IntSet short_length)) (stv 1.0 0.75))",
                },
                {
                    "kind": "fact",
                    "source": "article with AI topic",
                    "logic": "property",
                    "truth": {"frequency": 1.0, "confidence": 0.75},
                    "nal": "((--> planned_article ([] ai_topic)) (stv 1.0 0.75))",
                    "pln": "((Inheritance planned_article (IntSet ai_topic)) (stv 1.0 0.75))",
                },
                {
                    "kind": "query",
                    "source": "will it be engaging?",
                    "logic": "property",
                    "nal": "(--> planned_article ([] high_engagement))",
                    "pln": "(Inheritance planned_article (IntSet high_engagement))",
                },
            ],
        }),
    )

    parsed = semantic_parser.semantic_parse(
        "If an article has small length and has AI topic it will have high engagement."
    )

    assert parsed["summary"] == {"facts": 2, "rules": 1, "queries": 1}
    assert "(∧ " in parsed["items"][0]["nal"]
    assert "(Implication (Inheritance $art" in parsed["items"][0]["pln"]
    assert "skill_calls" not in parsed


def test_semantic_parse_drops_skill_calls_from_llm_output(monkeypatch):
    monkeypatch.setattr(
        semantic_parser,
        "_run_semantic_dspy",
        lambda text: json.dumps({
            "items": [
                {
                    "kind": "rule",
                    "source": text,
                    "logic": "implication",
                    "truth": {"frequency": 1.0, "confidence": 0.7},
                    "nal": "((==> (--> $1 ([] feathered)) (--> $1 bird)) (stv 1.0 0.7))",
                    "pln": "((Implication (Inheritance $1 (IntSet feathered)) (Inheritance $1 bird)) (stv 1.0 0.7))",
                }
            ],
            "skill_calls": [
                {
                    "skill": "metta",
                    "engine": "pln",
                    "argument": "(|~ ((Implication (Inheritance $1 (IntSet feathered)) (Inheritance $1 bird)) (stv 1.0 0.7)))",
                }
            ],
        }),
    )

    parsed = semantic_parser.semantic_parse("All feathered things are birds.")

    assert parsed["summary"] == {"facts": 0, "rules": 1, "queries": 0}
    assert "skill_calls" not in parsed


def test_semantic_parse_rejects_pln_and_in_item(monkeypatch):
    monkeypatch.setattr(
        semantic_parser,
        "_run_semantic_dspy",
        lambda text: json.dumps({
            "items": [
                {
                    "kind": "rule",
                    "source": text,
                    "logic": "implication",
                    "truth": {"frequency": 0.9, "confidence": 0.7},
                    "nal": "((==> (∧ (--> $1 ([] short_length)) (--> $1 ([] ai_topic))) (--> $1 ([] high_engagement))) (stv 0.9 0.7))",
                    "pln": "((Implication (And (Inheritance $1 (IntSet short_length)) (Inheritance $1 (IntSet ai_topic))) (Inheritance $1 (IntSet high_engagement))) (stv 0.9 0.7))",
                }
            ],
        }),
    )

    try:
        semantic_parser.semantic_parse("If an article is short and about AI, it has high engagement.")
    except ValueError as exc:
        assert "not consumed by lib_pln.metta" in str(exc)
    else:
        raise AssertionError("Expected PLN And in item to fail")


def test_semantic_parse_rejects_legacy_metta_field(monkeypatch):
    expression = "(|~ ((Implication (Inheritance $1 (IntSet feathered)) (Inheritance $1 bird)) (stv 1.0 0.7)) ((Inheritance pingu (IntSet feathered)) (stv 1.0 0.8)))"
    monkeypatch.setattr(
        semantic_parser,
        "_run_semantic_dspy",
        lambda text: json.dumps({
            "items": [
                {
                    "kind": "fact",
                    "source": text,
                    "logic": "property",
                    "truth": {"frequency": 1.0, "confidence": 0.8},
                    "nal": "((--> pingu ([] feathered)) (stv 1.0 0.8))",
                    "pln": "((Inheritance pingu (IntSet feathered)) (stv 1.0 0.8))",
                }
            ],
            "metta": {
                "pln": {
                    "steps": [
                        {
                            "expression": expression,
                            "uses": ["items[1].pln", "items[0].pln"],
                        }
                    ]
                }
            },
        }),
    )

    try:
        semantic_parser.semantic_parse("Pingu has feathers.")
    except ValueError as exc:
        assert "top-level metta is not supported" in str(exc)
    else:
        raise AssertionError("Expected legacy metta field to fail")
