import { readFileSync } from "node:fs";
import { createServer } from "node:http";

import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StreamableHTTPClientTransport } from "@modelcontextprotocol/sdk/client/streamableHttp.js";
import { InMemoryTransport } from "@modelcontextprotocol/sdk/inMemory.js";
import { afterEach, describe, expect, it, vi } from "vitest";

import { RESOURCE_MIME_TYPE, RESOURCE_URI, TOOL_NAME } from "../src/contracts.js";
import { createHttpApp } from "../src/http.js";
import { createPresentationServer } from "../src/mcp.js";

const connected: Array<{ client: Client; server: ReturnType<typeof createPresentationServer> }> = [];

async function inMemoryClient() {
  const server = createPresentationServer({
    widgetBundle: "window.__syntheticWidget = true;",
    connectDomains: ["https://files.example.test"],
    widgetDomain: "https://plugin.example.test",
  });
  const client = new Client({ name: "contract-test", version: "1.0.0" });
  const [clientTransport, serverTransport] = InMemoryTransport.createLinkedPair();
  await Promise.all([server.connect(serverTransport), client.connect(clientTransport)]);
  connected.push({ client, server });
  return client;
}

afterEach(async () => {
  vi.restoreAllMocks();
  await Promise.all(connected.splice(0).map(async ({ client, server }) => {
    await client.close(); await server.close();
  }));
});

describe("presentation MCP contract", () => {
  it("exposes exactly one tool with the OpenAI file schema and UI metadata", async () => {
    const client = await inMemoryClient();
    const tools = (await client.listTools()).tools;
    expect(tools).toHaveLength(1);
    const tool = tools[0];
    expect(tool.name).toBe(TOOL_NAME);
    expect(tool.annotations).toEqual({ readOnlyHint: true, openWorldHint: false, destructiveHint: false });
    expect(tool._meta?.["openai/fileParams"]).toEqual(["report"]);
    expect((tool._meta?.ui as { resourceUri: string }).resourceUri).toBe(RESOURCE_URI);
    const schema = tool.inputSchema as any;
    expect(schema.required).toEqual(["report"]);
    expect(schema.additionalProperties).toBe(false);
    const report = schema.properties.report;
    expect(Object.keys(report.properties).sort()).toEqual(["download_url", "file_id", "file_name", "mime_type"]);
    expect(report.required.sort()).toEqual(["download_url", "file_id"]);
    expect(report.additionalProperties).toBe(false);
  });

  it("serves one immutable, CSP-scoped MCP App resource", async () => {
    const client = await inMemoryClient();
    const resources = (await client.listResources()).resources;
    expect(resources).toHaveLength(1);
    expect(resources[0].uri).toBe(RESOURCE_URI);
    expect(resources[0].mimeType).toBe(RESOURCE_MIME_TYPE);
    const result = await client.readResource({ uri: RESOURCE_URI });
    expect(result.contents).toHaveLength(1);
    const content = result.contents[0] as any;
    expect(content.mimeType).toBe(RESOURCE_MIME_TYPE);
    expect(content.text).toContain("window.__syntheticWidget = true");
    expect(content._meta.ui.domain).toBe("https://plugin.example.test");
    expect(content._meta.ui.csp).toEqual({
      connectDomains: ["https://files.example.test"], resourceDomains: [], frameDomains: [],
    });
  });

  it("does not fetch, echo, or log the temporary file capability", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockRejectedValue(new Error("network trap"));
    const logSpy = vi.spyOn(console, "log").mockImplementation(() => undefined);
    const errorSpy = vi.spyOn(console, "error").mockImplementation(() => undefined);
    const client = await inMemoryClient();
    const canary = "PRIVATE-CANARY-4f0a";
    const result = await client.callTool({
      name: TOOL_NAME,
      arguments: {
        report: {
          download_url: `https://127.0.0.1:1/${canary}`,
          file_id: `file-${canary}`,
          mime_type: "application/json",
          file_name: `${canary}.json`,
        },
      },
    });
    expect(fetchSpy).not.toHaveBeenCalled();
    expect(result.isError).not.toBe(true);
    expect(JSON.stringify(result)).not.toContain(canary);
    expect(JSON.stringify(logSpy.mock.calls)).not.toContain(canary);
    expect(JSON.stringify(errorSpy.mock.calls)).not.toContain(canary);
  });

  it.each([
    [{}, "missing report"],
    [{ report: { download_url: "x", file_id: "f" }, extra: true }, "extra top-level field"],
    [{ report: { download_url: "x", file_id: "f", unexpected: true } }, "extra file field"],
    [{ report: { download_url: "x", file_id: "f", mime_type: "text/plain" } }, "wrong MIME"],
    [{ report: { download_url: "x", file_id: "f", file_name: "report.pdf" } }, "wrong extension"],
  ])("rejects invalid input: %s", async (argumentsValue, _label) => {
    const client = await inMemoryClient();
    const result = await client.callTool({ name: TOOL_NAME, arguments: argumentsValue });
    expect(result.isError).toBe(true);
  });

  it("rejects wildcard or non-origin CSP domains", () => {
    expect(() => createPresentationServer({ widgetBundle: "x", connectDomains: ["https://*/"] })).toThrow();
    expect(() => createPresentationServer({ widgetBundle: "x", connectDomains: ["https://example.test/path"] })).toThrow();
  });
});

describe("streamable HTTP service", () => {
  it("supports health and a real streamable-HTTP MCP client", async () => {
    const app = createHttpApp({ host: "127.0.0.1", widgetBundle: "window.widget=true;" });
    const httpServer = createServer(app);
    await new Promise<void>((resolve) => httpServer.listen(0, "127.0.0.1", resolve));
    const address = httpServer.address();
    if (!address || typeof address === "string") throw new Error("missing address");
    const base = `http://127.0.0.1:${address.port}`;
    try {
      const health = await fetch(`${base}/healthz`);
      expect(health.status).toBe(200);
      expect(await health.json()).toEqual({ status: "ok", version: "0.1.0" });
      const client = new Client({ name: "http-test", version: "1.0.0" });
      await client.connect(new StreamableHTTPClientTransport(new URL(`${base}/mcp`)));
      expect((await client.listTools()).tools.map((tool) => tool.name)).toEqual([TOOL_NAME]);
      await client.close();
    } finally {
      await new Promise<void>((resolve, reject) => httpServer.close((error) => error ? reject(error) : resolve()));
    }
  });

  it("rejects non-loopback browser origins and enforces the 64 KiB request limit", async () => {
    const app = createHttpApp({ host: "127.0.0.1", widgetBundle: "window.widget=true;" });
    const httpServer = createServer(app);
    await new Promise<void>((resolve) => httpServer.listen(0, "127.0.0.1", resolve));
    const address = httpServer.address();
    if (!address || typeof address === "string") throw new Error("missing address");
    const url = `http://127.0.0.1:${address.port}/mcp`;
    try {
      const forbidden = await fetch(url, { method: "POST", headers: { origin: "https://attacker.example", "content-type": "application/json" }, body: "{}" });
      expect(forbidden.status).toBe(403);
      const canary = "PRIVATE-BODY-CANARY";
      const oversized = await fetch(url, { method: "POST", headers: { origin: "http://localhost:3000", "content-type": "application/json" }, body: JSON.stringify({ canary, padding: "x".repeat(70 * 1024) }) });
      expect(oversized.status).toBe(413);
      expect(await oversized.text()).not.toContain(canary);
    } finally {
      await new Promise<void>((resolve, reject) => httpServer.close((error) => error ? reject(error) : resolve()));
    }
  });

  it("contains no report fixture in server source or health output", () => {
    const fixture = readFileSync(new URL("./fixtures/final-report.json", import.meta.url), "utf8");
    expect(fixture).toContain("synthetic-widget-test");
    expect(readFileSync(new URL("../src/http.ts", import.meta.url), "utf8")).not.toContain("synthetic-widget-test");
  });
});
