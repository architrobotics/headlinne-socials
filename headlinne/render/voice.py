"""Build a reel's narration track, and let it drive the edit.

This inverts how the silent reel is timed. Without narration, a beat lasts as
long as its text takes to read, which is a guess. With narration, a beat lasts
exactly as long as its spoken line plus a little air, which is not a guess. The
audio is therefore built *before* the scenes, and the durations it produces are
what the renderer lays out against.

The track is assembled in Python rather than with ffmpeg filters. Every clip
comes back in the same known PCM format, so padding and concatenation are byte
operations, and the whole thing is written once as a WAV that ffmpeg takes as a
plain second input. No filter graph, no intermediate files per beat.

**All or nothing.** If any line fails to synthesise, the whole track is
abandoned and the reel falls back to silence. A reel that narrates four beats
and then goes quiet for two reads as broken, and a failure here is almost always
systemic (a missing key, a quota) rather than specific to one line.
"""

from __future__ import annotations

import wave
from dataclasses import dataclass, field
from pathlib import Path

from ..config import (REEL_VOICE_EDUCATION, REEL_VOICE_LEAD_IN, REEL_VOICE_NEWS,
                      REEL_VOICE_TAIL, TTS_CHANNELS, TTS_SAMPLE_RATE,
                      TTS_SAMPLE_WIDTH)
from ..gemini.tts import TTSClient, pcm_seconds, silence
from ..logging_setup import get_logger
from ..models import Reel

log = get_logger("render.voice")

# What the sign-off says out loud. Spoken calls to action convert better than
# ones only shown, and this is the one moment the reel asks for anything.
OUTRO_LINE = "Follow Headlinne for a daily brief."

# Floor for a beat even when its line is very short, so a two-word payoff still
# gets a moment to land rather than snapping straight to the next cut.
MIN_BEAT_SECONDS = 2.0


@dataclass
class VoiceTrack:
    """A rendered narration track and the pacing it implies."""

    path: Path
    beat_seconds: list[float] = field(default_factory=list)
    outro_seconds: float = 0.0

    @property
    def total_seconds(self) -> float:
        return sum(self.beat_seconds) + self.outro_seconds


def voice_for(reel: Reel) -> str:
    return REEL_VOICE_NEWS if reel.kind == "news" else REEL_VOICE_EDUCATION


def _spoken_line(beat) -> str:
    """What this beat says out loud.

    Falls back to the on-screen text when the model gave no separate narration,
    which reads acceptably even though a line written to be *shown* is rarely the
    best line to *say*.
    """
    if beat.narration.strip():
        return beat.narration.strip()
    parts = [beat.caption.strip(), beat.detail.strip()]
    return ". ".join(p.rstrip(".") for p in parts if p).strip()


def build_voice_track(reel: Reel, out_path: Path,
                      client: TTSClient | None = None) -> VoiceTrack | None:
    """Narrate every beat and the sign-off, or return None and let it be silent."""
    client = client or TTSClient()
    voice = voice_for(reel)
    style = "news" if reel.kind == "news" else "education"

    lead_in = silence(REEL_VOICE_LEAD_IN)
    tail = silence(REEL_VOICE_TAIL)

    chunks: list[bytes] = []
    beat_seconds: list[float] = []

    for index, beat in enumerate(reel.beats, 1):
        line = _spoken_line(beat)
        if not line:
            log.error("beat %d of %s has nothing to say, dropping the voiceover.",
                      index, reel.slot)
            return None
        pcm = client.synthesize(line, voice=voice, style=style)
        if not pcm:
            log.error("could not narrate beat %d of %s, falling back to silence.",
                      index, reel.slot)
            return None

        chunks.extend([lead_in, pcm, tail])
        spoken = REEL_VOICE_LEAD_IN + pcm_seconds(pcm) + REEL_VOICE_TAIL
        beat_seconds.append(max(MIN_BEAT_SECONDS, round(spoken, 2)))

    outro_pcm = client.synthesize(OUTRO_LINE, voice=voice, style=style)
    if not outro_pcm:
        log.error("could not narrate the sign-off of %s, falling back to silence.",
                  reel.slot)
        return None
    chunks.extend([lead_in, outro_pcm, tail])
    outro_seconds = max(MIN_BEAT_SECONDS,
                        round(REEL_VOICE_LEAD_IN + pcm_seconds(outro_pcm)
                              + REEL_VOICE_TAIL, 2))

    # The rounding above nudges each beat's video length up by a few
    # milliseconds, so pad the audio to match rather than letting the two drift
    # apart over seven cuts.
    padded: list[bytes] = []
    for i, target in enumerate([*beat_seconds, outro_seconds]):
        actual = sum(pcm_seconds(c) for c in chunks[i * 3:i * 3 + 3])
        padded.extend(chunks[i * 3:i * 3 + 3])
        if target > actual:
            padded.append(silence(target - actual))

    _write_wav(out_path, b"".join(padded))
    track = VoiceTrack(path=out_path, beat_seconds=beat_seconds,
                       outro_seconds=outro_seconds)
    log.info("narrated %s: %d lines, %.1fs total", reel.slot,
             len(reel.beats) + 1, track.total_seconds)
    return track


def _write_wav(path: Path, pcm: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(TTS_CHANNELS)
        wf.setsampwidth(TTS_SAMPLE_WIDTH)
        wf.setframerate(TTS_SAMPLE_RATE)
        wf.writeframes(pcm)
