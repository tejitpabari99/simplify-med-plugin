import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { StreamableHTTPServerTransport } from "@modelcontextprotocol/sdk/server/streamableHttp.js";
import type { Express, NextFunction, Request, Response } from "express";
import express from "express";

import { SERVER_VERSION } from "./contracts.js";
import { createPresentationServer } from "./mcp.js";

export type HttpOptions = {
  host: string;
  allowedHosts?: string[];
  connectDomains?: string[];
  widgetDomain?: string;
  widgetBundle?: string;
};

function loadWidgetBundle(): string {
  const path = fileURLToPath(new URL("../ui/dist/report-viewer.js", import.meta.url));
  return readFileSync(path, "utf8");
}

export function createHttpApp(options: HttpOptions): Express {
  const app = express();
  const widgetBundle = options.widgetBundle ?? loadWidgetBundle();
  const loopback = ["localhost", "127.0.0.1", "[::1]"];
  const allowedHosts = options.allowedHosts ?? (loopback.includes(options.host) || options.host === "::1" ? loopback : []);
  // Browser-origin allowlist is derived from the same allowedHosts used for the Host
  // header check above (ALLOWED_HOSTS / the loopback default), not a second hardcoded
  // loopback-only list. This lets the server's own public host (e.g. the ngrok/PUBLIC_ORIGIN
  // hostname) pass a browser Origin check without opening the door to arbitrary origins.
  const browserOriginAllowlist = new Set(allowedHosts);

  app.disable("x-powered-by");
  app.use((request, response, next) => {
    const hostHeader = request.get("host");
    if (!hostHeader) return response.status(403).json({ error: "Missing Host header" });
    try {
      if (allowedHosts.includes(new URL(`http://${hostHeader}`).hostname)) return next();
    } catch { /* Reject malformed Host headers below. */ }
    return response.status(403).json({ error: "Host not allowed" });
  });
  app.use((request, response, next) => {
    const origin = request.get("origin");
    if (!origin) return next();
    try {
      if (browserOriginAllowlist.has(new URL(origin).hostname)) return next();
    } catch { /* Reject malformed origins below. */ }
    return response.status(403).json({ error: "Origin not allowed" });
  });
  app.use(express.json({ limit: "64kb", strict: true }));
  app.use((error: unknown, _request: Request, response: Response, next: NextFunction) => {
    if (!error) return next();
    const status = (error as { status?: number; type?: string }).status === 413 ||
      (error as { type?: string }).type === "entity.too.large" ? 413 : 400;
    return response.status(status).json({ error: status === 413 ? "Request body too large" : "Invalid JSON request" });
  });
  app.get("/healthz", (_request, response) => {
    response.set("Cache-Control", "no-store").json({ status: "ok", version: SERVER_VERSION });
  });

  const handleMcp = async (request: Request, response: Response) => {
    const server = createPresentationServer({
      widgetBundle,
      connectDomains: options.connectDomains,
      widgetDomain: options.widgetDomain,
    });
    // This server is stateless and never streams multiple messages per request, so a
    // plain JSON response is correct here (the streamable-HTTP spec allows either per
    // request) and avoids the default SSE (`text/event-stream`) response mode, which was
    // observed to hang/truncate through the public ngrok tunnel (200 status, a
    // Content-Length matching the full body, but zero bytes actually delivered) even
    // though the identical request succeeded against 127.0.0.1 directly. Returning a
    // single complete `application/json` body sidesteps whatever proxy/stream handling
    // was mishandling the SSE framing.
    const transport = new StreamableHTTPServerTransport({ sessionIdGenerator: undefined, enableJsonResponse: true });
    response.on("close", () => {
      void transport.close();
      void server.close();
    });
    try {
      await server.connect(transport);
      await transport.handleRequest(request, response, request.body);
    } catch {
      if (!response.headersSent) {
        response.status(500).json({ error: "MCP request failed" });
      }
    }
  };

  app.all("/mcp", handleMcp);
  app.use((_request, response) => response.status(404).json({ error: "Not found" }));
  return app;
}
