// HybridPay hackathon demo recorder (Playwright + Chromium, 1920x1080).
// Records REAL sandbox interactions — stops and reports on any failed step,
// never fabricates a result. Token comes only from DEMO_OP_TOKEN env and is
// typed exclusively into type=password fields (rendered as dots).
// Run: DEMO_OP_TOKEN=<operator-token> APP_URL=http://localhost:3000 npx tsx demo-video/record-demo.ts
import { chromium } from "playwright-core";
import * as fs from "node:fs";

const APP = process.env.APP_URL ?? "http://localhost:3000";
const TOKEN = process.env.DEMO_OP_TOKEN ?? "";
if (!TOKEN) throw new Error("DEMO_OP_TOKEN env is required (operator token; never committed)");

const OUT = new URL("./clips/", import.meta.url);
fs.mkdirSync(OUT, { recursive: true });

async function signIn(page: import("playwright-core").Page, ready: RegExp = /signed in|operator/) {
  const pwd = page.locator('input[type="password"]').first();
  await pwd.fill(TOKEN);
  await page.getByRole("button", { name: "Sign in" }).first().click();
  await page.getByText(ready).first().waitFor({ timeout: 20000 });
}

async function scene(name: string, fn: (page: import("playwright-core").Page) => Promise<void>) {
  const browser = await chromium.launch();
  const ctx = await browser.newContext({
    viewport: { width: 1920, height: 1080 },
    recordVideo: { dir: OUT.pathname, size: { width: 1920, height: 1080 } },
  });
  const page = await ctx.newPage();
  try {
    await fn(page);
  } catch (e) {
    console.error(`SCENE FAILED: ${name}:`, (e as Error).message);
    await ctx.close();
    await browser.close();
    throw e;
  }
  const vpath = await page.video()?.path();
  await ctx.close();
  await browser.close();
  if (vpath) fs.renameSync(vpath, new URL(`./${name}.webm`, OUT));
  console.log(`scene ok: ${name}`);
}

async function main() {
await scene("01-terminal", async (page) => {
  await page.goto(APP + "/", { waitUntil: "networkidle" });
  await page.getByRole("button", { name: "Refresh health" }).click();
  await page.getByText("liveMode").first().waitFor({ timeout: 20000 });
  await signIn(page);
  await page.getByText("Role:").first().waitFor();
  await page.waitForTimeout(800);
  await page.mouse.wheel(0, 900); await page.waitForTimeout(1200);
  await page.mouse.wheel(0, 900); await page.waitForTimeout(1200);
  await page.mouse.wheel(0, -1800); await page.waitForTimeout(1500);
});

await scene("02-banking", async (page) => {
  await page.goto(APP + "/banking/", { waitUntil: "networkidle" });
  await page.getByText("Banking Workspace").first().waitFor({ timeout: 20000 });
  await signIn(page);
  await page.getByRole("button", { name: "Refresh" }).first().click();
  await page.waitForTimeout(3000);
  await page.mouse.wheel(0, 1100); await page.waitForTimeout(1500);
  await page.mouse.wheel(0, 1100); await page.waitForTimeout(1500);
  await page.mouse.wheel(0, -2200); await page.waitForTimeout(2000);
});

await scene("03-personal-fiat", async (page) => {
  await page.goto(APP + "/personal/", { waitUntil: "networkidle" });
  await signIn(page);
  await page.getByRole("button", { name: "Send", exact: true }).click();
  await page.getByRole("button", { name: "Next" }).click();
  await page.getByRole("button", { name: "Next" }).click();
  await page.getByRole("button", { name: "Next" }).click();
  await page.getByRole("button", { name: "Confirm & send" }).click();
  await page.getByText("Done:", { exact: false }).first().waitFor({ timeout: 30000 });
  await page.waitForTimeout(5000);
});

await scene("04-simulator", async (page) => {
  await page.goto(APP + "/simulator/", { waitUntil: "networkidle" });
  await signIn(page);
  await page.getByRole("button", { name: /Successful fiat payment/ }).click();
  await page.getByText("Scenario PASSED", { exact: false }).first().waitFor({ timeout: 30000 });
  await page.getByRole("button", { name: /Declined payment/ }).click();
  await page.getByText("Payment DECLINED", { exact: false }).first().waitFor({ timeout: 30000 });
  await page.waitForTimeout(2500);
  await page.getByRole("button", { name: /Timeout/ }).click();
  await page.getByText("query-original", { exact: false }).first().waitFor({ timeout: 30000 });
  await page.waitForTimeout(2500);
  await page.getByRole("button", { name: /Contract with error/ }).click();
  await page.getByText("Payment REJECTED", { exact: false }).first().waitFor({ timeout: 30000 });
  await page.waitForTimeout(5000);
});

await scene("05-contracts", async (page) => {
  await page.goto(APP + "/personal/", { waitUntil: "networkidle" });
  await signIn(page);
  await page.getByRole("button", { name: "Scheduled", exact: true }).click();
  await page.getByRole("button", { name: "Create & activate" }).click();
  await page.getByText("Created and activated", { exact: false }).first().waitFor({ timeout: 30000 });
  await page.getByRole("button", { name: "Check status" }).click();
  await page.waitForTimeout(4000);
});

await scene("06-ai", async (page) => {
  await page.goto(APP + "/personal/", { waitUntil: "networkidle" });
  await signIn(page);
  await page.getByRole("button", { name: "Assistant", exact: true }).click();
  await page.getByPlaceholder(/Ask about payments/).fill("What can you do?");
  await page.getByRole("button", { name: "Ask", exact: true }).click();
  await page.getByText("AI", { exact: true }).first().waitFor({ timeout: 30000 });
  await page.waitForTimeout(5000);
});

await scene("07-history", async (page) => {
  await page.goto(APP + "/personal/", { waitUntil: "networkidle" });
  await signIn(page);
  await page.getByRole("button", { name: "History", exact: true }).click();
  await page.getByRole("button", { name: "Search" }).click();
  await page.getByText("pay-", { exact: false }).first().waitFor({ timeout: 30000 });
  await page.waitForTimeout(2000);
  await page.getByRole("button", { name: "Details" }).first().click();
  await page.waitForTimeout(4000);
});

await scene("08-private", async (page) => {
  await page.goto(APP + "/private/", { waitUntil: "networkidle" });
  await page.getByText("Private Workspace").first().waitFor({ timeout: 20000 });
  await signIn(page);
  await page.waitForTimeout(1000);
  await page.mouse.wheel(0, 800); await page.waitForTimeout(2000);
  await page.mouse.wheel(0, -800); await page.waitForTimeout(2000);
});

await scene("09-receive", async (page) => {
  await page.goto(APP + "/personal/", { waitUntil: "networkidle" });
  await signIn(page);
  await page.getByRole("button", { name: "Receive", exact: true }).click();
  await page.getByLabel(/Sepolia address/).fill("0x" + "ab".repeat(20));
  await page.getByRole("button", { name: "Create request" }).click();
  await page.getByText("paymentId=", { exact: false }).first().waitFor({ timeout: 30000 });
  await page.waitForTimeout(2000);
  await page.getByRole("button", { name: "Track", exact: true }).click();
  await page.waitForTimeout(4000);
});

console.log("ALL SCENES RECORDED");
}

main().catch((e) => { console.error("RECORDING ABORTED:", (e as Error).message); process.exit(1); });
