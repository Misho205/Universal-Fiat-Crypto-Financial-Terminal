import { describe, it, expect } from "vitest";
import * as fs from "node:fs";
import * as path from "node:path";

/**
 * Static accessibility contract (no browser).
 * Guards the WCAG 2.2 AA targets that are statically checkable so regressions
 * fail CI. This is NOT a replacement for a full axe-core run, screen-reader
 * pass, or device matrix — those remain manual (see DEMO_READINESS.md).
 */
const ROOT = path.resolve(__dirname, "..");

function readAll(dir: string, out: string[] = []): string[] {
  for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, e.name);
    if (e.isDirectory()) {
      if (e.name === "node_modules" || e.name === ".next" || e.name === "out") continue;
      readAll(p, out);
    } else if (/\.(tsx|ts)$/.test(e.name)) out.push(p);
  }
  return out;
}

const FILES = readAll(path.join(ROOT, "src")).concat(readAll(path.join(ROOT, "app")));
const src = (f: string) => fs.readFileSync(f, "utf8");

describe("a11y contract (static)", () => {
  it("no positive tabIndex (roving tabIndex -1/0 only)", () => {
    const bad: string[] = [];
    for (const f of FILES) {
      for (const m of src(f).matchAll(/tabIndex=\{?(-?\d+)[\s}]/g)) {
        const v = Number(m[1]);
        if (v > 0) bad.push(`${path.basename(f)}: tabIndex=${v}`);
      }
    }
    expect(bad).toEqual([]);
  });

  it("no raw <img> without alt (icons must be lucide aria-hidden or have alt)", () => {
    const bad = FILES.filter((f) => /<img(?![^>]*alt=)/.test(src(f)));
    expect(bad.map((f) => path.basename(f))).toEqual([]);
  });

  it("dialog primitive keeps role=dialog + aria-modal + Escape handling", () => {
    const d = src(path.join(ROOT, "src/components/ui/dialog.tsx"));
    expect(d).toMatch(/role="dialog"/);
    expect(d).toMatch(/aria-modal/);
    expect(d).toMatch(/Escape/);
  });

  it("tabs primitive keeps tablist/tab roles + aria-selected + arrow-key handling", () => {
    const t = src(path.join(ROOT, "src/components/ui/tabs.tsx"));
    expect(t).toMatch(/role="tablist"/);
    expect(t).toMatch(/role="tab"/);
    expect(t).toMatch(/aria-selected/);
    expect(t).toMatch(/ArrowRight|ArrowLeft/);
  });

  it("status badges expose text (never color-only)", () => {
    const b = src(path.join(ROOT, "src/components/ui/badge.tsx"));
    expect(b).toMatch(/aria-label/);
  });

  it("form Field wires error to input via aria-invalid/describedby", () => {
    const f = src(path.join(ROOT, "src/components/ui/field.tsx"));
    expect(f).toMatch(/aria-invalid/);
    expect(f).toMatch(/aria-describedby/);
  });

  it("tables are scroll regions with labels; charts have SR table fallback", () => {
    const t = src(path.join(ROOT, "src/components/ui/table.tsx"));
    expect(t).toMatch(/role="region"/);
    expect(t).toMatch(/aria-label/);
    const c = src(path.join(ROOT, "src/components/ui/chart.tsx"));
    expect(c).toMatch(/role="img"/);
    expect(c).toMatch(/<table/);
  });

  it("global CSS keeps focus-visible + reduced-motion + skip-link styles", () => {
    const css = src(path.join(ROOT, "app/globals.css"));
    expect(css).toMatch(/focus-visible/);
    expect(css).toMatch(/prefers-reduced-motion/);
    const shell = src(path.join(ROOT, "src/components/shell.tsx"));
    expect(shell).toMatch(/skip-link|sr-only/);
    expect(shell).toMatch(/aria-label/);
  });

  it("every page sets document language and main landmark via layout/shell", () => {
    const layout = src(path.join(ROOT, "app/layout.tsx"));
    expect(layout).toMatch(/<html lang="en"/);
    const shell = src(path.join(ROOT, "src/components/shell.tsx"));
    expect(shell).toMatch(/<main id="main"/);
    expect(shell).toMatch(/<nav aria-label/);
  });

  it("live regions exist for async updates (aria-live / role=status)", () => {
    const hits = FILES.filter((f) => /aria-live|role="status"|role="alert"/.test(src(f)));
    expect(hits.length).toBeGreaterThan(5);
  });

  it("money values use tabular figures with text labels (no color-only amounts)", () => {
    const m = src(path.join(ROOT, "src/components/ui/money.tsx"));
    expect(m).toMatch(/tabular-nums|num/);
    expect(m).toMatch(/aria-label/);
  });
});
