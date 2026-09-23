import { createServer } from "node:http";

import { createHttpApp } from "./http.js";

function csv(value: string | undefined): string[] | undefined {
  const items = value?.split(",").map((item) => item.trim()).filter(Boolean);
  return items?.length ? items : undefined;
}

const host = process.env.HOST || "127.0.0.1";
const port = Number.parseInt(process.env.PORT || "3000", 10);
if (!Number.isSafeInteger(port) || port < 1 || port > 65535) throw new Error("PORT must be 1-65535");

const allowedHosts = csv(process.env.ALLOWED_HOSTS);
if (!["127.0.0.1", "localhost", "::1"].includes(host) && !allowedHosts) {
  throw new Error("ALLOWED_HOSTS is required when binding to a non-loopback host");
}
if (!["127.0.0.1", "localhost", "::1"].includes(host) && !process.env.PUBLIC_ORIGIN) {
  throw new Error("PUBLIC_ORIGIN is required when binding to a non-loopback host");
}

const app = createHttpApp({
  host,
  allowedHosts,
  connectDomains: csv(process.env.OPENAI_FILE_DOWNLOAD_ORIGINS),
  widgetDomain: process.env.PUBLIC_ORIGIN,
});
const server = createServer(app);
server.requestTimeout = 15_000;
server.headersTimeout = 10_000;
server.listen(port, host, () => {
  process.stdout.write(`simplify-med-ui listening on ${host}:${port}\n`);
});

for (const signal of ["SIGINT", "SIGTERM"] as const) {
  process.on(signal, () => server.close(() => process.exit(0)));
}
