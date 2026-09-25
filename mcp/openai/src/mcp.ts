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

  const resourceMeta = {
    ui: {
      prefersBorder: true,
      ...(widgetDomain ? { domain: widgetDomain } : {}),
      csp: {
        connectDomains,
        resourceDomains: [] as string[],
        frameDomains: [] as string[],
      },
    },
  };
  const html = buildWidgetHtml(options.widgetBundle);

  registerAppResource(
    server,
    "Simplify Med report viewer v1",
    RESOURCE_URI,
    {
      title: "Simplify Med report viewer",
      description: "Static privacy-preserving viewer for a completed Simplify Med report",
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
