"""Build a reel's narration track, and let it drive the edit.

This inverts how the silent reel is timed. Without narration, a beat lasts as
long as its text takes to read, which is a guess. With narration, a beat lasts
exactly as long as the voice needs, which is not. The audio is therefore built
*before* the frames, and the durations it produces are what the renderer lays
out against.

**One request per reel.**

This used to be one request per beat plus one for the sign-off - eight calls for
a seven-beat reel. Speech is rate limited far more tightly than text: the Gemini
free tier allows three requests a minute, so those eight had to be spaced 21
seconds apart, and a day's narration became four minutes of deliberate waiting.
It was also eight chances to hit a quota wall, and a failure at beat six wasted
the five calls before it.

So the whole script is now sent as one request and comes back as one PCM stream.
Beat lengths are derived from it by word-count proportion rather than measured
per clip.

**The trade, stated plainly.** Sync is no longer sample-exact per cut. A beat
whose words happen to be spoken faster than average will hold a fraction of a
second longer than its audio, and the next will start a fraction early. For
kinetic text, where nothing is lip-synced and the cut lands on a word reveal,
that is imperceptible. What it buys is an eightfold drop in speech quota, which
is the difference between narration being a daily certainty and a daily gamble.

The track is assembled in Python rather than with ffmpeg filters. The clip comes
back in a known PCM format, so padding is a byte operation and the whole thing is
written once as a WAV that ffmpeg takes as a plain second input.

**All or nothing.** If the request fails, the track is abandoned and the reel
falls back to silence with reading-speed pacing. A reel that narrates half of
itself and then goes quiet reads as broken, and a failure here is almost always
systemic - a missing key, an exhausted quota - rather than specific to one line.
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

# What the sign-off says out loud, when the script does not already end with one.
# Spoken calls to action convert better than ones only shown, and this is the one
# moment the reel asks for anything.
OUTRO_LINE = "Follow Headlinne for a daily brief."

# Floor for a beat even when its line is very short, so a two-word payoff still
# gets a moment to land rather than snapping straight to the next cut.
MIN_BEAT_SECONDS = 2.0

# Joined between lines in the batched request. A full stop and a line break is
# what makes the model place a real pause at a cut rather than running two beats
# into one breath.
SCRIPT_JOIN = "\n\n"


@dataclass
class VoiceTrack:
    """A rendered narration track and the pacing it implies."""

    path: Path
    beat_seconds: list[float] = field(default_factory=list)
    outro_seconds: float = 0.0
    # How many speech requests this track cost. One, unless something changes.
    requests: int = 1

    @property
    def total_seconds(self) -> float:
        return sum(self.beat_seconds) + self.outro_seconds


def voice_for(reel: Reel) -> str:
    return REEL_VOICE_NEWS if reel.kind == "news" else REEL_VOICE_EDUCATION


def _spoken_line(beat) -> str:
    """What this beat says out loud.

    Falls back to the on-screen text when the model gave no separate narration,
    which reads acceptably even though a line written to be *shown* is rarely the
    best line to *say*. Emphasis markers are stripped: the asterisks are a
    rendering instruction and would otherwise be read aloud.
    """
    if beat.narration.strip():
        return beat.narration.strip()
    parts = [beat.caption.replace("*", "").strip(), beat.detail.strip()]
    return ". ".join(p.rstrip(".") for p in parts if p).strip()


def script_for(reel: Reel) -> tuple[list[str], bool]:
    """Every line the reel says, and whether a sign-off was appended.

    The sign-off is only added when the script does not already end with one.
    The daily reel's last beat *is* the call to action, so appending OUTRO_LINE
    there would have the voice ask twice.
    """
    lines = [_spoken_line(beat) for beat in reel.beats]
    if any(not line for line in lines):
        return [], False
    has_outro = bool(reel.beats) and reel.beats[-1].role == "outro"
    if has_outro:
        return lines, False
    return [*lines, OUTRO_LINE], True


def _split_by_words(lines: list[str], total: float) -> list[float]:
    """Divide `total` seconds across `lines` in proportion to their word counts.

    Word count rather than character count: speech rate is far more stable per
    word than per character, so "Danuri repositioned" and "it went up" take
    similar time despite one being nearly twice as long in characters.

    The floor is applied afterwards and the result is *not* rescaled back down.
    Rescaling would push another beat under the floor and the fix would chase
    itself; the caller pads the audio instead, which cannot fail.
    """
    counts = [max(1, len(line.split())) for line in lines]
    words = sum(counts)
    return [max(MIN_BEAT_SECONDS, round(total * count / words, 2))
            for count in counts]


def build_voice_track(reel: Reel, out_path: Path,
                      client: TTSClient | None = None) -> VoiceTrack | None:
    """Narrate the whole reel in a single request, or return None for silence."""
    client = client or TTSClient()
    voice = voice_for(reel)
    style = "news" if reel.kind == "news" else "education"

    lines, appended_outro = script_for(reel)
    if not lines:
        log.error("%s has a beat with nothing to say, dropping the voiceover.",
                  reel.slot)
        return None

    pcm = client.synthesize(SCRIPT_JOIN.join(lines), voice=voice, style=style)
    if not pcm:
        log.error("could not narrate %s, falling back to silence.", reel.slot)
        return None

    lead_in = silence(REEL_VOICE_LEAD_IN)
    tail = silence(REEL_VOICE_TAIL)
    spoken = pcm_seconds(pcm)
    budget = REEL_VOICE_LEAD_IN + spoken + REEL_VOICE_TAIL
    segments = _split_by_words(lines, budget)

    # The floors, and the rounding above, can push the video slightly past the
    # audio. Pad the tail so the two end together rather than letting ffmpeg's
    # -shortest clip the final cut.
    shortfall = sum(segments) - budget
    audio = b"".join([lead_in, pcm, tail]
                     + ([silence(shortfall)] if shortfall > 0 else []))
    _write_wav(out_path, audio)

    if appended_outro:
        beat_seconds, outro_seconds = segments[:-1], segments[-1]
    else:
        beat_seconds, outro_seconds = segments, 0.0

    track = VoiceTrack(path=out_path, beat_seconds=beat_seconds,
                       outro_seconds=outro_seconds, requests=1)
    log.info("narrated %s in 1 request: %d lines, %.1fs total",
             reel.slot, len(lines), track.total_seconds)
    return track


def _write_wav(path: Path, pcm: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(TTS_CHANNELS)
        wf.setsampwidth(TTS_SAMPLE_WIDTH)
        wf.setframerate(TTS_SAMPLE_RATE)
        wf.writeframes(pcm)
