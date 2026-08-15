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
    """Narrate the whole reel in one request, or return None and let it be silent.

    This used to call the API once per beat. Seven calls against a quota counted
    per minute meant the pacing alone spent two minutes per reel, and any one of
    the seven failing lost the entire track. A reel is one continuous piece of
    speech, so it is now one request: the lines are spoken as a single script and
    the beats take their share of the result.

    The split is proportional to how much each line has to say. It is not exact -
    only the API knows where it actually paused - but the total is exact, which
    is the part that matters: the audio and the video end together, and no beat
    can drift far when every beat is measured against the same total.
    """
    client = client or TTSClient()
    voice = voice_for(reel)
    style = "news" if reel.kind == "news" else "education"

    lines = [_spoken_line(beat) for beat in reel.beats]
    for index, line in enumerate(lines, 1):
        if not line:
            log.error("beat %d of %s has nothing to say, dropping the voiceover.",
                      index, reel.slot)
            return None
    lines.append(OUTRO_LINE)

    # One request. The blank line between each is what the model reads as a beat
    # of silence, which is also where the video cuts.
    script = "\n\n".join(lines)
    pcm = client.synthesize(script, voice=voice, style=style)
    if not pcm:
        log.error("could not narrate %s in one request, falling back to silence.",
                  reel.slot)
        return None

    lead_in = silence(REEL_VOICE_LEAD_IN)
    tail = silence(REEL_VOICE_TAIL)
    spoken = pcm_seconds(pcm)

    # Share the spoken time out by how much each line carries, then hold every
    # beat to the floor so a two-word payoff still gets time to be read.
    # The air at each end belongs to the reel too, so it is shared out with the
    # speech rather than added on top - otherwise the WAV is longer than the cut
    # list says it is, and the two drift apart.
    budget = REEL_VOICE_LEAD_IN + spoken + REEL_VOICE_TAIL
    weights = [max(1, len(line)) for line in lines]
    total_weight = sum(weights)
    shares = [budget * w / total_weight for w in weights]
    seconds = [max(MIN_BEAT_SECONDS, round(sh, 2)) for sh in shares]

    beat_seconds = seconds[:-1]
    outro_seconds = seconds[-1]

    # The floors and the rounding only ever lengthen the video, so pad the audio
    # to match rather than letting the two drift apart across the reel.
    audio = b"".join([lead_in, pcm, tail])
    target = sum(seconds)
    actual = pcm_seconds(audio)
    if target > actual:
        audio += silence(target - actual)

    _write_wav(out_path, audio)
    track = VoiceTrack(path=out_path, beat_seconds=beat_seconds,
                       outro_seconds=outro_seconds)
    log.info("narrated %s in 1 request: %d lines, %.1fs total", reel.slot,
             len(lines), track.total_seconds)
    return track

def _write_wav(path: Path, pcm: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(TTS_CHANNELS)
        wf.setsampwidth(TTS_SAMPLE_WIDTH)
        wf.setframerate(TTS_SAMPLE_RATE)
        wf.writeframes(pcm)
