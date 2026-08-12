"""Reel narration.

The guarantees that matter: the audio and the cuts stay in sync (because the
cuts are built from the audio, not guessed alongside it), and a speech failure
costs the reel its voice rather than costing the day its reel.

Nothing here talks to Gemini. A stub client returns silence of a known length,
which is exactly what the timing logic consumes.
"""

from __future__ import annotations

import tempfile
import wave
from pathlib import Path

from headlinne.config import (REEL_VOICE_EDUCATION, REEL_VOICE_LEAD_IN,
                              REEL_VOICE_NEWS, REEL_VOICE_TAIL,
                              TTS_SAMPLE_RATE)
from headlinne.gemini.tts import pcm_seconds, silence
from headlinne.models import Reel, ReelBeat
from headlinne.render import reel as reel_render
from headlinne.render.voice import (MIN_BEAT_SECONDS, VoiceTrack,
                                    build_voice_track, voice_for)


class StubVoice:
    """Returns silence of a fixed length per call, and records what it was asked."""

    def __init__(self, seconds: float = 3.0, fail_on: int | None = None):
        self.seconds = seconds
        self.fail_on = fail_on
        self.calls: list[tuple[str, str, str]] = []

    def synthesize(self, text, *, voice, style=""):
        self.calls.append((text, voice, style))
        if self.fail_on is not None and len(self.calls) == self.fail_on:
            return None
        return silence(self.seconds)


def _reel(kind: str = "news") -> Reel:
    return Reel(
        slot="reel_1" if kind == "news" else "reel_2", kind=kind,
        category="Technology", title="A title", hook="A hook",
        beats=[
            ReelBeat(role="hook", caption="A hook", detail="Under it.",
                     narration="Here is the spoken opening line."),
            ReelBeat(role="point", caption="What happened",
                     detail="A short supporting line.",
                     narration="Here is what actually happened today."),
            ReelBeat(role="graphic", caption="The chain", graphic="flow",
                     data={"steps": ["One", "Two", "Three"]},
                     narration="The chain runs in three steps."),
            ReelBeat(role="payoff", caption="That is the mechanism",
                     narration="And that is the whole mechanism."),
        ],
        caption="Caption.", hashtags=["Tech"],
        scheduled_time="2026-08-10T09:30:00+05:30")


# --------------------------------------------------------------------------- #
# Format arithmetic
# --------------------------------------------------------------------------- #
def test_pcm_length_is_arithmetic_not_a_probe():
    assert abs(pcm_seconds(silence(2.5)) - 2.5) < 0.01
    assert pcm_seconds(b"") == 0.0


def test_silence_is_whole_samples_at_the_expected_rate():
    pcm = silence(1.0)
    assert len(pcm) == TTS_SAMPLE_RATE * 2  # 16-bit mono


# --------------------------------------------------------------------------- #
# Track assembly
# --------------------------------------------------------------------------- #
def test_every_beat_and_the_sign_off_get_a_line():
    stub = StubVoice()
    with tempfile.TemporaryDirectory() as tmp:
        track = build_voice_track(_reel(), Path(tmp) / "v.wav", client=stub)
    assert track is not None
    # One call per beat, plus the spoken call to action.
    assert len(stub.calls) == 5
    assert len(track.beat_seconds) == 4


def test_beat_length_is_the_spoken_line_plus_its_air():
    stub = StubVoice(seconds=3.0)
    with tempfile.TemporaryDirectory() as tmp:
        track = build_voice_track(_reel(), Path(tmp) / "v.wav", client=stub)
    expected = 3.0 + REEL_VOICE_LEAD_IN + REEL_VOICE_TAIL
    assert all(abs(s - expected) < 0.02 for s in track.beat_seconds)


def test_a_very_short_line_still_gets_a_moment_to_land():
    stub = StubVoice(seconds=0.2)
    with tempfile.TemporaryDirectory() as tmp:
        track = build_voice_track(_reel(), Path(tmp) / "v.wav", client=stub)
    assert all(s >= MIN_BEAT_SECONDS for s in track.beat_seconds)


def test_the_wav_is_as_long_as_the_pacing_it_reports():
    # This is the sync guarantee: if the file and the cut list disagree, the
    # narration drifts away from the visuals over the course of the reel.
    stub = StubVoice(seconds=2.0)
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "v.wav"
        track = build_voice_track(_reel(), path, client=stub)
        with wave.open(str(path), "rb") as wf:
            assert wf.getnchannels() == 1
            assert wf.getframerate() == TTS_SAMPLE_RATE
            assert wf.getsampwidth() == 2
            actual = wf.getnframes() / float(wf.getframerate())
    assert abs(actual - track.total_seconds) < 0.05


def test_the_spoken_line_falls_back_to_the_on_screen_text():
    stub = StubVoice()
    reel = _reel()
    reel.beats[1].narration = ""
    with tempfile.TemporaryDirectory() as tmp:
        build_voice_track(reel, Path(tmp) / "v.wav", client=stub)
    spoken = stub.calls[1][0]
    assert "What happened" in spoken and "A short supporting line" in spoken


def test_the_two_formats_use_different_voices():
    # Otherwise the morning news reel and the evening lesson sound like the same
    # person reading two scripts.
    assert voice_for(_reel("news")) == REEL_VOICE_NEWS
    assert voice_for(_reel("education")) == REEL_VOICE_EDUCATION
    assert REEL_VOICE_NEWS != REEL_VOICE_EDUCATION


def test_the_style_direction_matches_the_format():
    stub = StubVoice()
    with tempfile.TemporaryDirectory() as tmp:
        build_voice_track(_reel("education"), Path(tmp) / "v.wav", client=stub)
    assert {call[2] for call in stub.calls} == {"education"}


# --------------------------------------------------------------------------- #
# Failure
# --------------------------------------------------------------------------- #
def test_one_failed_line_abandons_the_whole_track():
    # Partial narration reads as broken, and a failure here is almost always
    # systemic rather than specific to one line.
    stub = StubVoice(fail_on=3)
    with tempfile.TemporaryDirectory() as tmp:
        assert build_voice_track(_reel(), Path(tmp) / "v.wav", client=stub) is None


def test_a_failed_sign_off_also_abandons_the_track():
    stub = StubVoice(fail_on=5)
    with tempfile.TemporaryDirectory() as tmp:
        assert build_voice_track(_reel(), Path(tmp) / "v.wav", client=stub) is None


def test_a_rate_limit_hint_is_honoured_instead_of_guessing():
    # The free tier allows three speech requests a minute and a reel needs
    # seven, so 429s are normal operation. The server says how long its window
    # has left to run, and waiting that long beats an exponential guess.
    from headlinne.gemini.tts import _is_rate_limit, _retry_after

    body = ("429 RESOURCE_EXHAUSTED. {'error': {'code': 429, 'message': "
            "'You exceeded your current quota'}, 'details': [{'@type': "
            "'type.googleapis.com/google.rpc.RetryInfo', 'retryDelay': '11s'}]}")
    exc = RuntimeError(body)
    assert _is_rate_limit(exc)
    assert _retry_after(exc) == 11.0
    # A plain failure has no hint and falls back to exponential backoff.
    assert _retry_after(RuntimeError("connection reset")) is None
    assert not _is_rate_limit(RuntimeError("connection reset"))


def test_a_rate_limited_model_falls_through_to_the_next_one():
    """Quota is counted per model, so a second model is a second allowance.

    On the free tier this is the difference between narration working and not:
    one model's daily cap does not cover a day's fourteen lines.
    """
    from headlinne.gemini.tts import TTSClient

    class _Models:
        def __init__(self, working):
            self.working = working
            self.tried: list[str] = []

        def generate_content(self, *, model, contents, config):
            self.tried.append(model)
            if model != self.working:
                raise RuntimeError("429 RESOURCE_EXHAUSTED 'retryDelay': '2s'")
            part = type("P", (), {"inline_data": type("D", (), {"data": b"\x00" * 480})()})()
            content = type("C", (), {"parts": [part]})()
            return type("R", (), {"candidates": [type("X", (), {"content": content})()]})()

    client = TTSClient(api_key="x", min_interval=0,
                       fallback_models=("model-b", "model-c"))
    client.models = ["model-a", "model-b", "model-c"]
    fake = _Models("model-b")
    client._client = type("C", (), {"models": fake})()
    client._ensure_client = lambda: True

    assert client.synthesize("hello", voice="Kore") is not None
    assert fake.tried == ["model-a", "model-b"]      # no wasted waiting
    # The working model becomes sticky, so the next line does not rediscover it.
    fake.tried.clear()
    client.synthesize("again", voice="Kore")
    assert fake.tried == ["model-b"]


def test_a_non_quota_error_does_not_burn_the_other_models():
    # Another model will not fix a malformed request, so there is no point
    # spending its quota finding that out.
    from headlinne.gemini.tts import TTSClient

    tried: list[str] = []

    class _Models:
        def generate_content(self, *, model, contents, config):
            tried.append(model)
            raise RuntimeError("400 INVALID_ARGUMENT")

    client = TTSClient(api_key="x", min_interval=0, fallback_models=("b", "c"))
    client._client = type("C", (), {"models": _Models()})()
    client._ensure_client = lambda: True
    assert client.synthesize("hello", voice="Kore") is None
    assert tried.count("b") == 0


def test_calls_are_paced_so_the_quota_is_not_hit_in_the_first_place():
    import time

    from headlinne.gemini.tts import TTSClient

    client = TTSClient(api_key="x", min_interval=0.4)
    client._ensure_client = lambda: False   # no network, just exercise pacing
    start = time.monotonic()
    client._last_call = time.monotonic()
    client._wait_for_slot()
    assert time.monotonic() - start >= 0.35

    # Pacing is off entirely on a paid key, where it would only add minutes.
    fast = TTSClient(api_key="x", min_interval=0)
    fast._last_call = time.monotonic()
    start = time.monotonic()
    fast._wait_for_slot()
    assert time.monotonic() - start < 0.05


def test_a_beat_with_nothing_to_say_abandons_the_track():
    reel = _reel()
    reel.beats[1].caption = reel.beats[1].detail = reel.beats[1].narration = ""
    with tempfile.TemporaryDirectory() as tmp:
        assert build_voice_track(reel, Path(tmp) / "v.wav", client=StubVoice()) is None


# --------------------------------------------------------------------------- #
# The edit follows the audio
# --------------------------------------------------------------------------- #
def _no_photos(_src):
    return None


def test_scene_durations_come_from_the_narration_when_there_is_one():
    reel = _reel()
    track = VoiceTrack(path=Path("unused.wav"),
                       beat_seconds=[5.0, 4.0, 6.0, 3.0], outro_seconds=2.5)
    scenes = reel_render.build_scenes(reel, _no_photos, track)
    assert [s.duration for s in scenes] == [5.0, 4.0, 6.0, 3.0, 2.5]


def test_scene_durations_fall_back_to_reading_speed_without_a_track():
    reel = _reel()
    voiced = reel_render.build_scenes(reel, _no_photos)
    assert len(voiced) == len(reel.beats) + 1
    # The silent path still produces a sane runtime rather than nothing.
    assert 8 <= sum(s.duration for s in voiced) <= 56


def test_a_mismatched_track_is_ignored_rather_than_trusted():
    # A track built for a different beat list would silently desync the reel.
    reel = _reel()
    stale = VoiceTrack(path=Path("unused.wav"), beat_seconds=[5.0, 4.0],
                       outro_seconds=2.5)
    scenes = reel_render.build_scenes(reel, _no_photos, stale)
    assert [s.duration for s in scenes][:2] != [5.0, 4.0]
