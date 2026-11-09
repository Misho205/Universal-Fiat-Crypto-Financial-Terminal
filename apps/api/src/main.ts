import "reflect-metadata";
import { NestFactory } from "@nestjs/core";
import { AppModule } from "./app.module";

export async function createApp() {
  const app = await NestFactory.create(AppModule, { logger: ["error", "warn", "log"] });
  // Sandbox CORS: explicit allow-list only (mirrors the Modal backend).
  // Override with CORS_ORIGINS="https://app.example.com,https://admin.example.com".
  // Wildcard "*" is refused — fail closed to the local-dev default.
  const rawOrigins = (process.env.CORS_ORIGINS ??
    "http://localhost:3000,http://localhost:3001").split(",");
  const origins = rawOrigins.map((s) => s.trim()).filter((s) => s.length > 0);
  const allowlist = origins.includes("*")
    ? ["http://localhost:3000", "http://localhost:3001"]
    : origins;
  app.enableCors({
    origin: allowlist,
    methods: ["GET", "POST"],
    allowedHeaders: ["Authorization", "Content-Type", "X-Tenant-Id", "Idempotency-Key"],
    credentials: false,
    maxAge: 600,
  });
  return app;
}

if (process.env.VITEST == null) {
  const port = Number(process.env.PORT_API ?? 3001);
  createApp().then((app) => app.listen(port, () => console.log(`api listening on ${port}`)));
}
