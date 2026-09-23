# OpenAI / ChatGPT Packaging Brief

Status: approved for implementation behind the prototype and deployment gates below

Version target: `0.1.0`

Originally drafted: 2026-09-22

Revised for privacy-preserving MCP UI: 2026-09-23

## Decision summary

The first OpenAI package should combine the existing skill with a **minimal,
presentation-only MCP server**. ChatGPT performs all medical-document processing using
the packaged skill and bundled scripts. The MCP server serves only a static UI bundle
and a render tool; it must not download, parse, persist, or log the medical document,
final report JSON, or generated report files.

Version `0.1.0` should publish one report design:

1. A concise inline ChatGPT widget preview.
2. A user-initiated fullscreen view of the same widget.
3. One complete report containing the existing Simplify Med structure.
4. Downloadable Markdown.
5. Downloadable self-contained interactive HTML as a portable fallback.

The user journey is one direct pipeline: upload the source documents once, wait for
processing, and receive the completed inline report with a fullscreen action. There is
no second file picker or upload.

ChatGPT passes the generated report JSON to the render tool as an OpenAI file parameter.
The iframe then loads the file bytes directly from OpenAI in the user's browser. The MCP
endpoint necessarily receives the file ID and temporary download URL in the tool
request, and may also receive the filename and MIME type, but it does not need to fetch
the URL or receive the report bytes. Therefore the accurate claim is:
**medical-document and report bytes are not
downloaded, processed, stored, or logged by the developer-operated MCP endpoint**. It is
not accurate to claim that the endpoint receives no report-related data or access
capability.

This design does require a small, stable public HTTPS service for plugin review and
production use. Its compute and storage needs are minimal because it serves a static
component and a minimal render response; it does not perform medical processing.

Official references:

- [Plugin architecture](https://developers.openai.com/plugins/concepts/plugins)
- [Add UI to your MCP server](https://developers.openai.com/plugins/build/chatgpt-ui)
- [Package your plugin](https://developers.openai.com/plugins/build/plugins)
- [Build skills](https://developers.openai.com/plugins/build/skills)
- [OpenAI Apps SDK examples](https://github.com/openai/openai-apps-sdk-examples)

## What Simplify Med does

Simplify Med is a fact-preserving medical-document simplification pipeline. It:

1. Unitizes source documents.
2. Extracts anchored facts and medical terms.
3. Builds a plain-language care plan.
4. Reviews fidelity and coverage.
5. Applies bounded corrections and additions.
6. Produces Markdown, self-contained HTML, and audit artifacts.

Its safety model relies on file handoffs, schema validation, source citations,
deterministic checks after model stages, bounded correction scope, graceful degradation,
and an inspectable audit trail. The portable core is `skills/simplify-med/`; existing
Claude files are platform wrappers rather than the product itself.

The existing HTML renderer already provides persistent checkboxes, expandable details,
glossary interactions, offline operation, and no network calls. It should remain the
portable rich-output format for the OpenAI package.

## Why a presentation-only MCP server is viable

Model Context Protocol (MCP) is an open protocol through which an AI host discovers and
calls tools and retrieves resources from another process or service. OpenAI's current
plugin architecture uses an MCP resource with MIME type
`text/html;profile=mcp-app` to deliver custom UI into ChatGPT. The component then runs
inside an isolated iframe and communicates with ChatGPT through the MCP Apps bridge.

The normal OpenAI example pattern sends structured data to an MCP tool and returns it in
`structuredContent`. That pattern is **not acceptable here**, because the remote MCP
endpoint would receive the medical report as tool arguments or would produce it as a
server result.

Instead, use a direct presentation-only pattern:

1. The skill processes source files entirely in ChatGPT and writes the verified final
   report JSON plus Markdown and HTML artifacts.
2. ChatGPT calls a read-only MCP tool named `render_simplify_med_report`, passing the
   generated JSON artifact through the documented OpenAI file-parameter shape.
3. The endpoint ignores `download_url`, does not fetch the file, and returns only a
   static UI resource plus non-sensitive status text.
4. ChatGPT delivers the same file-parameter input to the iframe through
   `ui/notifications/tool-input` / `window.openai.toolInput`.
5. The widget takes `report.file_id`, calls
   `window.openai.getFileDownloadUrl({ fileId })`, and retrieves the JSON directly from
   OpenAI in the user's iframe/browser.
6. The component validates the JSON locally, renders an inline preview, and exposes a
   user-initiated **Open full report** action using
   `requestDisplayMode({ mode: "fullscreen" })`.
7. The component makes no call back to the MCP endpoint with report content and makes no
   third-party network requests.

This flow intentionally uses `_meta["openai/fileParams"]` because it is the documented
way to give the widget an automatically authorized file without asking the user to pick
it again. The tradeoff is that the tool request sent to the MCP endpoint contains both
`file_id` and an access-capable, temporary `download_url`. The handler and all upstream
infrastructure must ignore and never log or dereference that URL.

Current OpenAI documentation does not describe a zero-click host-to-widget channel that
withholds both the report bytes and its access reference from the MCP endpoint. If the
privacy requirement later becomes "the endpoint must not receive even a temporary file
capability," the documented choices are a user-mediated file picker or no embedded MCP
UI. This constraint must be accepted explicitly before production.

Do not pass the report JSON itself as ordinary tool input, `structuredContent`,
`content`, or `_meta`.

This is an important distinction:

| Experience | MCP/server needed? | Version 0.1.0 |
|---|---:|---:|
| ChatGPT follows `SKILL.md` and processes uploaded files | No | Yes |
| Native ChatGPT prose/Markdown preview | No | Yes |
| Generated downloadable Markdown | No | Yes |
| Generated self-contained interactive HTML | No external server | Yes |
| Static iframe component embedded in ChatGPT | Yes | Yes |
| User-initiated ChatGPT fullscreen component | Yes | Yes |
| MCP server receives file reference and temporary URL | Yes | Yes |
| MCP server fetches or processes report bytes | Not required | No |

## Proposed report experience

### Inline ChatGPT preview

After processing, ChatGPT should automatically invoke the render tool with the generated
report JSON file. The widget should show a skeleton/loading state while it obtains the
fresh OpenAI download URL and validates the JSON, then render the compact view without
asking the user to select or upload anything. It should include:

- What the document is and its date.
- The most important next actions.
- Medication changes or medication questions explicitly present in the source.
- Tests, appointments, and follow-up timing.
- Important uncertainty or contradictions.
- A clear statement that the result simplifies the supplied documents and is not a new
  diagnosis or treatment instruction.
- Downloadable Markdown and self-contained HTML in the surrounding native ChatGPT
  response. The widget may also generate equivalent client-side downloads from the
  validated JSON; it must not call the MCP server to obtain them.
- One primary **Open full report** action. Fullscreen must be requested from a user
  gesture; the host may grant a different display mode.

### One complete interactive report

The MCP widget and downloadable HTML should implement the same single supported report
layout. The fullscreen widget should use the existing report structure and work with
ChatGPT's composer, which remains available in fullscreen. It may use expand/collapse
behavior, local checklist state, section navigation, print/download controls, responsive
layout, dark/light themes, and follow-up prompts. The downloadable HTML remains the
portable full-window fallback and makes no network requests.

The initial layout should not add:

- A separate terminology explorer.
- Side-by-side original excerpts.
- Cross-report timelines.
- Longitudinal history.
- Alternate report layouts.

Those ideas are retained in `futures.md`.

### ChatGPT-specific experience enhancements

Use ChatGPT host capabilities that improve the single report without expanding its
medical scope:

- **Native fullscreen:** request fullscreen only after the user clicks **Open full
  report**; keep the native composer available for follow-up questions.
- **Contextual follow-ups:** section-level actions such as **Explain this section** and
  **Help me prepare questions** can use `ui/message` or
  `window.openai.sendFollowUpMessage`. Keep the report itself in ChatGPT; do not call an
  MCP data tool.
- **Model context from selection:** send only the selected section/fact identifiers or
  minimal relevant context through `ui/update-model-context` when a user wants to ask a
  contextual question.
- **Widget state:** use `window.openai.setWidgetState` for presentation state such as the
  open section, checklist state, or current filter. Avoid copying the full medical
  report into widget state.
- **Host adaptation:** respond to ChatGPT theme, locale, safe-area, available display
  modes, and maximum height rather than hard-coding a desktop-only layout.
- **Accessible interaction:** provide keyboard navigation, visible focus, semantic
  headings, reduced-motion support, screen-reader labels, WCAG AA contrast, and text
  resizing.
- **Graceful capability detection:** detect file download, fullscreen, persistence, and
  follow-up-message support individually; retain the native response and downloadable
  artifacts when any extension is unavailable.
- **Clear status and trust copy:** show when the report is loading, validated, malformed,
  or using a fallback, and state accurately that the presentation endpoint receives a
  temporary OpenAI file reference but does not download or process the report.

## OpenAI package layout

The portable OpenAI archive should use a root `plugin.json`. A
`.codex-plugin/plugin.json` may also be generated as a compatibility fallback, but it
should not be the only manifest.

```text
simplify-med/
├── plugin.json
├── mcp.json
├── .codex-plugin/
│   └── plugin.json              # optional compatibility manifest
└── skills/
    └── simplify-med/
        ├── SKILL.md
        ├── custom_start.md
        ├── custom_end.md
        ├── agents/
        │   └── openai.yaml       # OpenAI build: declares the UI MCP dependency
        ├── references/
        ├── scripts/
        └── templates/
```

The root manifest should use the portable Agent Plugins schema, retain version `0.1.0`,
and include OpenAI listing metadata where appropriate under
`extensions.com.openai.interface`.

The built archive's root `mcp.json` should be copied from `mcp/openai/mcp.json`. It uses
the portable Agent Plugins MCP schema and points to the deployed streamable-HTTP HTTPS
endpoint. An OpenAI-specific staged `skills/simplify-med/agents/openai.yaml` should
declare the same presentation dependency and describe it narrowly as a report viewer,
not a medical-processing service.

### Portable `mcp.json`

`mcp/openai/mcp.json` is the source file copied to the built plugin root. Replace the
example domain with the verified production endpoint before packaging a release:

```json
{
  "$schema": "https://agent-plugins.org/schemas/1.0.0/mcp.schema.json",
  "mcpServers": {
    "simplify-med-ui": {
      "type": "streamable-http",
      "url": "https://PLUGIN_DOMAIN.example/mcp"
    }
  }
}
```

The public endpoint must use stable HTTPS and streamable HTTP. A local server or tunnel
is suitable for developer-mode testing but not public submission.

### Staged `agents/openai.yaml`

The OpenAI build should add this dependency to the staged skill, using the same endpoint:

```yaml
dependencies:
  tools:
    - type: mcp
      value: simplify-med-ui
      description: Render a completed Simplify Med JSON report in ChatGPT
      transport: streamable_http
      url: https://PLUGIN_DOMAIN.example/mcp
```

The endpoint value should come from one build configuration source so `mcp.json` and
`openai.yaml` cannot drift.

### Render-tool contract

Register exactly one model-visible tool for the initial UI. Its top-level `report` field
must use the complete OpenAI file schema, including the two optional properties that
submission validation expects:

```json
{
  "name": "render_simplify_med_report",
  "title": "Render Simplify Med report",
  "description": "Render an already-generated Simplify Med report JSON. Always pass the final report JSON file; never pass source medical documents.",
  "inputSchema": {
    "type": "object",
    "$defs": {
      "OpenAIFile": {
        "type": "object",
        "properties": {
          "download_url": { "type": "string" },
          "file_id": { "type": "string" },
          "mime_type": { "type": "string" },
          "file_name": { "type": "string" }
        },
        "required": ["download_url", "file_id"],
        "additionalProperties": false
      }
    },
    "properties": {
      "report": { "$ref": "#/$defs/OpenAIFile" }
    },
    "required": ["report"],
    "additionalProperties": false
  },
  "annotations": {
    "readOnlyHint": true,
    "openWorldHint": false,
    "destructiveHint": false
  },
  "_meta": {
    "openai/fileParams": ["report"],
    "ui": {
      "resourceUri": "ui://simplify-med/report-v1.html"
    }
  }
}
```

The server handler must not read or dereference `report.download_url`. It should return
only generic text such as "Opening the completed report" and attach the versioned UI
resource. It should not echo the file object in `structuredContent`, `content`, or
`_meta`.

### Widget data-loading contract

The UI receives the tool input from ChatGPT, not from a custom data API. The following is
implementation-oriented pseudocode; use the current MCP Apps React helpers where
possible:

```ts
async function loadReport(toolInput: unknown) {
  const report = validateFileParam(toolInput).report;
  const fileId = report.file_id;

  const { downloadUrl } = await window.openai.getFileDownloadUrl({
    fileId,
  });

  const response = await fetch(downloadUrl, {
    method: "GET",
    credentials: "omit",
    cache: "no-store",
  });
  if (!response.ok) throw new Error("Unable to load report");

  const json = await response.json();
  return validateSimplifyMedReport(json);
}
```

Subscribe to `ui/notifications/tool-input` or the supported `window.openai.toolInput`
compatibility value. Do not depend on the server echoing the file ID. Never send the
parsed report to `window.openai.callTool` or another network endpoint.

The fullscreen action must be initiated by a click or equivalent user gesture:

```ts
await window.openai.requestDisplayMode({ mode: "fullscreen" });
```

Treat the returned mode as authoritative because ChatGPT can deny the request or grant a
different presentation.

## Platform-aware build design

The intended command is:

```bash
python build.py openai
python build.py claude-code
python build.py claude-ai
```

Recommended source layout:

```text
build.py
mcp/
└── openai/
    ├── mcp.json                  # copied to archive root during OpenAI packaging
    ├── README.md                 # deployment and privacy-boundary contract
    ├── package.json
    ├── tsconfig.json
    ├── src/
    │   └── server.ts             # file-ref render tool + static UI resource only
    └── ui/
        ├── src/
        │   └── report-viewer.tsx
        └── dist/                 # generated component bundle; not hand-edited
packaging/
├── build.py
├── default/
│   ├── custom_start.md
│   └── custom_end.md
├── claude-code/
│   ├── build-claude-code.py
│   ├── claude-code.ignore
│   └── custom_end.md
├── claude-ai/
│   ├── build-claude-ai.py
│   ├── claude-ai.ignore
│   └── custom_end.md
└── openai/
    ├── build-openai.py
    ├── openai.ignore
    ├── custom_end.md
    ├── plugin.json
    ├── agents/
    │   └── openai.yaml
    └── assets/
```

Shared build code should own version checks, temporary staging, default custom files,
ignore processing, copying, archive naming, and ZIP creation. Platform builders should
own archive layout, manifest overlays, platform exclusions, platform instructions, and
copying `mcp/openai/mcp.json` to the OpenAI archive root. The deployed server code is not
copied into the plugin ZIP; the ZIP contains only the endpoint declaration and packaged
skill/UI metadata.

The existing `python packaging/build.py --platform ...` form may remain as a compatibility
entry point.

## Platform custom instructions

Use exactly two platform extension files:

- `custom_start.md`
- `custom_end.md`

Blank canonical versions should live in `packaging/default/`. During a build, they are
copied into the staged skill and then replaced by platform versions when present. The
source skill directory must not be mutated.

`SKILL.md` should:

1. Read `custom_start.md` after resolving its bundled paths and before Stage 0.
2. Read `custom_end.md` after finalization and before presenting results to the user.

An empty custom file is a deliberate no-op. There should not be a third `custom.md`
convention.

The OpenAI `custom_end.md` should instruct ChatGPT to provide the native inline summary,
attach or link the JSON, Markdown, and self-contained HTML outputs, and immediately call
`render_simplify_med_report` with the **final report JSON file only**. It must never pass
the uploaded source documents, raw unit files, fact ledger, audit files, or review files
to the MCP tool. It must not ask the user to select the report a second time.

## MCP privacy and security contract

The presentation endpoint must enforce these invariants:

- Exactly one read-only, non-destructive, closed-world render tool for the initial
  version.
- The tool accepts exactly one OpenAI file parameter named `report`; it rejects other
  fields and non-JSON report files.
- Tool output contains no user or report data.
- The UI resource is static and versioned by URI.
- Production serves an immutable, reviewable bundle whose release hash is recorded; UI
  changes require a new resource version rather than silently replacing reviewed code.
- No request-body, tool-argument, prompt, file reference, download URL, or report logging
  at the application, reverse proxy, CDN, load balancer, APM, tracing, or error-reporting
  layers.
- No analytics, telemetry pixels, third-party fonts, third-party scripts, or external
  assets.
- A restrictive CSP: no arbitrary `connectDomains`, `resourceDomains`, or
  `frameDomains`; allow only origins proven necessary for ChatGPT's file download flow.
- No cookies, user accounts, database, durable server state, or cross-session medical
  state.
- The server never dereferences or validates file-parameter `download_url` values. Only
  the browser widget uses `file_id` to request a fresh URL through `window.openai`.
- Client-side JSON Schema validation before rendering.
- Clear error and fallback behavior for unavailable file APIs, malformed JSON, wrong
  schema versions, expired download URLs, and denied fullscreen requests.
- Logs limited to coarse operational health such as status code, latency, and release
  version, subject to verifying that infrastructure defaults do not capture sensitive
  request metadata.

The endpoint will see the MCP connection, ordinary HTTP/service metadata, the file ID,
and a temporary access-capable OpenAI download URL; it may also see a generic filename
and MIME type.
OpenAI may also include anonymized session metadata. Privacy copy must therefore say
"the MCP endpoint does not download or process the medical document or report bytes,"
not "no data leaves ChatGPT" or "the endpoint receives no report data."

## Health data, PHI, and distribution

Keeping processing inside ChatGPT materially simplifies the data flow: the
developer-operated MCP endpoint is designed not to download the document or report
bytes. It does receive a temporary report-file capability as described above. The UI
code receives the report in the user's browser so it can render it, and OpenAI continues
to process and store data according to the applicable ChatGPT product terms and
workspace configuration.
However, that does **not by itself establish that a public plugin may process PHI**.

The current public plugin guidelines state that plugins must not collect, solicit, or
process protected health information. The documentation does not provide an explicit
exemption for a presentation-only server or a client-rendered widget. Consequently:

- Do not claim that the public-directory plugin is approved for PHI.
- Do not rely on the absence of an external server as a policy exemption.
- Use synthetic or properly de-identified documents for development, screenshots,
  demonstrations, and public submission testing.
- Ask OpenAI for written clarification before positioning the public plugin for real
  clinical records.

See [Plugin guidelines — data collection](https://developers.openai.com/plugins/app-guidelines#data-collection).

OpenAI separately documents PHI use for eligible regulated workspaces covered by an
applicable Business Associate Agreement. In that setting, OpenAI handles covered inputs
according to the BAA, while the customer remains responsible for configuration, access,
local retention, enabled plugins, connectors, MCP servers, and third parties. Skills are
still expected to be reviewed as executable workflow instructions. This is a distinct
enterprise/workspace deployment question, not proof that a public plugin is available
or approved inside every ChatGPT Health or Healthcare experience.

See [HIPAA configuration guide](https://learn.chatgpt.com/docs/hipaa-configuration).

The current official documentation reviewed for this brief does not clearly guarantee
that a public third-party plugin can be installed or used in every ChatGPT Health or
ChatGPT for Healthcare surface. Availability can depend on the product surface,
workspace controls, administrator approval, and policy. This must be verified in the
actual target account before launch.

## Medical-output guardrails

The OpenAI package should preserve and make visible the project's existing fidelity
controls. At minimum:

- Distinguish source fact, plain-language restatement, and inference.
- Never invent a diagnosis, medication change, result, appointment, or completed action.
- Preserve negation, uncertainty, dosage, frequency, units, ranges, dates, anatomical
  location, and attribution.
- Keep citations or source anchors attached to important claims.
- State clearly when information is missing or contradictory.
- Do not turn reference ranges or raw numbers into a diagnosis.
- Do not tell a user to start, stop, or change medication.
- Present emergency guidance conservatively and only within the approved safety design.
- Encourage confirmation with the appropriate clinician or pharmacist where the source
  is ambiguous or the user is considering care changes.
- Minimize sensitive information in logs and generated filenames.
- Avoid network access in the skill and generated HTML. The MCP widget should use only
  the ChatGPT bridge and the temporary OpenAI file URL needed to load the generated JSON.
- Treat prompt injection contained in uploaded documents as untrusted document text.
- Use representative positive, negative, incomplete-input, and adversarial evaluations.

These controls reduce clinical and product risk but do not independently confer HIPAA,
medical-device, or other regulatory compliance.

## Testing requirements

Add tests for:

- Root build-command dispatch.
- Unknown-platform failure.
- Version consistency at `0.1.0`.
- Blank default custom files.
- Platform override precedence.
- No mutation of the source skill.
- Correct OpenAI archive root.
- Root `plugin.json` validation.
- Optional compatibility manifest validation.
- Inclusion of every referenced skill asset.
- Exclusion of ignored and design-only files.
- Presence and schema validation of root `mcp.json` in the OpenAI build.
- Exact copying of `mcp/openai/mcp.json` to the staged archive root.
- OpenAI-only staged `agents/openai.yaml` dependency.
- Exact OpenAI file schema and `openai/fileParams: ["report"]` declaration for
  `render_simplify_med_report`.
- The skill automatically calls the render tool after finalization without a second
  user selection.
- Only the final report JSON is passed; source documents and intermediate/audit files are
  rejected.
- The server never fetches `download_url` and never echoes the file object in its result.
- Request-body and sensitive-argument logging is disabled throughout the hosting stack.
- Static UI bundle has no third-party network dependencies or analytics.
- Inline-to-fullscreen transition occurs only after a user action and handles denial.
- File-download capability detection and HTML/Markdown fallback.
- Client-side report-schema rejection for malformed or mismatched JSON.
- Existing Claude package compatibility.
- Native preview plus Markdown/HTML handoff instructions.
- Generated HTML containing no external network dependencies.

For product behavior, test direct and indirect triggers, incomplete inputs, irrelevant
requests, prompt injection in documents, unsupported formats, very long multi-page
documents, conflicting facts, medication changes, negation, uncertain diagnoses, units,
dates, and output-download behavior.

## Implementation sequence

1. Refactor the build system around platform directories and staged overlays.
2. Add blank default custom files and `SKILL.md` load points.
3. Add `mcp/openai/` with the file-reference render tool, static UI resource, fullscreen report
   component, and source `mcp.json`.
4. Add `packaging/openai/`, copy `mcp.json` to the archive root, and generate the OpenAI
   plugin package.
5. Define the OpenAI inline summary, file handoff, and privacy-safe viewer invocation in
   `custom_end.md`.
6. Make the MCP widget and downloadable HTML share one report information architecture.
7. Add build, manifest, package-content, data-flow, UI, and output tests.
8. Prototype the automatic file-parameter handoff in developer mode using synthetic
   data. Verify that the server can ignore the URL while the widget obtains and renders
   the file through `window.openai` without another user action.
9. Deploy the minimal endpoint to a stable public HTTPS URL and test submission checks.
10. Confirm public-directory and Healthcare/Health availability with OpenAI before making
   claims about real medical-record use.

## Prototype gates and unresolved implementation details

Treat the architecture as viable but not production-proven until a synthetic-data
prototype passes every gate below. These are validation items, not decisions the end
user should be asked to make:

1. Confirm that the final JSON artifact created by the skill is represented as a
   ChatGPT file object that the model can pass automatically to a field declared in
   `_meta["openai/fileParams"]`.
2. Confirm that `ui/notifications/tool-input` or `window.openai.toolInput` exposes the
   original file parameter to the iframe even when the MCP handler does not echo it in
   its result.
3. Confirm that `window.openai.getFileDownloadUrl({ fileId })` works for that generated
   artifact, not only for a file manually uploaded through the UI.
4. Record the exact download origin used in production and allow only that origin in the
   component CSP. Do not use a wildcard to make the prototype pass.
5. Measure maximum supported report size, JSON parsing/render time, iframe memory use,
   and behavior for expired URLs and long multi-page inputs.
6. Verify the feature on each intended ChatGPT surface and workspace tier; do not infer
   universal availability from developer mode.
7. Inspect application, proxy, CDN, load-balancer, APM, tracing, and error-reporting
   configuration to prove that request bodies, tool arguments, file IDs, and temporary
   URLs are not retained.
8. Obtain explicit OpenAI clarification on public distribution and real-PHI use before
   marketing the plugin for clinical records or ChatGPT Health/Healthcare.

If gates 1–3 fail, keep the direct user journey by returning the native ChatGPT report
plus Markdown and self-contained HTML downloads. Do not introduce a second file picker
without revisiting the product decision.

## Deferred work

Term exploration, original source-excerpt navigation, cross-report comparison,
longitudinal history, multi-page source navigation, and alternate layouts are
deliberately deferred. They are recorded in `futures.md`.

## Implementation reference index

The following links are the implementation reading list. Review them again immediately
before coding and submission because the plugin platform is evolving.

### Architecture, skills, packaging, and MCP

- [Plugin architecture](https://developers.openai.com/plugins/concepts/plugins) — how
  skills, MCP servers, UI resources, and ChatGPT fit together.
- [Build skills](https://developers.openai.com/plugins/build/skills) — `SKILL.md`, skill
  resources, and dependency declaration.
- [Build an MCP server](https://developers.openai.com/plugins/build/mcp-server) — MCP
  transport, tool registration, resource registration, and local testing.
- [Package your plugin](https://developers.openai.com/plugins/build/plugins) — manual
  `plugin.json` creation, package layout, schema, and ZIP packaging.
- [Plugin reference](https://developers.openai.com/plugins/reference) — authoritative
  field reference, including tool metadata, file parameters, UI resources, bridge APIs,
  CSP, and host globals.
- [Agent Plugin manifest schema](https://agent-plugins.org/schemas/1.0.0/plugin.schema.json)
  — schema URL for root `plugin.json`.
- [Agent Plugin MCP schema](https://agent-plugins.org/schemas/1.0.0/mcp.schema.json) —
  schema URL for root `mcp.json`.

### UI implementation

- [Add UI to your MCP server](https://developers.openai.com/plugins/build/chatgpt-ui) —
  registering `text/html;profile=mcp-app` resources, binding a tool to a UI, bridge
  events, fullscreen, and deployment.
- [Plugin UI reference](https://developers.openai.com/plugins/reference) — exact
  `window.openai` and `ui/*` APIs, including `toolInput`, `getFileDownloadUrl`, widget
  state, follow-up messages, model context, and display modes.
- [UI guidelines](https://developers.openai.com/plugins/concepts/ui-guidelines) —
  component layout, accessibility, fullscreen behavior, responsive design, and ChatGPT
  visual conventions.
- [MCP Apps extension specification](https://modelcontextprotocol.io/docs/extensions/apps)
  — underlying `ui/*` protocol and resource conventions used by MCP Apps.
- [`@openai/apps-sdk-ui` components](https://openai.github.io/apps-sdk-ui/) — optional
  OpenAI component library for matching ChatGPT UI conventions.
- [OpenAI Apps SDK examples](https://github.com/openai/openai-apps-sdk-examples) — official
  runnable examples. This brief inspected repository commit
  [`18cc38e7`](https://github.com/openai/openai-apps-sdk-examples/commit/18cc38e78a968712c357bacdc3c79fead5bfc6b4);
  re-pin the commit when implementation begins.
- [Basic Node MCP UI server example](https://github.com/openai/openai-apps-sdk-examples/blob/main/mcp_app_basics_node/src/server.ts)
  — minimal tool/resource wiring.
- [Fullscreen request example](https://github.com/openai/openai-apps-sdk-examples/blob/main/src/request-display-mode/App.tsx)
  — user-initiated `requestDisplayMode` behavior.

### Testing, security, and publication

- [Connect and test a plugin](https://developers.openai.com/plugins/deploy/connect-chatgpt)
  — developer-mode connection and end-to-end testing in ChatGPT.
- [Security and privacy](https://developers.openai.com/plugins/guides/security-privacy) —
  data minimization, validation, prompt-injection resistance, authorization, and secure
  operational practices.
- [Plugin guidelines](https://developers.openai.com/plugins/app-guidelines) — content,
  behavior, privacy, and health-data review constraints.
- [MCP server review requirements](https://developers.openai.com/plugins/deploy/app-review)
  — requirements applied to a remote MCP server during review.
- [Submit and publish](https://developers.openai.com/plugins/deploy/submission) — package
  validation, submission, review, and publishing workflow.
- [Submission error reference](https://developers.openai.com/plugins/deploy/submission-errors)
  — common package, schema, and validation failures.
- [Plugin changelog](https://developers.openai.com/plugins/changelog) — platform changes
  that may require updates to this design.
- [HIPAA configuration guide](https://learn.chatgpt.com/docs/hipaa-configuration) — separate
  workspace/BAA configuration considerations; it does not override plugin review rules.
- [GPT Actions introduction](https://developers.openai.com/api/docs/actions/introduction) —
  useful background for OpenAPI-backed GPT actions, but not the chosen UI mechanism;
  Actions do not replace the MCP Apps UI resource required for this embedded report.

The implementation team should record the documentation review date, the exact example
repository commit used, the deployed UI bundle hash, the schema versions, and the result
of every prototype gate in the release notes.
