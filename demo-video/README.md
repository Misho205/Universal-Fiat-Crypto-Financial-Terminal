# HybridPay Hackathon Demo — reproducibility package

`hybridpay-demo.mp4` — 109s, 1920×1080, H264+AAC. Real app, real sandbox
interactions; nothing fabricated. Recorded 2026-11-04 against a local
backend+frontend running the **exact committed code** (same code as deployed).

## What the video shows (all genuine)

1. Terminal home: backend health (`liveMode OFF, sandbox true`), operator sign-in.
2. Banking Workspace: live KPIs, AccessGate, section nav.
3. Personal Workspace: operator sign-in → 5-step fiat send → `Done: pay-… → succeeded`.
4. Simulator: unified result cards — PASSED/AUTHORIZED, PASSED/DECLINED
   (`PROVIDER_ERROR`), PASSED/UNKNOWN (`TIMEOUT_UNKNOWN`), PASSED/REJECTED.
5. Personal Program tab: contract create & activate → status check.
6. Personal Assistant: advisory answer card (`advisoryOnly`, stub model labeled).
7. Personal History: tenant-isolated search + details.
8. Private Workspace: banking-style sign-in.
9. Personal Receive: Sepolia request + track (`requested 0/2`, RPC-not-configured note).

Honesty notes (also narrated on screen): AI runs as a transparent sandbox stub
(no live model key); crypto send needs `BTCPAY_*_TEST` or returns an honest
503; fiat/crypto are mock/testnet — no real money, `LIVE_MODE=OFF`.

## Files

- `script.md` — exact English narration (as synthesized).
- `storyboard.md` — shots, actions, expected on-screen verdicts.
- `record-demo.ts` — Playwright recorder (1920×1080, per-scene .webm).
  Needs `DEMO_OP_TOKEN` (throwaway local dev token) + `APP_URL`.
  Token is typed only into `type=password` fields (dots on screen).
- `assemble.py` — deterministic assembler (primary): per-scene TTS
  (edge-tts, en-US-GuyNeural), freeze-frame extension, lower-thirds,
  concat, title/end cards, ASS subtitles. `edit-video.sh` is the equivalent
  bash version (kept for reference; python is canonical — see script header).
- `subtitles.srt` / `subtitles.ass` — generated, synchronized cues.
- `clips/` — raw recorded scenes (regenerable).
- `audio/` — generated narration mp3s.

## Reproduce

```bash
# 1. local backend + frontend (throwaway dev tokens, sandbox only)
API_SHARED_TOKEN=dev-op API_ADMIN_TOKEN=dev-ad \
  python3 -m uvicorn modal_backend.api:app --port 8101 &
NEXT_PUBLIC_MODAL_API_URL=http://localhost:8101 \
NEXT_PUBLIC_API_URL=http://localhost:8101 NEXT_PUBLIC_API_TOKEN="" \
  pnpm --filter @hybridpay/terminal build
python3 -m http.server 3000 --directory apps/terminal/out &

# 2. record (needs playwright-core + chromium)
DEMO_OP_TOKEN=dev-op APP_URL=http://localhost:3000 \
  ./node_modules/.bin/tsx demo-video/record-demo.ts   # NODE_PATH to playwright-core

# 3. assemble (needs edge-tts + imageio-ffmpeg static binary)
python3 demo-video/assemble.py   # -> demo-video/hybridpay-demo.mp4
```

## QA (2026-11-04)

- `hybridpay-demo.mp4`: 109.2s (≤180s ✅), 1920×1080, H264+AAC, decodes clean.
- Frame spot-checks (6 scenes): real `Done: pay-…`, real unified cards,
  real advisory answer; token fields show dots only; no cookies/keys/URLs
  with secrets on screen; no real-money claims.
- Subtitles: sentence-split cues timed from actual segment durations, burned
  in, synced with narration and on-screen action.
- Tests: frontend vitest 43/43; backend suites green (see repo).
