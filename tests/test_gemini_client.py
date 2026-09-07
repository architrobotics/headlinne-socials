"""The text model's fallback ladder.

`GEMINI_FALLBACK_MODELS` sat in config, in .env.example and in the generate
workflow's env block from the beginning, and nothing read it. Every text call
went to one model, retried that same model four times when it refused, and gave
up. Quota is counted per model, so a second model is a second daily allowance
rather than another go at an empty one - the reasoning the TTS client was
already built around and text never had.

What that cost was not an error message. It was a format quietly missing for
the day.
"""

from __future__ import annotations

import pytest

from headlinne.gemini import client as C


class _Response:
    def __init__(self, text):
        self.text = text


class _Models:
    """Stands in for `genai.Client().models`, per-model scripted behaviour."""

    def __init__(self, behaviour):
        self.behaviour = behaviour
        self.calls: list[str] = []

    def generate_content(self, *, model, contents, config):
        self.calls.append(model)
        outcome = self.behaviour.get(model, '{"ok": true}')
        if isinstance(outcome, Exception):
            raise outcome
        return _Response(outcome)


class _Fake:
    def __init__(self, behaviour):
        self.models = _Models(behaviour)


def _client(behaviour, monkeypatch, **kw):
    c = C.GeminiClient(api_key="test-key", **kw)
    c._client = _Fake(behaviour)
    monkeypatch.setattr(C.time, "sleep", lambda _s: None)
    return c


def test_a_rate_limited_model_hands_over_to_the_next_one(monkeypatch):
    c = _client({"a": Exception("429 RESOURCE_EXHAUSTED")}, monkeypatch,
                model="a", fallback_models=("b",))

    assert c.generate_json(system="s", prompt="p") == {"ok": True}
    assert c._client.models.calls == ["a", "b"], "it never tried the second model"


def test_the_run_stays_on_the_model_that_answered(monkeypatch):
    """A model that starts refusing keeps refusing, and a generate run makes
    eight or nine of these calls. Rediscovering the dead model every time
    spends a retry budget on a known answer."""
    c = _client({"a": Exception("429 RESOURCE_EXHAUSTED")}, monkeypatch,
                model="a", fallback_models=("b",))

    c.generate_json(system="s", prompt="p")
    c.generate_json(system="s", prompt="p")

    assert c._client.models.calls == ["a", "b", "b"]
    assert c.model == "b"


def test_a_real_error_does_not_walk_the_whole_ladder(monkeypatch):
    """A malformed request fails identically on every model, so trying each one
    turns a fast failure into a slow one."""
    c = _client({"a": Exception("400 INVALID_ARGUMENT")}, monkeypatch,
                model="a", fallback_models=("b", "c"))

    with pytest.raises(C.GeminiError):
        c.generate_json(system="s", prompt="p")

    assert c._client.models.calls == ["a"] * 4, "it should retry a, not fan out"


def test_an_unparseable_answer_is_nudged_rather_than_handed_to_another_model(
        monkeypatch):
    seen: list[str] = []

    class _Nudged(_Models):
        def generate_content(self, *, model, contents, config):
            seen.append(contents)
            self.calls.append(model)
            if len(self.calls) == 1:
                return _Response("here you go: not json at all")
            return _Response('{"ok": true}')

    c = C.GeminiClient(api_key="test-key", model="a", fallback_models=("b",))
    c._client = _Fake({})
    c._client.models = _Nudged({})
    monkeypatch.setattr(C.time, "sleep", lambda _s: None)

    assert c.generate_json(system="s", prompt="p") == {"ok": True}
    assert c._client.models.calls == ["a", "a"], "a parse error is not a quota error"
    assert "minified JSON only" in seen[1]


def test_the_retry_delay_the_server_offers_is_honoured(monkeypatch):
    waits: list[float] = []
    monkeypatch.setattr(C.time, "sleep", waits.append)
    c = C.GeminiClient(api_key="test-key", model="a", fallback_models=())
    c._client = _Fake({"a": Exception("429 {'retryDelay': '11s'}")})

    with pytest.raises(C.GeminiError):
        c.generate_json(system="s", prompt="p")

    assert waits and all(abs(w - 12.0) < 0.01 for w in waits), waits


def test_the_ladder_is_the_configured_one_and_holds_no_duplicates():
    c = C.GeminiClient(api_key="test-key", model="a",
                       fallback_models=("a", "b", "", "c"))
    assert c.models == ["a", "b", "c"]
