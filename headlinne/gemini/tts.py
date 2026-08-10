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

import time

from ..config import (GEMINI_MAX_RETRIES, REEL_TTS_MODEL, REEL_VOICE_STYLE,
                      SECRETS, TTS_CHANNELS, TTS_SAMPLE_RATE, TTS_SAMPLE_WIDTH)
from ..logging_setup import get_logger

log = get_logger("gemini.tts")

_BYTES_PER_SECOND = TTS_SAMPLE_RATE * TTS_SAMPLE_WIDTH * TTS_CHANNELS


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

    def __init__(self, api_key: str | None = None, model: str = REEL_TTS_MODEL):
        self.model = model
        self._api_key = api_key or SECRETS.gemini_api_key
        self._client = None

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
        for attempt in range(1, GEMINI_MAX_RETRIES + 1):
            try:
                response = self._client.models.generate_content(
                    model=self.model, contents=prompt, config=config)
                pcm = _extract_audio(response)
                if pcm:
                    return pcm
                last_err = RuntimeError("response carried no audio")
            except Exception as exc:  # noqa: BLE001 - retry broadly, then give up
                last_err = exc
            if attempt < GEMINI_MAX_RETRIES:
                wait = min(2 ** attempt, 20)
                log.warning("TTS attempt %d/%d failed: %s (retrying in %ss)",
                            attempt, GEMINI_MAX_RETRIES, last_err, wait)
                time.sleep(wait)

        log.error("TTS failed for %r after %d attempts: %s",
                  text[:60], GEMINI_MAX_RETRIES, last_err)
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
