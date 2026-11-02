# White-Label & Embed — HybridPay Terminal

Run the terminal under your bank/exchange brand, inside your portal.

## 1. Iframe embed (fastest)

```html
<iframe src="https://<terminal>/banking?embed=1&tenant=bank-a"
        title="Payments" width="100%" height="900" style="border:0"></iframe>
```

- `?embed=1` hides the top navigation and footer (chrome-less widget mode).
  All workspace functionality (operations, approvals, audit) keeps working.
- `?tenant=bank-a` prefills the tenant field (convenience only — the backend
  derives authorization from the bearer token, never from this parameter).
- Auth inside the iframe: the operator pastes the sandbox bearer into the
  session (memory-only, cleared on logout); for SSO, front the iframe with
  your portal session and inject the token via your own wrapper page that
  posts it to the terminal's sign-in (token never touches localStorage).

## 2. White-label build

Brand strings are build-time env (public display values only — never secrets):

```bash
NEXT_PUBLIC_BRAND_NAME="NovaBank Payments" \
NEXT_PUBLIC_BRAND_TAGLINE="Corporate payments terminal" \
NEXT_PUBLIC_BRAND_SUPPORT_URL="https://support.novabank.example" \
NEXT_PUBLIC_BRAND_LOGO_TEXT="NovaBank" \
NEXT_PUBLIC_MODAL_API_URL=/api \
pnpm --filter @hybridpay/terminal build
```

Palette override: all colors resolve through CSS variables in
`apps/terminal/app/globals.css` (`--bg`, `--surface`, `--brand-*`, `--ok`,
`--warn`, `--danger`, `--info`). Fork the `:root` block for a full theme;
dark mode follows the `.dark` block automatically.

## 3. Backend pointing

- Same-origin (recommended): proxy `/api/*` to the Modal backend as in
  `modal_site_server.py` — no CORS, no secrets in the browser.
- `NEXT_PUBLIC_MODAL_API_URL` = backend base URL (or `/api` when proxied).
- `NEXT_PUBLIC_API_TOKEN` = optional dev bearer prefill (staging only).

## 4. Print & accessibility (kept across brands)

Receipts print cleanly (`@media print` hides nav/gates), focus-visible rings,
reduced-motion, skip-link, and live regions are brand-independent and guarded
by `test/a11y-contract.test.ts` — keep them green after re-theming.

## 5. What NOT to rebrand away

The `SANDBOX` badge, the "no real money" footer, and the "NOT escrow / NOT
fiscal receipt" disclosures are compliance markers — keep them visible in
every theme until a licensed production build replaces them with your
regulatory disclosures.
