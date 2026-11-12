"""بناء جدول زمني جديد من تعليق جديد: الكلمات، الأسطر على الشاشة، وحدود المشاهد.

    python3 rebuild_timeline.py [--align data/align_full.json] [--end 90.0]

- الكلمات: أوقات مقاسة ومضبوطة على الطاقة (من newalign.py).
- الأسطر: 3–4 كلمات أو حتى 1.9 ثانية، بلا تقاطع بين سطرين.
- المشاهد: نفس المشاهد الفنية والانتقالات، لكن حدودها تُعاد ربطها بالكلمات
  التي كانت تُطلقها في النسخة القديمة (نفس اللحظة القصصية، وقت التعليق الجديد).
"""
import argparse, json, os

HERE = os.path.dirname(os.path.abspath(__file__))

# حدود المشاهد القديمة (النسخة السابقة) —تُستخدم فقط لمعرفة أي كلمة أطلقت المشهد
OLD = json.load(open(os.path.join(HERE, "data", "timeline.json")))
OLD_WORDS = OLD["words"]
SCENES = [
    dict(id="title", art="01_fall", trans=None, look="dawn"),
    dict(id="flight", art="02_plane_jungle", trans="torn"),
    dict(id="lightning", art="03_storm", trans="flash"),
    dict(id="breakup", art="04_breakup", trans="punch"),
    dict(id="freefall", art="05_freefall", trans="torn"),
    dict(id="waking", art="06_waking", trans="flash"),
    dict(id="wreckage", art="07_wreckage", trans="slide"),
    dict(id="advice", art="08_river", trans="torn"),
    dict(id="jungle", art="09_dark_jungle", trans="slide"),
    dict(id="ten-days", art="09_dark_jungle", trans="flash"),
    dict(id="hut", art="10_hut", trans="torn"),
    dict(id="rescue", art="11_rescue", trans="slide"),
    dict(id="twice", art="02_plane_jungle", trans="torn"),
    dict(id="only-one", art="12_seats", trans="torn"),
    dict(id="outro", art="01_fall", trans="torn"),
]


def nearest_word_idx(t, words):
    best = None
    for w in words:
        d = abs(w["start"] - t)
        if best is None or d < best[0]:
            best = (d, w["i"])
    return best[1]


def build(align_path, end=90.0, max_words=4, max_line_len=1.9):
    al = json.load(open(align_path))
    words = []
    for w in al["words"]:
        words.append({"i": w["i"], "text": w["text"], "start": w["start"], "end": w["end"],
                      "pause_after": w.get("pause_after", 0.0), "emphasis": w.get("emphasis", False)})

    # ---- الأسطر
    cues, cur = [], []
    for k, w in enumerate(words):
        cur.append(w)
        nxt = words[k + 1] if k + 1 < len(words) else None
        dur = cur[-1]["end"] - cur[0]["start"]
        if len(cur) >= max_words or dur >= max_line_len or not nxt:
            st = cur[0]["start"]
            en = cur[-1]["end"] + 0.30
            if nxt:
                en = min(en, nxt["start"] - 0.02)
            cues.append({"index": len(cues), "tokens": [x["i"] for x in cur],
                         "start": round(st, 3), "end": round(en, 3), "lines": None,
                         "text": " ".join(x["text"] for x in cur if x["text"])})
            cur = []
    # لا تقاطع
    for i, c in enumerate(cues[:-1]):
        c["end"] = round(min(c["end"], cues[i + 1]["start"] - 0.02), 3)

    # ---- المشاهد: نأخذ الكلمة التي كانت تُطلق المشهد قديماً ونستخدم وقتها الجديد
    starts = []
    for si, sc in enumerate(SCENES):
        if si == 0:
            starts.append(0.0)
            continue
        old_start = OLD["scenes"][si]["start"]
        idx = nearest_word_idx(old_start, OLD_WORDS)
        new_start = words[idx]["start"] if idx < len(words) else old_start
        starts.append(round(new_start, 3))
    # رتابة + حد أدنى للمدة
    for i in range(1, len(starts)):
        starts[i] = max(starts[i], starts[i - 1] + 2.2)
    starts[-1] = min(starts[-1], end - 2.5)
    scenes = []
    for si, sc in enumerate(SCENES):
        s = starts[si]
        e = starts[si + 1] if si + 1 < len(starts) else end
        scenes.append({**sc, "start": s, "end": round(e, 3), "dur": round(e - s, 3)})

    tl = {"duration": end, "words": words, "cues": cues, "scenes": scenes,
          "title": OLD["title"], "credit": OLD["credit"]}
    return tl


def srt(tl, path):
    def ts(t):
        h = int(t // 3600); m = int(t % 3600 // 60); s = t % 60
        return f"{h:02d}:{m:02d}:{s:06.3f}".replace(".", ",")
    with open(path, "w") as f:
        for i, c in enumerate(tl["cues"], 1):
            f.write(f"{i}\n{ts(c['start'])} --> {ts(c['end'])}\n{c['text']}\n\n")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--align", default=os.path.join(HERE, "data", "align_full.json"))
    ap.add_argument("--out", default=os.path.join(HERE, "data", "timeline.json"))
    ap.add_argument("--end", type=float, default=90.0)
    a = ap.parse_args()
    tl = build(a.align, a.end)
    if not os.path.exists(a.out.replace("timeline.json", "timeline_old.json")):
        json.dump(OLD, open(a.out.replace("timeline.json", "timeline_old.json"), "w"), ensure_ascii=False, indent=1)
    json.dump(tl, open(a.out, "w"), ensure_ascii=False, indent=1)
    srt(tl, os.path.join(HERE, "data", "subtitles.srt"))
    print("كلمات %d · أسطر %d · مشاهد %d" % (len(tl["words"]), len(tl["cues"]), len(tl["scenes"])))
    for s in tl["scenes"]:
        print("  %-10s %6.2f → %6.2f  (%.1f ث)" % (s["id"], s["start"], s["end"], s["dur"]))
