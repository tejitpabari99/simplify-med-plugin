import { registerAppResource, registerAppTool } from "@modelcontextprotocol/ext-apps/server";
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";

import {
  RESOURCE_MIME_TYPE,
  RESOURCE_URI,
  SERVER_NAME,
  SERVER_VERSION,
  TOOL_CONFIG,
  TOOL_NAME,
  renderInputSchema,
} from "./contracts.js";
import { buildWidgetHtml } from "./widget-html.js";

export type PresentationServerOptions = {
  widgetBundle: string;
  connectDomains?: string[];
  widgetDomain?: string;
};

function cleanDomains(domains: string[] | undefined): string[] {
  return (domains ?? []).map((domain) => domain.trim()).filter(Boolean).map((domain) => {
    const url = new URL(domain);
    if (url.pathname !== "/" || url.search || url.hash || !["https:", "http:"].includes(url.protocol)) {
      throw new Error("CSP connect domains must be bare HTTP(S) origins");
    }
    if (url.hostname === "*") throw new Error("Wildcard CSP domains are forbidden");
    return url.origin;
  });
}

export function createPresentationServer(options: PresentationServerOptions): McpServer {
  const connectDomains = cleanDomains(options.connectDomains);
  const widgetDomain = options.widgetDomain ? cleanDomains([options.widgetDomain])[0] : undefined;
  const server = new McpServer(
    { name: SERVER_NAME, version: SERVER_VERSION },
    {
      capabilities: { tools: {}, resources: {} },
      instructions:
        "Presentation only. Call the render tool only with a completed Simplify Med final report JSON file. Never pass source or intermediate medical files.",
    },
  );

  registerAppTool(
    server,
    TOOL_NAME,
    { ...TOOL_CONFIG, inputSchema: renderInputSchema },
    async () => ({ content: [{ type: "text", text: "Opening the completed report." }] }),
  );

  const widgetDescription = "Static privacy-preserving viewer for a completed Simplify Med report";
  const resourceMeta = {
    // `ui.domain` is kept as a full `https://` origin (not a bare hostname): the generic
    // MCP Apps spec's own examples are bare hostnames, but ChatGPT is the only host this
    // server targets, and developers.openai.com/apps-sdk/reference and
    // developers.openai.com/plugins/reference (checked 2026-09-26) both document
    // `_meta.ui.domain` / the `openai/widgetDomain` alias as a full origin, e.g. defaulting
    // to `https://web-sandbox.oaiusercontent.com`. No change needed here.
    ui: {
      prefersBorder: true,
      ...(widgetDomain ? { domain: widgetDomain } : {}),
      csp: {
        connectDomains,
        resourceDomains: [] as string[],
        frameDomains: [] as string[],
      },
    },
    // OpenAI-specific compatibility aliases (still documented as honored on the pages
    // above): the model-facing widget summary, and the legacy flat widget-domain key
    // mirroring `ui.domain`.
    "openai/widgetDescription": widgetDescription,
    ...(widgetDomain ? { "openai/widgetDomain": widgetDomain } : {}),
  };
  const html = buildWidgetHtml(options.widgetBundle);

  registerAppResource(
    server,
    "Simplify Med report viewer v1",
    RESOURCE_URI,
    {
      title: "Simplify Med report viewer",
      description: widgetDescription,
      _meta: resourceMeta,
    },
    async () => ({
      contents: [
        {
          uri: RESOURCE_URI,
          mimeType: RESOURCE_MIME_TYPE,
          text: html,
          _meta: resourceMeta,
        },
      ],
    }),
  );

  return server;
}
