"use client";
import * as React from "react";
import { ModalBackendClient, friendlyError } from "@hybridpay/sdk";
import { ConfirmDialog } from "./ui/dialog";
import { StatusBadge } from "./ui/badge";
import { Alert } from "./ui/feedback";
import { TableWrap, Td, Th } from "./ui/table";

export interface TxItem { kind: string; id: string; state: string; detail: string; ref: string; explorer?: string | null }

export function TxTable({ items, modal, isAdmin, locale, onChanged, onView }: {
  items: TxItem[]; modal: ModalBackendClient; isAdmin: boolean; locale: "bg" | "en";
  onChanged: () => void; onView?: (item: TxItem) => void;
}) {
  const [confirm, setConfirm] = React.useState<null | { paymentId: string; action: "cancel" | "refund" }>(null);
  const [err, setErr] = React.useState("");
  const [busy, setBusy] = React.useState(false);

  async function act() {
    if (!confirm) return;
    setBusy(true); setErr("");
    try {
      if (confirm.action === "cancel") await modal.fiatCancel(confirm.paymentId);
      else await modal.fiatRefund(confirm.paymentId);
      onChanged();
    } catch (e) { setErr(friendlyError(e, locale)); }
    finally { setBusy(false); setConfirm(null); }
  }

  if (!items.length) return <p className="muted">—</p>;
  return (
    <div>
      {err && <Alert tone="danger" className="mb-2">{err}</Alert>}
      <TableWrap label={locale === "bg" ? "Транзакции" : "Transactions"}>
        <thead><tr>
          <Th>ID</Th><Th>{locale === "bg" ? "Тип" : "Kind"}</Th><Th>{locale === "bg" ? "Състояние" : "State"}</Th>
          <Th>{locale === "bg" ? "Детайл" : "Detail"}</Th><Th>{locale === "bg" ? "Действия" : "Actions"}</Th>
        </tr></thead>
        <tbody>
          {items.map((i) => (
            <tr key={`${i.kind}:${i.id}`}>
              <Td><code className="num">{i.id}</code>{i.explorer && <div><a className="text-xs underline" href={i.explorer} target="_blank" rel="noreferrer">explorer</a></div>}</Td>
              <Td>{i.kind}</Td>
              <Td><StatusBadge state={i.state} /></Td>
              <Td className="max-w-64 truncate" title={i.detail}>{i.detail}</Td>
              <Td>
                {onView && (
                  <button onClick={() => onView(i)}
                    className="mr-1 rounded-lg border border-line px-2 py-1 text-xs font-semibold">View</button>
                )}
                {i.kind === "fiat" && isAdmin && (i.state === "pending" || i.state === "unknown") && (
                  <button disabled={busy} onClick={() => setConfirm({ paymentId: i.id, action: "cancel" })}
                    className="mr-1 rounded-lg border border-line px-2 py-1 text-xs font-semibold">Cancel</button>
                )}
                {i.kind === "fiat" && isAdmin && i.state === "succeeded" && (
                  <button disabled={busy} onClick={() => setConfirm({ paymentId: i.id, action: "refund" })}
                    className="rounded-lg border border-line px-2 py-1 text-xs font-semibold">Refund</button>
                )}
              </Td>
            </tr>
          ))}
        </tbody>
      </TableWrap>
      <ConfirmDialog open={!!confirm} onClose={() => setConfirm(null)} onConfirm={act}
        title={confirm?.action === "cancel" ? "Cancel payment" : "Refund payment"}
        body={locale === "bg"
          ? `Потвърдете ${confirm?.action} за ${confirm?.paymentId}. Sandbox — без реални пари.`
          : `Confirm ${confirm?.action} for ${confirm?.paymentId}. Sandbox — no real money.`}
        confirmLabel={locale === "bg" ? "Потвърди" : "Confirm"} danger />
    </div>
  );
}
