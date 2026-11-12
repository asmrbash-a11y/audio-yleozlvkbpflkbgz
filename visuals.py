"""Paper-collage visual library: torn sheets, halftone, tape, type, stamps."""
import functools, math, random
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageChops, ImageFont, ImageEnhance
import os

HERE = os.path.dirname(os.path.abspath(__file__))
FONTS = os.path.join(HERE, "fonts")

FONT_FILES = {
    "title": "Tajawal-ExtraBold.ttf",
    "title_b": "Tajawal-Bold.ttf",
    "body": "Tajawal-Medium.ttf",
    "bold": "Tajawal-Bold.ttf",
    "kufi": "ReemKufi.ttf",
    "amiri": "Amiri-Bold.ttf",
    "latin": "ArchivoBlack.ttf",
    "latin2": "BebasNeue.ttf",
}

# ---------------------------------------------------------------- palette
PAL = {
    "navy":    (16, 28, 51),
    "navy2":   (26, 43, 71),
    "ink":     (22, 26, 36),
    "cream":   (242, 228, 201),
    "paper":   (232, 217, 188),
    "paper2":  (223, 205, 172),
    "yellow":  (232, 178, 58),
    "red":     (176, 67, 47),
    "teal":    (47, 111, 107),
    "green":   (62, 91, 57),
    "white":   (250, 246, 236),
}


def C(name, alpha=255):
    r, g, b = PAL[name]
    return (r, g, b, alpha)


@functools.lru_cache(maxsize=256)
def font(kind, size):
    return ImageFont.truetype(os.path.join(FONTS, FONT_FILES[kind]), size)


# ---------------------------------------------------------------- text
@functools.lru_cache(maxsize=4096)
def text_img(text, kind, size, color_name, alpha=255, stroke=0, stroke_name="ink",
             direction="rtl", spacing=0, align="center"):
    """Render shaped Arabic (or LTR latin) text into a tight RGBA image."""
    f = font(kind, size)
    fill = C(color_name, alpha)
    tmp = Image.new("RGBA", (10, 10))
    d = ImageDraw.Draw(tmp)
    kw = dict(font=f, fill=fill, direction=direction, language="ar",
              stroke_width=stroke, stroke_fill=C(stroke_name, alpha), spacing=spacing)
    box = d.textbbox((0, 0), text, font=f, direction=direction, language="ar",
                     stroke_width=stroke, spacing=spacing)
    w = max(1, box[2] - box[0] + 4)
    h = max(1, box[3] - box[1] + 4)
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.text((2 - box[0], 2 - box[1]), text, **kw)
    return img


def text_size(text, kind, size, direction="rtl"):
    f = font(kind, size)
    d = ImageDraw.Draw(Image.new("RGBA", (10, 10)))
    box = d.textbbox((0, 0), text, font=f, direction=direction, language="ar")
    return box[2] - box[0], box[3] - box[1]


def fit(text, kind, max_w, max_h, start=120, direction="rtl", min_size=18):
    """Largest size whose rendered text fits the box."""
    size = start
    while size > min_size:
        w, h = text_size(text, kind, size, direction)
        if w <= max_w and h <= max_h:
            return size
        size -= max(1, size // 24)
    return min_size


def wrap(text, kind, size, max_w, direction="rtl"):
    """Greedy wrap by words for Arabic text."""
    words = text.split()
    lines, cur = [], ""
    for w in words:
        trial = (cur + " " + w).strip()
        if text_size(trial, kind, size, direction)[0] <= max_w or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


# ---------------------------------------------------------------- paper
def _noise(w, h, seed, scale=1.0):
    rng = np.random.default_rng(seed)
    small = rng.normal(0, 1, (max(2, int(h / scale)), max(2, int(w / scale))))
    img = Image.fromarray(((small * 0.5 + 0.5).clip(0, 1) * 255).astype(np.uint8))
    return img.resize((w, h), Image.BICUBIC)


@functools.lru_cache(maxsize=64)
def paper_texture(w=1080, h=1920, seed=7):
    """Fibrous paper: fine grain + long fibres + soft blotches, as an L mask."""
    rng = np.random.default_rng(seed)
    fine = np.asarray(_noise(w, h, seed, 1.0), dtype=np.float32) - 128
    mid = np.asarray(_noise(w, h, seed + 1, 3.0), dtype=np.float32) - 128
    big = np.asarray(_noise(w, h, seed + 2, 24.0), dtype=np.float32) - 128
    field = fine * 0.5 + mid * 0.7 + big * 1.1
    # fibres
    fib = Image.new("L", (w, h), 128)
    d = ImageDraw.Draw(fib)
    for _ in range(int(w * h / 5200)):
        x, y = rng.uniform(0, w), rng.uniform(0, h)
        ln = rng.uniform(6, 46)
        ang = rng.uniform(-0.35, 0.35) + (0 if rng.random() > 0.25 else math.pi / 2)
        val = 128 + rng.choice([-1, 1]) * rng.uniform(4, 16)
        d.line([(x, y), (x + math.cos(ang) * ln, y + math.sin(ang) * ln)], fill=int(val), width=1)
    field += (np.asarray(fib.filter(ImageFilter.GaussianBlur(0.4)), dtype=np.float32) - 128) * 0.9
    out = (128 + field * 0.9).clip(0, 255).astype(np.uint8)
    return Image.fromarray(out)


def shade(img, texture=None, strength=0.20):
    """Multiply a paper texture over an RGBA image."""
    tex = texture or paper_texture(img.width, img.height)
    rgb = img.convert("RGB")
    t = tex.resize(rgb.size, Image.BILINEAR)
    t = t.point(lambda v: int(128 + (v - 128) * strength * 2))
    out = ImageChops.multiply(rgb, Image.merge("RGB", (t, t, t)).point(
        lambda v: min(255, int(v * 2))))
    return Image.merge("RGBA", (*out.split(), img.split()[3]))


def torn_mask(w, h, seed, edges=("t", "b", "l", "r"), amp=9, step=14):
    """White polygon mask whose listed edges look hand-torn."""
    rng = random.Random(seed)
    m = Image.new("L", (w, h), 0)
    d = ImageDraw.Draw(m)
    pts = []
    # top
    for x in range(0, w + step, step):
        o = rng.uniform(0, amp) if "t" in edges else 0
        pts.append((min(x, w), o))
    # right
    for y in range(0, h + step, step):
        o = rng.uniform(0, amp) if "r" in edges else 0
        pts.append((w - o, min(y, h)))
    # bottom
    for x in range(w, -step, -step):
        o = rng.uniform(0, amp) if "b" in edges else 0
        pts.append((max(x, 0), h - o))
    # left
    for y in range(h, -step, -step):
        o = rng.uniform(0, amp) if "l" in edges else 0
        pts.append((o, max(y, 0)))
    d.polygon(pts, fill=255)
    return m


@functools.lru_cache(maxsize=512)
def sheet(w, h, color_name, seed=1, edges=("t", "b"), amp=9, alpha=255, fiber=0.22):
    """A torn paper sheet (RGBA) with fibre and a light rim on the torn edge."""
    w, h = int(w), int(h)
    mask = torn_mask(w, h, seed, edges, amp)
    base = Image.new("RGBA", (w, h), C(color_name, alpha))
    img = shade(base, paper_texture(w, h, seed % 17), fiber)
    img.putalpha(ImageChops.multiply(mask, base.split()[3]))
    # torn edge highlight: dilate minus mask, lighter colour
    dil = mask.filter(ImageFilter.MaxFilter(3))
    rim = ImageChops.subtract(dil, mask).filter(ImageFilter.GaussianBlur(0.6))
    light = Image.new("RGBA", (w, h), C("white", int(alpha * 0.42)))
    img = Image.composite(Image.alpha_composite(img, light), img,
                          ImageChops.multiply(rim, mask.point(lambda v: 255 - v // 3)))
    return img


def shadow(img, offset=(0, 14), blur=18, alpha=105, spread=1.0):
    """Paper drop shadow behind an RGBA image, returned bigger and offset."""
    pad = int(blur * 2.4)
    W, H = img.width + pad * 2, img.height + pad * 2
    a = Image.new("L", (W, H), 0)
    a.paste(img.split()[3], (pad, pad))
    if spread > 1.0:
        a = a.filter(ImageFilter.MaxFilter(int(spread)))
    a = a.filter(ImageFilter.GaussianBlur(blur))
    a = a.point(lambda v: int(v * alpha / 255))
    dark = Image.new("RGBA", (W, H), (8, 10, 20, 255))
    dark.putalpha(a)
    return dark, (pad - offset[0], pad - offset[1])


def with_shadow(img, offset=(0, 14), blur=18, alpha=105):
    sh, (dx, dy) = shadow(img, offset, blur, alpha)
    out = Image.new("RGBA", (max(sh.width, img.width + dx), max(sh.height, img.height + dy)), (0, 0, 0, 0))
    out.alpha_composite(sh, (max(0, -dx), max(0, -dy)))
    out.alpha_composite(img, (max(0, dx), max(0, dy)))
    return out


@functools.lru_cache(maxsize=32)
def halftone(w, h, spacing=9, radius=2.6, color_name="ink", alpha=90, angle=27):
    """Screen-printed halftone dots on transparent."""
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    col = C(color_name, alpha)
    a = math.radians(angle)
    diag = int(math.hypot(w, h)) + spacing * 2
    n = diag // spacing + 1
    for i in range(-n, n):
        for j in range(-n, n):
            x = i * spacing * math.cos(a) - j * spacing * math.sin(a) + w / 2
            y = i * spacing * math.sin(a) + j * spacing * math.cos(a) + h / 2
            if -radius <= x <= w + radius and -radius <= y <= h + radius:
                d.ellipse([x - radius, y - radius, x + radius, y + radius], fill=col)
    return img


@functools.lru_cache(maxsize=128)
def tape(w, h, seed=3, color_name="cream", alpha=205):
    """Strip of masking tape with soft ends."""
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    rng = random.Random(seed)
    d = ImageDraw.Draw(img)
    pts = [(0, 0), (w, 0), (w, h), (0, h)]
    jag = []
    for (x, y) in pts:
        jag.append((x + rng.uniform(-3, 3), y + rng.uniform(-3, 3)))
    d.polygon(jag, fill=C(color_name, alpha))
    tex = paper_texture(w, h, seed)
    img2 = shade(img, tex, 0.3)
    img2.putalpha(ImageChops.multiply(img.split()[3], tex.point(lambda v: 150 + v // 8)))
    g = img2.split()[3].filter(ImageFilter.GaussianBlur(0.7))
    img2.putalpha(g)
    return img2


# ---------------------------------------------------------------- overlays
@functools.lru_cache(maxsize=8)
def vignette(w, h, strength=0.55):
    y, x = np.ogrid[:h, :w]
    cx, cy = w / 2, h / 2
    r = np.sqrt(((x - cx) / (w * 0.72)) ** 2 + ((y - cy) / (h * 0.72)) ** 2)
    v = np.clip((r - 0.55) / 0.85, 0, 1) ** 1.6 * strength
    a = (v * 255).astype(np.uint8)
    img = Image.new("RGBA", (w, h), (6, 8, 16, 255))
    img.putalpha(Image.fromarray(a))
    return img


@functools.lru_cache(maxsize=8)
def grain_tiles(seed=11):
    rng = np.random.default_rng(seed)
    tiles = []
    for i in range(4):
        a = rng.normal(128, 46, (480, 270)).clip(0, 255).astype(np.uint8)
        tiles.append(Image.fromarray(a).resize((1080, 1920), Image.BILINEAR))
    return tuple(tiles)


def add_grain(img, t, amount=12):
    tiles = grain_tiles()
    g = tiles[int(t * 24) % len(tiles)]
    arr = np.asarray(img.convert("RGB"), dtype=np.int16)
    noise = np.asarray(g, dtype=np.int16) - 128
    noise = (noise * amount / 255).astype(np.int16)
    out = np.clip(arr + noise[:, :, None], 0, 255).astype(np.uint8)
    return Image.fromarray(out)


def glow(img, radius=30, strength=1.4, color_name="yellow"):
    """Soft light bloom around bright areas."""
    a = img.convert("L").point(lambda v: max(0, int((v - 175) * 2.2)))
    a = a.filter(ImageFilter.GaussianBlur(radius))
    col = Image.new("RGBA", img.size, C(color_name, 255))
    col.putalpha(a.point(lambda v: int(v * strength)))
    return Image.alpha_composite(img.convert("RGBA"), col)


# ---------------------------------------------------------------- marks
def hand_arrow(length=260, thickness=9, color_name="yellow", curve=0.35, seed=4, flip=False):
    """Tapered hand-drawn arrow pointing right (flip for left)."""
    W, H = int(length + 90), int(abs(curve) * length + 120)
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    col = C(color_name, 255)
    rng = random.Random(seed)
    pts = []
    n = 26
    for i in range(n + 1):
        t = i / n
        x = 40 + t * length
        y = H / 2 + math.sin(t * math.pi) * curve * length * 0.5 + rng.uniform(-1.5, 1.5)
        pts.append((x, y))
    for i in range(len(pts) - 1):
        t = i / (len(pts) - 1)
        wdt = max(2, int(thickness * (1.0 - 0.55 * t)))
        d.line([pts[i], pts[i + 1]], fill=col, width=wdt)
    tip = pts[-1]
    d.polygon([(tip[0] + 34, tip[1]), (tip[0] - 8, tip[1] - 22), (tip[0] - 8, tip[1] + 22)], fill=col)
    if flip:
        img = img.transpose(Image.FLIP_LEFT_RIGHT)
    return img


def hand_circle(w, h, thickness=8, color_name="yellow", seed=9, dash=True):
    """Rough hand-drawn ellipse."""
    img = Image.new("RGBA", (w + 60, h + 60), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    rng = random.Random(seed)
    cx, cy = img.width / 2, img.height / 2
    n = 120
    pts = []
    for i in range(n + 1):
        t = i / n * 2 * math.pi
        wob = 1 + rng.uniform(-0.022, 0.022)
        pts.append((cx + math.cos(t) * (w / 2 + 30) * wob,
                    cy + math.sin(t) * (h / 2 + 30) * wob))
    d.line(pts, fill=C(color_name, 255), width=thickness, joint="curve")
    return img


def underline(w, thickness=10, color_name="yellow", seed=5):
    W, H = w, thickness * 4
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    rng = random.Random(seed)
    pts = [(6 + i * (W - 12) / 22, H / 2 + math.sin(i * 0.6) * 2.6 + rng.uniform(-1.2, 1.2)) for i in range(23)]
    d.line(pts, fill=C(color_name, 255), width=thickness, joint="curve")
    return img


@functools.lru_cache(maxsize=64)
def stamp(text, kind="title", size=54, color_name="red", seed=2, alpha=235, box=True):
    """Press-stamp look: text in a rough double frame."""
    tw, th = text_size(text, kind, size)
    pad_x, pad_y = 34, 22
    w, h = tw + pad_x * 2, th + pad_y * 2
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    rng = random.Random(seed)
    col = C(color_name, alpha)
    for inset, wd in ((2, 3), (9, 1)):
        pts = []
        for x in range(inset, w - inset, 12):
            pts.append((x + rng.uniform(-1, 1), inset + rng.uniform(-1.2, 1.2)))
        for y in range(inset, h - inset, 12):
            pts.append((w - inset + rng.uniform(-1.2, 1.2), y + rng.uniform(-1, 1)))
        for x in range(w - inset, inset, -12):
            pts.append((x + rng.uniform(-1, 1), h - inset + rng.uniform(-1.2, 1.2)))
        for y in range(h - inset, inset, -12):
            pts.append((inset + rng.uniform(-1.2, 1.2), y + rng.uniform(-1, 1)))
        d.line(pts + [pts[0]], fill=col, width=wd, joint="curve")
    t = text_img(text, kind, size, color_name, alpha)
    img.alpha_composite(t, (int(w / 2 - t.width / 2), int(h / 2 - t.height / 2)))
    # distress
    rngm = Image.new("L", (w, h), 255)
    dm = ImageDraw.Draw(rngm)
    for _ in range(int(w * h / 2200)):
        x, y = rng.uniform(0, w), rng.uniform(0, h)
        r = rng.uniform(0.6, 2.4)
        dm.ellipse([x - r, y - r, x + r, y + r], fill=rng.randint(150, 235))
    img.putalpha(ImageChops.multiply(img.split()[3], rngm.filter(ImageFilter.GaussianBlur(0.5))))
    return img


def ease_out(t):
    t = min(1, max(0, t))
    return 1 - (1 - t) ** 3


def ease_in_out(t):
    t = min(1, max(0, t))
    return t * t * (3 - 2 * t)


def back_out(t, s=1.7):
    t = min(1, max(0, t))
    return 1 + (s + 1) * (t - 1) ** 3 + s * (t - 1) ** 2


def lerp(a, b, t):
    return a + (b - a) * t


def paste_alpha(base, img, xy, opacity=1.0):
    if opacity <= 0.01:
        return base
    if opacity < 0.995:
        img = img.copy()
        img.putalpha(img.split()[3].point(lambda v: int(v * opacity)))
    base.alpha_composite(img, (int(xy[0]), int(xy[1])))
    return base


def place(base, img, center, scale=1.0, rot=0.0, opacity=1.0):
    """Paste img centred at `center` with scale/rotation around its centre."""
    if scale <= 0.001 or opacity <= 0.01:
        return base
    w = max(1, int(img.width * scale))
    h = max(1, int(img.height * scale))
    im = img.resize((w, h), Image.LANCZOS) if (w != img.width or h != img.height) else img
    if abs(rot) > 0.05:
        im = im.rotate(rot, resample=Image.BICUBIC, expand=True)
    return paste_alpha(base, im, (center[0] - im.width / 2, center[1] - im.height / 2), opacity)


def blend(img_a, img_b, mask):
    """Composite img_b over img_a using an L mask."""
    return Image.composite(img_b, img_a, mask)


@functools.lru_cache(maxsize=32)
def person(color_name="navy", size=260, seed=1):
    """A simple standing paper-cut silhouette of a person."""
    w, h = int(size * 0.52), int(size)
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    col = C(color_name, 255)
    hr = w * 0.24
    d.ellipse([w / 2 - hr, h * 0.02, w / 2 + hr, h * 0.02 + hr * 2], fill=col)
    d.rounded_rectangle([w * 0.20, h * 0.20, w * 0.80, h * 0.56], radius=int(w * 0.16), fill=col)
    d.line([(w * 0.30, h * 0.55), (w * 0.20, h * 0.98)], fill=col, width=int(w * 0.13))
    d.line([(w * 0.70, h * 0.55), (w * 0.80, h * 0.98)], fill=col, width=int(w * 0.13))
    d.line([(w * 0.24, h * 0.26), (w * 0.06, h * 0.52)], fill=col, width=int(w * 0.11))
    d.line([(w * 0.76, h * 0.26), (w * 0.94, h * 0.52)], fill=col, width=int(w * 0.11))
    img = shade(img, paper_texture(w, h, seed), 0.3)
    m = torn_mask(w, h, seed, ("t", "b", "l", "r"), amp=4, step=9)
    img.putalpha(ImageChops.multiply(img.split()[3], m))
    return V_shadow_wrap(img)


def V_shadow_wrap(img):
    return with_shadow(img, (0, 8), 12, 120)
