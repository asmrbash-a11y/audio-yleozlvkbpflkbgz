"""CLI: preview stills | full render."""
import argparse, os, subprocess, sys, time
from PIL import Image
import numpy as np
import engine as E
import scenes as S

FPS = E.FPS
TL = E.TL
OUT = "renders"


def frame_at(t):
    return E.render_frame(t, S.SCENE_FNS, TL["scenes"])


def preview(times, sheet="preview.jpg"):
    os.makedirs(OUT, exist_ok=True)
    imgs = []
    for t in times:
        img = frame_at(t)
        p = f"{OUT}/f_{t:06.2f}.jpg"
        img.save(p, quality=88)
        imgs.append((t, img))
        print("still", t, p)
    cols = 4
    tw, th = 300, 533
    rows = (len(imgs) + cols - 1) // cols
    sh = Image.new("RGB", (cols * tw, rows * th), (24, 24, 30))
    for i, (t, im) in enumerate(imgs):
        sh.paste(im.resize((tw, th), Image.LANCZOS), ((i % cols) * tw, (i // cols) * th))
    sh.save(sheet, quality=90)
    print("sheet", sheet)


def full(start=0.0, end=None, out="renders/video_raw.mp4", crf=20, preset="medium", audio=None,
         maxrate=None):
    os.makedirs(OUT, exist_ok=True)
    end = end if end is not None else TL["duration"]
    n = int(round((end - start) * FPS))
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
           "-s", f"{E.W}x{E.H}", "-r", str(FPS), "-i", "pipe:0"]
    if audio:
        cmd += ["-i", audio]
    cmd += ["-c:v", "libx264", "-preset", preset, "-crf", str(crf), "-pix_fmt", "yuv420p",
            "-tune", "animation", "-g", "50", "-movflags", "+faststart"]
    if maxrate:
        cmd += ["-maxrate", maxrate, "-bufsize", maxrate.replace("k", "k").replace("M", "M")]
    if audio:
        cmd += ["-c:a", "aac", "-b:a", "112k", "-shortest"]
    cmd += [out]
    pr = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    t0 = time.time()
    for i in range(n):
        t = start + i / FPS
        pr.stdin.write(frame_at(t).tobytes())
        if i % 50 == 0:
            el = time.time() - t0
            print(f"frame {i}/{n}  {el:6.1f}s  eta {el / (i + 1) * (n - i - 1):6.0f}s", flush=True)
    pr.stdin.close()
    pr.wait()
    print("done", out, f"{time.time() - t0:.0f}s")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["preview", "full", "sheet"])
    ap.add_argument("--times", default="0.8,2.5,5.0,8.5,11.0,15.0,17.5,20.5,24.0,26.8,29.0,31.5,34.5,38.5,41.5,45.6,48.0,50.5,53.0,56.5,59.0,62.5,66.5,69.8,73.5,76.0,79.5,81.5,84.0,86.5,88.8,89.6")
    ap.add_argument("--out", default="renders/video_raw.mp4")
    ap.add_argument("--crf", type=float, default=20)
    ap.add_argument("--maxrate", default=None)
    ap.add_argument("--audio", default=None)
    ap.add_argument("--start", type=float, default=0.0)
    ap.add_argument("--end", type=float, default=None)
    a = ap.parse_args()
    if a.cmd == "preview":
        preview([float(x) for x in a.times.split(",")])
    elif a.cmd == "full":
        full(a.start, a.end, a.out, a.crf, audio=a.audio, maxrate=a.maxrate)
