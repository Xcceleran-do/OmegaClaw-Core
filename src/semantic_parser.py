import re

try:
    from src.dspy_gemini import dumps, parse_json_output, predict_json
except ImportError:
    from dspy_gemini import dumps, parse_json_output, predict_json


SCHEMA = "omegaclaw.semantic_parser.v3"
WORKSPACE_ARCHITECTURE = "seven_stage_elaboration_workspace"
WORKSPACE_TRACE_MODE = "compact"
SEMANTIC_STAGES = (
    ("normalization", "Auto-spell-check, cleanup, and lexical normalization."),
    ("pos_tagging", "Ranked part-of-speech and token-role hypotheses."),
    ("pos_coherence", "Grammar/coherence checks over the POS hypotheses."),
    ("logical_form", "Logical-form candidates with quantification and roles."),
    ("reference_resolution", "Anaphora, entity, and discourse referent binding."),
    ("time_modality", "Tense, temporal frame, modality, and hypothetical status."),
    ("semantic_binding", "Bind validated logical forms to OmegaClaw NAL/PLN atoms."),
)
STAGE_PURPOSES = {name: purpose for name, purpose in SEMANTIC_STAGES}
ALLOWED_LOGIC = {
    "inheritance",
    "property",
    "evaluation",
    "relation",
    "similarity",
    "implication",
    "unknown",
}
PLN_AND_RE = re.compile(r"\(And(?:\s|\))")


def atomize(text):
    try:
        return dumps(semantic_parse(text))
    except Exception as exc:
        return dumps(_error_response(str(text), exc))


def semantic_parse(text):
    raw = _run_semantic_dspy(str(text))
    parsed = parse_json_output(raw)
    return _validate_semantic_parse(parsed, str(text))


def _run_semantic_dspy(text):
    import dspy

    class SemanticParserSignature(dspy.Signature):
        """
        Convert natural language into OmegaClaw reasoning atoms.

        Return one JSON object only. Do not include markdown.
        Do not extract topic, tone, sentiment, style, or article metadata here.

        Return an empty items list for greetings, chit-chat, commands without claims,
        or text that does not contain explicit facts, rules, or questions.

        Required schema:
        {
          "schema": "omegaclaw.semantic_parser.v3",
          "input": "<original text>",
          "workspace": "<optional compact diagnostics only; omit when there are no repairs or unresolved ambiguities>",
          "items": [
            {
              "kind": "fact | rule | query",
              "source": "<exact source span>",
              "logic": "inheritance | property | relation | evaluation | similarity | implication | unknown",
              "truth": {"frequency": 1.0, "confidence": 0.0},
              "slots": {},
              "premise": {},
              "conclusion": {},
              "target": {},
              "nal": "<NAL atom/premise rendering; not a skill call>",
              "pln": "<PLN atom/premise rendering; not a skill call>"
            }
          ],
          "summary": {"facts": 0, "rules": 0, "queries": 0}
        }

        Architecture rules:
        Treat parsing as a staged, provisional workspace, not a single direct translation, but keep
        the JSON cost low. Do not narrate all seven stages. The runtime adds the compact stage
        skeleton automatically. Include workspace diagnostics only when an ambiguity, repair, or
        unresolved issue materially affects the final binding.
        The architecture stages are: normalization, pos_tagging, pos_coherence, logical_form,
        reference_resolution, time_modality, semantic_binding.
        Final items must come only from the semantic_binding stage's selected reasoner-ready
        interpretation.
        Do not export unresolved or merely grammatical hypotheses as final items.

        Target only the atom shapes consumed by lib_nal.metta and lib_pln.metta. Do not
        invent compatibility schemas, alternate operators, or executable metta calls.
        Use lower_snake_case symbols. Use MeTTa variables only in rules, and keep each
        variable consistent within that rule.
        Never use quoted symbols, escaped quotes, Variable, or string literals inside NAL/PLN atoms.
        Use Concept only inside Evaluation/List/Member-style PLN predicate forms and their supporting
        Inheritance premises, not around ordinary Inheritance terms or variables.
        Facts and rules must include truth values. Queries should not include truth values.
        items[].nal and items[].pln are atom renderings only. They are not skill calls and
        must not be wrapped in metta, |~, |-, |~pln, or |-nal by this parser.
        Make each item atomic: one fact, one rule, or one query per item.
        For multi-condition PLN rules, use nested Implication forms rather than And/conjunction.
        Never emit (And ...) in PLN items; lib_pln.metta does not consume that constructor.
        Each nested antecedent is consumed by a separate PLN |~ step.
        Keep exact source spans short and grounded in the input text.
        Do not invent facts, entities, or conclusions that are not stated or directly queried.

        NAL forms consumed by lib_nal.metta:
        - inheritance: (--> subject object)
        - property/intensional set: (--> subject ([] property))
        - extensional/intensional set terms: (ExtSet x), (IntSet x), ({} x), ([] x)
        - binary relation product: (--> (× subject object) predicate)
        - similarity: (<-> left right)
        - set operators: (∪ left right), (∩ left right), (~ left right), (− left right)
        - negation: (¬ term)
        - conjunction/disjunction: (∧ left right), (∨ left right)
        - implication rule: (==> premise conclusion)

        PLN link forms consumed by lib_pln.metta:
        - inheritance: (Inheritance subject object)
        - implication rule: (Implication premise conclusion)
        - similarity links: (Similarity left right), (IntentionalSimilarity left right), (ExtensionalSimilarity left right)
        - equivalence: (Equivalence left right)
        - negation: (Not term)
        - membership: (Member instance class)
        - predicate evaluation: (Evaluation (Predicate predicate) (List (Concept subject)))
        - binary predicate evaluation: (Evaluation (Predicate predicate) (List (Concept subject) (Concept object)))
        - evaluation support inheritance: (Inheritance (Concept subject) (Concept class))
        Terms such as (IntSet property) and (Product subject object) may appear as ordinary
        arguments inside these links, but lib_pln.metta has no special rule for IntSet or Product.
        Use Evaluation/Predicate/List/Concept when you need the predicate-inheritance rules in
        lib_pln.metta.

        Wrap fact/rule renderings as ((atom) (stv frequency confidence)).
        Correct: ((Inheritance pingu (IntSet feathered)) (stv 1.0 0.78))
        Incorrect: (stv 1.0 0.78 (Inheritance pingu (IntSet feathered)))
        Queries are bare atoms without truth values.
        Preserve uncertainty from the source: direct assertions usually have confidence around 0.65-0.85;
        weak or analogical statements should be lower; externally grounded claims can be higher.

        Examples:
        Input: "Pingu has feathers. All feathered things are birds. Is Pingu a bird?"
        Output items: property fact for pingu/feathered, implication rule feathered -> bird, query pingu -> bird.
        PLN fact: ((Inheritance pingu (IntSet feathered)) (stv 1.0 0.78))
        PLN rule: ((Implication (Inheritance $1 (IntSet feathered)) (Inheritance $1 bird)) (stv 1.0 0.74))
        PLN query: (Inheritance pingu bird)

        Input: "If an article has small length and has AI topic it will have high engagement. I am about to write an article with AI topic with small length. Do you think it will be engaging?"
        Output items: rule article small_length -> (ai_topic -> high_engagement); fact planned_article small_length; fact planned_article ai_topic; query planned_article high_engagement.
        PLN rule form: ((Implication (Inheritance $1 (IntSet small_length)) (Implication (Inheritance $1 (IntSet ai_topic)) (Inheritance $1 (IntSet high_engagement)))) (stv 1.0 0.75))
        PLN facts/query: ((Inheritance planned_article (IntSet small_length)) (stv 1.0 0.75)); ((Inheritance planned_article (IntSet ai_topic)) (stv 1.0 0.75)); query (Inheritance planned_article (IntSet high_engagement)).

        Input: "thanks ok"
        Output: schema v3, the seven workspace stages marked skipped or selected with no
        semantic_binding export, items [], summary {"facts": 0, "rules": 0, "queries": 0}.
        """

        text = dspy.InputField(desc="Natural language to atomize.")
        output_json = dspy.OutputField(desc="JSON object matching the schema exactly.")

    return predict_json(SemanticParserSignature, text=text)


def _validate_semantic_parse(data, original_text):
    if not isinstance(data, dict):
        raise ValueError("Semantic parser returned non-object JSON.")

    data["schema"] = SCHEMA
    data.setdefault("input", original_text)
    if "metta" in data:
        raise ValueError("Semantic parser output must contain atoms only; top-level metta is not supported.")

    data["workspace"] = _validate_workspace(data.get("workspace"))
    data.pop("stages", None)
    data.pop("skill_calls", None)
    items = data.get("items")
    if not isinstance(items, list):
        raise ValueError("Semantic parser output must contain an items list.")

    for item in items:
        if not isinstance(item, dict):
            raise ValueError("Each semantic parser item must be an object.")
        if item.get("kind") not in {"fact", "rule", "query"}:
            raise ValueError(f"Invalid semantic parser item kind: {item.get('kind')!r}")
        item.setdefault("source", "")
        item.setdefault("logic", "unknown")
        if item["logic"] not in ALLOWED_LOGIC:
            raise ValueError(f"Invalid semantic parser item logic: {item['logic']!r}")
        item.setdefault("nal", "")
        item.setdefault("pln", "")
        if item["logic"] != "unknown" and (not item["nal"].strip() or not item["pln"].strip()):
            raise ValueError("Recognized semantic parser items must include NAL and PLN renderings.")
        _validate_item_renderings(item)
        if item["kind"] in {"fact", "rule"}:
            truth = item.get("truth")
            if not isinstance(truth, dict):
                raise ValueError("Fact/rule items must include a truth object.")
            _validate_truth(truth)

    data["summary"] = {
        "facts": sum(1 for item in items if item["kind"] == "fact"),
        "rules": sum(1 for item in items if item["kind"] == "rule"),
        "queries": sum(1 for item in items if item["kind"] == "query"),
    }
    return data


def _validate_workspace(workspace):
    if not isinstance(workspace, dict):
        workspace = {}

    stages = workspace.get("stages")
    if not isinstance(stages, list):
        stages = []

    by_name = {}
    for stage in stages:
        normalized = _validate_workspace_stage(stage)
        name = normalized["name"]
        if name in STAGE_PURPOSES and name not in by_name:
            by_name[name] = normalized

    reported = [by_name[name] for name, _ in SEMANTIC_STAGES if name in by_name]

    return {
        "architecture": str(workspace.get("architecture") or WORKSPACE_ARCHITECTURE),
        "trace_mode": str(workspace.get("trace_mode") or WORKSPACE_TRACE_MODE),
        "stages": [name for name, _ in SEMANTIC_STAGES],
        "reported": reported,
        "repairs": _validate_string_list(workspace.get("repairs")),
        "unresolved": _validate_string_list(workspace.get("unresolved")),
    }


def _validate_workspace_stage(stage):
    if not isinstance(stage, dict):
        stage = {}

    name = str(stage.get("name", "")).strip()
    if name not in STAGE_PURPOSES:
        name = ""
    status = str(stage.get("status", "")).strip() or "selected"
    return {
        "name": name,
        "status": status,
        "hypotheses": _validate_hypotheses(stage.get("hypotheses")),
        "selected": str(stage.get("selected", "")),
        "repairs": _validate_string_list(stage.get("repairs")),
    }


def _validate_hypotheses(hypotheses):
    if not isinstance(hypotheses, list):
        return []

    normalized = []
    for hypothesis in hypotheses:
        if isinstance(hypothesis, dict):
            confidence = hypothesis.get("confidence", 0.0)
            try:
                confidence = float(confidence)
            except (TypeError, ValueError):
                confidence = 0.0
            confidence = max(0.0, min(1.0, confidence))
            depends_on = hypothesis.get("depends_on", [])
            if not isinstance(depends_on, list):
                depends_on = []
            normalized.append({
                "value": str(hypothesis.get("value", "")),
                "confidence": confidence,
                "evidence": str(hypothesis.get("evidence", "")),
                "depends_on": [str(dep) for dep in depends_on],
            })
        else:
            normalized.append({
                "value": str(hypothesis),
                "confidence": 0.0,
                "evidence": "",
                "depends_on": [],
            })
    return normalized


def _validate_string_list(value):
    if not isinstance(value, list):
        return []
    return [str(item) for item in value]


def _validate_truth(truth):
    for field in ("frequency", "confidence"):
        value = truth.get(field)
        if not isinstance(value, (int, float)):
            raise ValueError(f"Truth field {field!r} must be numeric.")
        if value < 0.0 or value > 1.0:
            raise ValueError(f"Truth field {field!r} must be between 0 and 1.")


def _validate_item_renderings(item):
    _reject_unsupported_pln(str(item.get("pln", "")), "items[].pln")


def _reject_unsupported_pln(text, surface):
    if PLN_AND_RE.search(text):
        raise ValueError(
            f"{surface} uses PLN And, which is not consumed by lib_pln.metta; use nested Implication."
        )


def _error_response(text, exc):
    return {
        "schema": SCHEMA,
        "input": text,
        "workspace": _validate_workspace({}),
        "items": [],
        "summary": {"facts": 0, "rules": 0, "queries": 0},
        "error": {
            "type": type(exc).__name__,
            "message": str(exc),
        },
    }
