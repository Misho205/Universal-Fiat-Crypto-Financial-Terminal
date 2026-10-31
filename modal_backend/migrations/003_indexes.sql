-- 003_indexes: query paths used by dashboard/history (tenant-scoped lists, provider refs)
CREATE INDEX IF NOT EXISTS idx_tx_tenant ON transactions(tenant);
CREATE INDEX IF NOT EXISTS idx_tx_tenant_state ON transactions(tenant, state);
CREATE INDEX IF NOT EXISTS idx_tx_provider_ref ON transactions(provider_ref);
CREATE INDEX IF NOT EXISTS idx_idem_tenant ON idempotency(tenant);
CREATE INDEX IF NOT EXISTS idx_evm_tenant ON evm_payments(tenant);
CREATE INDEX IF NOT EXISTS idx_evm_tenant_state ON evm_payments(tenant, state);
CREATE INDEX IF NOT EXISTS idx_evm_provider_tx ON evm_payments(tx_hash);
CREATE INDEX IF NOT EXISTS idx_pag_tenant ON contract_agreements(tenant);
CREATE INDEX IF NOT EXISTS idx_pag_tenant_state ON contract_agreements(tenant, state);
