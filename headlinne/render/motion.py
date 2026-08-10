"""A small animation engine: Pillow frames piped straight into ffmpeg.

Reels are the only Instagram surface that reliably reaches people who do not
already follow the account, so the system needs to produce real video rather
than a slideshow. This module is the machinery for that, deliberately kept tiny:

  - a `Scene` is one cut. It builds its static plate once, then draws only the
    animated parts per frame.
  - frames are written to ffmpeg's stdin as raw RGBA, so nothing ever touches
    the disk between Pillow and the MP4. A 28 second reel is 840 frames, and
    writing those as PNGs first would cost more time than rendering them.
  - the encode targets Meta's published Reels spec: H.264 in MP4, yuv420p,
    faststart so the moov atom sits at the front, and a silent AAC track because
    the spec expects an audio stream.

Why hand-rolled instead of a video library: the whole point of this repo is that
it runs on free CI with no server, and moviepy-style dependencies pull in a
large tree for what is, here, one subprocess and a loop.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Sequence

from PIL import Image, ImageDraw

from ..config import (FFMPEG_BINARY, REEL_CRF, REEL_FPS, REEL_PRESET,
                      REEL_SILENT_AUDIO)
from ..logging_setup import get_logger
from . import fonts, theme

log = get_logger("render.motion")


class VideoEncodeError(RuntimeError):
    pass


# --------------------------------------------------------------------------- #
# Easing
# --------------------------------------------------------------------------- #
def clamp01(value: float) -> float:
    return 0.0 if value < 0.0 else (1.0 if value > 1.0 else value)


def ease_out_cubic(t: float) -> float:
    t = clamp01(t)
    return 1.0 - (1.0 - t) ** 3


def ease_out_quint(t: float) -> float:
    t = clamp01(t)
    return 1.0 - (1.0 - t) ** 5


def ease_in_out(t: float) -> float:
    """Smoothstep. Used for slow drifts where a cubic feels too abrupt."""
    t = clamp01(t)
    return t * t * (3.0 - 2.0 * t)


def ease_out_back(t: float) -> float:
    """Overshoots slightly before settling. Good for things that 'land'."""
    t = clamp01(t)
    c1 = 1.70158
    c3 = c1 + 1.0
    return 1.0 + c3 * (t - 1.0) ** 3 + c1 * (t - 1.0) ** 2


def window(t: float, start: float, end: float) -> float:
    """Re-map `t` so it runs 0..1 across the sub-range start..end.

    This is how one beat sequences several elements: each element gets its own
    slice of the beat's progress instead of its own timer.
    """
    if end <= start:
        return 1.0 if t >= end else 0.0
    return clamp01((t - start) / (end - start))


def hold(t: float, rise: float = 0.16, fall: float = 0.94) -> float:
    """Opacity for something that fades in, holds, then fades out at the cut."""
    return min(ease_out_cubic(window(t, 0.0, rise)),
               1.0 - ease_in_out(window(t, fall, 1.0)))


# --------------------------------------------------------------------------- #
# Scenes
# --------------------------------------------------------------------------- #
class Scene:
    """One cut of the video.

    Subclasses build whatever is static in `prepare` (called once) and draw the
    moving parts in `frame`. Splitting it this way is what makes the renderer
    fast enough to be practical: the expensive work (photo fitting, scrims,
    gradients, brand furniture) happens once per cut, not once per frame.
    """

    duration: float = 3.0

    def prepare(self) -> None:  # pragma: no cover - default is a no-op
        return None

    def frame(self, t: float) -> Image.Image:  # pragma: no cover - interface
        raise NotImplementedError


class KenBurns:
    """A slow push on a still photo, precomputed so each frame is one crop.

    The plate is rendered once at the largest zoom the move will ever reach, so
    per frame we only crop a rectangle out of it and scale that down. Resizing
    the original photo every frame would be several times slower and would also
    resample from scratch each time.
    """

    def __init__(self, source: Image.Image, size: tuple[int, int], *,
                 zoom_from: float = 1.04, zoom_to: float = 1.14,
                 drift: tuple[float, float] = (0.0, 0.0)):
        self.w, self.h = size
        self.zoom_from = zoom_from
        self.zoom_to = zoom_to
        self.drift = drift
        self.max_zoom = max(zoom_from, zoom_to)
        self.plate = theme.cover_fit(source, int(self.w * self.max_zoom),
                                     int(self.h * self.max_zoom))

    def at(self, t: float) -> Image.Image:
        eased = ease_in_out(t)
        zoom = self.zoom_from + (self.zoom_to - self.zoom_from) * eased
        crop_w = self.w * self.max_zoom / zoom
        crop_h = self.h * self.max_zoom / zoom

        # Drift is expressed as a fraction of the slack we actually have, so a
        # pan can never walk off the edge of the plate.
        slack_x = (self.plate.width - crop_w) / 2.0
        slack_y = (self.plate.height - crop_h) / 2.0
        cx = self.plate.width / 2.0 + self.drift[0] * slack_x * eased
        cy = self.plate.height / 2.0 + self.drift[1] * slack_y * eased

        left = int(round(max(0.0, min(self.plate.width - crop_w, cx - crop_w / 2.0))))
        top = int(round(max(0.0, min(self.plate.height - crop_h, cy - crop_h / 2.0))))
        box = (left, top, left + int(round(crop_w)), top + int(round(crop_h)))
        # BILINEAR, not LANCZOS: this runs once per frame and the difference is
        # invisible after H.264 encoding.
        return self.plate.crop(box).resize((self.w, self.h), Image.BILINEAR)


# --------------------------------------------------------------------------- #
# Animated text
# --------------------------------------------------------------------------- #
def draw_rising_lines(
    canvas: Image.Image,
    lines: Sequence[str],
    font,
    *,
    x: int,
    y: int,
    t: float,
    fill,
    line_spacing: float = 1.06,
    stagger: float = 0.09,
    rise: float = 34,
    duration: float = 0.42,
    shadow: bool = True,
    align: str = "left",
    max_width: int | None = None,
) -> int:
    """Draw wrapped lines that fade up into place one after another.

    The stagger is the point: a block of text that arrives all at once reads as
    a slide, and a block that arrives line by line reads as something being
    said. Returns the y below the block (its settled position, not its animated
    one, so callers can lay out against it).

    Alpha is baked into the fill colour rather than composited as a layer,
    because a full-canvas alpha composite per line per frame is the single
    easiest way to make this renderer too slow to use.
    """
    draw = ImageDraw.Draw(canvas)
    lh = int(fonts.line_height(font) * line_spacing)
    r, g, b = fill[:3]

    for i, line in enumerate(lines):
        progress = ease_out_quint(window(t, i * stagger, i * stagger + duration))
        if progress <= 0.001:
            continue
        alpha = int(255 * progress)
        dy = int(rise * (1.0 - progress))
        settled_y = y + i * lh
        ly = settled_y + dy

        lx = x
        if align in ("center", "right") and max_width is not None:
            w = fonts.text_width(font, line)
            lx = x + (max_width - w) // 2 if align == "center" else x + (max_width - w)

        if shadow:
            # A cheap offset shadow. A real blur costs more than every other
            # per-frame operation combined, and at phone size this reads the
            # same over a scrimmed photo.
            draw.text((lx + 3, ly + 4), line, font=font,
                      fill=(0, 0, 0, int(alpha * 0.55)))
        draw.text((lx, ly), line, font=font, fill=(r, g, b, alpha))

    return y + len(lines) * lh


def draw_wipe_rule(draw: ImageDraw.ImageDraw, x: int, y: int, accent, *,
                   t: float, width: int = 120, thickness: int = 8) -> None:
    """An accent rule that wipes out from the left as a beat opens."""
    grown = int(width * ease_out_quint(t))
    if grown < thickness:
        return
    draw.rounded_rectangle([x, y, x + grown, y + thickness],
                           radius=thickness // 2, fill=theme.rgba(accent))


def draw_progress_bar(draw: ImageDraw.ImageDraw, *, width: int, y: int,
                      progress: float, accent, height: int = 7,
                      margin: int = 76) -> None:
    """A thin bar across the top showing how much of the reel is left.

    Telling people how long they have to wait measurably helps completion, which
    is the signal the Reels ranking cares about most.
    """
    x0, x1 = margin, width - margin
    draw.rounded_rectangle([x0, y, x1, y + height], radius=height // 2,
                           fill=theme.rgba(theme.TEXT_MUTED, 70))
    filled = x0 + int((x1 - x0) * clamp01(progress))
    if filled > x0 + height:
        draw.rounded_rectangle([x0, y, filled, y + height], radius=height // 2,
                               fill=theme.rgba(accent))


def fit_caption(text: str, *, max_width: int, max_height: int,
                start_size: int = 108, min_size: int = 58):
    """Fit a burned-in caption. Display face, because reels are read at a glance."""
    return fonts.fit_block(fonts.title_font, text, max_width=max_width,
                           max_height=max_height, start_size=start_size,
                           min_size=min_size, line_spacing=1.04)


def fit_detail(text: str, *, max_width: int, max_height: int,
               start_size: int = 46, min_size: int = 32):
    """Fit the smaller supporting line under a caption."""
    return fonts.fit_block(fonts.body_font, text, max_width=max_width,
                           max_height=max_height, start_size=start_size,
                           min_size=min_size, weight=500, line_spacing=1.2)


# --------------------------------------------------------------------------- #
# Encoding
# --------------------------------------------------------------------------- #
def ffmpeg_binary() -> str:
    """Locate ffmpeg: an explicit override, then PATH, then the bundled build.

    GitHub's Ubuntu runners ship ffmpeg, so CI uses the system one. Locally
    (especially on Windows) it is usually absent, and imageio-ffmpeg carries a
    static build as a normal pip dependency, which keeps setup to one command.
    """
    if FFMPEG_BINARY:
        found = shutil.which(FFMPEG_BINARY) or (
            FFMPEG_BINARY if Path(FFMPEG_BINARY).exists() else None)
        if found:
            return found
        log.warning("FFMPEG_BINARY=%r not found, falling back to auto-detection.",
                    FFMPEG_BINARY)

    found = shutil.which("ffmpeg")
    if found:
        return found

    try:
        import imageio_ffmpeg  # noqa: PLC0415 - optional, resolved lazily

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception as exc:  # pragma: no cover - depends on the environment
        raise VideoEncodeError(
            "ffmpeg is not available. Install it on the system, or run "
            "`pip install imageio-ffmpeg` to use the bundled build, or set "
            "FFMPEG_BINARY to its path."
        ) from exc


def ffmpeg_available() -> bool:
    """Whether video rendering can run here (used to skip it gracefully)."""
    try:
        ffmpeg_binary()
    except VideoEncodeError:
        return False
    return True


def _encode_command(binary: str, out_path: Path, size: tuple[int, int],
                    fps: int, crf: int, preset: str, silent_audio: bool,
                    audio_path: Path | None) -> list[str]:
    w, h = size
    cmd = [
        binary, "-y", "-loglevel", "error", "-nostdin",
        "-f", "rawvideo", "-pix_fmt", "rgba", "-s", f"{w}x{h}",
        "-r", str(fps), "-i", "-",
    ]
    # A narration track when there is one, silence when there is not. Meta's
    # spec expects an audio stream either way.
    has_audio = audio_path is not None or silent_audio
    if audio_path is not None:
        cmd += ["-i", str(audio_path)]
    elif silent_audio:
        cmd += ["-f", "lavfi",
                "-i", "anullsrc=channel_layout=stereo:sample_rate=48000"]
    cmd += [
        "-c:v", "libx264", "-preset", preset, "-crf", str(crf),
        # Meta's spec: yuv420p, progressive, closed GOP, and the moov atom at the
        # front so the file can start playing before it has fully downloaded.
        "-pix_fmt", "yuv420p", "-profile:v", "high", "-level", "4.1",
        "-g", str(fps * 2), "-keyint_min", str(fps), "-sc_threshold", "0",
        "-bf", "2", "-movflags", "+faststart",
    ]
    if has_audio:
        # Meta's ceiling is 48 kHz, and the narration arrives at 24 kHz mono, so
        # it is resampled up to stereo here rather than shipped as-is.
        cmd += ["-c:a", "aac", "-b:a", "128k", "-ar", "48000", "-ac", "2",
                "-shortest"]
    cmd += [str(out_path)]
    return cmd


def render_scenes(scenes: Sequence[Scene], out_path: Path, *,
                  size: tuple[int, int], fps: int = REEL_FPS,
                  crf: int = REEL_CRF, preset: str = REEL_PRESET,
                  silent_audio: bool = REEL_SILENT_AUDIO,
                  audio_path: Path | None = None) -> float:
    """Render every scene in order into an MP4. Returns the duration in seconds.

    Each scene is asked for `round(duration * fps)` frames with `t` running from
    0 up to (but not including) 1, so cuts land exactly on a frame boundary and
    the total length is deterministic.

    `audio_path` is a narration track whose per-line lengths the scene durations
    were already built from, so the two line up without any stretching here.
    """
    if not scenes:
        raise VideoEncodeError("no scenes to render")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    binary = ffmpeg_binary()
    cmd = _encode_command(binary, out_path, size, fps, crf, preset, silent_audio,
                          audio_path)
    log.info("encoding %s (%d scenes) with %s", out_path.name, len(scenes), binary)

    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                            stderr=subprocess.PIPE)
    total_frames = 0
    try:
        for index, scene in enumerate(scenes):
            scene.prepare()
            count = max(1, int(round(scene.duration * fps)))
            for i in range(count):
                frame = scene.frame(i / count)
                if frame.size != size:
                    frame = frame.resize(size, Image.BILINEAR)
                if frame.mode != "RGBA":
                    frame = frame.convert("RGBA")
                proc.stdin.write(frame.tobytes())
            total_frames += count
            log.debug("scene %d/%d rendered (%d frames)", index + 1, len(scenes), count)
    except BrokenPipeError as exc:
        stderr = (proc.stderr.read() or b"").decode("utf-8", "replace")[-600:]
        raise VideoEncodeError(f"ffmpeg closed the stream early: {stderr}") from exc
    finally:
        if proc.stdin and not proc.stdin.closed:
            try:
                proc.stdin.close()
            except BrokenPipeError:  # pragma: no cover - already reported above
                pass

    stderr = (proc.stderr.read() or b"").decode("utf-8", "replace")
    code = proc.wait()
    if code != 0:
        raise VideoEncodeError(f"ffmpeg exited {code}: {stderr.strip()[-600:]}")

    duration = total_frames / float(fps)
    size_mb = out_path.stat().st_size / (1024 * 1024) if out_path.exists() else 0.0
    log.info("wrote %s (%.1fs, %d frames, %.1f MB)",
             out_path.name, duration, total_frames, size_mb)
    return duration


def save_cover(scene: Scene, out_path: Path, *, t: float = 0.62) -> Path:
    """Save one frame of a scene as the video's cover image.

    Taken partway through the opening beat rather than at t=0, so the hook text
    is fully on screen. The cover is what shows in the Reels tab and in the
    profile grid, so it has to be legible as a still.
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)
    scene.prepare()
    frame = scene.frame(t)
    frame.convert("RGB").save(out_path, "PNG")
    return out_path


def normalise_durations(durations: list[float], *, target: float,
                        minimum: float, maximum: float) -> list[float]:
    """Scale beat lengths so the reel lands inside its target window.

    Beat lengths are chosen from how much text each beat carries, which is the
    right instinct but does not add up to a fixed runtime. Scaling them
    proportionally keeps the rhythm the text asked for while guaranteeing the
    total stays in the range that actually holds attention.
    """
    total = sum(durations)
    if total <= 0:
        return durations
    desired = min(max(target, minimum), maximum)
    factor = desired / total
    # Only correct when it is meaningfully off, so a naturally well-sized reel
    # keeps its own pacing.
    if 0.9 <= factor <= 1.1:
        factor = 1.0
    scaled = [max(1.2, round(d * factor, 2)) for d in durations]

    # Clamp the hard ceiling even if the per-beat minimum pushed us back over it.
    over = sum(scaled) - maximum
    while over > 0.01:
        longest = max(range(len(scaled)), key=lambda i: scaled[i])
        take = min(over, scaled[longest] - 1.2)
        if take <= 0.01:
            break
        scaled[longest] = round(scaled[longest] - take, 2)
        over -= take
    return scaled


def seconds_for_text(caption: str, detail: str = "", *, base: float = 1.9,
                     cap: float = 6.0) -> float:
    """A beat's natural length, from how much there is to read.

    Roughly 14 characters a second for the big line and 22 for the small one,
    which is a comfortable silent-reading pace with a moment left over for the
    idea to land.

    `base` and `cap` exist for beats whose length is not really about their
    text. A graphic beat carries almost no words but has a device that has to
    animate in before there is anything to read, so it needs the longest slot in
    the reel while asking for the shortest one by this measure.
    """
    span = base + len(caption or "") / 14.0 + len(detail or "") / 22.0
    return round(min(cap, max(2.0, span)), 2)


__all__ = [
    "KenBurns", "Scene", "VideoEncodeError", "clamp01", "draw_progress_bar",
    "draw_rising_lines", "draw_wipe_rule", "ease_in_out", "ease_out_back",
    "ease_out_cubic", "ease_out_quint", "ffmpeg_available", "ffmpeg_binary",
    "fit_caption", "fit_detail", "hold", "normalise_durations", "render_scenes",
    "save_cover", "seconds_for_text", "window",
]
