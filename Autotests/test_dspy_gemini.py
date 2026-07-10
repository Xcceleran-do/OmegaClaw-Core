import sys
import types

from src import dspy_gemini


def test_predict_json_uses_json_adapter(monkeypatch):
    observed = {}

    class FakeJSONAdapter:
        pass

    class FakePrediction:
        output_json = {"ok": True}

    class FakePredict:
        def __init__(self, signature_cls):
            observed["signature_cls"] = signature_cls

        def __call__(self, **inputs):
            observed["inputs"] = inputs
            return FakePrediction()

    class FakeContext:
        def __init__(self, **kwargs):
            observed["context"] = kwargs

        def __enter__(self):
            return None

        def __exit__(self, exc_type, exc, tb):
            return False

    fake_dspy = types.SimpleNamespace(
        JSONAdapter=FakeJSONAdapter,
        Predict=FakePredict,
        context=lambda **kwargs: FakeContext(**kwargs),
    )

    class FakeSignature:
        pass

    monkeypatch.setitem(sys.modules, "dspy", fake_dspy)
    monkeypatch.setattr(dspy_gemini, "get_lm", lambda: "fake-lm")

    result = dspy_gemini.predict_json(FakeSignature, text="hello")

    assert result == {"ok": True}
    assert observed["signature_cls"] is FakeSignature
    assert observed["inputs"] == {"text": "hello"}
    assert observed["context"]["lm"] == "fake-lm"
    assert isinstance(observed["context"]["adapter"], FakeJSONAdapter)


def test_parse_json_output_accepts_todict_object():
    class ToDict:
        def toDict(self):
            return {"ok": True}

    assert dspy_gemini.parse_json_output(ToDict()) == {"ok": True}
