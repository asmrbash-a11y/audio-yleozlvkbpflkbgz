"""التعليق + مؤثرات ورقية هادئة.

المراحل (كلها قابلة لإعادة التوليد بـ python3 audio.py):
1. التعليق: 0–34 ثانية كما هي، ومن 34 ثانية للنهاية تُنظَّف خلفية الأمطار/الغابة
   (ضجيج عريض داخل ملف التعليق نفسه) ثم يُدمج الطرفان بتلاشي 1 ثانية بلا أي إزاحة زمنية.
2. المؤثرات: سقف ذروتها −28 dBFS، والعابر القوية أخفض، وكل مؤثر «ضجيجي» بعد 34 ثانية
   أخفض 6 dB إضافية.
3. المزيج: التعليق ‎−14.5 LUFS مرة واحدة، ثم المؤثرات بمستواها، ثم limiter على 192 kHz
   (يمسك القمم بين العينات) وترميز AAC 128k بذروة −1.3 dBFS.
"""
import json, math, os, re, subprocess
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
KIT = os.path.join(HERE, "..", "reel-studio", "Sound-Kits", "cc0")
SFX = os.path.join(HERE, "assets", "sfx")
OUT = os.path.join(HERE, "renders")
VOICE = os.path.join(HERE, "assets", "voice.m4a")
os.makedirs(OUT, exist_ok=True)
os.makedirs(SFX, exist_ok=True)

# ---- مستويات الصوت (عُدِّلت ثلاث مرات بناءً على ملاحظات صاحب العمل)
SFX_SCALE = 0.354          # −3 dB عن 0.50
HIT_TRIM = 0.794           # −2 dB إضافية على العابر القوية
SFX_CEILING_DBFS = -28.0   # سقف ذروة المؤثرات: 26 dB تحت أقصى التعليق
QUIET_AFTER = 34.0         # من هذه الثانية تُخفَّض المؤثرات الضجيجية
QUIET_TRIM = 0.5           # −6 dB إضافية لها
SPLIT_AT = 34.0            # بداية معالجة خلفية الأمطار/الغابة
XFADE = 1.0
TAIL_CLEAN = ("afftdn=nr=26:nf=-20:tn=0,anlmdn=s=1:p=0.003:r=0.006:m=15,"
              "highshelf=f=5500:g=-5,lowpass=f=8500")
TARGET_TP = -1.3

CUE = []


def run(cmd):
    subprocess.run(cmd, check=True)


def synth():
    """رعد، شرارة، مسحة ورق، ورايزر — من ضجيج مُرشَّح (بلا مواد محمية)."""
    run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "anoisesrc=d=2.8:c=brown:a=0.9:r=48000",
         "-af", "lowpass=f=180,lowpass=f=320,afade=t=in:st=0:d=0.05,afade=t=out:st=1.1:d=1.7,"
                "aeval=val(0)*exp(-3.2*t)", os.path.join(SFX, "thunder.wav")])
    run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "anoisesrc=d=0.5:c=white:a=0.8:r=48000",
         "-af", "highpass=f=900,lowpass=f=7000,afade=t=out:st=0.02:d=0.45,volume=0.9",
         os.path.join(SFX, "crack.wav")])
    run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "anoisesrc=d=0.62:c=pink:a=0.7:r=48000",
         "-af", "highpass=f=600,lowpass=f=5200,afade=t=in:st=0:d=0.16,afade=t=out:st=0.24:d=0.36,volume=0.85",
         os.path.join(SFX, "sweep.wav")])
    run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "anoisesrc=d=1.1:c=pink:a=0.6:r=48000",
         "-af", "highpass=f=300,lowpass=f=3000,afade=t=in:st=0:d=0.9,afade=t=out:st=0.95:d=0.15,volume=0.8",
         os.path.join(SFX, "riser.wav")])


def add(path, when, gain):
    CUE.append((path, round(when, 3), gain))


def build_cues(tl):
    K = lambda f: os.path.join(KIT, f + ".wav")
    S = lambda f: os.path.join(SFX, f + ".wav")
    landings = {7.00: "landing-wood", 13.88: "landing-cinematic", 19.04: "landing-soft-heavy",
                23.00: "landing-wood", 30.30: "landing-soft-medium", 37.14: "landing-plank",
                43.92: "landing-soft-medium", 49.32: "landing-soft-heavy", 55.68: "landing-cinematic",
                61.50: "landing-plank", 65.68: "landing-soft-medium", 72.33: "landing-wood",
                78.68: "landing-cinematic", 84.34: "landing-soft-heavy"}
    for i, (t, name) in enumerate(landings.items()):
        add(K(name), t - 0.02, 0.30)
        add(S("sweep"), t - 0.13, 0.20 if i % 2 == 0 else 0.16)
    add(S("crack"), 13.92, 0.42); add(S("thunder"), 13.96, 0.55)
    add(S("thunder"), 19.10, 0.34); add(S("crack"), 19.06, 0.20)
    for i, t in enumerate([1.00, 8.90, 15.24, 20.00, 31.30, 45.30, 62.20, 66.20, 70.40, 79.00, 82.60, 88.00]):
        add(K("pop-minimal" if i % 2 == 0 else "pop-organic"), t, 0.26)
    for k in range(6): add(K("tick-1" if k % 2 == 0 else "tick-3"), 26.62 + k * 0.30, 0.18)
    for k in range(6): add(K("tick-2" if k % 2 == 0 else "tick-1"), 55.72 + k * 0.16, 0.14)
    for k in range(5): add(K("tick-3"), 78.90 + k * 0.14, 0.11)
    for t in (20.00, 66.20): add(K("landing-plank"), t, 0.22)
    add(K("chime-soft"), 88.00, 0.20)
    add(S("riser"), 17.9, 0.18)


def clean_voice(out):
    """0–34 كما هي + 34–90 منزوعة الضجيج، بتلاشي طويل يحافظ على توقيت كل كلمة."""
    head = os.path.join(OUT, "head.wav"); tail = os.path.join(OUT, "tail.wav")
    run(["ffmpeg", "-y", "-v", "error", "-i", VOICE, "-t", str(SPLIT_AT), "-c:a", "pcm_s16le", head])
    run(["ffmpeg", "-y", "-v", "error", "-ss", str(SPLIT_AT - XFADE), "-i", VOICE,
         "-af", TAIL_CLEAN, "-c:a", "pcm_s16le", tail])
    run(["ffmpeg", "-y", "-v", "error", "-i", head, "-i", tail, "-filter_complex",
         f"[0:a][1:a]acrossfade=d={XFADE}:c1=tri:c2=tri,apad,atrim=0:90[out]",
         "-map", "[out]", "-c:a", "pcm_s16le", out])


def measure_loudnorm(path):
    p = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", path, "-af",
                        "loudnorm=I=-14.5:TP=-2:LRA=9:print_format=json", "-f", "null", "-"],
                       capture_output=True, text=True)
    j = json.loads(p.stderr[p.stderr.rindex("{"):p.stderr.rindex("}") + 1])
    return (f"loudnorm=I=-14.5:TP=-2:LRA=9:measured_I={j['input_i']}:measured_TP={j['input_tp']}:"
            f"measured_LRA={j['input_lra']}:measured_thresh={j['input_thresh']}:"
            f"offset={j['target_offset']}:linear=true")


def stats(path):
    o = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", path, "-af", "ebur128=peak=true",
                        "-f", "null", "-"], capture_output=True, text=True)
    return (float(re.findall(r"I:\s+(-?\d+\.\d+) LUFS", o.stderr)[-1]),
            float(re.findall(r"Peak:\s+(-?\d+\.\d+) dBFS", o.stderr)[-1]))


def peak_dbfs(path):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-ac", "1", "-ar", "48000",
                          "-f", "s16le", "-"], capture_output=True).stdout
    x = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    return 20 * math.log10(max(float(abs(x).max()), 1e-9))


def main(out="renders/soundtrack.m4a"):
    synth()
    tl = json.load(open(os.path.join(HERE, "data", "timeline.json")))
    build_cues(tl)
    voice_clean = os.path.join(OUT, "voice_clean.wav")
    voice_final = os.path.join(OUT, "voice_final.wav")
    clean_voice(voice_clean)
    run(["ffmpeg", "-y", "-v", "error", "-i", voice_clean, "-af",
         "highpass=f=75,acompressor=threshold=0.09:ratio=2.8:attack=8:release=160," + measure_loudnorm(voice_clean),
         "-ar", "48000", "-c:a", "pcm_s16le", voice_final])

    # المؤثرات وحدها، ثم تُثبَّت ذروتها عند السقف
    inputs, chains = ["-i", voice_final], []
    for i, (f, t, g) in enumerate(CUE, start=1):
        inputs += ["-i", f]
        gg = g * SFX_SCALE * (HIT_TRIM if os.path.basename(f).startswith(("thunder", "crack", "landing", "riser")) else 1.0)
        if t >= QUIET_AFTER and os.path.basename(f).startswith(("sweep", "pop", "tick", "riser")):
            gg *= QUIET_TRIM
        ms = int(max(0, t) * 1000)
        chains.append(f"[{i}:a]aformat=sample_rates=48000:channel_layouts=mono,volume={round(gg, 5)},"
                      f"adelay={ms}|{ms}[s{i}]")
    n = len(CUE)
    stem = os.path.join(OUT, "stem_raw.wav")
    run(["ffmpeg", "-y", "-v", "error", *inputs, "-filter_complex",
         ";".join(chains) + ";" + "".join(f"[s{i}]" for i in range(1, n + 1)) +
         f"amix=inputs={n}:normalize=0:dropout_transition=0[out]",
         "-map", "[out]", "-c:a", "pcm_s16le", stem])
    g = 10 ** ((SFX_CEILING_DBFS - peak_dbfs(stem)) / 20)

    stage = os.path.join(OUT, "mix_stage.wav")
    run(["ffmpeg", "-y", "-v", "error", "-i", voice_final, "-i", stem, "-filter_complex",
         f"[1:a]volume={g:.4f},alimiter=limit=0.4:level=false[sfx];[0:a]anull[voice];"
         "[voice][sfx]amix=inputs=2:normalize=0:dropout_transition=0,atrim=0:90[out]",
         "-map", "[out]", "-c:a", "pcm_s16le", stage])
    master = os.path.join(OUT, "master.wav")
    run(["ffmpeg", "-y", "-v", "error", "-i", stage, "-af",
         "aresample=192000,alimiter=limit=0.60:attack=5:release=70:level=false,aresample=48000",
         "-c:a", "pcm_s16le", master])
    gain = 0.0
    for _ in range(5):
        run(["ffmpeg", "-y", "-v", "error", "-i", master, "-af", f"volume={gain:.2f}dB",
             "-ar", "48000", "-c:a", "aac", "-b:a", "128k", "-ac", "1", out])
        I, P = stats(out)
        if abs(P - TARGET_TP) < 0.2:
            break
        gain += TARGET_TP - P
    print(f"mixed {out}: {n} cues · effects ceiling {SFX_CEILING_DBFS} dBFS · "
          f"{I:.1f} LUFS · true peak {P} dBFS")


if __name__ == "__main__":
    main()
