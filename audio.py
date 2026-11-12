"""Soundtrack: voice + CC0 foley + synthesized thunder/paper sweeps, mixed under the narration."""
import json, os, subprocess, math

HERE = os.path.dirname(os.path.abspath(__file__))
KIT = os.path.join(HERE, "..", "reel-studio", "Sound-Kits", "cc0")
SFX = os.path.join(HERE, "assets", "sfx")
os.makedirs("renders", exist_ok=True)
os.makedirs(SFX, exist_ok=True)


def run(cmd):
    subprocess.run(cmd, check=True)


def synth():
    """Thunder rumble and paper sweeps, made from filtered noise."""
    # deep thunder: brown noise, low-passed, slow decay, 2.6 s
    run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i",
         "anoisesrc=d=2.8:c=brown:a=0.9:r=48000",
         "-af", "lowpass=f=180,lowpass=f=320,volume=1.0,"
                "afade=t=in:st=0:d=0.05,afade=t=out:st=1.1:d=1.7,"
                "aeval=val(0)*exp(-3.2*t)",
         os.path.join(SFX, "thunder.wav")])
    # crack: short bright noise burst for the lightning hit
    run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i",
         "anoisesrc=d=0.5:c=white:a=0.8:r=48000",
         "-af", "highpass=f=900,lowpass=f=7000,afade=t=out:st=0.02:d=0.45,volume=0.9",
         os.path.join(SFX, "crack.wav")])
    # paper sweep: band-passed noise with a rising then falling envelope
    run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i",
         "anoisesrc=d=0.62:c=pink:a=0.7:r=48000",
         "-af", "highpass=f=600,lowpass=f=5200,"
                "afade=t=in:st=0:d=0.16,afade=t=out:st=0.24:d=0.36,volume=0.85",
         os.path.join(SFX, "sweep.wav")])
    # soft riser for the drop
    run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i",
         "anoisesrc=d=1.1:c=pink:a=0.6:r=48000",
         "-af", "highpass=f=300,lowpass=f=3000,afade=t=in:st=0:d=0.9,afade=t=out:st=0.95:d=0.15,volume=0.8",
         os.path.join(SFX, "riser.wav")])


CUE = []  # (file, when, gain)


def add(name, when, gain):
    CUE.append((name, round(when, 3), gain))


def build_cues(tl):
    K = lambda f: os.path.join(KIT, f + ".wav")
    S = lambda f: os.path.join(SFX, f + ".wav")
    # scene changes: a paper sweep under a soft landing
    landings = {
        7.00: "landing-wood", 13.88: "landing-cinematic", 19.04: "landing-soft-heavy",
        23.00: "landing-wood", 30.30: "landing-soft-medium", 37.14: "landing-plank",
        43.92: "landing-soft-medium", 49.32: "landing-soft-heavy", 55.68: "landing-cinematic",
        61.50: "landing-plank", 65.68: "landing-soft-medium", 72.33: "landing-wood",
        78.68: "landing-cinematic", 84.34: "landing-soft-heavy",
    }
    for i, (t, name) in enumerate(landings.items()):
        add(K(name), t - 0.02, 0.30)
        add(S("sweep"), t - 0.13, 0.20 if i % 2 == 0 else 0.16)
    # thunder over the strike
    add(S("crack"), 13.92, 0.42)
    add(S("thunder"), 13.96, 0.55)
    add(S("thunder"), 19.10, 0.34)
    add(S("crack"), 19.06, 0.20)
    # paper pops on arrivals
    pops = [1.00, 8.90, 15.24, 20.00, 31.30, 45.30, 62.20, 66.20, 70.40, 79.00, 82.60, 88.00]
    for i, t in enumerate(pops):
        add(K("pop-minimal" if i % 2 == 0 else "pop-organic"), t, 0.26)
    # counters
    for k in range(6):
        add(K("tick-1" if k % 2 == 0 else "tick-3"), 26.62 + k * 0.30, 0.18)
    for k in range(6):
        add(K("tick-2" if k % 2 == 0 else "tick-1"), 55.72 + k * 0.16, 0.14)
    for k in range(5):
        add(K("tick-3"), 78.90 + k * 0.14, 0.11)
    # stamp hits
    for t in (20.00, 66.20):
        add(K("landing-plank"), t, 0.22)
    # small confirmation at the end
    add(K("chime-soft"), 88.00, 0.20)
    # riser into the crash
    add(S("riser"), 17.9, 0.18)


def mix(voice="assets/voice.m4a", out="renders/soundtrack.m4a"):
    tl = json.load(open("data/timeline.json"))
    build_cues(tl)
    inputs = ["-i", voice]
    chains = []
    for i, (f, t, g) in enumerate(CUE, start=1):
        inputs += ["-i", f]
        ms = int(max(0, t) * 1000)
        chains.append(f"[{i}:a]aformat=sample_rates=48000:channel_layouts=mono,"
                      f"volume={g},adelay={ms}|{ms}[s{i}]")
    n = len(CUE)
    mixed = "".join(f"[s{i}]" for i in range(1, n + 1))
    fc = ";".join(chains) + f";{mixed}amix=inputs={n}:normalize=0:dropout_transition=0,"
    fc += "alimiter=limit=0.95[sfx];"
    fc += ("[0:a]aformat=sample_rates=48000:channel_layouts=mono,"
           "highpass=f=75,acompressor=threshold=0.12:ratio=2.2:attack=12:release=180,"
           "loudnorm=I=-15.5:TP=-2:LRA=9[voice];"
           "[voice][sfx]amix=inputs=2:normalize=0:dropout_transition=0,"
           "loudnorm=I=-14:TP=-1.5:LRA=10,aresample=48000[out]")
    cmd = ["ffmpeg", "-y", "-v", "error", *inputs, "-filter_complex", fc,
           "-map", "[out]", "-c:a", "aac", "-b:a", "128k", out]
    run(cmd)
    print("mixed", out, "cues:", n)


if __name__ == "__main__":
    synth()
    mix()
