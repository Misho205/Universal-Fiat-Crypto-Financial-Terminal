"""EVM Sepolia testnet payment tracking (backend NEVER holds keys).

Security model:
- The backend NEVER requests, receives, or stores seed phrases or private keys.
- Signing happens exclusively in the user's wallet (frontend, viem + window.ethereum).
- The backend tracks payment requests, validates chainId (Sepolia 11155111 ONLY;
  mainnet 1 and all other chains are refused), registers wallet-submitted tx hashes,
  and verifies on-chain receipts + required confirmations via JSON-RPC.
- Chain confirmation != business settlement: receipts prove inclusion, settlement
  is a separate business decision recorded explicitly.

Mainnet is refused by construction (see assert_testnet).
"""
from __future__ import annotations

import hashlib
import re
import time
from dataclasses import dataclass

from . import config

SEPOLIA_CHAIN_ID = 11155111
MAINNET_CHAIN_ID = 1
EXPLORER_TX = "https://sepolia.etherscan.io/tx/"
REQUIRED_CONFIRMATIONS = 2
RPC_TIMEOUT_S = 10.0

_ADDRESS_RE = re.compile(r"^0x[0-9a-fA-F]{40}$")
_TXHASH_RE = re.compile(r"^0x[0-9a-fA-F]{64}$")

# Lifecycle for tracked EVM payments.
EVM_STATES = ("requested", "pending", "confirmed", "failed", "expired", "replaced")


def assert_testnet(chain_id: int) -> None:
    """Refuse everything that is not Sepolia testnet."""
    if chain_id == MAINNET_CHAIN_ID:
        raise ValueError("MAINNET_REFUSED: hackathon build supports Sepolia testnet only")
    if chain_id != SEPOLIA_CHAIN_ID:
        raise ValueError(f"UNSUPPORTED_CHAIN: expected {SEPOLIA_CHAIN_ID}, got {chain_id}")


def is_valid_address(addr: str) -> bool:
    return bool(_ADDRESS_RE.match(addr or ""))


def is_valid_txhash(h: str) -> bool:
    return bool(_TXHASH_RE.match(h or ""))


def explorer_link(tx_hash: str) -> str:
    return f"{EXPLORER_TX}{tx_hash}"


def request_id(tenant: str, to: str, value_wei: str, nonce_scope: str) -> str:
    """Legacy chain-implied ID (Sepolia). Prefer request_id_for_chain."""
    return request_id_for_chain(tenant, SEPOLIA_CHAIN_ID, to, value_wei, nonce_scope)


def request_id_for_chain(tenant: str, chain_id: int, to: str,
                         value_wei: str, nonce_scope: str) -> str:
    """Chain-bound request ID: the same (to, value) on different chains can
    never collide, and a mainnet request can never reuse a testnet ID."""
    assert_testnet(chain_id)
    digest = hashlib.sha256(
        f"{tenant}:{chain_id}:{to}:{value_wei}:{nonce_scope}".encode()
    ).hexdigest()[:12]
    return f"evm-{digest}"


def verify_submission_attestation(tx_hash: str, from_address: str = "",
                                  to_address: str = "") -> dict[str, str]:
    """Validate a wallet-side signing attestation.

    The backend NEVER signs and NEVER accepts private keys or seed phrases —
    there is no such field anywhere in this module. A submission must carry a
    well-formed tx hash (produced by the user's wallet) and, when provided, a
    well-formed sender address. Returns the recorded attestation.
    """
    if not is_valid_txhash(tx_hash):
        raise ValueError("invalid tx hash (expected 0x + 64 hex)")
    if from_address and not is_valid_address(from_address):
        raise ValueError("invalid from address (expected 0x + 40 hex)")
    return {"txHash": tx_hash,
            "submittedBy": from_address or "wallet-undisclosed",
            "signedBy": "user-wallet (backend never signs)"}


@dataclass
class RpcReceipt:
    found: bool
    status_ok: bool | None = None
    block_number: int | None = None
    confirmations: int = 0
    replaced_by: str | None = None


def _rpc(endpoint: str, method: str, params: list) -> dict:
    """Minimal JSON-RPC call with failure mapping (no keys, read-only methods)."""
    import httpx
    try:
        r = httpx.post(endpoint, json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params},
                       timeout=RPC_TIMEOUT_S)
    except Exception as exc:
        raise ConnectionError(f"RPC_UNREACHABLE: {str(exc)[:120]}") from exc
    if r.status_code != 200:
        raise ConnectionError(f"RPC_HTTP_{r.status_code}")
    body = r.json()
    if "error" in body:
        raise ConnectionError(f"RPC_ERROR: {str(body['error'])[:160]}")
    return body.get("result")


def verify_receipt(tx_hash: str, confirmations_required: int = REQUIRED_CONFIRMATIONS,
                   now: int | None = None) -> RpcReceipt:
    """Verify inclusion + confirmations. Raises on RPC failure (caller maps to pending/retry)."""
    _ = now
    import os
    endpoint = (os.environ.get("SEPOLIA_RPC_URL") or config.SEPOLIA_RPC_URL or "").strip()
    if not endpoint:
        raise ConnectionError("RPC_NOT_CONFIGURED: set SEPOLIA_RPC_URL to verify receipts")
    tx = _rpc(endpoint, "eth_getTransactionByHash", [tx_hash])
    if not tx or not tx.get("blockNumber"):
        return RpcReceipt(found=False)
    receipt = _rpc(endpoint, "eth_getTransactionReceipt", [tx_hash])
    if not receipt:
        return RpcReceipt(found=False)
    try:
        latest = int(_rpc(endpoint, "eth_blockNumber", []), 16)
        mined = int(tx["blockNumber"], 16)
    except (TypeError, ValueError) as exc:
        raise ConnectionError(f"RPC_BAD_BLOCK: {exc}") from exc
    confs = max(0, latest - mined + 1)
    status_ok = receipt.get("status") == "0x1"
    return RpcReceipt(found=True, status_ok=status_ok, block_number=mined, confirmations=confs)


def evaluate_chain_state(receipt: RpcReceipt, confirmations_required: int = REQUIRED_CONFIRMATIONS,
                         expiry_ts: int | None = None, now: int | None = None) -> str:
    """Deterministic chain-state mapping. 'confirmed' means N on-chain confirmations,
    NOT business settlement (recorded separately by the operator)."""
    ts = now if now is not None else int(time.time())
    if expiry_ts is not None and ts > expiry_ts and not receipt.found:
        return "expired"
    if not receipt.found:
        return "pending"
    if receipt.replaced_by:
        return "replaced"
    if receipt.status_ok is False:
        return "failed"
    if receipt.status_ok and receipt.confirmations >= confirmations_required:
        return "confirmed"
    return "pending"
