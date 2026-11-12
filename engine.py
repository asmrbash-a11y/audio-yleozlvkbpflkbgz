"""Frame engine: paper camera, captions, transitions, overlays."""
import functools, json, math, os
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageChops, ImageEnhance
import visuals as V
from visuals import PAL, C, ease_out, ease_in_out, back_out, lerp, place, paste_alpha, vignette, add_grain

HERE = os.path.dirname(os.path.abspath(__file__))
W, H = 1080, 1920
FPS = 25
ART_DIR = os.path.join(HERE, "assets", "art")
SRC_W, SRC_H = 2200, 3908          # upscaled art canvas used by the camera
TL = json.load(open(os.path.join(HERE, "data", "timeline.json")))


# ------------------------------------------------------------------ art
@functools.lru_cache(maxsize=24)
def load_art(name):
    if name is None:
        img = Image.new("RGB", (SRC_W, SRC_H), PAL["navy"])
    else:
        raw = Image.open(os.path.join(ART_DIR, name + ".png")).convert("RGB")
        img = raw.resize((SRC_W, SRC_H), Image.LANCZOS)
        img = img.filter(ImageFilter.UnsharpMask(radius=2.2, percent=62, threshold=2))
    return img


def grade(img, tint=None, sat=1.0, contrast=1.0, bright=1.0, lift=0.0):
    if sat != 1.0:
        img = ImageEnhance.Color(img).enhance(sat)
    if contrast != 1.0:
        img = ImageEnhance.Contrast(img).enhance(contrast)
    if bright != 1.0:
        img = ImageEnhance.Brightness(img).enhance(bright)
    if tint or lift:
        a = np.asarray(img, dtype=np.float32)
        if tint:
            col, amt = tint
            a = a * (1 - amt) + np.array(col, dtype=np.float32) * amt
        if lift:
            a = a + lift * 255
        img = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))
    return img


def interp_keys(keys, t):
    """keys: [(t, zoom, cx, cy, rot), ...] with t ascending."""
    if t <= keys[0][0]:
        return keys[0][1:]
    if t >= keys[-1][0]:
        return keys[-1][1:]
    for a, b in zip(keys, keys[1:]):
        if a[0] <= t <= b[0]:
            p = 0 if b[0] == a[0] else (t - a[0]) / (b[0] - a[0])
            e = ease_in_out(p)
            return tuple(lerp(x, y, e) for x, y in zip(a[1:], b[1:]))
    return keys[-1][1:]


def camera(art_name, t, keys, grade_kw=None):
    zoom, cx, cy, rot = interp_keys(keys, t)
    src = load_art(art_name)
    if grade_kw:
        src = grade(src, **grade_kw)
    k = 1.0 / zoom
    th = math.radians(rot)
    a, b = k * math.cos(th), -k * math.sin(th)
    d, e = k * math.sin(th), k * math.cos(th)
    c = cx * SRC_W - a * (W / 2) - b * (H / 2)
    f = cy * SRC_H - d * (W / 2) - e * (H / 2)
    return src.transform((W, H), Image.AFFINE, (a, b, c, d, e, f), resample=Image.BICUBIC)


# ------------------------------------------------------------------ scrims
@functools.lru_cache(maxsize=16)
def scrim(pos="bottom", strength=190, height=760):
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    a = np.zeros((H, W), dtype=np.uint8)
    if pos == "bottom":
        for y in range(H - height, H):
            v = (y - (H - height)) / height
            a[y, :] = int(strength * (v ** 1.35))
    elif pos == "top":
        for y in range(0, height):
            v = 1 - y / height
            a[y, :] = int(strength * (v ** 1.35))
    elif pos == "center":
        yy, xx = np.ogrid[:H, :W]
        r = np.sqrt(((xx - W / 2) / (W * 0.62)) ** 2 + ((yy - H * 0.42) / (H * 0.42)) ** 2)
        a = (np.clip(1 - r, 0, 1) ** 1.2 * strength).astype(np.uint8)
    img.putalpha(Image.fromarray(a))
    return img


def darken(frame, pos="bottom", strength=190, height=760):
    return Image.alpha_composite(frame, scrim(pos, strength, height))


# ------------------------------------------------------------------ captions
CAP_FONT = 64
CAP_KIND = "title_b"


@functools.lru_cache(maxsize=512)
def word_img(text, kind, size, color, alpha=255):
    """Trimmed ink of one word (correctly shaped Arabic) + its advance width."""
    img = V.text_img(text, kind, size, color, alpha, direction="rtl")
    f = V.font(kind, size)
    adv = f.getlength(text, direction="rtl", language="ar")
    return img, adv


class Caption:
    """A paper strip with the line; the spoken word is marked as it is said."""

    def __init__(self, cue, words):
        self.cue = cue
        toks = [w for w in words if w["text"]]
        forced = cue.get("lines")
        self.tokens = toks
        self.size = CAP_FONT
        self.pad_x, self.pad_y = 52, 24
        self.line_gap = 14
        layers = [word_img(w["text"], CAP_KIND, self.size, "ink", 255) for w in toks]
        self.inks = [l[0] for l in layers]
        self.advs = [l[1] for l in layers]
        self.space = V.font(CAP_KIND, self.size).getlength(" ", direction="rtl", language="ar") * 1.15
        if forced and len(forced) == len(toks):
            self.lines = []
            k = 0
            for ln in forced:
                self.lines.append(list(range(k, k + ln)))
                k += ln
            self.line_ws = [sum(self.advs[i] for i in ln) + self.space * (len(ln) - 1) for ln in self.lines]
            self.line_h = max(i.height for i in self.inks)
            self.strip_w = int(max(self.line_ws) + self.pad_x * 2)
            self.strip_h = int(len(self.lines) * self.line_h + (len(self.lines) - 1) * self.line_gap + self.pad_y * 2)
            return
        max_w = W - 200
        self.lines = [list(range(len(toks)))]
        line_w = [sum(self.advs) + self.space * (len(toks) - 1)]
        if line_w[0] > max_w:
            best, bi = None, 1
            for i in range(1, len(toks)):
                w1 = sum(self.advs[:i]) + self.space * (i - 1)
                w2 = sum(self.advs[i:]) + self.space * (len(toks) - i - 1)
                m = max(w1, w2)
                if best is None or m < best:
                    best, bi = m, i
            self.lines = [list(range(bi)), list(range(bi, len(toks)))]
            line_w = [sum(self.advs[i] for i in ln) + self.space * (len(ln) - 1) for ln in self.lines]
        self.line_ws = line_w
        self.line_h = max(i.height for i in self.inks)
        self.strip_w = int(max(line_w) + self.pad_x * 2)
        self.strip_h = int(len(self.lines) * self.line_h + (len(self.lines) - 1) * self.line_gap + self.pad_y * 2)

    def render(self, active_idx=None):
        strip = V.sheet(self.strip_w, self.strip_h, "cream", seed=int(self.cue["index"]) + 3,
                        edges=("t", "b"), amp=6, alpha=248, fiber=0.14)
        d = ImageDraw.Draw(strip)
        d.rectangle([7, 7, self.strip_w - 8, self.strip_h - 8], outline=(0, 0, 0, 24), width=2)
        for li, ln in enumerate(self.lines):
            x = self.strip_w / 2 + self.line_ws[li] / 2          # right edge, RTL
            y = self.pad_y + li * (self.line_h + self.line_gap)
            for ti in ln:
                adv = self.advs[ti]
                ink = self.inks[ti]
                x0 = x - adv                                    # slot left edge
                if ti == active_idx:
                    chip = V.sheet(int(adv) + 20, self.line_h + 12, "yellow",
                                   seed=77 + ti, edges=("t", "b", "l", "r"), amp=4, alpha=255, fiber=0.08)
                    strip.alpha_composite(chip, (int(x0 - 10), int(y - 6)))
                strip.alpha_composite(ink, (int(x0 + (adv - ink.width) / 2),
                                            int(y + (self.line_h - ink.height) / 2)))
                x = x0 - self.space
        return V.with_shadow(strip, offset=(0, 10), blur=16, alpha=115)


CAPTIONS = {}
# map each word index -> caption
WORD_CAP = {}
for cue in TL["cues"]:
    words = [w for w in TL["words"] if w["i"] in cue["tokens"]]
    cap = Caption(cue, words)
    CAPTIONS[cue["index"]] = cap
    for w in words:
        WORD_CAP[w["i"]] = cue["index"]

CAP_CACHE = {}


def draw_caption(frame, t):
    cue = next((c for c in TL["cues"] if c["start"] <= t <= c["end"]), None)
    if cue is None:
        return frame
    cap = CAPTIONS[cue["index"]]
    active = None
    for w in TL["words"]:
        if w["i"] in cue["tokens"] and w["text"] and w["start"] - 0.05 <= t <= w["end"] + 0.08:
            active = cap.tokens.index(w) if w in cap.tokens else None
    key = (cue["index"], active)
    if key not in CAP_CACHE:
        CAP_CACHE[key] = cap.render(active)
    img = CAP_CACHE[key]
    p = (t - cue["start"]) / 0.26
    dy = int((1 - ease_out(p)) * 28)
    op = min(1.0, 0.3 + p)
    x = (W - img.width) / 2
    y = H - 228 - img.height + dy
    return paste_alpha(frame, img, (x, max(252, y)), op)


# ------------------------------------------------------------------ transitions
TDUR = 0.38


@functools.lru_cache(maxsize=24)
def torn_path(seed, n=34):
    import random
    rng = random.Random(seed)
    pts = []
    for i in range(n + 1):
        y = -40 + (H + 80) * i / n
        x = rng.uniform(-70, 60) + (math.sin(i * 0.7) * 22)
        pts.append((x, y))
    return tuple(pts)


def transition(a, b, p, kind, seed=1):
    """Blend frames a -> b, p in 0..1."""
    p = min(1, max(0, p))
    if kind == "flash":
        # cream flash peaks at the middle, screens swap under it
        base = a if p < 0.5 else b
        f = math.sin(math.pi * min(1, p * 1.12)) ** 0.9
        flash = Image.new("RGBA", (W, H), C("cream", int(150 * f)))
        return Image.alpha_composite(base, flash)
    if kind == "punch":
        s = 1 + 0.06 * math.sin(math.pi * p)
        a2 = a.rotate(0)
        img = a if p < 0.5 else b
        img = img.transform((W, H), Image.AFFINE,
                            (1 / s, 0, W / 2 - W / (2 * s), 0, 1 / s, H / 2 - H / (2 * s)),
                            resample=Image.BICUBIC)
        f = math.sin(math.pi * p) ** 1.4
        img = Image.alpha_composite(img, Image.new("RGBA", (W, H), C("white", int(105 * f))))
        return img
    if kind == "slide":
        # incoming sheet slides up over the outgoing frame, torn top edge
        e = ease_in_out(p)
        off = int((1 - e) * H)
        mask = V.torn_mask(W, H, seed, ("t",), amp=26, step=12)
        shifted = Image.new("L", (W, H), 0)
        shifted.paste(mask.crop((0, 0, W, H - off)), (0, off)) if off < H - 1 else None
        b2 = b.copy()
        b2.putalpha(shifted)
        sh, (dx, dy) = V.shadow(b2, (0, 0), 26, 130)
        out = a.copy()
        out = paste_alpha(out, sh, (0, 0))
        out.alpha_composite(b2)
        return out
    # default: torn vertical wipe
    e = ease_in_out(p)
    pts = torn_path(seed)
    cut = e * (W + 220) - 110
    mask = Image.new("L", (W, H), 0)
    d = ImageDraw.Draw(mask)
    poly = [(W + 10, -10), (W + 10, H + 10)]
    for (x, y) in pts:
        poly.append((x + cut, y))
    poly.append((-10, H + 10))
    poly.append((-10, -10))
    d.polygon(poly, fill=255)
    # paper lip on the moving edge
    edge = Image.new("L", (W, H), 0)
    de = ImageDraw.Draw(edge)
    lip = [(x + cut, y) for (x, y) in pts]
    de.line(lip, fill=255, width=16)
    edge = edge.filter(ImageFilter.GaussianBlur(6))
    b2 = b.copy()
    b2.putalpha(mask)
    out = a.copy()
    lipc = Image.new("RGBA", (W, H), C("cream", 0))
    lipc.putalpha(edge.point(lambda v: int(v * 0.55)))
    out = paste_alpha(out, lipc, (0, 0))
    sh, _ = V.shadow(b2, (0, 0), 22, 150)
    out = paste_alpha(out, sh, (0, 0))
    out.alpha_composite(b2)
    return out


# ------------------------------------------------------------------ frame
def render_frame(t, scene_fns, scenes):
    s_i = max(i for i, s in enumerate(scenes) if s["start"] <= t + 1e-9)
    sc = scenes[s_i]
    p = t - sc["start"]
    frame = scene_fns[sc["id"]](p, sc)
    if sc.get("trans") and p < TDUR and s_i > 0:
        prev = scenes[s_i - 1]
        pp = min(prev["dur"], prev["dur"] + p)
        a = scene_fns[prev["id"]](pp, prev)
        frame = transition(a, frame, p / TDUR, sc["trans"], seed=s_i * 7 + 3)
    frame = Image.alpha_composite(frame, vignette(W, H, 0.50))
    frame = draw_caption(frame, t)
    rgb = add_grain(frame.convert("RGB"), t, amount=7)
    rgb = progress_bar(rgb, t, TL["duration"])
    return rgb


def progress_bar(frame, t, total):
    d = ImageDraw.Draw(frame)
    x = int((W - 120) * min(1, t / total))
    d.rectangle([0, 0, W, 9], fill=(10, 16, 28))
    d.rectangle([0, 0, x + 60, 9], fill=PAL["yellow"])
    d.rectangle([0, 0, x + 60, 3], fill=(250, 235, 200))
    return frame
