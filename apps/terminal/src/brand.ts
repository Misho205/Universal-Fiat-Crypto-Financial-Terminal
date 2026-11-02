// White-label brand configuration for bank/exchange embedding.
// Override via NEXT_PUBLIC_BRAND_* env at build time; all values are public
// display strings only (never secrets). See docs/white-label-embed.md.
export interface Brand {
  name: string;
  tagline: string;
  supportUrl: string;
  logoText: string;
}

const env = (k: string, fallback: string): string => {
  try {
    const g = globalThis as unknown as { process?: { env?: Record<string, string | undefined> } };
    return g.process?.env?.[k]?.trim() || fallback;
  } catch {
    return fallback;
  }
};

export const BRAND: Brand = {
  name: env("NEXT_PUBLIC_BRAND_NAME", "HybridPay"),
  tagline: env("NEXT_PUBLIC_BRAND_TAGLINE", "Universal payment terminal"),
  supportUrl: env("NEXT_PUBLIC_BRAND_SUPPORT_URL", ""),
  logoText: env("NEXT_PUBLIC_BRAND_LOGO_TEXT", ""),
};

/** Embed mode: `?embed=1` hides top navigation + footer for iframe embedding. */
export function isEmbedMode(): boolean {
  try {
    return new URLSearchParams(window.location.search).get("embed") === "1";
  } catch {
    return false;
  }
}

/** Tenant prefill from `?tenant=` (convenience only — the backend token binding decides). */
export function tenantFromUrl(): string {
  try {
    const t = new URLSearchParams(window.location.search).get("tenant") ?? "";
    return /^[a-zA-Z0-9][a-zA-Z0-9-_]{0,63}$/.test(t) ? t : "";
  } catch {
    return "";
  }
}
