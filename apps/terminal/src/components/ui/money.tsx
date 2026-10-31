import { formatMinor, formatWei } from "../../lib/format";

/** Monetary amount display: tabular numerals + ISO code (screen-reader friendly). */
export function Money({ minor, currency, locale }: { minor: string; currency: string; locale?: string }) {
  const text = formatMinor(minor, currency, locale);
  return (
    <span className="num font-semibold" aria-label={`${text}`}>
      {text}
    </span>
  );
}

export function Wei({ value, locale }: { value: string; locale?: string }) {
  const text = formatWei(value, locale);
  return (
    <span className="num font-semibold" aria-label={text}>
      {text}
    </span>
  );
}
