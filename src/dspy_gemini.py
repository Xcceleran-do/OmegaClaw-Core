import json
import os
import re


DEFAULT_GEMINI_MODEL = "gemini/gemini-2.5-flash"
DEFAULT_TEMPERATURE = 0.0


def get_lm():
    try:
        import dspy
    except ImportError as exc:
        raise RuntimeError("DSPy is required for atomize/extract-metadata; install the dspy package.") from exc

    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        raise RuntimeError("Gemini API key is required; set GEMINI_API_KEY or GOOGLE_API_KEY.")

    model = os.environ.get("GEMINI_MODEL", DEFAULT_GEMINI_MODEL)
    temperature = float(os.environ.get("GEMINI_TEMPERATURE", DEFAULT_TEMPERATURE))
    return dspy.LM(model, api_key=api_key, temperature=temperature)


def predict_json(signature_cls, **inputs):
    try:
        import dspy
    except ImportError as exc:
        raise RuntimeError("DSPy is required for atomize/extract-metadata; install the dspy package.") from exc

    lm = get_lm()
    predictor = dspy.Predict(signature_cls)
    adapter = dspy.JSONAdapter()
    with dspy.context(lm=lm, adapter=adapter):
        result = predictor(**inputs)
    return getattr(result, "output_json", result)


def parse_json_output(raw):
    if isinstance(raw, dict):
        return raw
    if hasattr(raw, "toDict"):
        raw = raw.toDict()
        if isinstance(raw, dict):
            return raw
    if not isinstance(raw, str):
        raw = str(raw)

    text = raw.strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL | re.IGNORECASE)
    if fenced:
        text = fenced.group(1).strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            return json.loads(text[start:end + 1])
        raise


def dumps(data):
    return json.dumps(data, ensure_ascii=False, indent=2)
