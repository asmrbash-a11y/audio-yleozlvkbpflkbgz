"""توليد الأصوات رقمياً بـ numpy/scipy: مطر، غابة، رعد، ارتطام، تصدّع، ورق.

كل الأصوات مركّبة من ضجيج ونغمات مُصفّاة — بلا أي مادة محمية — والناتج حتمي
(بذرة ثابتة) فلا يتغيّر المزيج بين تشغيلين.
"""
import os
import numpy as np
from scipy import signal

SR = 48000
RNG = np.random.default_rng(20261112)


def _sos(kind, fc, order=2, btype=None):
    return signal.butter(order, fc, btype=kind, fs=SR, output="sos")


def band(x, lo, hi, order=2):
    return signal.sosfilt(_sos("bandpass", [lo, hi], order), x).astype(np.float32)


def lowpass(x, fc, order=2):
    return signal.sosfilt(_sos("lowpass", fc, order), x).astype(np.float32)


def highpass(x, fc, order=2):
    return signal.sosfilt(_sos("highpass", fc, order), x).astype(np.float32)


def noise(n):
    return RNG.standard_normal(n).astype(np.float32)


def brown(n):
    x = np.cumsum(noise(n))
    x -= signal.sosfilt(_sos("highpass", 8, 1), x)
    return (x / (np.abs(x).max() + 1e-9)).astype(np.float32)


def env_adsr(n, a, d, curve=4.0):
    e = np.ones(n, np.float32)
    na = max(1, int(a * SR))
    e[:na] = np.linspace(0, 1, na, dtype=np.float32)
    t = np.arange(n, dtype=np.float32) / SR
    e *= np.exp(-curve * t).astype(np.float32)
    return e


def soft_reverb(x, decay=0.18, mix=0.25, seed=7):
    r = np.random.default_rng(seed)
    n = int(decay * 4 * SR)
    ir = r.standard_normal(n).astype(np.float32) * np.exp(-np.arange(n) / (decay * SR)).astype(np.float32)
    ir = band(ir, 250, 5000)
    ir /= np.abs(ir).max() + 1e-9
    y = signal.fftconvolve(x, ir)[: len(x)].astype(np.float32)
    return ((1 - mix) * x + mix * y / (np.abs(y).max() + 1e-9) * (np.abs(x).max() + 1e-9)).astype(np.float32)


def norm(x, db_peak=-3.0):
    return (x / (np.abs(x).max() + 1e-9) * 10 ** (db_peak / 20)).astype(np.float32)


# ------------------------------------------------------------------ المطر
def rain(dur=14.0, density=55.0, warm=1.0):
    """هسيس ناعم + قطرات منفصلة — يُسمع كمطر لا كضجيج ميكروفون."""
    n = int(dur * SR)
    base = highpass(noise(n), 220)
    base = lowpass(base, 5200)
    base = band(base, 250, 5200, order=1) * 0.8 + base * 0.2
    t = np.arange(n) / SR
    # تنفّس بطيء للمطر (لا تُسمع دورية واضحة)
    mod = (0.80 + 0.10 * np.sin(2 * np.pi * 0.07 * t) + 0.06 * np.sin(2 * np.pi * 0.19 * t + 1.1)).astype(np.float32)
    base *= mod
    # قطرات: نبضات قصيرة عشوائية
    drops = np.zeros(n, np.float32)
    count = int(density * dur)
    pos = RNG.integers(0, n - 2000, count)
    for p in pos:
        ln = int(RNG.integers(180, 900))
        g = RNG.uniform(0.15, 0.9) ** 2
        f = RNG.uniform(1200, 4200)
        seg = noise(ln) * np.exp(-np.arange(ln) / (ln * 0.28)).astype(np.float32)
        drops[p:p + ln] += band(seg, f * 0.7, min(f * 1.6, 8000)) * g
    drops = soft_reverb(drops, 0.09, 0.18, seed=11)
    mixx = base * 0.55 + norm(drops, -8) * 0.45
    if warm > 1:
        mixx = lowpass(mixx, 6400)
    return norm(mixx, -6)


# ------------------------------------------------------------------ الغابة
def jungle(dur=14.0):
    """حشرات نبضية + طيور صغيرة + طنين غابة منخفض."""
    n = int(dur * SR)
    t = np.arange(n) / SR
    out = np.zeros(n, np.float32)
    # حشرات: مجموعات نبضية 3.6–5.2 كيلو
    for f0, rate, amp in ((3860, 23.0, 0.5), (4620, 17.0, 0.35), (5250, 29.0, 0.22)):
        pulse = (0.5 + 0.5 * np.sign(np.sin(2 * np.pi * rate * t))).astype(np.float32)
        pulse = lowpass(pulse, 600, 1)
        out += (amp * np.sin(2 * np.pi * f0 * t).astype(np.float32)) * pulse
    out = band(out, 2600, 7000) * 0.35
    # طنين الغابة
    hum = lowpass(brown(n), 140, 2) * 0.25
    out += hum
    # طيور
    out = out.copy()
    for k in range(7):
        st = RNG.uniform(0.4, dur - 1.2)
        d = RNG.uniform(0.07, 0.16)
        f0 = RNG.uniform(1900, 3100)
        f1 = f0 * RNG.uniform(0.8, 1.35)
        m = int(d * SR)
        tt = np.arange(m) / SR
        f = f0 + (f1 - f0) * (tt / d)
        ph = 2 * np.pi * np.cumsum(f) / SR
        chirp = np.sin(ph).astype(np.float32) * np.sin(np.pi * tt / d).astype(np.float32) ** 2
        i = int(st * SR)
        out[i:i + m] += chirp * RNG.uniform(0.10, 0.26)
    return norm(soft_reverb(out, 0.22, 0.3, seed=5), -8)


# ------------------------------------------------------------------ الرعد
def thunder(near=True):
    """هدير منخفض طويل؛ القريب يبدأ بصفعة عريضة."""
    dur = 4.6 if not near else 3.8
    n = int(dur * SR)
    t = np.arange(n) / SR
    body = lowpass(brown(n), 150 if near else 105, 2)
    body = lowpass(body, 240 if near else 160, 1)
    roll = (np.exp(-(t / (1.5 if near else 2.6)) ** 0.7)).astype(np.float32)
    # تمويج الهدير كأنه يتدحرج
    roll *= (0.75 + 0.25 * np.sin(2 * np.pi * 1.7 * t + 0.4)).astype(np.float32)
    out = body * roll
    if near:
        m = int(0.55 * SR)
        crack = band(noise(m), 700, 4200) * np.exp(-np.arange(m) / (0.06 * SR)).astype(np.float32)
        out[:m] += norm(crack, -10) * 1.0
    return norm(soft_reverb(out, 0.5, 0.22, seed=3), -5)


# ------------------------------------------------------------------ ارتطام
def impact(dur=2.4):
    n = int(dur * SR)
    t = np.arange(n) / SR
    f = 62 * np.exp(-2.6 * t) + 27
    sub = np.sin(2 * np.pi * np.cumsum(f) / SR).astype(np.float32) * np.exp(-4.2 * t).astype(np.float32)
    m = int(0.4 * SR)
    slap = lowpass(band(noise(m), 180, 2600), 3000) * np.exp(-np.arange(m) / (0.05 * SR)).astype(np.float32)
    out = sub * 1.0
    out[:m] += norm(slap, -12) * 1.6
    # رنين خشبي قصير
    wood = (np.sin(2 * np.pi * 186 * t) * np.exp(-18 * t) + 0.5 * np.sin(2 * np.pi * 311 * t) * np.exp(-24 * t)).astype(np.float32)
    out += wood * 0.22
    return norm(soft_reverb(out, 0.25, 0.18, seed=9), -3)


def crack(dur=1.6):
    n = int(dur * SR)
    t = np.arange(n) / SR
    body = band(noise(n), 900, 5200) * np.exp(-6.5 * t).astype(np.float32)
    metal = (np.sin(2 * np.pi * 1480 * t) * np.exp(-9 * t) + 0.6 * np.sin(2 * np.pi * 2270 * t) * np.exp(-13 * t)).astype(np.float32)
    out = body * 0.9 + metal * 0.25
    return norm(soft_reverb(out, 0.2, 0.25, seed=13), -4)


def paper(dur=0.75):
    n = int(dur * SR)
    t = np.arange(n) / SR
    x = band(noise(n), 900, 6000)
    e = np.minimum(1, t / 0.12) * np.exp(-3.2 * np.maximum(0, t - 0.12)).astype(np.float32)
    return norm(x * e, -6)


def riser(dur=1.6):
    n = int(dur * SR)
    t = np.arange(n) / SR
    x = band(noise(n), 500, 7000)
    sweep = np.clip(t / dur, 0, 1).astype(np.float32)
    x *= sweep ** 2
    tone = np.sin(2 * np.pi * np.cumsum(180 + 900 * sweep) / SR).astype(np.float32) * sweep ** 3 * 0.25
    return norm(x + tone, -5)




# ------------------------------------------------------------------ أصوات النصف الثاني
def water(dur=14.0):
    """جدول ماء رقراق: ضجيج مُرشَّح بتعديل عشوائي — يتبع النصيحة «اتبعي مجرى الماء»."""
    n = int(dur * SR)
    t = np.arange(n) / SR
    base = band(noise(n), 380, 5200, 2)
    bubbles = np.zeros(n, np.float32)
    for _ in range(int(28 * dur)):
        p = RNG.integers(0, n - 1200)
        ln = int(RNG.integers(120, 420))
        f = RNG.uniform(600, 2400)
        seg = np.sin(2 * np.pi * f * np.arange(ln) / SR).astype(np.float32) * np.exp(-np.arange(ln) / (ln * 0.3)).astype(np.float32)
        bubbles[p:p + ln] += seg * RNG.uniform(0.05, 0.22)
    mod = (0.6 + 0.25 * np.sin(2 * np.pi * 0.11 * t) + 0.15 * np.sin(2 * np.pi * 0.29 * t + 0.7)).astype(np.float32)
    out = band(base, 400, 4800, 1) * mod * 0.5 + bubbles
    return norm(soft_reverb(out, 0.16, 0.2, seed=21), -8)


def heartbeat(dur=14.0, bpm=62.0):
    """نَبضتان لكل ضربة — لأيام الألم والجوع والخوف."""
    n = int(dur * SR)
    out = np.zeros(n, np.float32)
    per = 60.0 / bpm
    t0 = 0.0
    while t0 < dur - 0.5:
        for off, amp in ((0.0, 1.0), (0.26, 0.62)):
            m = int(0.32 * SR)
            tt = np.arange(m) / SR
            f = 58 * np.exp(-14 * tt) + 34
            th = np.sin(2 * np.pi * np.cumsum(f) / SR).astype(np.float32) * np.exp(-16 * tt).astype(np.float32)
            i = int((t0 + off) * SR)
            if i + m < n:
                out[i:i + m] += th * amp
        t0 += per
    return norm(lowpass(out, 220, 2), -7)


def ticks(dur=14.0, rate=2.2):
    """تكّات إيقاعية هادئة (ساعات تمر) — آخر 10 أيام."""
    n = int(dur * SR)
    out = np.zeros(n, np.float32)
    per = 1.0 / rate
    t0 = 0.0
    k = 0
    while t0 < dur - 0.2:
        m = int(0.09 * SR)
        tt = np.arange(m) / SR
        f = 2600 if k % 2 == 0 else 2100
        seg = (np.sin(2 * np.pi * f * tt) * np.exp(-45 * tt)).astype(np.float32)
        i = int(t0 * SR)
        if i + m < n:
            out[i:i + m] += seg * (1.0 if k % 2 == 0 else 0.75)
        t0 += per
        k += 1
    return norm(band(out, 1500, 4000), -10)


def chime(dur=2.6, f0=1180.0):
    """جرس دافئ للخلاص/الكوخ."""
    n = int(dur * SR)
    t = np.arange(n) / SR
    parts = [(1.0, 1.0, 2.6), (2.01, 0.45, 3.4), (2.98, 0.25, 4.4), (4.07, 0.12, 5.5)]
    out = np.zeros(n, np.float32)
    for mult, amp, dec in parts:
        out += (amp * np.sin(2 * np.pi * f0 * mult * t) * np.exp(-dec * t)).astype(np.float32)
    out *= np.minimum(1, t / 0.006).astype(np.float32)
    return norm(soft_reverb(out, 0.6, 0.45, seed=31), -4)


def animal(dur=2.2):
    """نداء حيوان بعيد — منخفض وناعم، لا مخيف."""
    n = int(dur * SR)
    t = np.arange(n) / SR
    f = (150 + 60 * np.sin(np.pi * np.minimum(t / dur, 1))).astype(np.float32)
    tone = np.sin(2 * np.pi * np.cumsum(f) / SR).astype(np.float32)
    breath = band(noise(n), 200, 1800) * 0.25
    e = np.minimum(1, t / 0.25) * np.exp(-1.1 * np.maximum(0, t - 0.3)).astype(np.float32)
    return norm(lowpass((tone * 0.8 + breath) * e, 2600, 2), -14)


def write(path, x):
    import wave
    x = np.clip(x, -1, 1)
    pcm = (x * 32767).astype(np.int16)
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())


def build_all(outdir):
    os.makedirs(outdir, exist_ok=True)
    files = {
        "rain.wav": rain(14.0),
        "jungle.wav": jungle(14.0),
        "thunder_near.wav": thunder(True),
        "thunder_far.wav": thunder(False),
        "impact.wav": impact(),
        "crack.wav": crack(),
        "paper.wav": paper(),
        "riser.wav": riser(),
        "water.wav": water(14.0),
        "heartbeat.wav": heartbeat(14.0),
        "ticks.wav": ticks(14.0),
        "chime.wav": chime(),
        "chime_low.wav": chime(3.2, 780.0),
        "animal.wav": animal(),
    }
    for k, v in files.items():
        write(os.path.join(outdir, k), v)
    return {k: len(v) / SR for k, v in files.items()}


if __name__ == "__main__":
    import sys
    d = sys.argv[1] if len(sys.argv) > 1 else "assets/sfx2"
    print(build_all(d))
