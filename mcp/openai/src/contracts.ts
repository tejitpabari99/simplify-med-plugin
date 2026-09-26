import { z } from "zod/v4";

export const SERVER_NAME = "simplify-med-ui";
export const SERVER_VERSION = "0.1.0";
export const TOOL_NAME = "render_simplify_med_report";
export const RESOURCE_URI = "ui://simplify-med/report-v1.html";
export const RESOURCE_MIME_TYPE = "text/html;profile=mcp-app";

export const openAiFileSchema = z
  .object({
    download_url: z.string(),
    file_id: z.string().min(1),
    mime_type: z.string().optional(),
    file_name: z.string().optional(),
  })
  .strict();

export const renderInputSchema = z
  .object({ report: openAiFileSchema })
  .strict()
  .superRefine(({ report }, context) => {
    if (
      report.mime_type !== undefined &&
      !/^(application\/json|[^/]+\/[^;]+\+json)(?:\s*;.*)?$/i.test(report.mime_type)
    ) {
      context.addIssue({
        code: "custom",
        path: ["report", "mime_type"],
        message: "The report must be a JSON file",
      });
    }
    if (report.file_name !== undefined && !report.file_name.toLowerCase().endsWith(".json")) {
      context.addIssue({
        code: "custom",
        path: ["report", "file_name"],
        message: "The report filename must end in .json",
      });
    }
  });

export type RenderInput = z.infer<typeof renderInputSchema>;

export const TOOL_CONFIG = {
  title: "Render Simplify Med report",
  description:
    "Render an already-generated Simplify Med report JSON. Always pass the final report JSON file; never pass source medical documents.",
  annotations: {
    readOnlyHint: true,
    openWorldHint: false,
    destructiveHint: false,
  },
  _meta: {
    "openai/fileParams": ["report"],
    // Compatibility aliases verified against developers.openai.com/apps-sdk/reference
    // and developers.openai.com/plugins/reference (2026-09-26): ChatGPT reads
    // `_meta.ui.resourceUri` directly today, but still documents `openai/outputTemplate`
    // as an honored compatibility alias, and `openai/toolInvocation/invoking`/`invoked`
    // as the native "status while/after the tool runs" strings (<=64 chars each).
    "openai/outputTemplate": RESOURCE_URI,
    "openai/toolInvocation/invoking": "Opening the report…",
    "openai/toolInvocation/invoked": "Report opened.",
    ui: {
      resourceUri: RESOURCE_URI,
      visibility: ["model"] as const,
    },
  },
} as const;
