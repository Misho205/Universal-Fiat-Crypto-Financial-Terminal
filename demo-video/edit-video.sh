#!/bin/bash
# HybridPay demo assembly: title + 9 recorded scenes + end card, per-scene
# edge-tts narration, lower-thirds, subtitles. Re-runnable. No secrets involved
# (tokens appear only as password dots in footage). Requires: ffmpeg binary,
# edge-tts, DejaVu fonts. Produces demo-video/hybridpay-demo.mp4 (<=180s).
set -euo pipefail
cd "$(dirname "$0")"
FF=/home/codespace/.python/current/lib/python3.14/site-packages/imageio_ffmpeg/binaries/ffmpeg-linux-x86_64-v9.0.2
FONT=/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf
[ -f "$FONT" ] || FONT=$(fc-match -f '%{file}\n' sans 2>/dev/null || echo /usr/share/fonts/truetype/dejavu/DejaVuSans.ttf)
W=clips; A=audio; mkdir -p "$A" segs
rm -f segs/*.mp4 subtitles.srt filelist.txt

declare -a NARR=(
"Meet HybridPay — a universal fiat and crypto payment terminal. One sandbox for banks, wallets, and smart contracts, where deterministic backend rules authorize every movement, and everything is audited."
"The Banking Workspace shows live KPIs, programmable contracts, disputes, and an admin-gated control plane. Operators read; money movement needs an admin token plus maker-checker approval."
"In the Personal Workspace I sign in with an operator token that lives only in browser memory, then send one thousand minor units. Create, then confirm: the provider decides, never the frontend."
"The simulator proves failures are first-class: a declined payment returns a structured provider decline, recorded as scenario passed, payment declined. Timeouts stay ambiguous, contracts validate — never confused with an outage."
"Money with conditions: a plain-words agreement becomes a validated programmable contract, activated by its creator. Guardrails never sleep — unknown categories rejected, wrong networks refused."
"The Meta Muse Spark integration advises only — never authorizes. Every answer arrives labeled advisory-only; here it runs as a transparent sandbox stub, while real keys stay server-side in Modal Secrets."
"History is tenant-isolated and searchable, with downloadable sandbox receipts for every record."
"The Private Workspace mirrors banking sign-in: role badges, tenant context, and a health-checked backend."
"Receiving is Sepolia-only: a tracked request is created, and your own wallet signs — the terminal never sees keys. Sandbox today, trusted rails tomorrow."
)
declare -a LOWER=(
"HybridPay Terminal — sandbox, no real money"
"Banking Workspace — live KPIs, admin-gated"
"Personal Workspace — sandbox fiat payment"
"Simulator — expected decline, handled safely"
"Programmable contracts — validated, not escrow"
"Meta Muse Spark AI — advisory only"
"History — tenant-isolated, exportable receipts"
"Private Workspace — same sign-in model"
"Sepolia receive — your wallet signs"
)
declare -a CLIPS=(01-terminal 02-banking 03-personal-fiat 04-simulator 05-contracts 06-ai 07-history 08-private 09-receive)

# 1. narration audio
for i in "${!NARR[@]}"; do
  edge-tts --voice en-US-GuyNeural --text "${NARR[$i]}" --write-media "$A/n$i.mp3" >/dev/null
done

# 2. per-segment assembly (freeze last frame to fit narration, lower-third, subtitles timing)
> subtitles.srt
t=4  # after title card
idx=1
for i in "${!CLIPS[@]}"; do
  c="${CLIPS[$i]}"
  echo "${LOWER[$i]}" > segs/label$i.txt
  # audio length
  dur=$($FF -i "$A/n$i.mp3" 2>&1 | grep Duration | sed 's/.*Duration: \([0-9:.]*\).*/\1/' | awk -F: '{print $1*3600+$2*60+$3}')
  dur=$(awk -v d="$dur" 'BEGIN{printf "%.2f", d+0.9}')  # breath at end
  $FF -y -v error -i "$W/$c.webm" -i "$A/n$i.mp3" -filter_complex \
    "[0:v]scale=1920:1080,fps=30,tpad=stop=-1:stop_mode=clone,trim=duration=$dur,drawtext=fontfile=$FONT:textfile=segs/label$i.txt:fontsize=34:fontcolor=white:x=60:y=h-110:box=1:boxcolor=black@0.6:boxborderw=12:enable='lt(t,3.5)'[v]" \
    -map "[v]" -map 1:a -c:v libx264 -preset veryfast -crf 21 -pix_fmt yuv420p -c:a aac -b:a 128k -shortest "segs/s$i.mp4"
  # srt entry (HH:MM:SS,mmm)
  ts() { awk -v s="$1" 'BEGIN{h=int(s/3600); m=int((s-h*3600)/60); sec=s-h*3600-m*60; printf "%02d:%02d:%06.3f", h, m, sec}' | sed 's/\./,/'; }
  end=$(awk -v t="$t" -v d="$dur" 'BEGIN{printf "%.2f", t+d}')
  { echo "$idx"; echo "$(ts "$t") --> $(ts "$end")"; echo "${NARR[$i]}"; echo; } >> subtitles.srt
  t=$end
  idx=$((idx+1))
  echo "seg $c: ${dur}s (cum ${t}s)"
done

# 3. title + end cards
mkcard() { # $1 textfile-lines $2 duration $3 outfile
  printf '%s' "$1" > segs/card.txt
  $FF -y -v error -f lavfi -i "color=0x0b1020:1920x1080:d=$2:r=30" -vf \
    "drawtext=fontfile=$FONT:textfile=segs/card.txt:fontsize=56:fontcolor=white:x=(w-text_w)/2:y=(h-text_h)/2-40:line_spacing=18" \
    -c:v libx264 -preset veryfast -crf 20 -pix_fmt yuv420p -an segs/"$3"
}
mkcard "HybridPay
Universal Fiat-Crypto Terminal
Meta AI Hackathon — sandbox only, no real money" 4 title.mp4
mkcard "Sandbox today, trusted infrastructure tomorrow.
No real money · No live keys" 5 end.mp4

# 4. concat + subtitles
rm -f segs/list.txt
echo "file 'title.mp4'" > segs/list.txt
for i in "${!CLIPS[@]}"; do echo "file 's$i.mp4'" >> segs/list.txt; done
echo "file 'end.mp4'" >> segs/list.txt
(cd segs && $FF -y -v error -f concat -safe 0 -i list.txt -c copy ../joined.mp4)
$FF -y -v error -i joined.mp4 -vf "subtitles=subtitles.srt:force_style='FontSize=22,PrimaryColour=&HFFFFFF,OutlineColour=&H80000000,BorderStyle=1,Outline=1,MarginV=30'" \
  -c:v libx264 -preset veryfast -crf 20 -pix_fmt yuv420p -c:a copy hybridpay-demo.mp4
rm -f joined.mp4
echo "--- final:"; $FF -i hybridpay-demo.mp4 2>&1 | grep -E 'Duration|Video:|Audio:'
tot=$($FF -i hybridpay-demo.mp4 2>&1 | grep Duration | sed 's/.*Duration: \([0-9:.]*\).*/\1/' | awk -F: '{print $1*3600+$2*60+$3}')
awk -v s="$tot" 'BEGIN{printf "seconds: %.1f | within 180s: %s\n", s, (s<=180 ? "YES" : "NO")}'
