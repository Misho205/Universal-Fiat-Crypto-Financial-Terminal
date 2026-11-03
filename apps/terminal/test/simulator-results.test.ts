// Unit tests for the unified simulator result model.
// Covers: success, expected decline, timeout, invalid request, unauthorized,
// wrong crypto network, invalid contract, backend unavailable, CORS failure,
// duplicate (409), expired auth, local demo, and network-vs-response split.
import { describe, expect, it } from "vitest";
import { ApiError } from "@hybridpay/sdk";
import {
  errorToResult, headline, isNetworkFailure, localDemoResult, successToResult,
} from "../src/simulator-results";

const AT = "12:00:00";

describe("unified payment result model", () => {
  it("successful fiat payment → AUTHORIZED / PASSED / BACKEND_SANDBOX", () => {
    const r = successToResult("fiat-ok", { transactionId: "tx-1", state: "AUTHORIZED", providerRef: "pi_test_x", sandbox: true }, AT);
    expect(r).toMatchObject({
      scenarioId: "fiat-ok", transactionId: "tx-1", paymentState: "AUTHORIZED",
      testOutcome: "PASSED", executionSource: "BACKEND_SANDBOX",
      providerReference: "pi_test_x", errorCode: null, sandbox: true, timestamp: AT,
    });
    expect(headline(r)).toBe("Scenario PASSED — Payment AUTHORIZED");
  });
  it("expected provider decline (422 PROVIDER_ERROR) → DECLINED / PASSED, not unreachable", () => {
    const r = errorToResult("fiat-fail", new ApiError(422, "PROVIDER_ERROR: mock declined"), AT);
    expect(r).toMatchObject({
      paymentState: "DECLINED", testOutcome: "PASSED", executionSource: "BACKEND_SANDBOX",
      errorCode: "PROVIDER_ERROR", transactionId: null,
    });
    expect(isNetworkFailure(new ApiError(422, "x"))).toBe(false);
    expect(headline(r)).toBe("Scenario PASSED — Payment DECLINED");
  });
  it("provider timeout (502 TIMEOUT_UNKNOWN) → UNKNOWN / PASSED with idempotency guidance", () => {
    const r = errorToResult("fiat-timeout", new ApiError(502, "TIMEOUT_UNKNOWN: mock timeout -> UNKNOWN, query original before retry"), AT);
    expect(r).toMatchObject({ paymentState: "UNKNOWN", testOutcome: "PASSED", errorCode: "TIMEOUT_UNKNOWN" });
    expect(r.userMessage).toMatch(/SAME idempotency key/i);
  });
  it("invalid request (client 400) → REJECTED / PASSED, no money movement", () => {
    const r = errorToResult("fiat-ok", new ApiError(400, "amountMinor must be an integer"), AT);
    expect(r).toMatchObject({ paymentState: "REJECTED", testOutcome: "PASSED" });
    expect(r.userMessage).toMatch(/before any money movement/i);
  });
  it("missing token (401) → FAILED / AUTH_MISSING with sign-in guidance", () => {
    const r = errorToResult("fiat-ok", new ApiError(401, "missing bearer token"), AT);
    expect(r).toMatchObject({ paymentState: "UNKNOWN", testOutcome: "FAILED", errorCode: "AUTH_MISSING" });
    expect(r.userMessage).toMatch(/Sign in/i);
    expect(headline(r)).toBe("Scenario FAILED — Authentication required");
  });
  it("expired/invalid token (401) → FAILED / AUTH_INVALID", () => {
    const r = errorToResult("fiat-ok", new ApiError(401, "invalid token"), AT);
    expect(r).toMatchObject({ testOutcome: "FAILED", errorCode: "AUTH_INVALID" });
  });
  it("operator on admin path (403) → FAILED / AUTHZ_FORBIDDEN", () => {
    const r = errorToResult("fiat-ok", new ApiError(403, "admin role required"), AT);
    expect(r).toMatchObject({ paymentState: "UNKNOWN", testOutcome: "FAILED", errorCode: "AUTHZ_FORBIDDEN" });
  });
  it("wrong crypto network (client 422) → REJECTED / PASSED", () => {
    const r = errorToResult("crypto-wrong", new ApiError(422, "wrong-network or bad regtest address (expected bcrt1…)"), AT);
    expect(r).toMatchObject({ paymentState: "REJECTED", testOutcome: "PASSED", executionSource: "BACKEND_SANDBOX" });
  });
  it("backend accepting wrong network → FAILED (real defect signal)", () => {
    const r = successToResult("crypto-wrong", { transactionId: "tx-9" }, AT);
    expect(r).toMatchObject({ testOutcome: "FAILED", errorCode: "UNEXPECTED_ACCEPT" });
  });
  it("invalid contract (200 ok:false) → REJECTED / PASSED / BACKEND_SANDBOX", () => {
    const r = successToResult("contract-bad", { ok: false, errors: ["disallowed"], versionHash: null }, AT);
    expect(r).toMatchObject({ paymentState: "REJECTED", testOutcome: "PASSED", executionSource: "BACKEND_SANDBOX" });
    expect(headline(r)).toBe("Scenario PASSED — Payment REJECTED");
  });
  it("backend accepted garbage contract → FAILED", () => {
    expect(successToResult("contract-bad", { ok: true }, AT).testOutcome).toBe("FAILED");
  });
  it("backend unavailable (503 transport) → FAILED / NETWORK_UNREACHABLE, never LOCAL", () => {
    const e = new ApiError(503, "Backend unreachable at https://x. Message: fetch failed");
    expect(isNetworkFailure(e)).toBe(true);
    const r = errorToResult("fiat-ok", e, AT);
    expect(r).toMatchObject({ paymentState: "UNKNOWN", testOutcome: "FAILED", errorCode: "NETWORK_UNREACHABLE" });
    expect(r.executionSource).not.toBe("LOCAL_SIMULATION");
    expect(headline(r)).toBe("Scenario FAILED — Backend unreachable");
    expect(r.userMessage).toMatch(/Nothing was executed/);
  });
  it("CORS failure (fetch TypeError) → NETWORK_UNREACHABLE with allow-list hint", () => {
    const e = new TypeError("Failed to fetch");
    expect(isNetworkFailure(e)).toBe(true);
    const r = errorToResult("fiat-ok", e, AT);
    expect(r.errorCode).toBe("NETWORK_UNREACHABLE");
    expect(r.userMessage).toMatch(/allow-listed/i);
  });
  it("duplicate key (409) → FAILED / IDEMPOTENCY_CONFLICT with safe-replay guidance", () => {
    const r = errorToResult("fiat-ok", new ApiError(409, "IDEMPOTENCY_CONFLICT"), AT);
    expect(r).toMatchObject({ testOutcome: "FAILED", errorCode: "IDEMPOTENCY_CONFLICT" });
    expect(r.userMessage).toMatch(/SAME|SAME/i);
  });
  it("local demo outcomes are deterministic, PASSED, LOCAL_SIMULATION", () => {
    for (const s of ["fiat-ok", "fiat-fail", "fiat-timeout", "crypto-wrong", "contract-bad"] as const) {
      const r = localDemoResult(s, AT);
      expect(r).toMatchObject({ scenarioId: s, testOutcome: "PASSED", executionSource: "LOCAL_SIMULATION", sandbox: true });
    }
    expect(localDemoResult("fiat-fail", AT).paymentState).toBe("DECLINED");
    expect(localDemoResult("fiat-ok", AT).paymentState).toBe("AUTHORIZED");
  });
});
