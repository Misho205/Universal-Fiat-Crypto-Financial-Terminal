# Money flows

## Roles
Accounting entity assumption (to be validated by accountant): each merchant tenant is the principal seller; platform is agent/processor (no pooling). No platform-owned omnibus holding simulated as escrow. Fees recorded explicitly.

## Denomination vs payment vs settlement
- `denominationAsset` (e.g. EUR): contract unit.
- `paymentAsset` (e.g. EUR, BTC-regtest): what customer pays with.
- `settlementAsset` (e.g. EUR): what merchant is settled in.
- Conversion requires approved executable route (quote with source/timestamp/expiry/maxDebit/minOut/slippage). Without route, method hidden/rejected.

## Journal rules
- Append-only `JournalEntry` + `JournalLine(asset, account, debit, credit)` in integer minor/atomic units.
- Balanced per asset: sum(debit-credit) == 0 for each asset in an entry. Never offset BTC debit against EUR credit. FX uses two legs via `FX_CLEARING_<pair>` + fee lines.
- Posted entries immutable; corrections via compensating entries. State transitions validated.

## Example: EUR order, card direct charge (Stripe Direct)
1. Instruction AUTHORIZED: no journal (memo only).
2. Capture SETTLED (provider settled 100.00 EUR, fee 1.50): entry { EUR merchant_receivable Dr 100.00 / EUR revenue Cr 100.00 }, entry { EUR fees Dr 1.50 / EUR stripe_payable Cr 1.50 }.
3. Refund: compensating entries on same rail; never net against unrelated sales.

## Example: EUR contract paid in BTC, settled in EUR (requires approved route)
1. BTC funding observed (>= confirmations): { BTC customer_funds Dr X / BTC merchant_btc_payable Cr X }.
2. Conversion execution at frozen quote: { BTC merchant_btc_payable Dr X / BTC fx_clearing Cr X }, { EUR fx_clearing Dr Y / EUR merchant_receivable Cr Y }, fee lines.
3. Reorg after fulfillment: original entries stay; new incident/exposure entry, not deletion.

## Refunds/disputes
- Fiat: original rail when permitted; dispute opens `DISPUTED` state, funds stay until resolved.
- Crypto: new authorized transfer to verified recipient; denomination/quote/fee policy from agreement; network fee disclosed.
