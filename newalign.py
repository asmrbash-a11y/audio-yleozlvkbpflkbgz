"""مزامنة كلمات النص مع تعليق صوتي جديد — بلا افتراض أن ترتيب ASR يطابق النص.

الطريقة: ترتيب محاذاة عالمي (Needleman–Wunsch) بين كلمات النص الأصلي وكلمات ASR،
بدرجة تشابه ضبابية على العربية المُطبَّعة، فتتحمل أخطاء الإملاء من ASR
(استيقضت/استيقظت، مصيحة/نصيحة) والتقديم والتأخير والحذف.
الناتج: أوقات دقيقة لكل كلمة من النص، ثم ترجمة SRT وملف JSON.

الاستعمال:
    python3 newalign.py <voice.wav|mp3|m4a> [--asr asr.json] [--end 51.89]
"""
import argparse, difflib, json, os, re, subprocess, sys

import content as C

FILLER = set("،.!؟…ـ:؛\"'()[]")

def norm(s):
    s = re.sub(r"[\u064B-\u0652\u0670\u0640]", "", s)          # حركات وتطويل
    s = s.translate(str.maketrans("أإآٱ", "اااا"))
    s = s.replace("ى", "ي").replace("ة", "ه").replace("ؤ", "و").replace("ئ", "ي")
    s = "".join(ch for ch in s if ch not in FILLER)
    s = re.sub(r"[^\w\u0600-\u06FF]", "", s)
    return s.strip().lower()

def sim(a, b):
    a, b = norm(a), norm(b)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    return difflib.SequenceMatcher(None, a, b).ratio()

def align(script, asr, gap=-0.55):
    """يرجع قائمة [(idx_script or None, idx_asr or None)] لأزواج المحاذاة."""
    n, m = len(script), len(asr)
    S = [[0.0] * (m + 1) for _ in range(n + 1)]
    B = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(1, n + 1):
        S[i][0] = i * gap; B[i][0] = 1
    for j in range(1, m + 1):
        S[0][j] = j * gap; B[0][j] = 2
    sc = [[None] * (m + 1) for _ in range(n + 1)]
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            r = sim(script[i - 1], asr[j - 1]["word"])
            sc[i][j] = r
            match = S[i - 1][j - 1] + (r if r >= 0.62 else r - 1.1)
            dele = S[i - 1][j] + gap
            ins = S[i][j - 1] + gap
            best = max(match, dele, ins)
            S[i][j] = best
            B[i][j] = 0 if best == match else (1 if best == dele else 2)
    pairs, i, j = [], n, m
    while i > 0 or j > 0:
        if i > 0 and j > 0 and B[i][j] == 0:
            pairs.append((i - 1, j - 1)); i -= 1; j -= 1
        elif i > 0 and (j == 0 or B[i][j] == 1):
            pairs.append((i - 1, None)); i -= 1
        else:
            pairs.append((None, j - 1)); j -= 1
    return list(reversed(pairs)), sc

def transcribe(path):
    """ASR على مستوى الكلمة عبر faster-whisper (نمرّر numpy تفادياً لمشكلة PyAV)."""
    import numpy as np
    from faster_whisper import WhisperModel
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-ac", "1", "-ar", "16000",
                          "-f", "f32le", "-"], capture_output=True).stdout
    a = np.frombuffer(raw, dtype=np.float32)
    model = WhisperModel("small", device="cpu", compute_type="int8")
    segs, info = model.transcribe(a, language="ar", word_timestamps=True, vad_filter=False,
                                  condition_on_previous_text=False)
    words = []
    for s in segs:
        for w in s.words:
            t = w.word.strip()
            if t:
                words.append({"word": t, "start": round(float(w.start), 3), "end": round(float(w.end), 3)})
    return words, float(info.duration)

def snap_to_onsets(words, voice, search_ms=150, win_ms=20):
    """يضبط بداية كل كلمة على أول ارتفاع حقيقي في الطاقة حولها (±150 مللي).

    Whisper يميل إلى تقديم بداية الكلمة بنحو 50–100 مللي؛ هذا الضبط يزيل الإزاحة
    فتصبح الكلمة على الشاشة والمؤثر على نطقها بالضبط.
    """
    import numpy as np
    hop = 240                                   # 5 مللي
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", voice, "-ac", "1", "-ar", "48000",
                          "-f", "f32le", "-"], capture_output=True).stdout
    x = np.frombuffer(raw, dtype=np.float32).astype(np.float64)
    w = int(win_ms * 48)
    e = np.sqrt(np.convolve(x ** 2, np.ones(w) / w, "same")[::hop])
    edb = 20 * np.log10(e + 1e-12)
    out = []
    prev_start = -1.0
    for k, wd in enumerate(words):
        i = int(wd["start"] * 48000 / hop)
        lo, hi = max(0, i - search_ms // 5), min(len(edb) - 1, i + search_ms // 5)
        seg = edb[lo:hi + 1]
        if len(seg) >= 5:
            rise = seg - np.minimum.accumulate(seg)
            j = int(np.argmax(rise))
            new_start = (lo + j) * hop / 48000 if rise[j] >= 4.0 else wd["start"]
        else:
            new_start = wd["start"]
        new_start = max(new_start, prev_start + 0.04 if prev_start > 0 else 0.0)
        end = max(wd["end"], new_start + 0.06)
        out.append({**wd, "start": round(new_start, 3), "end": round(end, 3)})
        prev_start = new_start
    return out


def build(voice, end=None):
    asr, dur = transcribe(voice)
    if end:
        asr = [w for w in asr if w["start"] < end - 0.05]
    script = [w for w in C.WORDS]
    pairs, _ = align(script, asr)
    # أوقات النص: الكلمات المتطابقة تأخذ وقتها، والفجوات تُستكمل بالاستقراء
    times = [None] * len(script)
    for si, ai in pairs:
        if si is not None and ai is not None and sim(script[si], asr[ai]["word"]) >= 0.62:
            times[si] = (asr[ai]["start"], asr[ai]["end"])
    # حدود المقطع الصوتي المُغطّى
    covered = [i for i, t in enumerate(times) if t]
    if not covered:
        raise SystemExit("لم يتم العثور على أي تطابق — تحقّق من ملف الصوت/النص")
    first, last = covered[0], covered[-1]
    # استقراء الكلمات داخل النطاق
    i = first
    while i <= last:
        if times[i] is None:
            j = i
            while j <= last and times[j] is None:
                j += 1
            a = times[i - 1][1] if i > 0 and times[i - 1] else 0.0
            b = times[j][0] if j <= last and times[j] else a
            k = j - i
            for n_, idx in enumerate(range(i, j)):
                s = a + (b - a) * n_ / (k + 1)
                e = a + (b - a) * (n_ + 1) / (k + 1)
                times[idx] = (round(s, 3), round(e, 3))
            i = j
        else:
            i += 1
    words = []
    for idx, t in enumerate(times):
        if t is None:
            break
        words.append({"i": idx, "text": script[idx], "start": t[0], "end": t[1],
                      "pause_after": 0.0, "emphasis": idx in C.EMPHASIS})
    for k in range(len(words) - 1):
        words[k]["pause_after"] = round(max(0.0, words[k + 1]["start"] - words[k]["end"]), 3)
    words = snap_to_onsets(words, voice)
    for k in range(len(words) - 1):
        words[k]["pause_after"] = round(max(0.0, words[k + 1]["start"] - words[k]["end"]), 3)
    return asr, dur, words, pairs

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("voice")
    ap.add_argument("--end", type=float, default=None)
    ap.add_argument("--out", default="data/align_new.json")
    a = ap.parse_args()
    asr, dur, words, pairs = build(a.voice, a.end)
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    json.dump({"asr": asr, "duration": dur, "words": words}, open(a.out, "w"), ensure_ascii=False, indent=1)
    print("ASR words: %d · script words timed: %d / %d" % (len(asr), len(words), len(C.WORDS)))
    print("مدة الملف %.2fs · آخر كلمة: %s %.2f–%.2f" % (dur, words[-1]["text"], words[-1]["start"], words[-1]["end"]))
    # تقرير أخطاء المزامنة
    bad = []
    for si, ai in pairs:
        if si is not None and ai is not None:
            r = sim(C.WORDS[si], asr[ai]["word"])
            if r < 0.62:
                bad.append((C.WORDS[si], asr[ai]["word"], round(r, 2)))
    print("أزواج منخفضة التشابه:", bad[:10] if bad else "لا شيء")
    for w in words[:8]:
        print("  %5.2f–%5.2f  %s" % (w["start"], w["end"], w["text"]))
