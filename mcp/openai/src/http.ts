import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { createMcpExpressApp } from "@modelcontextprotocol/sdk/server/express.js";
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
  const app = createMcpExpressApp({ host: options.host, allowedHosts: options.allowedHosts });
  const widgetBundle = options.widgetBundle ?? loadWidgetBundle();

  app.disable("x-powered-by");
  app.use(express.json({ limit: "64kb", strict: true }));
  app.use((error: unknown, _request: Request, response: Response, next: NextFunction) => {
    if (!error) return next();
    return response.status(400).json({ error: "Invalid JSON request" });
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
    const transport = new StreamableHTTPServerTransport({ sessionIdGenerator: undefined });
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
