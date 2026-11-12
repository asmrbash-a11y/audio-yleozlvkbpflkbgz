"""The fifteen scenes: camera, paper graphics, kinetic type."""
import math, os, functools
from PIL import Image, ImageDraw, ImageFilter, ImageChops
import visuals as V
from visuals import PAL, C, ease_out, ease_in_out, back_out, lerp, place, paste_alpha
import engine as E
from engine import W, H, camera, darken, scrim

HERE = os.path.dirname(os.path.abspath(__file__))


@functools.lru_cache(maxsize=16)
def cutout(art_name, box, seed=1, scale=1.0):
    """A torn paper cut-out of a region of another collage (bx0,by0,bx1,by1 in 0..1)."""
    src = E.load_art(art_name)
    bx0, by0, bx1, by1 = box
    box_px = (int(bx0 * src.width), int(by0 * src.height), int(bx1 * src.width), int(by1 * src.height))
    piece = src.crop(box_px)
    if scale != 1.0:
        piece = piece.resize((int(piece.width * scale), int(piece.height * scale)), Image.LANCZOS)
    piece = piece.convert("RGBA")
    m = V.torn_mask(piece.width, piece.height, seed, ("t", "b", "l", "r"), amp=16, step=16)
    piece.putalpha(m)
    # paper rim
    rim = ImageChops.subtract(m.filter(ImageFilter.MaxFilter(3)), m).filter(ImageFilter.GaussianBlur(0.7))
    lightc = Image.new("RGBA", piece.size, (250, 244, 230, 120))
    lightc.putalpha(rim)
    piece = Image.alpha_composite(piece, lightc)
    return V.with_shadow(piece, (0, 16), 20, 130)


def art_or(name, fallback):
    return name if os.path.exists(os.path.join(E.ART_DIR, name + ".png")) else fallback


# --------------------------------------------------------------- helpers
def show(frame, img, cx, cy, t, t0, t1=None, style="drop", rot=0.0, scale=1.0,
         dur=0.36, opacity=1.0):
    """Animate one paper element onto the frame."""
    if t < t0:
        return frame
    p = (t - t0) / dur
    op = opacity
    if t1 is not None and t >= t1 - 0.22:
        op *= max(0.0, (t1 - t) / 0.22)
    if style == "drop":
        e = back_out(min(1, p), 1.5)
        dy = (1 - ease_out(min(1, p))) * -52
        return place(frame, img, (cx, cy + dy), scale * (0.94 + 0.06 * e), rot, op * min(1, p * 2.2))
    if style == "rise":
        dy = (1 - ease_out(min(1, p))) * 64
        return place(frame, img, (cx, cy + dy), scale, rot, op * min(1, p * 2.2))
    if style == "stamp":
        e = back_out(min(1, p), 2.4)
        s = scale * (1.55 - 0.55 * e)
        r = rot + (1 - min(1, p)) * 8
        return place(frame, img, (cx, cy), s, r, op * min(1, p * 3.0))
    if style == "slide_r":
        dx = (1 - ease_out(min(1, p))) * 220
        return place(frame, img, (cx + dx, cy), scale, rot, op * min(1, p * 2.0))
    if style == "slide_l":
        dx = (1 - ease_out(min(1, p))) * -220
        return place(frame, img, (cx + dx, cy), scale, rot, op * min(1, p * 2.0))
    if style == "pop":
        e = back_out(min(1, p), 2.0)
        return place(frame, img, (cx, cy), scale * (0.6 + 0.4 * e), rot, op * min(1, p * 3))
    if style == "type":
        return place(frame, img, (cx, cy), scale, rot, op * min(1, p * 3))
    return place(frame, img, (cx, cy), scale, rot, op)


@functools.lru_cache(maxsize=256)
def chip(text, kind="title_b", size=54, bg="cream", fg="ink", seed=1, pad=(38, 22),
         edge=("t", "b"), amp=6):
    tw, th = V.text_size(text, kind, size)
    w, h = int(tw + pad[0] * 2), int(th + pad[1] * 2)
    sheetimg = V.sheet(w, h, bg, seed=seed, edges=edge, amp=amp, alpha=250, fiber=0.16)
    t = V.text_img(text, kind, size, fg, 250)
    sheetimg.alpha_composite(t, (int(w / 2 - t.width / 2), int(h / 2 - t.height / 2)))
    return V.with_shadow(sheetimg, (0, 12), 15, 105)


@functools.lru_cache(maxsize=128)
def strip(text, kind="title", size=78, bg="cream", fg="ink", seed=2, pad=(52, 30), rot=0.0):
    tw, th = V.text_size(text, kind, size)
    w, h = int(tw + pad[0] * 2), int(th + pad[1] * 2)
    s = V.sheet(w, h, bg, seed=seed, edges=("t", "b"), amp=11, alpha=252, fiber=0.18)
    t = V.text_img(text, kind, size, fg, 252)
    s.alpha_composite(t, (int(w / 2 - t.width / 2), int(h / 2 - t.height / 2)))
    d = ImageDraw.Draw(s)
    d.rectangle([5, 5, w - 6, h - 6], outline=(0, 0, 0, 22), width=2)
    out = V.with_shadow(s, (0, 14), 18, 120)
    return out.rotate(rot, resample=Image.BICUBIC, expand=True) if rot else out


@functools.lru_cache(maxsize=256)
def typed(text, kind, size, color, alpha=255, shadow=True):
    img = V.text_img(text, kind, size, color, alpha)
    if not shadow:
        return img
    pad = 26
    out = Image.new("RGBA", (img.width + pad * 2, img.height + pad * 2), (0, 0, 0, 0))
    sh = Image.new("RGBA", img.size, (6, 9, 18, 200))
    sh.putalpha(img.split()[3].filter(ImageFilter.GaussianBlur(10)).point(lambda v: int(v * 0.55)))
    out.alpha_composite(sh, (pad + 3, pad + 7))
    out.alpha_composite(img, (pad, pad))
    return out


def shake(frame, amount=10.0, speed=42.0, t=0.0, decay=0.0):
    dx = int(math.sin(t * speed) * amount)
    dy = int(math.cos(t * speed * 1.37) * amount * 0.7)
    return frame.transform((W, H), Image.AFFINE, (1, 0, -dx, 0, 1, -dy), resample=Image.BILINEAR)


def white_flash(frame, amount):
    if amount <= 0.004:
        return frame
    return Image.alpha_composite(frame, Image.new("RGBA", (W, H), (252, 246, 232, int(255 * min(1, amount)))))


def kicker(frame, text, t, t0=0.12, y=286, bg="navy", fg="cream", seed=11):
    img = chip(text, "title_b", 46, bg=bg, fg=fg, seed=seed, pad=(30, 16))
    return show(frame, img, W / 2, y, t, t0, style="drop")


def graded(name, t, keys, **kw):
    return camera(name, t, keys, grade_kw=kw or None)


# --------------------------------------------------------------- scenes
CAM = {
    "title":     [(0, 1.26, 0.50, 0.44, 0), (3.2, 1.08, 0.50, 0.48, 0), (7.2, 1.18, 0.52, 0.55, 0)],
    "flight":    [(0, 1.04, 0.50, 0.40, 0), (6.9, 1.18, 0.50, 0.52, 1.6)],
    "lightning": [(0, 1.08, 0.50, 0.50, 0), (3.0, 1.22, 0.52, 0.44, -2.2), (5.2, 1.30, 0.50, 0.42, -1.0)],
    "breakup":   [(0, 1.14, 0.50, 0.44, 0), (2.6, 1.02, 0.50, 0.50, 2.6), (4.0, 1.20, 0.50, 0.50, 1.2)],
    "freefall":  [(0, 1.24, 0.50, 0.42, -3.0), (3.5, 1.38, 0.50, 0.50, 3.0), (6.9, 1.50, 0.50, 0.58, 5.0)],
    "waking":    [(0, 1.24, 0.50, 0.56, 0), (3.0, 1.06, 0.50, 0.50, 0), (6.8, 1.14, 0.48, 0.46, -1.2)],
    "wreckage":  [(0, 1.18, 0.50, 0.50, 0), (3.2, 1.04, 0.50, 0.42, 1.2), (6.8, 1.14, 0.50, 0.50, 0)],
    "advice":    [(0, 1.12, 0.50, 0.52, 0), (5.4, 1.02, 0.50, 0.44, 0)],
    "jungle":    [(0, 1.20, 0.50, 0.54, 0), (6.3, 1.38, 0.50, 0.62, 1.8)],
    "ten-days":  [(0, 1.36, 0.50, 0.58, 0), (5.8, 1.54, 0.50, 0.62, 2.2)],
    "hut":       [(0, 1.22, 0.50, 0.56, 0), (4.2, 1.04, 0.50, 0.46, 0)],
    "rescue":    [(0, 1.16, 0.50, 0.52, 0), (4.7, 1.36, 0.50, 0.58, -1.6)],
    "twice":     [(0, 1.06, 0.50, 0.50, 0)],
    "only-one":  [(0, 1.0, 0.5, 0.5, 0)],
    "outro":     [(0, 1.18, 0.50, 0.48, 0), (5.7, 1.00, 0.50, 0.44, 0)],
}


def s_title(t, sc):
    f = graded("01_fall", t, CAM["title"], tint=((255, 226, 176), 0.10), sat=1.06, contrast=1.04)
    f = f.convert("RGBA")
    f = Image.alpha_composite(f, scrim("center", 205, 1000))
    f = Image.alpha_composite(f, scrim("bottom", 150, 620))
    # big title block
    f = show(f, typed("الفتاة التي", "title", 86, "cream"), W / 2, 540, t, 0.10, style="drop")
    f = show(f, typed("سقطت من السماء", "title", 98, "cream"), W / 2, 686, t, 0.52, style="drop")
    yel = typed("ونجت!", "title", 132, "yellow")
    f = show(f, yel, W / 2, 872, t, 0.98, style="pop")
    f = show(f, V.underline(380, 12, "yellow", seed=3), W / 2, 972, t, 1.25, style="rise", dur=0.3)
    f = show(f, V.stamp("قصة نجاة حقيقية", "title_b", 44, "red", seed=5), 740, 1105, t, 1.9,
             style="stamp", rot=-7, scale=0.92)
    return f


def s_flight(t, sc):
    f = graded("02_plane_jungle", t, CAM["flight"], sat=1.04, contrast=1.03)
    f = f.convert("RGBA")
    f = kicker(f, "بيرو · 1971", t, 0.1)
    card = chip("جوليان كوبكه", "title_b", 50, "cream", "ink", seed=23, pad=(34, 18))
    f = show(f, card, W / 2, 1080, t, 0.9, style="drop")
    card2 = chip("17 عاماً", "title", 64, "yellow", "ink", seed=31, pad=(40, 18))
    f = show(f, card2, W / 2, 1210, t, 2.1, style="pop")
    return f


def s_lightning(t, sc):
    f = graded("03_storm", t, CAM["lightning"], tint=((20, 34, 62), 0.14), contrast=1.10, bright=0.92, sat=0.96)
    f = f.convert("RGBA")
    strike = 1.30
    if 0 <= t - strike < 0.6:
        k = max(0.0, 1 - (t - strike) / 0.6)
        f = white_flash(f, 0.55 * k ** 1.6)
        f = shake(f, amount=16 * k, t=t, speed=60)
    f = kicker(f, "الكابوس", t, 0.2, bg="red", fg="cream", seed=44)
    f = Image.alpha_composite(f, scrim("bottom", 165, 700))
    f = show(f, strip("البرق", "title", 96, "cream", "red", seed=51, rot=-3), W / 2, 1120, t, 1.35, style="stamp")
    f = show(f, chip("عاصفة عنيفة", "title", 66, "navy", "cream", seed=52), W / 2, 1300, t, 3.05, style="rise")
    return f


def s_breakup(t, sc):
    f = graded("04_breakup", t, CAM["breakup"], contrast=1.08, sat=1.02, bright=0.96)
    f = f.convert("RGBA")
    if t < 0.5:
        f = shake(f, amount=9 * (1 - t / 0.5), t=t, speed=70)
    f = show(f, strip("انفصل الجناح", "title", 82, "red", "cream", seed=61, rot=2), W / 2, 1090, t, 0.15, style="stamp")
    f = show(f, V.hand_arrow(230, 9, "yellow", 0.4, seed=12, flip=True), 300, 1280, t, 1.1,
             style="rise", rot=-38, scale=0.9)
    f = show(f, chip("تتفكك في السماء", "title_b", 50, "cream", "ink", seed=71), 660, 1330, t, 1.9, style="drop")
    return f


def s_freefall(t, sc):
    f = graded("05_freefall", t, CAM["freefall"], tint=((40, 60, 96), 0.08), contrast=1.06)
    f = f.convert("RGBA")
    # rolling altitude counter
    c0, c1 = 2.95, 3.75
    if t >= c0:
        p = ease_out(min(1, (t - c0) / (c1 - c0)))
        val = int(round(3000 * p))
        card = V.sheet(470, 240, "cream", seed=81, edges=("t", "b"), amp=10, alpha=250, fiber=0.18)
        num = V.text_img(f"{val}", "latin", 118, "ink", 255, direction="ltr")
        card.alpha_composite(num, (int(235 - num.width / 2), 40))
        lab = V.text_img("ارتفاع السقوط · متر", "title_b", 44, "ink", 225)
        card.alpha_composite(lab, (int(235 - lab.width / 2), 172))
        card = V.with_shadow(card, (0, 14), 18, 120)
        f = show(f, card, W / 2, 1090, t, c0 - 0.18, style="drop")
    f = show(f, chip("مربوطة بمقعدها", "title_b", 52, "navy", "cream", seed=91), W / 2, 1290, t, 5.3, style="rise")
    return f


def s_waking(t, sc):
    f = graded("06_waking", t, CAM["waking"], tint=((255, 214, 150), 0.10), sat=1.06, bright=1.04)
    f = f.convert("RGBA")
    if t < 0.7:
        f = white_flash(f, 0.85 * (1 - t / 0.7) ** 1.4)
    f = Image.alpha_composite(f, scrim("bottom", 120, 760))
    plate = V.sheet(420, 190, "navy", seed=101, edges=("t", "b", "l", "r"), amp=9, alpha=252, fiber=0.16)
    mt = V.text_img("المعجزة", "title", 96, "yellow", 255)
    plate.alpha_composite(mt, (int(210 - mt.width / 2), int(95 - mt.height / 2)))
    plate = V.with_shadow(plate, (0, 16), 20, 130)
    f = show(f, plate, W / 2, 1080, t, 0.85, style="stamp", rot=-3.5)
    f = show(f, chip("كسر في عظمة الترقوة", "title_b", 48, "cream", "ink", seed=111), W / 2, 1250, t, 3.9,
             style="drop")
    f = show(f, chip("جروح في جسدها", "title_b", 48, "red", "cream", seed=112), W / 2, 1370, t, 5.5,
             style="drop")
    return f


def s_wreckage(t, sc):
    f = graded("07_wreckage", t, CAM["wreckage"], sat=0.88, contrast=1.05, tint=((30, 44, 60), 0.12))
    f = f.convert("RGBA")
    f = kicker(f, "بعد ساعات", t, 0.1, bg="navy", fg="cream", seed=12)
    y = 1030
    f = show(f, chip("الأم: مفقودة", "title_b", 52, "red", "cream", seed=121), 480, y, t, 0.5, style="slide_r")
    f = show(f, chip("الطائرة: محطّمة", "title_b", 52, "cream", "ink", seed=122), 500, y + 118, t, 1.7, style="slide_r")
    f = show(f, chip("لا أحد حولها", "title_b", 52, "navy", "cream", seed=123), 520, y + 236, t, 3.0, style="slide_r")
    return f


def s_advice(t, sc):
    f = graded("08_river", t, CAM["advice"], tint=((255, 220, 170), 0.06), sat=1.04)
    f = f.convert("RGBA")
    quote = Image.new("RGBA", (820, 330), (0, 0, 0, 0))
    sheetq = V.sheet(820, 330, "cream", seed=131, edges=("t", "b", "l", "r"), amp=9, alpha=252, fiber=0.2)
    quote.alpha_composite(sheetq)
    head = V.text_img("نصيحة والدها", "title_b", 44, "red", 235)
    quote.alpha_composite(head, (int(410 - head.width / 2), 42))
    q = V.text_img("اتبعي مجرى الماء", "amiri", 96, "ink", 252)
    quote.alpha_composite(q, (int(410 - q.width / 2), 120))
    quote.alpha_composite(V.underline(420, 9, "yellow", seed=17), (200, 258))
    tp = V.tape(150, 46, seed=5, alpha=210)
    quote.alpha_composite(tp, (30, -18))
    tp2 = V.tape(150, 46, seed=6, alpha=210).rotate(-8, expand=True)
    quote.alpha_composite(tp2, (640, -20))
    quote = V.with_shadow(quote, (0, 18), 22, 130)
    f = show(f, quote, W / 2, 1080, t, 1.15, style="drop", rot=-2.2)
    f = show(f, V.hand_arrow(260, 10, "yellow", 0.45, seed=21), 700, 1330, t, 2.7, style="rise", rot=62)
    f = show(f, chip("يقودك إلى البشر", "title_b", 48, "navy", "cream", seed=141), W / 2, 1400, t, 3.5,
             style="rise")
    return f


def s_jungle(t, sc):
    f = graded("09_dark_jungle", t, CAM["jungle"], tint=((10, 24, 34), 0.16), bright=0.86, contrast=1.1, sat=0.92)
    f = f.convert("RGBA")
    f = kicker(f, "وحدها في الأمازون", t, 0.1, bg="navy", fg="cream", seed=13)
    items = [("حشرات", 0.6, "yellow"), ("حيوانات مفترسة", 1.9, "red"), ("بلا طعام", 3.6, "navy")]
    y = 1060
    for i, (txt, t0, bg) in enumerate(items):
        f = show(f, chip(txt, "title_b", 52, bg, "cream" if bg != "yellow" else "ink", seed=151 + i),
                 520, y + i * 116, t, t0, style="slide_r")
    return f


def s_tendays(t, sc):
    f = graded("09_dark_jungle", t, CAM["ten-days"], tint=((8, 18, 30), 0.22), bright=0.74, contrast=1.14, sat=0.85)
    f = f.convert("RGBA")
    # day counter 1 -> 10
    c0, c1 = 0.10, 1.05
    p = ease_out(min(1, max(0, (t - c0) / (c1 - c0))))
    day = max(1, int(round(1 + 9 * p)))
    card = V.sheet(560, 300, "cream", seed=161, edges=("t", "b"), amp=11, alpha=252, fiber=0.18)
    num = V.text_img(str(day), "latin", 150, "ink", 255, direction="ltr")
    card.alpha_composite(num, (int(280 - num.width / 2), 26))
    lab = V.text_img("أيام في الغابة", "title_b", 46, "ink", 230)
    card.alpha_composite(lab, (int(280 - lab.width / 2), 214))
    for i in range(10):
        on = i < day
        col = C("yellow", 255) if on else (0, 0, 0, 40)
        d = ImageDraw.Draw(card)
        d.ellipse([56 + i * 45, 268, 76 + i * 45, 288], fill=col)
    card = V.with_shadow(card, (0, 14), 18, 125)
    f = show(f, card, W / 2, 1040, t, 0.02, style="drop")
    words = [("الألم", 1.5, "red"), ("الجوع", 2.4, "yellow"), ("الخوف", 3.2, "navy")]
    for i, (txt, t0, bg) in enumerate(words):
        f = show(f, chip(txt, "title", 56, bg, "cream" if bg != "yellow" else "ink", seed=171 + i),
                 300 + i * 240, 1320, t, t0, style="pop")
    return f


def s_hut(t, sc):
    f = graded(art_or("10_hut", "08_river"), t, CAM["hut"], tint=((255, 206, 148), 0.10), sat=1.06, bright=1.02)
    f = f.convert("RGBA")
    f = kicker(f, "اليوم العاشر", t, 0.1, bg="yellow", fg="ink", seed=14)
    f = Image.alpha_composite(f, scrim("bottom", 130, 640))
    f = show(f, V.hand_circle(360, 250, 8, "yellow", seed=31), 540, 900, t, 0.9, style="type", dur=0.55)
    f = show(f, chip("كوخ صغير قرب النهر", "title_b", 54, "cream", "ink", seed=181), W / 2, 1240, t, 1.6,
             style="drop")
    return f


def s_rescue(t, sc):
    f = graded("08_river", t, [(0, 1.12, 0.50, 0.66, 0), (4.7, 1.26, 0.52, 0.72, -1.4)],
               tint=((255, 198, 138), 0.14), sat=1.12, bright=1.05)
    f = f.convert("RGBA")
    if t < 0.4:
        f = white_flash(f, 0.30 * (1 - t / 0.4))
    f = Image.alpha_composite(f, scrim("bottom", 195, 760))
    f = show(f, V.hand_arrow(230, 10, "yellow", 0.4, seed=33), 250, 1000, t, 0.7, style="rise", rot=118, scale=0.9)
    f = show(f, strip("الإنقاذ", "title", 92, "cream", "red", seed=191, rot=-2), W / 2, 1150, t, 0.45,
             style="stamp")
    f = show(f, chip("وجدوها!", "title", 78, "navy", "yellow", seed=192, pad=(46, 22)),
             W / 2, 1310, t, 2.0, style="pop")
    f = show(f, chip("رجال محليون · في اليوم التالي", "title_b", 42, "cream", "ink", seed=201),
             W / 2, 1430, t, 3.3, style="rise")
    return f


def s_twice(t, sc):
    f = Image.new("RGBA", (W, H), PAL["navy"])
    f = Image.alpha_composite(f, V.paper_texture(W, H, 7).convert("RGBA") if False else Image.new("RGBA", (W, H), (0, 0, 0, 0)))
    # two panels
    top = camera("02_plane_jungle", t, [(0, 1.10, 0.5, 0.45, 0), (6.3, 1.22, 0.5, 0.52, 1.5)], grade_kw=dict(sat=1.02))
    bot = camera("08_river", t, [(0, 1.12, 0.5, 0.55, 0), (6.3, 1.26, 0.5, 0.62, -1.5)], grade_kw=dict(sat=1.02))
    tp = top.crop((0, 180, W, 180 + 700)).resize((W, 700), Image.LANCZOS)
    bp = bot.crop((0, 520, W, 520 + 700)).resize((W, 700), Image.LANCZOS)
    # panels slide in, then settle
    e1 = ease_out(min(1, t / 0.55))
    e2 = ease_out(min(1, max(0, (t - 0.45) / 0.55)))
    f.paste(tp, (int(-W * (1 - e1)), 250))
    f.paste(bp, (int(W * (1 - e2)), 1010))
    f = Image.alpha_composite(f, scrim("bottom", 170, 700))
    tape = V.tape(W - 60, 62, seed=9, alpha=225)
    f = show(f, tape, W / 2, 978, t, 1.0, style="pop", rot=-1.5)
    f = show(f, chip("سقوط طائرة", "title_b", 50, "red", "cream", seed=211), 300, 380, t, 1.1, style="slide_r")
    f = show(f, chip("عشرة أيام في الأمازون", "title_b", 46, "navy", "cream", seed=212), 440, 1140, t, 1.5,
             style="slide_l")
    return f


@functools.lru_cache(maxsize=4)
def seat_glyph(color_name, size=84):
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse([size * 0.32, size * 0.06, size * 0.68, size * 0.42], fill=C(color_name, 255))
    d.rounded_rectangle([size * 0.22, size * 0.46, size * 0.78, size * 0.94], radius=int(size * 0.16),
                        fill=C(color_name, 255))
    return img.filter(ImageFilter.GaussianBlur(0.4))


def s_onlyone(t, sc):
    base = V.sheet(W, H, "navy", seed=221, edges=(), amp=0, alpha=255, fiber=0.3)
    f = Image.alpha_composite(Image.new("RGBA", (W, H), PAL["navy2"]), base)
    f = Image.alpha_composite(f, V.halftone(W, H, 11, 2.2, "cream", 26, 24))
    f = kicker(f, "كانوا على متن الطائرة", t, 0.1, bg="cream", fg="ink", seed=15)
    # 92 seats
    cols, rows = 10, 10
    cw, ch = 100, 100
    x0 = W / 2 - (cols - 1) * cw / 2
    y0 = 480
    for i in range(92):
        cx = x0 + (i % cols) * cw
        cy = y0 + (i // cols) * ch
        t0 = 0.25 + i * 0.016
        if t < t0:
            continue
        highlight = i == 46
        p = min(1, (t - t0) / 0.3)
        e = back_out(p, 2.0)
        if highlight:
            col = "yellow"
            s = 0.95 * (0.55 + 0.45 * e) * (1 + 0.42 * ease_out(min(1, max(0, (t - 1.9) / 0.6))))
            op = 1.0
        else:
            col = "cream"
            dim = ease_out(min(1, max(0, (t - 1.9) / 0.7)))
            op = 0.62 * (1 - 0.72 * dim) * min(1, p * 2)
            s = 0.95 * (0.55 + 0.45 * e)
        g = seat_glyph(col)
        f = place(f, g, (cx, cy), s, 0, op)
    # the one
    if t > 1.75:
        k = ease_out(min(1, (t - 1.75) / 0.6))
        ring = V.hand_circle(210, 200, 7, "yellow", seed=41)
        f = place(f, ring, (x0 + 6 * cw, y0 + 4 * ch), 0.9 * (0.8 + 0.2 * k), 0, 0.85 * k)
    # numbers
    if t > 2.5:
        n1 = typed("1", "latin", 190, "yellow")
        f = show(f, n1, 790, 1330, t, 2.5, style="pop")
        na2 = typed("ناجية", "title_b", 52, "yellow")
        f = show(f, na2, 790, 1452, t, 2.72, style="drop")
        mn = typed("من", "title_b", 62, "cream")
        f = show(f, mn, 630, 1340, t, 2.95, style="type")
        n92 = typed("92", "latin", 130, "cream")
        f = show(f, n92, 460, 1340, t, 3.1, style="pop")
        na = typed("شخصاً", "title_b", 52, "cream")
        f = show(f, na, 460, 1452, t, 3.3, style="drop")
    return f


def s_outro(t, sc):
    f = graded("01_fall", t, CAM["outro"], tint=((255, 222, 172), 0.12), sat=1.05, bright=1.02)
    f = f.convert("RGBA")
    f = Image.alpha_composite(f, scrim("center", 225, 1000))
    f = Image.alpha_composite(f, scrim("bottom", 160, 560))
    f = show(f, typed("أحياناً، تكون الرغبة في الحياة", "amiri", 72, "cream"), W / 2, 690, t, 0.15, style="rise")
    f = show(f, typed("أقوى من كل احتمالات الموت", "amiri", 80, "yellow"), W / 2, 820, t, 0.75, style="rise")
    f = show(f, V.underline(500, 10, "yellow", seed=27), W / 2, 912, t, 1.1, style="rise", dur=0.3)
    # credit card
    card = Image.new("RGBA", (800, 320), (0, 0, 0, 0))
    card.alpha_composite(V.sheet(800, 320, "cream", seed=241, edges=("t", "b", "l", "r"), amp=8, alpha=255, fiber=0.18))
    l1 = V.text_img("إعداد وإخراج", "bold", 48, "red", 255)
    card.alpha_composite(l1, (int(400 - l1.width / 2), 44))
    l2 = V.text_img("Shaaib Beshr", "latin", 64, "ink", 255, direction="ltr")
    card.alpha_composite(l2, (int(400 - l2.width / 2), 116))
    card.alpha_composite(V.underline(440, 9, "yellow", seed=29), (180, 216))
    l3 = V.text_img("وثائقي · موشن جرافيك", "bold", 36, "ink", 215)
    card.alpha_composite(l3, (int(400 - l3.width / 2), 248))
    card = V.with_shadow(card, (0, 18), 24, 140)
    f = show(f, card, W / 2, 1195, t, 4.35, style="drop", rot=-1.4)
    # fade out
    if t > 5.05:
        k = min(1, (t - 5.05) / 0.6)
        f = Image.alpha_composite(f, Image.new("RGBA", (W, H), (10, 14, 26, int(255 * k * 0.92))))
    return f


SCENE_FNS = {
    "title": s_title, "flight": s_flight, "lightning": s_lightning, "breakup": s_breakup,
    "freefall": s_freefall, "waking": s_waking, "wreckage": s_wreckage, "advice": s_advice,
    "jungle": s_jungle, "ten-days": s_tendays, "hut": s_hut, "rescue": s_rescue,
    "twice": s_twice, "only-one": s_onlyone, "outro": s_outro,
}
