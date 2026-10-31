/** Money + date formatting (display only — never parse money from formatted strings). */
const MINOR_EXPONENTS: Record<string, number> = { EUR: 2, USD: 2, GBP: 2, BGN: 2, CHF: 2, SEK: 2, NOK: 2, DKK: 2, PLN: 2, CZK: 2, HUF: 0, RON: 2 };

export function formatMinor(amountMinor: string, currency: string, locale = "en-GB"): string {
  const exp = MINOR_EXPONENTS[currency] ?? 2;
  const minor = BigInt(amountMinor || "0");
  const neg = minor < BigInt(0);
  const abs = neg ? -minor : minor;
  const divisor = BigInt(10) ** BigInt(exp);
  const major = abs / divisor;
  const frac = exp > 0 ? "." + (abs % divisor).toString().padStart(exp, "0") : "";
  const grouped = major.toString().replace(/\B(?=(\d{3})+(?!\d))/g, locale.startsWith("bg") ? " " : ",");
  try {
    return new Intl.NumberFormat(locale, { style: "currency", currency }).format(Number(major) + (exp ? Number(frac) : 0));
  } catch {
    return `${neg ? "-" : ""}${grouped}${frac} ${currency}`;
  }
}

export function formatWei(wei: string, locale = "en-GB"): string {
  try {
    const eth = Number(BigInt(wei || "0")) / 1e18;
    return `${new Intl.NumberFormat(locale, { maximumFractionDigits: 6 }).format(eth)} ETH`;
  } catch {
    return `${wei} wei`;
  }
}

export function formatDateTime(iso: string, locale = "en-GB"): string {
  try {
    return new Intl.DateTimeFormat(locale, { dateStyle: "medium", timeStyle: "short" }).format(new Date(iso));
  } catch {
    return iso;
  }
}
