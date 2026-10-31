// Append-only double-entry journal. Balanced PER ASSET. Integer minor units.
export interface JournalLine {
  asset: string; // assetId
  account: string;
  debitMinor: string; // integer string
  creditMinor: string;
}
export interface JournalEntry {
  id: string;
  tenantId: string;
  instructionId: string;
  asset: string;
  lines: JournalLine[];
  memo: string;
  compensatesEntryId: string | null;
  postedAt: string;
}

export function validateEntry(e: JournalEntry): string[] {
  const errors: string[] = [];
  const byAsset = new Map<string, bigint>();
  for (const l of e.lines) {
    if (!/^-?\d+$/.test(l.debitMinor) || !/^-?\d+$/.test(l.creditMinor)) errors.push("non-integer line amount");
    if (l.asset !== e.asset) errors.push("multi-asset entry forbidden: split into per-asset entries with FX clearing legs");
    const net = BigInt(l.debitMinor) - BigInt(l.creditMinor);
    byAsset.set(l.asset, (byAsset.get(l.asset) ?? 0n) + net);
  }
  for (const [asset, net] of byAsset) if (net !== 0n) errors.push(`unbalanced asset ${asset}: net ${net}`);
  return errors;
}

/** Build FX conversion as two balanced entries + fee entry (never offset BTC vs EUR). */
export function fxConversionEntries(o: {
  tenantId: string; instructionId: string; postedAt: string;
  fromAsset: string; fromAmountMinor: string; fromAccount: string;
  toAsset: string; toAmountMinor: string; toAccount: string;
  feeAsset: string; feeAmountMinor: string; seq: number;
}): JournalEntry[] {
  const pair = `${o.fromAsset}->${o.toAsset}`;
  return [
    { id: `${o.instructionId}-fx-${o.seq}-a`, tenantId: o.tenantId, instructionId: o.instructionId, asset: o.fromAsset, memo: `FX leg ${pair} source`, compensatesEntryId: null, postedAt: o.postedAt, lines: [
      { asset: o.fromAsset, account: `${o.fromAccount}`, debitMinor: "0", creditMinor: o.fromAmountMinor },
      { asset: o.fromAsset, account: `FX_CLEARING_${pair}`, debitMinor: o.fromAmountMinor, creditMinor: "0" }] },
    { id: `${o.instructionId}-fx-${o.seq}-b`, tenantId: o.tenantId, instructionId: o.instructionId, asset: o.toAsset, memo: `FX leg ${pair} target`, compensatesEntryId: null, postedAt: o.postedAt, lines: [
      { asset: o.toAsset, account: `FX_CLEARING_${pair}`, debitMinor: "0", creditMinor: o.toAmountMinor },
      { asset: o.toAsset, account: `${o.toAccount}`, debitMinor: o.toAmountMinor, creditMinor: "0" }] },
    { id: `${o.instructionId}-fx-${o.seq}-fee`, tenantId: o.tenantId, instructionId: o.instructionId, asset: o.feeAsset, memo: `FX fee ${pair}`, compensatesEntryId: null, postedAt: o.postedAt, lines: [
      { asset: o.feeAsset, account: `FEES`, debitMinor: o.feeAmountMinor, creditMinor: "0" },
      { asset: o.feeAsset, account: `PROVIDER_PAYABLE`, debitMinor: "0", creditMinor: o.feeAmountMinor }] },
  ];
}
