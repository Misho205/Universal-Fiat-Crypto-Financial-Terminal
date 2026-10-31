import "reflect-metadata";
import { NestFactory } from "@nestjs/core";
import { AppModule } from "./app.module";

export async function createApp() {
  const app = await NestFactory.create(AppModule, { logger: ["error", "warn", "log"] });
  app.enableCors();
  return app;
}

if (process.env.VITEST == null) {
  const port = Number(process.env.PORT_API ?? 3001);
  createApp().then((app) => app.listen(port, () => console.log(`api listening on ${port}`)));
}
