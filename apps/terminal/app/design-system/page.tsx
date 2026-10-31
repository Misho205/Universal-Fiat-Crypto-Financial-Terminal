"use client";
import * as React from "react";
import { Shell } from "../../src/components/shell";
import { Alert, EmptyState, Skeleton } from "../../src/components/ui/feedback";
import { Button } from "../../src/components/ui/button";
import { Badge, SandboxBadge, StatusBadge } from "../../src/components/ui/badge";
import { Card, CardTitle } from "../../src/components/ui/card";
import { StateBarChart } from "../../src/components/ui/chart";
import { ConfirmDialog, Dialog } from "../../src/components/ui/dialog";
import { Field, Input, Select, Textarea } from "../../src/components/ui/field";
import { Money, Wei } from "../../src/components/ui/money";
import { TableWrap, Td, Th } from "../../src/components/ui/table";
import { Tabs } from "../../src/components/ui/tabs";
import { ThemeToggle } from "../../src/components/ui/theme-toggle";

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <Card>
      <CardTitle>{title}</CardTitle>
      <div className="flex flex-wrap items-center gap-2">{children}</div>
    </Card>
  );
}

export default function DesignSystemPage() {
  const [tab, setTab] = React.useState("a");
  const [dlg, setDlg] = React.useState(false);
  const [confirm, setConfirm] = React.useState(false);
  const [done, setDone] = React.useState("");
  return (
    <Shell locale="en" role="—">
      <h1 className="mb-1 text-2xl font-extrabold">HybridPay Design System</h1>
      <p className="muted mb-4">Tokens, components, states. Light + dark (toggle in header). Target: WCAG 2.2 AA. No gradients, no glassmorphism, no animation clutter.</p>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        <Section title="1 · Colors & status">
          {(["succeeded", "pending", "failed", "created", "expired", "unknown"] as const).map((s) => (
            <StatusBadge key={s} state={s} />
          ))}
          <Badge tone="info">info</Badge>
          <SandboxBadge sandbox /> <SandboxBadge sandbox={false} />
        </Section>

        <Section title="2 · Buttons">
          <Button>Primary</Button>
          <Button variant="secondary">Secondary</Button>
          <Button variant="ghost">Ghost</Button>
          <Button variant="danger">Danger</Button>
          <Button size="sm">Small</Button>
          <Button disabled>Disabled</Button>
        </Section>

        <Section title="3 · Money & amounts">
          <Money minor="2599" currency="EUR" /> <Money minor="100000" currency="BGN" />
          <Wei value="1000000000000000" />
        </Section>

        <Section title="4 · Form + validation">
          <div className="w-full max-w-sm">
            <Field label="Amount (minor units)" error="Must be an integer, e.g. 1000.">
              <Input defaultValue="10.00" aria-label="demo invalid" />
            </Field>
            <Field label="Currency">
              <Select defaultValue="EUR" aria-label="demo select"><option>EUR</option><option>USD</option></Select>
            </Field>
            <Field label="Note"><Textarea rows={2} defaultValue="demo" aria-label="demo textarea" /></Field>
          </div>
        </Section>

        <Section title="5 · Table">
          <TableWrap label="Demo table">
            <thead><tr><Th>ID</Th><Th>State</Th><Th>Amount</Th></tr></thead>
            <tbody>
              <tr><Td><code>pay-1</code></Td><Td><StatusBadge state="succeeded" /></Td><Td><Money minor="1000" currency="EUR" /></Td></tr>
              <tr><Td><code>pay-2</code></Td><Td><StatusBadge state="pending" /></Td><Td><Money minor="250" currency="USD" /></Td></tr>
            </tbody>
          </TableWrap>
        </Section>

        <Section title="6 · Alerts, skeleton, empty">
          <div className="w-full space-y-2">
            <Alert tone="info">Info: quote expires in 60 seconds.</Alert>
            <Alert tone="ok">Success: payment confirmed by provider.</Alert>
            <Alert tone="warn">Warning: rate limit approached, retry shortly.</Alert>
            <Alert tone="danger">Error: invalid signature, webhook rejected.</Alert>
            <Skeleton className="h-6 w-2/3" />
            <EmptyState title="No transactions yet" body="Create a sandbox payment to see it here." />
          </div>
        </Section>

        <Section title="7 · Dialogs & confirmation">
          <Button variant="secondary" onClick={() => setDlg(true)}>Open dialog (Esc closes)</Button>
          <Button variant="danger" onClick={() => setConfirm(true)}>Refund… (confirm)</Button>
          <Dialog open={dlg} onClose={() => setDlg(false)} title="Sample dialog">
            <p className="muted">Focus moves here on open and returns on close. Press Escape to dismiss.</p>
          </Dialog>
          <ConfirmDialog open={confirm} onClose={() => setConfirm(false)} onConfirm={() => setDone("confirmed at " + new Date().toLocaleTimeString())}
            title="Confirm refund" body="Sandbox only — no real money moves." confirmLabel="Confirm refund" danger />
          {done && <Alert tone="ok">{done}</Alert>}
        </Section>

        <Section title="8 · Tabs (keyboard: ← → Home End)">
          <Tabs label="demo tabs" value={tab} onChange={setTab} tabs={[{ id: "a", label: "Overview" }, { id: "b", label: "Activity" }, { id: "c", label: "Settings" }]} />
        </Section>

        <Section title="9 · Chart (with table fallback for SR)">
          <StateBarChart label="Demo: payments by state" data={[{ name: "succeeded", value: 4 }, { name: "pending", value: 2 }, { name: "failed", value: 1 }]} />
        </Section>

        <Section title="10 · Theme">
          <ThemeToggle locale="en" />
          <span className="muted text-sm">Toggles <code>.dark</code> on <code>&lt;html&gt;</code>; charts and badges adapt via CSS variables.</span>
        </Section>
      </div>

      <Card>
        <CardTitle>Accessibility contract (WCAG 2.2 AA)</CardTitle>
        <ul className="list-disc space-y-1 pl-5 text-sm">
          <li>Every status has a text label + shape, never color alone.</li>
          <li>All interactive elements are keyboard reachable with visible focus.</li>
          <li>Dialogs trap initial focus, close on Escape, return focus on dismiss.</li>
          <li>Live regions (`role=status/alert`, `aria-live`) announce async results.</li>
          <li>Charts always ship a screen-reader data table.</li>
          <li>Text contrast ≥ 4.5:1 on both themes; `prefers-reduced-motion` disables animation.</li>
        </ul>
      </Card>
    </Shell>
  );
}
