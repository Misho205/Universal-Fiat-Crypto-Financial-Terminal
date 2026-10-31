# EVM Sepolia testnet payments — setup, funding, verification

> Testnet only. Mainnet (chainId 1) is refused in code. The backend never holds keys;
> signing happens in the user's wallet (viem + `window.ethereum`).

## Setup
1. Install a wallet (MetaMask or any EIP-1193 wallet) in the demo browser.
2. Backend env (never secrets of value — RPC URL is read-only):
   ```
   SEPOLIA_RPC_URL=https://rpc.sepolia.org        # or Alchemy/Infura Sepolia endpoint
   EVM_CONFIRMATIONS_REQUIRED=2
   API_SHARED_TOKEN=dev-shared-token
   ```
3. Frontend env: `NEXT_PUBLIC_MODAL_API_URL=http://localhost:8000` (or the Modal dev URL).
4. Terminal → tab **EVM Sepolia** → Connect wallet → Switch to Sepolia on prompt.

## Funding (free testnet ETH, no value)
- Faucet: https://sepoliafaucet.com (Alchemy) or https://faucet.sepolia.dev —
  paste the wallet address, receive test SepoliaETH (valueless).
- Verify: `https://sepolia.etherscan.io/address/<0x…>` shows the faucet transfer.

## Demo flow (verified end-to-end in tests)
1. **Create tracked request**: enter `to` + ETH amount → backend `POST /api/payments/evm/request`
   returns `paymentId` (chainId asserted 11155111; anything else → 422).
2. **Sign + send in wallet**: MetaMask popup → confirm. Private key never leaves the wallet;
   the app only receives the tx hash.
3. **Submit hash**: `POST /api/payments/evm/{id}/submit` → `pending` + explorer link.
4. **Verify receipt**: tab Check receipt → backend `eth_getTransactionByHash` +
   `eth_getTransactionReceipt` + `eth_blockNumber` → `confirmed` only at ≥ N confirmations;
   `failed` on `status 0x0`. Without `SEPOLIA_RPC_URL` the state stays `pending` (never faked).
5. **Replacement**: same nonce + higher fee → `POST .../replace` links the new hash, old one kept.
6. **Chain ≠ settlement**: `confirmed` + `businessSettled: false` — settlement is a separate business step.

## Verification evidence
- Mocked unit/integration: `pytest modal_backend/test_evm_payments.py -q` (6 passed, 1 skipped opt-in).
- Frontend E2E (mocked fetch): terminal `demo-flow.test.ts` → sepolia request/submit/receipt case.
- Optional live-RPC (no funds move, reads only):
  `RUN_SEPOLIA_RPC_TEST=1 SEPOLIA_RPC_URL=<url> SEPOLIA_KNOWN_TX=0x… pytest modal_backend/test_evm_payments.py -q`
- Explorer: every submitted payment links `https://sepolia.etherscan.io/tx/<hash>`.
