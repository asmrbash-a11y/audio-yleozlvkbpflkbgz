"""Attach the corrected script to the ASR word timings -> data/timeline.json + subtitles.srt"""
import json, os
import content as C

asr = json.load(open("data/asr.json"))["words"]
assert len(asr) == len(C.WORDS), f"{len(asr)} asr vs {len(C.WORDS)} script words"

words = []
for i, (a, t) in enumerate(zip(asr, C.WORDS)):
    words.append({"i": i, "text": t, "start": round(a["s"], 3), "end": round(a["e"], 3),
                  "pause_after": 0.0, "emphasis": i in C.EMPHASIS})

# a following gap means the word holds a little longer on screen
for k in range(len(words) - 1):
    gap = words[k + 1]["start"] - words[k]["end"]
    words[k]["pause_after"] = round(max(0.0, gap), 3)

# cues
cues = []
for ci, toks in enumerate(C.CUES):
    tt = [words[i] for i in toks]
    start = tt[0]["start"]
    end = tt[-1]["end"]
    nxt = None
    if ci + 1 < len(C.CUES):
        nxt = words[C.CUES[ci + 1][0]]["start"]
    # hold the line until the next one starts (max 0.45s past the last word)
    hold = min(0.45, (nxt - end) * 0.8) if nxt else 0.5
    cues.append({
        "index": ci,
        "tokens": toks,
        "start": round(start, 3),
        "end": round(end + max(0.12, hold), 3),
        "lines": C.CUE_LINES.get(ci),
        "text": " ".join(words[i]["text"] for i in toks if words[i]["text"]),
    })

# clamp: never let two lines overlap, never pass the end of the recording
for i, c in enumerate(cues):
    if i + 1 < len(cues):
        c["end"] = min(c["end"], cues[i + 1]["start"] - 0.02)
    c["end"] = min(c["end"], C.END - 0.05)

# scenes
scenes = []
for si, s in enumerate(C.SCENES):
    start = s["start"]
    end = C.SCENES[si + 1]["start"] if si + 1 < len(C.SCENES) else C.END
    scenes.append({**s, "start": start, "end": end, "dur": round(end - start, 3)})

tl = {"duration": C.END, "words": words, "cues": cues, "scenes": scenes,
      "title": C.TITLE_LINES, "credit": C.CREDIT}
os.makedirs("data", exist_ok=True)
json.dump(tl, open("data/timeline.json", "w"), ensure_ascii=False, indent=1)

# srt (line per cue)
def ts(t):
    h = int(t // 3600); m = int(t % 3600 // 60); s = t % 60
    return f"{h:02d}:{m:02d}:{s:06.3f}".replace(".", ",")

with open("data/subtitles.srt", "w") as f:
    for i, c in enumerate(cues, 1):
        f.write(f"{i}\n{ts(c['start'])} --> {ts(c['end'])}\n{c['text']}\n\n")

print("words", len(words), "cues", len(cues), "scenes", len(scenes))
for c in cues:
    print(f"{c['start']:6.2f}-{c['end']:6.2f} ({c['end']-c['start']:.2f}s) {c['text']}")
