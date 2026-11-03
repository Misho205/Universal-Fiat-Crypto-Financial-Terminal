#!/usr/bin/env python3
"""HybridPay demo assembler (Python driver — deterministic, re-runnable).
Title + 9 recorded scenes + end card, edge-tts narration, lower-thirds,
subtitles. Output: demo-video/hybridpay-demo.mp4 (<=180s)."""
import os, re, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
FF = "/home/codespace/.python/current/lib/python3.14/site-packages/imageio_ffmpeg/binaries/ffmpeg-linux-x86_64-v9.0.2"
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
os.chdir(HERE)
os.makedirs("audio", exist_ok=True)
os.makedirs("segs", exist_ok=True)

NARR = [
"Meet HybridPay — a universal fiat and crypto payment terminal. One sandbox for banks, wallets, and smart contracts, where deterministic backend rules authorize every movement, and everything is audited.",
"The Banking Workspace shows live KPIs, programmable contracts, disputes, and an admin-gated control plane. Operators read; money movement needs an admin token plus maker-checker approval.",
"In the Personal Workspace I sign in with an operator token that lives only in browser memory, then send one thousand minor units. Create, then confirm: the provider decides, never the frontend.",
"The simulator proves failures are first-class: a declined payment returns a structured provider decline, recorded as scenario passed, payment declined. Timeouts stay ambiguous, contracts validate — never confused with an outage.",
"Money with conditions: a plain-words agreement becomes a validated programmable contract, activated by its creator. Guardrails never sleep — unknown categories rejected, wrong networks refused.",
"The Meta Muse Spark integration advises only — never authorizes. Every answer arrives labeled advisory-only; here it runs as a transparent sandbox stub, while real keys stay server-side in Modal Secrets.",
"History is tenant-isolated and searchable, with downloadable sandbox receipts for every record.",
"The Private Workspace mirrors banking sign-in: role badges, tenant context, and a health-checked backend.",
"Receiving is Sepolia-only: a tracked request is created, and your own wallet signs — the terminal never sees keys. Sandbox today, trusted rails tomorrow.",
]
LOWER = [
"HybridPay Terminal — sandbox, no real money",
"Banking Workspace — live KPIs, admin-gated",
"Personal Workspace — sandbox fiat payment",
"Simulator — expected decline, handled safely",
"Programmable contracts — validated, not escrow",
"Meta Muse Spark AI — advisory only",
"History — tenant-isolated, exportable receipts",
"Private Workspace — same sign-in model",
"Sepolia receive — your wallet signs",
]
CLIPS = ["01-terminal","02-banking","03-personal-fiat","04-simulator","05-contracts","06-ai","07-history","08-private","09-receive"]

def run(*a):
    r = subprocess.run(a, capture_output=True, text=True)
    if r.returncode != 0:
        print("FAILED:", " ".join(a[:6]), r.stderr[-1500:], file=sys.stderr)
        sys.exit(1)
    return r

def dur(path):
    r = subprocess.run([FF,"-i",path], capture_output=True, text=True)
    m = re.search(r"Duration: (\d+):(\d+):([\d.]+)", r.stderr)
    return int(m.group(1))*3600 + int(m.group(2))*60 + float(m.group(3))

def ts(s):
    h, m, sec = int(s//3600), int(s%3600//60), s%3600%60
    return f"{h:02d}:{m:02d}:{sec:06.3f}".replace(".", ",")

# 1. narration
for i, text in enumerate(NARR):
    out = f"audio/n{i}.mp3"
    if not os.path.exists(out) or os.path.getsize(out) == 0:
        run("edge-tts","--voice","en-US-GuyNeural","--text",text,"--write-media",out)
    print(f"audio {i}: {dur(out):.1f}s", flush=True)

# 2. segments
t, idx, srt = 4.0, 1, []
for i, c in enumerate(CLIPS):
    with open(f"segs/label{i}.txt","w") as f: f.write(LOWER[i])
    d = round(dur(f"audio/n{i}.mp3")+0.9, 2)
    fc = (f"[0:v]scale=1920:1080,fps=30,tpad=stop=-1:stop_mode=clone,trim=duration={d},"
          f"drawtext=fontfile={FONT}:textfile=segs/label{i}.txt:fontsize=34:fontcolor=white:"
          f"x=60:y=h-110:box=1:boxcolor=black@0.6:boxborderw=12:enable='lt(t,3.5)'[v]")
    run(FF,"-y","-v","error","-i",f"clips/{c}.webm","-i",f"audio/n{i}.mp3",
        "-filter_complex",fc,"-map","[v]","-map","1:a",
        "-c:v","libx264","-preset","veryfast","-crf","21","-pix_fmt","yuv420p",
        "-c:a","aac","-b:a","128k","-shortest",f"segs/s{i}.mp4")
    srt += [str(idx), f"{ts(t)} --> {ts(t+d)}", NARR[i], ""]
    t, idx = round(t+d, 2), idx+1
    print(f"seg {c}: {d}s (cum {t}s)", flush=True)

with open("subtitles.srt","w") as f: f.write("\n".join(srt))
# Rebuild subtitles from ACTUAL segment durations, split into sentences.
import re as _re
segs_d = []
for i in range(len(CLIPS)):
    segs_d.append(dur(f"segs/s{i}.mp4"))
entries, t, idx = [], 4.0, 1
for i, text in enumerate(NARR):
    parts = [p.strip() for p in _re.split(r"(?<=[.!?])\s+", text) if p.strip()]
    weights = [max(len(p), 1) for p in parts]
    total_w = sum(weights)
    for p, w in zip(parts, weights):
        dd = round(segs_d[i] * w / total_w, 2)
        entries += [str(idx), f"{ts(t)} --> {ts(round(t+dd,2))}", p, ""]
        t, idx = round(t+dd, 2), idx+1
with open("subtitles.srt","w") as f: f.write("\n".join(entries))
# ASS version with explicit PlayRes (force_style cannot set PlayRes) + wrapping.
ass = ["[Script Info]", "ScriptType: v4.00+", "PlayResX: 1280", "PlayResY: 720",
 "[V4+ Styles]", "Format: Name, Fontname, Fontsize, PrimaryColour, OutlineColour, BorderStyle, Outline, MarginL, MarginR, MarginV, Alignment, WrapStyle",
 "Style: Default,DejaVu Sans,20,&HFFFFFF,&H80000000,1,1,60,60,30,2,2",
 "[Events]", "Format: Layer, Start, End, Style, Text"]
def srt2ass(t):
    h, m, rest = t.split(":"); s = rest.replace(",", ".")
    return f"{int(h)}:{m}:{float(s):05.2f}"
cues = [e.split("\n") for e in "\n".join(entries).strip().split("\n\n") if e.strip()]
for i, c in enumerate(cues):
    ass.append(f"Dialogue: 0,{srt2ass(c[1].split('-->')[0].strip())},{srt2ass(c[1].split('-->')[1].strip())},Default,{c[2]}")
with open("subtitles.ass","w") as f: f.write("\n".join(ass))
print(f"srt+ass rebuilt from actual durations ({len(cues)} cues)", flush=True)

# 3. cards
def card(text, secs, out):
    with open("segs/card.txt","w") as f: f.write(text)
    # Silent mono 24kHz audio matches the narration segments (concat requires identical streams).
    run(FF,"-y","-v","error","-f","lavfi","-i",f"color=0x0b1020:1920x1080:d={secs}:r=30",
        "-f","lavfi","-i",f"anullsrc=r=24000:cl=mono:d={secs}",
        "-vf",f"drawtext=fontfile={FONT}:textfile=segs/card.txt:fontsize=56:fontcolor=white:x=(w-text_w)/2:y=(h-text_h)/2-40:line_spacing=18",
        "-c:v","libx264","-preset","veryfast","-crf","20","-pix_fmt","yuv420p",
        "-c:a","aac","-b:a","98k","-shortest",out)
card("HybridPay\nUniversal Fiat-Crypto Terminal\nMeta AI Hackathon — sandbox only, no real money",4,"segs/title.mp4")
card("Sandbox today, trusted infrastructure tomorrow.\nNo real money - No live keys",5,"segs/end.mp4")

# 4. concat + subs
with open("segs/list.txt","w") as f:
    f.write("file 'title.mp4'\n" + "".join(f"file 's{i}.mp4'\n" for i in range(len(CLIPS))) + "file 'end.mp4'\n")
run("bash","-c",f"cd segs && {FF} -y -v error -f concat -safe 0 -i list.txt -c copy ../joined.mp4")
run(FF,"-y","-v","error","-i","joined.mp4","-vf",
    "subtitles=subtitles.ass",
    "-c:v","libx264","-preset","veryfast","-crf","20","-pix_fmt","yuv420p","-c:a","copy","hybridpay-demo.mp4")
os.remove("joined.mp4")
d = dur("hybridpay-demo.mp4")
print(f"FINAL: {d:.1f}s | 1920x1080 | within 180s: {d<=180}")
r = subprocess.run([FF,"-i","hybridpay-demo.mp4"],capture_output=True,text=True)
print([l.strip() for l in r.stderr.splitlines() if "Duration" in l or "Video:" in l or "Audio:" in l])
