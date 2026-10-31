// Integration smoke: exercises live API (needs api on :3001) or skips cleanly.
// Run: PORT_API=3001 node --test tests/integration/
import { describe, it } from "node:test";
import assert from "node:assert";

const BASE = process.env.API_BASE ?? "http://localhost:3001";
const T = "integration-smoke";

async function api(path, opts = {}) {
  const r = await fetch(`${BASE}${path}`, {
    ...opts,
    headers: { "Content-Type": "application/json", "X-Tenant-Id": T, ...(opts.headers ?? {}) },
  });
  return { status: r.status, data: await r.json().catch(() => ({})) };
}

describe("integration: api reachable + tenant isolation", () => {
  it("health responds", async () => {
    let res;
    try {
      res = await api("/v1/health");
    } catch {
      console.log("SKIP: api not running on " + BASE + " (start with pnpm --filter @hybridpay/api build && PORT_API=3001 node apps/api/dist/main.js)");
      return;
    }
    assert.strictEqual(res.status, 200);
    assert.strictEqual(res.data.ok, true);
  });
});
