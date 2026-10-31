-- 001_init: minimal SQL mirror of migrations/schema.prisma (Prisma migrate wires up in M2; this keeps pilot runnable with psql).
CREATE TABLE IF NOT EXISTS "Tenant" (id TEXT PRIMARY KEY, name TEXT NOT NULL, "createdAt" TIMESTAMPTZ DEFAULT now());
CREATE TABLE IF NOT EXISTS "Store" (id TEXT PRIMARY KEY, "tenantId" TEXT NOT NULL, name TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS "User_" (id TEXT PRIMARY KEY, "tenantId" TEXT NOT NULL, email TEXT NOT NULL, role TEXT NOT NULL, UNIQUE("tenantId", email));
CREATE TABLE IF NOT EXISTS "Device" (id TEXT PRIMARY KEY, "tenantId" TEXT NOT NULL, label TEXT NOT NULL DEFAULT '', revoked BOOLEAN DEFAULT FALSE, credential TEXT NOT NULL DEFAULT '', "enrolledAt" TIMESTAMPTZ DEFAULT now());
CREATE TABLE IF NOT EXISTS "Order" (id TEXT PRIMARY KEY, "tenantId" TEXT NOT NULL, "storeId" TEXT NOT NULL, denomination TEXT NOT NULL, "totalMinor" BIGINT NOT NULL, status TEXT DEFAULT 'DRAFT', "createdAt" TIMESTAMPTZ DEFAULT now());
CREATE TABLE IF NOT EXISTS "Instruction" (id TEXT PRIMARY KEY, "tenantId" TEXT NOT NULL, "orderId" TEXT NOT NULL, "agreementId" TEXT NOT NULL, "methodRoute" TEXT NOT NULL, "paymentAsset" TEXT DEFAULT '', "amountMinor" BIGINT NOT NULL, state TEXT DEFAULT 'PENDING', "providerRef" TEXT, "idempotencyKey" TEXT UNIQUE NOT NULL, "deviceId" TEXT NOT NULL, "createdAt" TIMESTAMPTZ DEFAULT now());
CREATE TABLE IF NOT EXISTS "JournalEntry" (id TEXT PRIMARY KEY, "tenantId" TEXT NOT NULL, "instructionId" TEXT NOT NULL, asset TEXT NOT NULL, memo TEXT DEFAULT '', "compensatesEntry" TEXT, "postedAt" TIMESTAMPTZ DEFAULT now());
CREATE TABLE IF NOT EXISTS "JournalLine" (id TEXT PRIMARY KEY, "entryId" TEXT NOT NULL, asset TEXT NOT NULL, account TEXT NOT NULL, debit BIGINT NOT NULL, credit BIGINT NOT NULL);
CREATE TABLE IF NOT EXISTS "Outbox" (id TEXT PRIMARY KEY, "tenantId" TEXT NOT NULL, "aggregateId" TEXT NOT NULL, type TEXT NOT NULL, "payloadJson" TEXT NOT NULL, claimed BOOLEAN DEFAULT FALSE, "createdAt" TIMESTAMPTZ DEFAULT now());
CREATE TABLE IF NOT EXISTS "Inbox" (id TEXT PRIMARY KEY, provider TEXT NOT NULL, "eventId" TEXT NOT NULL, "payloadJson" TEXT NOT NULL, processed BOOLEAN DEFAULT FALSE, UNIQUE(provider, "eventId"));
