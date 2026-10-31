// Temporal worker entrypoint. Runs only with TEMPORAL_ADDRESS set; otherwise exits with guidance.
// Activities are the ONLY place provider APIs are called (never inside DB tx).
import { Worker, NativeConnection } from "@temporalio/worker";
import * as path from "node:path";
import * as activities from "./activities";

export async function createWorker() {
  const address = process.env.TEMPORAL_ADDRESS;
  if (!address) {
    console.log("TEMPORAL_ADDRESS not set — worker idle (unit tests use in-memory stub).");
    return null;
  }
  const connection = await NativeConnection.connect({ address });
  const worker = await Worker.create({
    connection,
    namespace: "default",
    taskQueue: "hybridpay-payments",
    workflowsPath: path.join(__dirname, "workflows.js"),
    activities,
  });
  return worker;
}

// ESM-safe direct-run guard (works with ts-node and compiled dist/main.js)
const isDirectRun = process.argv[1]?.endsWith("main.js") || process.argv[1]?.endsWith("main.ts");
if (isDirectRun) {
  createWorker().then(async (worker) => {
    if (!worker) return;
    console.log("Temporal worker running on queue hybridpay-payments");
    await worker.run();
  }).catch((err) => {
    console.error("worker failed to start", err);
    process.exit(1);
  });
}
