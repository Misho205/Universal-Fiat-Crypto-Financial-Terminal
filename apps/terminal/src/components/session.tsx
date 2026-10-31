"use client";
import * as React from "react";
import { ModalBackendClient } from "@hybridpay/sdk";

const MODAL_URL = process.env.NEXT_PUBLIC_MODAL_API_URL ?? process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const DEV_TOKEN = process.env.NEXT_PUBLIC_API_TOKEN ?? "";

export interface Session {
  modal: ModalBackendClient;
  tenant: string; setTenant: (t: string) => void;
  token: string; setTokenInput: (t: string) => void;
  role: string; refreshRole: () => Promise<void>;
  signIn: (raw: string) => void; logout: () => void;
}

/** In-memory session: token lives in React state only (never localStorage). */
export function useSession() {
  const [tenant, setTenant] = React.useState("demo-tenant");
  const [token, setToken] = React.useState(DEV_TOKEN);
  const [tokenInput, setTokenInput] = React.useState("");
  const [role, setRole] = React.useState("—");
  const modal = React.useMemo(
    () => new ModalBackendClient({ baseUrl: MODAL_URL, tenantId: tenant, token: token || undefined }),
    [tenant, token]);
  async function refreshRole() {
    try { const r = await modal.me(); setRole((r.data as { role: string }).role); }
    catch { setRole("unreachable"); }
  }
  React.useEffect(() => { refreshRole(); }, [tenant, token]);
  return {
    modal, tenant, setTenant, token, role, refreshRole,
    tokenInput, setTokenInput,
    signIn: (raw: string) => { setToken(raw); setTokenInput(""); },
    logout: () => { setToken(""); setTokenInput(""); setRole("—"); },
  };
}
