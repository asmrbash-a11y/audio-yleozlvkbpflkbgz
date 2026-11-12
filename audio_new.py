"""محرّك الصوت: تعليق نظيف + طبقات أجواء ومؤثرات مربوطة بكلمات التعليق نفسها.

    python3 sfxgen.py assets/sfx3          # (مرة واحدة) توليد المواد
    python3 newalign.py <voice> --end ..   # أوقات الكلمات
    python3 audio_new.py <voice>           # المزيج النهائي

المبادئ:
- كل مؤثر يُوضع عند **الكلمة** التي يصفها (البرق، فانفصل، استيقظت…)، فالمزامنة
  تتبع الإلقاء ولو تغيّر إيقاعه.
- المستويات مقاسة لا مقدَّرة: سقف المؤثرات = ذروة التعليق − 26 dB،
  وطبقات الأجواء = ذروة التعليق − 34 dB مع تخفيض 5 dB تحت الكلام.
"""
import argparse, json, math, os, subprocess
import numpy as np

import sfxgen

SR = 48000
HERE = os.path.dirname(os.path.abspath(__file__))
SFXD = os.path.join(HERE, "assets", "sfx3")
OUT = os.path.join(HERE, "renders")
os.makedirs(OUT, exist_ok=True)

CEIL_BELOW_VOICE = 26.0
BED_BELOW_VOICE = 20.0     # بالـRMS: مستوى المطر/الغابة تحت مستوى الكلام
DUCK_DB = 5.0
TARGET_LUFS = -15.3
TARGET_TP = -1.3


# ---------------------------------------------------------------- أدوات
def load(path):
    cmd = ["ffmpeg", "-v", "error", "-i", path, "-ac", "1", "-ar", str(SR), "-f", "f32le", "-"]
    return np.frombuffer(subprocess.run(cmd, capture_output=True).stdout, dtype=np.float32)


def db(x):
    return 20 * math.log10(max(float(x), 1e-12))


def peak(x):
    return float(np.abs(x).max()) if len(x) else 0.0


def rms(x):
    return float(np.sqrt(np.mean(np.square(x, dtype=np.float64)) + 1e-18))


def place(track, clip, t, gain=1.0, fade=0.0):
    i = int(round(t * SR))
    if i < 0:
        clip = clip[-i:]
        i = 0
    if i >= len(track) or len(clip) == 0:
        return
    n = min(len(clip), len(track) - i)
    c = clip[:n].astype(np.float32).copy()
    if fade > 0:
        f = min(int(fade * SR), n // 2)
        if f > 1:
            c[:f] *= np.linspace(0, 1, f, dtype=np.float32)
            c[-f:] *= np.linspace(1, 0, f, dtype=np.float32)
    track[i:i + n] += c * gain


def tile(track, clip, start, end, gain_at=None, xfade=1.0, offset=0.0):
    """يرصف مقطعاً متكرراً بتلاشٍ متساوي القدرة (بلا نبض عند الوصل)."""
    L = len(clip)
    f = int(xfade * SR)
    t = start
    first = True
    while t < end:
        seg = clip
        g = 1.0 if gain_at is None else gain_at(t)
        if first and offset > 0:
            seg = clip[int(offset * SR):]
            first = False
        i = int(round(t * SR))
        if i >= len(track):
            break
        n = min(len(seg), len(track) - i)
        piece = seg[:n] * g
        if n > 2 * f and f > 1:
            win = np.ones(n, np.float32)
            if t > start:
                win[:f] = np.sin(np.linspace(0, np.pi / 2, f, dtype=np.float32))
            win[-f:] = np.cos(np.linspace(0, np.pi / 2, f, dtype=np.float32))
            piece = piece * win
        track[i:i + n] += piece
        t += (len(seg) - f) / SR


def envelope_db(x, hop=240, win=480):
    n = len(x) // hop + 1
    pad = np.pad(x, (0, n * hop - len(x)))
    e = np.sqrt(np.convolve(pad.astype(np.float64) ** 2, np.ones(win) / win, "same")[::hop] + 1e-12)
    return 20 * np.log10(e)


def duck_gain(env, thr, depth_db, atk=0.02, rel=0.35):
    g = np.clip((thr - env) / 12.0, 0.0, 1.0)
    g = 1.0 - g
    a = math.exp(-1.0 / (atk * SR / 240.0))
    r = math.exp(-1.0 / (rel * SR / 240.0))
    out = np.empty_like(g)
    s = 0.0
    for i, v in enumerate(g):
        s = a * s + (1 - a) * v if v > s else r * s + (1 - r) * v
        out[i] = s
    return 10 ** ((-depth_db * out) / 20.0)


def clean_voice(v, lufs):
    raw = os.path.join(OUT, "_v.raw")
    wav = os.path.join(OUT, "_v_clean.wav")
    v.astype(np.float32).tofile(raw)
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "f32le", "-ar", str(SR), "-ac", "1",
                    "-i", raw, "-af",
                    "highpass=f=72,equalizer=f=260:t=q:w=1.1:g=-1.0,"
                    "equalizer=f=3400:t=q:w=1.3:g=0.7,deesser=i=0.3,"
                    "agate=threshold=0.015:ratio=1.6:attack=10:release=200,"
                    "loudnorm=I=%g:TP=-2:LRA=9" % lufs, wav], check=True)
    return load(wav)


# ---------------------------------------------------------------- البناء
def build(voice_path, end=None, target_lufs=TARGET_LUFS, bed_below=None, ceil_below=None):
    if not os.path.isdir(SFXD):
        sfxgen.build_all(SFXD)
    tl = json.load(open(os.path.join(HERE, "data", "align_new.json")))
    words = tl["words"]
    if end is None:
        end = min(tl["duration"], words[-1]["end"] + 1.2)
    N = int(round(end * SR))

    def T(text, back=0.0, after=False):
        for w in words:
            if w["text"].strip("…!؟.،") == text:
                return max(0.0, (w["end"] if after else w["start"]) - back)
        return None

    v = load(voice_path)[:N]
    if len(v) < N:
        v = np.pad(v, (0, N - len(v)))
    vp_raw = db(peak(v))
    vc = clean_voice(v, target_lufs + 0.7)[:N]
    if len(vc) < N:
        vc = np.pad(vc, (0, N - len(vc)))
    v_peak = peak(vc)
    print("التعليق: ذروة %.1f dBFS → بعد التنظيف %.1f dBFS · RMS %.1f dBFS"
          % (vp_raw, db(v_peak), db(rms(vc))))

    # ------------------------------------------------ طبقات الأجواء
    rain = load(os.path.join(SFXD, "rain.wav"))
    junglec = load(os.path.join(SFXD, "jungle.wav"))
    beds = np.zeros(N, np.float32)
    notes = []
    storm = T("البرق") or 20.0
    crash = T("استيقظت") or (storm + 18)
    rain_start = T("الأمازون") or max(0.0, storm - 7)
    rain_start = max(0.0, rain_start - 0.4)

    def rain_gain(t):
        if t < storm - 0.8:
            return 0.42
        if t <= crash:
            return 1.0
        return 0.30 + 0.42 * math.exp(-(t - crash) / 12.0)

    tile(beds, rain, rain_start, end, gain_at=rain_gain, xfade=1.2, offset=0.3)
    notes.append("مطر: %.2f → %.2f (يشتد عند العاصفة، يهدأ بعد الارتطام)" % (rain_start, end))
    j_start = T("الغابة")
    if j_start:
        j_start = max(0.0, j_start - 0.3)
        tile(beds, junglec, j_start, end, gain_at=lambda t: 0.9, xfade=1.4, offset=0.5)
        notes.append("غابة/حشرات/طيور: %.2f → %.2f" % (j_start, end))

    env = envelope_db(vc)
    thr = float(np.percentile(env, 62))
    dg = np.repeat(duck_gain(env, thr, DUCK_DB), 240)[:N]
    if len(dg) < N:
        dg = np.pad(dg, (0, N - len(dg)), constant_values=1.0)
    beds *= dg

    # ------------------------------------------------ المؤثرات الحادثة
    bed_below = BED_BELOW_VOICE if bed_below is None else bed_below
    ceil_below = CEIL_BELOW_VOICE if ceil_below is None else ceil_below
    beds *= 10 ** ((db(rms(vc)) - bed_below - db(rms(beds))) / 20.0)   # معايرة بالـRMS لا بالذروة

    fx = np.zeros(N, np.float32)
    ev = []

    def hit(name, t, gain=1.0, fade=0.0):
        if t is None:
            return
        place(fx, load(os.path.join(SFXD, name)), t, gain=gain, fade=fade)
        ev.append((name.replace(".wav", ""), round(t, 2)))

    hit("thunder_far.wav", T("وفجأة", back=0.10), 0.85, 0.4)
    tn = T("البرق", back=0.22)
    hit("thunder_near.wav", tn, 1.0)
    hit("crack.wav", T("فانفصل", back=0.06), 0.85)
    hit("crack.wav", T("تتفكك", back=0.06), 0.6)
    hit("riser.wav", T("لحظات", back=0.25), 0.55)
    hit("impact.wav", T("استيقظت", back=0.62), 1.0)
    seen = set()
    for wt in ["حدثت", "كانت", "تحولت", "وفي", "لكن", "مصابة", "لكنها", "تذكرت"]:
        tt = T(wt, back=0.10)
        if tt is not None and round(tt, 2) not in seen:
            seen.add(round(tt, 2))
            hit("paper.wav", tt, 0.45, 0.08)

    fx *= 10 ** ((db(v_peak) - ceil_below - db(peak(fx))) / 20.0)
    print("سقف المؤثرات %.1f dBFS (تحت ذروة التعليق %.0f dB) · الأجواء RMS %.1f dBFS (تحت الكلام %.0f dB، بعد التخفيض %.0f dB)"
          % (db(peak(fx)), ceil_below, db(rms(beds)), bed_below, bed_below + DUCK_DB))
    for n_ in notes:
        print("  " + n_)
    print("  المؤثرات: " + ", ".join("%s@%.2f" % e for e in ev))

    mix = (vc.astype(np.float64) + fx + beds).astype(np.float32)
    raw = os.path.join(OUT, "_mix.raw")
    mix.tofile(raw)
    wav = os.path.join(OUT, "mix_new.wav")
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "f32le", "-ar", str(SR), "-ac", "1",
                    "-i", raw, "-af",
                    "aresample=192000,alimiter=limit=0.62:attack=5:release=80:level=false,"
                    "aresample=48000", "-c:a", "pcm_f32le", wav], check=True)
    return wav, {"voice_peak": db(v_peak), "fx_peak": db(peak(fx)), "bed_peak": db(peak(beds)),
                 "events": ev, "end": end}


def measure(path):
    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", path, "-af",
                        "loudnorm=print_format=json", "-f", "null", "-"],
                       capture_output=True, text=True).stderr
    j = json.loads(r[r.rindex("{"):r.rindex("}") + 1])
    return float(j["input_i"]), float(j["input_tp"])


def encode(wav, out, gain_db, br="128k"):
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", wav, "-af", "volume=%.2fdB" % gain_db,
                    "-c:a", "aac", "-b:a", br, "-ac", "1", "-ar", "48000", out], check=True)
    return measure(out)


def floor_db(x, hop=2400):
    """أرضية الطاقة: 10% المئين من إطارات 50 مللي — يقيس الخلفية وحدها بلا افتراض حدود كلمات."""
    n = len(x) // hop
    e = np.sqrt((x[: n * hop].reshape(n, hop).astype(np.float64) ** 2).mean(1)) + 1e-12
    return float(np.percentile(20 * np.log10(e), 10))


def hi_share(x):
    S = np.abs(np.fft.rfft(x.astype(np.float64) * np.hanning(len(x)))) ** 2
    f = np.fft.rfftfreq(len(x), 1 / SR)
    return 100 * float(S[f > 6000].sum() / S.sum())


def report_balance(path, voice_only):
    x = load(path)
    v = load(voice_only)
    n = min(len(x), len(v))
    print("قياس على الملف النهائي: كلام %.1f dBFS · أرضية الخلفية %.1f dBFS "
          "(التعليق وحده %.1f dBFS → أضفنا %.1f dB) · طاقة >6kHz %.1f%%"
          % (db(rms(x)), floor_db(x), floor_db(v[:n]), floor_db(x) - floor_db(v[:n]), hi_share(x)))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("voice")
    ap.add_argument("--end", type=float, default=None)
    ap.add_argument("--out", default=os.path.join(OUT, "soundtrack_new.m4a"))
    ap.add_argument("--gain", type=float, default=0.0, help="إزاحة يدوية بالمستوى")
    ap.add_argument("--bed", type=float, default=None, help="ذروة الأجواء تحت ذروة التعليق (dB)")
    ap.add_argument("--ceil", type=float, default=None, help="ذروة المؤثرات تحت ذروة التعليق (dB)")
    a = ap.parse_args()
    wav, info = build(a.voice, a.end, bed_below=a.bed, ceil_below=a.ceil)
    g = a.gain
    for _ in range(7):
        lufs, tp = encode(wav, a.out, g)
        print("  محاولة: إزاحة %+.2f dB → %.1f LUFS · ذروة %.1f dBFS" % (g, lufs, tp))
        if abs(tp - TARGET_TP) < 0.2:
            break
        g += TARGET_TP - tp
    tl = json.load(open(os.path.join(HERE, "data", "align_new.json")))
    report_balance(a.out, os.path.join(OUT, "_v_clean.wav"))
    print("المدة %.3fs · الحجم %.2f ميجا" % (len(load(a.out)) / SR, os.path.getsize(a.out) / 1e6))
