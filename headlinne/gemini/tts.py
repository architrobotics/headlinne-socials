"""Gemini text-to-speech, for reel narration.

Kept separate from ``gemini.client`` because the shape is different: that client
asks for JSON and parses it, this one asks for audio and hands back raw PCM. They
share nothing but the API key.

Two design choices worth knowing:

**Failures return None rather than raising.** A reel with no narration is a
worse reel. A run that dies because a speech endpoint was busy is a lost day. So
every failure here is recoverable by the caller, which falls back to a silent
track and still ships the video.

**The style direction is a prompt, not a parameter.** Gemini TTS takes
plain-language delivery notes in the text itself, and without one it reads news
copy with an advertisement's cadence. The direction lives in
``config.REEL_VOICE_STYLE`` so it can be tuned without touching this file.
"""

from __future__ import annotations

import re
import time

from ..config import (REEL_TTS_FALLBACK_MODELS, REEL_TTS_MAX_RETRIES,
                      REEL_TTS_MIN_INTERVAL, REEL_TTS_MODEL, REEL_VOICE_STYLE,
                      SECRETS, TTS_CHANNELS, TTS_SAMPLE_RATE, TTS_SAMPLE_WIDTH)
from ..logging_setup import get_logger

log = get_logger("gemini.tts")

_BYTES_PER_SECOND = TTS_SAMPLE_RATE * TTS_SAMPLE_WIDTH * TTS_CHANNELS

# Gemini returns a "retryDelay": "11s" hint inside a 429 body. Honouring it is
# far better than guessing with exponential backoff, because it is the server
# telling us exactly how long its quota window has left to run.
_RETRY_DELAY = re.compile(r"'?retryDelay'?\s*:\s*'?(\d+(?:\.\d+)?)s")


def _retry_after(exc: Exception) -> float | None:
    match = _RETRY_DELAY.search(str(exc))
    return float(match.group(1)) if match else None


def _is_rate_limit(exc: Exception) -> bool:
    text = str(exc)
    return "429" in text or "RESOURCE_EXHAUSTED" in text


def pcm_seconds(pcm: bytes) -> float:
    """Length of a raw PCM buffer in seconds.

    The format is fixed and known, so this is arithmetic rather than a probe.
    """
    return len(pcm) / float(_BYTES_PER_SECOND)


def silence(seconds: float) -> bytes:
    """A run of silence in the same PCM format, for padding between lines."""
    frames = max(0, int(round(seconds * TTS_SAMPLE_RATE)))
    return b"\x00" * (frames * TTS_SAMPLE_WIDTH * TTS_CHANNELS)


class TTSClient:
    """Turns a line of script into spoken PCM."""

    def __init__(self, api_key: str | None = None, model: str = REEL_TTS_MODEL,
                 min_interval: float = REEL_TTS_MIN_INTERVAL,
                 fallback_models: tuple[str, ...] = REEL_TTS_FALLBACK_MODELS):
        # Quota is per model, so the fallbacks are extra allowance rather than
        # merely extra chances. Order matters: best voice first.
        self.models = [model, *(m for m in fallback_models if m and m != model)]
        self.min_interval = max(0.0, float(min_interval))
        self._api_key = api_key or SECRETS.gemini_api_key
        self._client = None
        self._last_call = 0.0
        # Once a model starts refusing it will keep refusing for the rest of the
        # run, so remember where we got to and start there next time instead of
        # rediscovering it line by line.
        self._model_index = 0

    @property
    def model(self) -> str:
        """The model currently in use."""
        return self.models[min(self._model_index, len(self.models) - 1)]

    def _wait_for_slot(self) -> None:
        """Space calls out so we do not walk into the quota in the first place.

        Reacting to 429s alone is not enough: a burst of seven requests against
        a three-per-minute limit spends most of its retries being refused, and
        the run gives up before it finishes the reel. Pacing up front turns a
        likely failure into a slow success.
        """
        if self.min_interval <= 0:
            return
        elapsed = time.monotonic() - self._last_call
        if self._last_call and elapsed < self.min_interval:
            wait = self.min_interval - elapsed
            log.debug("pacing TTS, waiting %.1fs for the next slot", wait)
            time.sleep(wait)

    def _ensure_client(self) -> bool:
        if self._client is not None:
            return True
        if not self._api_key:
            log.warning("GEMINI_API_KEY is not set, so reels will have no voiceover.")
            return False
        try:
            from google import genai  # imported lazily
        except ImportError:  # pragma: no cover - dependency is in requirements
            log.warning("google-genai is not installed, so reels will have no voiceover.")
            return False
        self._client = genai.Client(api_key=self._api_key)
        return True

    def synthesize(self, text: str, *, voice: str, style: str = "") -> bytes | None:
        """Speak one line. Returns raw PCM, or None if it could not be produced.

        `style` is a key into ``config.REEL_VOICE_STYLE`` ("news" or "education"),
        not the direction itself, so both reels stay consistent with whatever is
        configured there.
        """
        text = (text or "").strip()
        if not text:
            return None
        if not self._ensure_client():
            return None

        direction = REEL_VOICE_STYLE.get(style, "")
        prompt = f"{direction}\n\n{text}" if direction else text

        from google.genai import types

        config = types.GenerateContentConfig(
            response_modalities=["AUDIO"],
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=voice)
                )
            ),
        )

        last_err: Exception | None = None
        for round_number in range(1, REEL_TTS_MAX_RETRIES + 1):
            waits: list[float] = []

            # One pass across every model still worth trying. A refusal from one
            # is not a reason to wait, because the next model has its own quota,
            # so we move on immediately and only sleep once nothing is left.
            for index in range(self._model_index, len(self.models)):
                model = self.models[index]
                self._wait_for_slot()
                try:
                    response = self._client.models.generate_content(
                        model=model, contents=prompt, config=config)
                    self._last_call = time.monotonic()
                    pcm = _extract_audio(response)
                    if pcm:
                        if index != self._model_index:
                            log.info("TTS now using %s", model)
                            self._model_index = index
                        return pcm
                    last_err = RuntimeError("response carried no audio")
                except Exception as exc:  # noqa: BLE001 - try the next model
                    self._last_call = time.monotonic()
                    last_err = exc

                if _is_rate_limit(last_err):
                    waits.append(_retry_after(last_err) or 30.0)
                    if index + 1 < len(self.models):
                        log.info("%s is rate limited, trying %s",
                                 model, self.models[index + 1])
                    continue
                break  # a real error, not quota: another model will not help

            if round_number >= REEL_TTS_MAX_RETRIES:
                break

            # Everything available is refusing, so now the wait is worth it. Use
            # the shortest window any model offered rather than guessing.
            wait = (min(waits) + 1.0) if waits else min(2 ** round_number, 30)
            log.warning("all TTS models unavailable (%s), waiting %.0fs",
                        "rate limited" if waits else "error", wait)
            time.sleep(wait)

        log.error("TTS failed for %r after %d rounds across %d model(s): %s",
                  text[:60], REEL_TTS_MAX_RETRIES, len(self.models), last_err)
        return None


def _extract_audio(response) -> bytes | None:
    """Pull the PCM out of a generate_content response.

    Walks the parts rather than indexing the first one, because a response can
    carry a text part alongside the audio.
    """
    try:
        parts = response.candidates[0].content.parts
    except (AttributeError, IndexError, TypeError):
        return None
    for part in parts or []:
        inline = getattr(part, "inline_data", None)
        data = getattr(inline, "data", None)
        if data:
            return data
    return None
