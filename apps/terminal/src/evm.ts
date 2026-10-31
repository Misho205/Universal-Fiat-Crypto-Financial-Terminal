// Browser wallet helpers (viem = established integration lib; EIP-1193 provider).
// The wallet SIGNS locally — private keys and seeds never leave it, never reach
// our backend, the AI, or localStorage. Mainnet is refused before any signing.
import { isAddress, parseEther, formatEther } from "viem";

export const SEPOLIA_CHAIN_ID = 11155111;
export const SEPOLIA_HEX = "0xaa36a7";
export const EXPLORER_TX = "https://sepolia.etherscan.io/tx/";

type EthProvider = {
  request: (args: { method: string; params?: unknown }) => Promise<unknown>;
  on?: (ev: string, cb: (...a: unknown[]) => void) => void;
};

function injected(): EthProvider | null {
  const w = globalThis as unknown as { ethereum?: EthProvider };
  return w.ethereum ?? null;
}

export function walletAvailable(): boolean {
  return injected() !== null;
}

export async function connectWallet(): Promise<string> {
  const p = injected();
  if (!p) throw new Error("NO_WALLET");
  const accs = (await p.request({ method: "eth_requestAccounts" })) as string[];
  if (!accs?.[0] || !isAddress(accs[0])) throw new Error("NO_ACCOUNT");
  return accs[0];
}

export async function walletChainId(): Promise<number> {
  const p = injected();
  if (!p) throw new Error("NO_WALLET");
  const hex = (await p.request({ method: "eth_chainId" })) as string;
  return parseInt(hex, 16);
}

export async function switchToSepolia(): Promise<void> {
  const p = injected();
  if (!p) throw new Error("NO_WALLET");
  try {
    await p.request({ method: "wallet_switchEthereumChain", params: [{ chainId: SEPOLIA_HEX }] });
  } catch (e) {
    const err = e as { code?: number };
    if (err?.code === 4902) {
      await p.request({
        method: "wallet_addEthereumChain",
        params: [{ chainId: SEPOLIA_HEX, chainName: "Sepolia testnet",
                   nativeCurrency: { name: "SepoliaETH", symbol: "ETH", decimals: 18 },
                   rpcUrls: ["https://rpc.sepolia.org"], blockExplorerUrls: ["https://sepolia.etherscan.io"] }],
      });
    } else throw e;
  }
}

/** Ask the wallet to sign+send (user confirms in wallet UI). Returns tx hash. */
export async function sendSepoliaTx(from: string, to: string, valueEth: string): Promise<string> {
  const p = injected();
  if (!p) throw new Error("NO_WALLET");
  const chain = await walletChainId();
  if (chain === 1) throw new Error("MAINNET_REFUSED");
  if (chain !== SEPOLIA_CHAIN_ID) throw new Error("WRONG_CHAIN");
  if (!isAddress(to)) throw new Error("BAD_ADDRESS");
  const value = "0x" + parseEther(valueEth).toString(16);
  const hash = (await p.request({
    method: "eth_sendTransaction", params: [{ from, to, value }],
  })) as string;
  return hash;
}

export { isAddress, parseEther, formatEther };
export function explorerTx(hash: string): string {
  return `${EXPLORER_TX}${hash}`;
}
