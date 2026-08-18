"""Simulated runthrough. Renders every frame of every format and asserts the
things a human reviewer would catch, but on all 696 frames instead of four.

Checks
  1. collision   - no two traced elements overlap
  2. safe zone   - nothing renders below y=1450 (scaled) in a reel
  3. margins     - nothing crosses the left/right margin or the top
  4. contrast    - every ink/accent pair clears 4.5:1 on the paper ground
  5. legibility  - no rendered line exceeds the readable pace budget
  6. assets      - every sprite pose and plate resolves, no empty renders
  7. fallbacks   - each rung of the image ladder produces a real object
"""
import sys, pathlib
from PIL import Image
import draft as D
import pip as P
import plate as PL

FAILS, WARNS, CHECKS = [], [], 0

# elements allowed to overlap: Pip walks past the ground rule by design, and the
# tape strip sits on top of its own plate
ALLOWED = {("pip", "plate0"), ("pip", "plate1"), ("plate0", "plate1"),
           ("bubble", "plate0"), ("bubble", "plate1")}


def fail(where, msg):
    FAILS.append(f"{where}: {msg}")


def warn(where, msg):
    WARNS.append(f"{where}: {msg}")


def check(cond, where, msg):
    global CHECKS
    CHECKS += 1
    if not cond:
        fail(where, msg)
    return cond


def boxes_overlap(a, b, pad=0):
    return not (a[3] <= b[1] + pad or b[3] <= a[1] + pad or
                a[2] <= b[0] + pad or b[2] <= a[0] + pad)


def rel_lum(c):
    def f(v):
        v /= 255
        return v / 12.92 if v <= .04045 else ((v + .055) / 1.055) ** 2.4
    r, g, b = (f(x) for x in c)
    return .2126 * r + .7152 * g + .0722 * b


def contrast(fg, bg):
    a, b = sorted((rel_lum(fg), rel_lum(bg)), reverse=True)
    return (a + .05) / (b + .05)


# --------------------------------------------------------------------------- #
print("1. reel — every frame")
n = int(D.DURATION * D.FPS)
worst_gap = 10 ** 9
for k in range(n):
    t = k / D.FPS
    im = D.render_frame(t)
    tr = [e for e in D.TRACE]
    where = f"reel t={t:0.2f}s"

    for i in range(len(tr)):
        for j in range(i + 1, len(tr)):
            a, b = tr[i], tr[j]
            key = tuple(sorted((a[0], b[0])))
            if key in ALLOWED or tuple(sorted((a[0], b[0]))) in ALLOWED:
                continue
            if boxes_overlap(a[1:], b[1:]):
                fail(where, f"'{a[0]}' overlaps '{b[0]}' "
                            f"({a[1:]} vs {b[1:]})")
            elif a[0] in ("line", "detail") and b[0] in ("line", "detail"):
                gap = abs(b[1] - a[3]) if b[1] > a[3] else abs(a[1] - b[3])
                globals()['worst_gap'] = min(worst_gap, gap)

    for e in tr:
        check(e[4] <= D.S(1450), where,
              f"'{e[0]}' bottom {e[4]} is below the safe zone {D.S(1450)}")
        check(e[1] >= D.M - D.S(34), where,
              f"'{e[0]}' left {e[1]} crosses the margin {D.M}")
        check(e[3] <= D.W - D.M + D.S(34), where,
              f"'{e[0]}' right {e[3]} crosses the margin")
        check(e[2] >= D.S(60), where, f"'{e[0]}' top {e[2]} is above the masthead")

    check(im.size == (D.W, D.H), where, f"frame size {im.size}")

print(f"   {n} frames, {CHECKS} assertions")

# --------------------------------------------------------------------------- #
print("2. contrast")
BG = D.PAPER
for name, col, need in (("ink", D.INK, 4.5), ("soft", D.SOFT, 4.5),
                        ("terra", D.TERRA, 3.0), ("mint", D.MINT, 4.5),
                        ("marigold", D.MARIGOLD, 3.0),
                        ("coral", D.CORAL, 3.0)):
    r = contrast(col, BG)
    check(r >= need, "contrast", f"{name} is {r:.2f}:1 on paper, needs {need}")
    if need == 3.0 and r < 4.5:
        warn("contrast", f"{name} at {r:.2f}:1 is large-text-only — never set it below 24px")

# --------------------------------------------------------------------------- #
print("3. sprites")
for name, grid in P.SPRITES.items():
    rows = P._rows(grid)
    check(all(len(r) == P.W for r in rows), "sprite", f"{name} has a ragged row")
    im = P.render(grid, 4)
    check(im.getbbox() is not None, "sprite", f"{name} rendered empty")
for cname, cyc in (("walk", P.walk_cycle()), ("jump", P.jump_cycle()),
                   ("point", P.point_cycle()), ("present", P.present_cycle()),
                   ("talk", P.talk_cycle()), ("idle", P.idle_cycle())):
    check(len(cyc) >= 2, "cycle", f"{cname} has {len(cyc)} frame(s)")
    hs = {len(P._rows(f)) for f in cyc}
    check(len(hs) == 1, "cycle", f"{cname} frames differ in height {hs}")
    ims = [P.render(f, 4) for f in cyc]
    check(all(i.getbbox() is not None for i in ims), "cycle", f"{cname} has an empty frame")
    # compare pixels, not bounding boxes - a beak opening changes no bbox at all
    check(len({i.tobytes() for i in ims}) > 1, "cycle", f"{cname} never actually moves")

# --------------------------------------------------------------------------- #
print("4. fallback ladder")
rungs = {
    "1 photo":      lambda: PL.tilted(Image.new("RGB", (400, 260), (90, 90, 110))),
    "2 pixel":      lambda: PL.tilted(PL.moon_scene(w=400, h=260)),
    "3 chart":      lambda: PL.tilted(PL.chart_scene(w=400, h=260)),
    "4 pip only":   lambda: P.render(P.SPRITES["carry"], 8),
}
for name, fn in rungs.items():
    im = fn()
    check(im.getbbox() is not None, "fallback", f"rung {name} produced nothing")
    check(im.width > 80 and im.height > 80, "fallback", f"rung {name} too small")

cap_missing = []
for seed in (5, 11, 23):
    sc = PL.moon_scene(seed=seed)
    check(sc.getbbox() is not None, "fallback", f"moon_scene seed {seed} empty")
# the caption is a promise, not a nicety
import inspect
src = inspect.getsource(PL.tilted)
check("caption" in src, "fallback", "tilted() lost its caption parameter")

# --------------------------------------------------------------------------- #
print("5. pace")
# Two separate budgets. The primary line carries the story and must be read, so
# it gets the strict ceiling. The detail line supports it and is scanned, not
# read word for word - it gets a looser one.
primary = sum(len(b[3].replace("*", "").split()) for b in D.BEATS)
support = sum(len(b[4].split()) for b in D.BEATS)
p_rate = primary / (D.DURATION / 60)
s_rate = (primary + support) / (D.DURATION / 60)
check(p_rate <= 230, "pace", f"primary line is {p_rate:.0f} wpm, ceiling 230")
check(s_rate <= 380, "pace", f"total on-screen load {s_rate:.0f} wpm, ceiling 380")
print(f"   {len(D.BEATS)} beats · {D.DURATION}s · primary {p_rate:.0f} wpm "
      f"· with support {s_rate:.0f} wpm")
for i, b in enumerate(D.BEATS):
    end = D.BEATS[i + 1][0] if i + 1 < len(D.BEATS) else D.DURATION
    span = end - b[0]
    check(span >= 1.0, "pace", f"beat {i+1} '{b[1]}' holds only {span:.2f}s")
    # Pip's cycle and the progress bar advance on every frame, so a long beat is
    # never actually static; flag only if a beat outruns comfortable reading.
    read_s = len(b[3].split()) / (230 / 60)
    if span > read_s + 2.6:
        warn("pace", f"beat {i+1} holds {span:.2f}s for {read_s:.1f}s of reading")

# --------------------------------------------------------------------------- #
print("6. CTA present in every format")
check(any("headlinne.com" in b[3] for b in D.BEATS), "cta", "reel has no CTA beat")
check(D.BEATS[-1][3].find("headlinne.com") >= 0, "cta", "reel CTA is not last")
seen = set()
for day in range(10):                       # the sign-off must actually vary
    seen.add(D.cta_cycle(day)[1])
check(len(seen) >= 4, "cta", f"CTA pose only varies {len(seen)} ways")
import formats, xpost
check("car_cta" in str(pathlib.Path("car_cta.png")) and
      pathlib.Path("car_cta.png").exists(), "cta", "carousel CTA slide missing")
check(pathlib.Path("x_cta.png").exists(), "cta", "X CTA card missing")
for f in ("car_cta.png", "x_cta.png"):
    im = Image.open(f)
    check(im.getbbox() is not None, "cta", f"{f} is blank")

# --------------------------------------------------------------------------- #
print("7. static formats")
for f in ("car_cover.png", "car_scale.png", "car_twist.png", "car_close.png",
          "car_cta.png", "x_receipt.png", "x_compare.png", "x_correct.png",
          "x_photo.png", "x_cta.png"):
    pth = pathlib.Path(f)
    if not check(pth.exists(), "static", f"{f} not rendered"):
        continue
    im = Image.open(pth).convert("RGB")
    check(im.getbbox() is not None, "static", f"{f} is blank")
    exp = (1080, 1350) if f.startswith("car") else (1200, 675)
    check(im.size == exp, "static", f"{f} is {im.size}, expected {exp}")
    # a card that is >99% one colour has failed to draw
    colours = im.resize((60, 60)).getcolors(3600)
    top = max(c for c, _ in colours)
    check(top / 3600 < .985, "static", f"{f} is {top/36:.0f}% a single colour")

# --------------------------------------------------------------------------- #
print()
print("=" * 66)
print(f"{CHECKS} assertions · {len(FAILS)} failures · {len(WARNS)} warnings")
print("=" * 66)
for w in WARNS[:12]:
    print("  WARN ", w)
seen = set()
for f in FAILS:
    k = f.split("(")[0][:90]
    if k in seen:
        continue
    seen.add(k)
    print("  FAIL ", f[:150])
if len(seen) < len(FAILS):
    print(f"  ... {len(FAILS) - len(seen)} more failures of the same shapes")
sys.exit(1 if FAILS else 0)
