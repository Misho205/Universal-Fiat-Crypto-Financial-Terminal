# Storyboard — HybridPay demo (≈170s, 1920×1080)

All clips: Chromium 1920×1080, real app at local static build + local FastAPI
sandbox (same code as deployed). Token entered only into `type=password`
fields (rendered as dots). No URLs with secrets; no real payments.

| # | Time | Shot | Action (authentic) | Narration key | Verdict on screen |
|---|---|---|---|---|---|
| 0 | 0:00–0:06 | Title card (generated) | "HybridPay — Universal Fiat-Crypto Terminal · Meta AI Hackathon · sandbox only" | intro | — |
| 1 | 0:06–0:20 | `/` terminal home | Click Refresh health → `liveMode OFF, sandbox true`; sign in (dots) → role `operator` | problem | role chip |
| 2 | 0:20–0:50 | `/banking/` | Overview KPIs Refresh; scroll section nav; AccessGate notice visible | architecture | KPI counts |
| 3 | 0:50–1:20 | `/personal/` Send tab | Sign in → Recipient → Method fiat → Amount 1000 → Review → Confirm & send → `Done: pay-… → succeeded` | fiat success | AUTHORIZED sandbox |
| 4 | 1:20–1:45 | `/simulator/` | Sign in → run Successful fiat → PASSED/AUTHORIZED card → run Declined → PASSED/DECLINED, PROVIDER_ERROR | safe failure | unified cards |
| 5 | 1:45–2:10 | `/personal/` Program tab | Create & activate → status check (`active`); note guardrails (403 money paths) | contracts | agreement state |
| 6 | 2:10–2:35 | `/personal/` Assistant tab | Ask "What can you do?" → advisory answer card (`advisoryOnly`, stub model) | Muse Spark AI | advisory label |
| 7 | 2:35–2:50 | Montage + end card | banking KPIs → simulator cards → `/private/` sign-in → end card "Sandbox only · No real money" | close | — |

Total narration ≈ 430 words ≈ 170s @150wpm. Section headings burned in as
lower-thirds; full subtitles from `subtitles.srt` (generated from script).
