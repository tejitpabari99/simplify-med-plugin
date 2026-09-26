# OpenAI and ChatGPT integration

This document describes the OpenAI-specific layer around Simplify Med: what is packaged,
what must be hosted, how the report reaches the ChatGPT widget, and where the privacy
boundary sits. For the medical pipeline itself, read [architecture.md](architecture.md).
The OpenAI layer does not replace or reorder that pipeline.

> **Note:** everything below describes the default build (`python3 build.py openai`),
> which includes the MCP viewer. `python3 build.py openai --no-mcp` instead produces a
> skills-only plugin with no MCP server, connector wiring, or widget — none of that mode
> is covered in this file. See the README's [Packaging](../README.md#packaging) section
> and
> [`docs/agent_files/2026-09-26-openai-skills-only/DESIGN.md`](agent_files/2026-09-26-openai-skills-only/DESIGN.md)
> for what it omits and how to install it.

## Scope and status

The `0.1.0` OpenAI package combines the portable `simplify` skill with a minimal,
presentation-only MCP server. ChatGPT runs the skill and its bundled Python scripts,
producing the same verified final JSON, Markdown, and self-contained HTML as other
hosts. The MCP server supplies one render tool and one static UI resource. It does not
perform medical extraction, simplification, review, correction, or rendering on the
server.

The repository can test the package, server contract, and widget in isolation. A release
is not production-proven until the [prototype gates](#prototype-gates) pass in a real
ChatGPT account against the deployed endpoint.

## Components

| Component | Location | Role |
|---|---|---|
| Portable skill | `skills/simplify/` | Runs the unchanged fact-first medical pipeline in the host. |
| Platform hooks | staged `custom_start.md`, `custom_end.md` | Add host-specific instructions before Stage 0 and after finalization. Blank defaults are no-ops. |
| Portable manifest | staged root `plugin.json` | Identifies the plugin and carries OpenAI listing metadata. |
| MCP declaration | `mcp/openai/mcp.json`, copied to staged root | Points the installed package at the deployed streamable-HTTP endpoint. |
| Compatibility manifest | staged `.codex-plugin/plugin.json` | Supports OpenAI hosts that still use the Codex compatibility ingestion path. |
| Compatibility MCP declaration | staged `.mcp.json` | Mirrors the root MCP server map without the portable-only schema field. |
| Skill dependency | staged `skills/simplify/agents/openai.yaml` | Declares the same endpoint as a report-viewer dependency. |
| MCP server | `mcp/openai/src/` | Registers one read-only render tool and serves the static UI resource. |
| Report widget | `mcp/openai/ui/` | Loads the final JSON from OpenAI in the iframe and renders inline/fullscreen views. |
| Portable reports | run folder `report.md`, and, on request, `report.html` | Remain the complete downloadable fallback; `report.html` works offline. |
| OpenAI package profile | `packaging/openai/` | Supplies the manifest, hooks, dependency overlay, plugin-root and skill-level icon assets, and exclusions used while staging the OpenAI archive. |

The MCP server source is deployed separately. It is not included in the plugin ZIP.

## Where OpenAI fits in the pipeline

The core stages remain exactly as documented in [architecture.md](architecture.md):

```text
uploaded document(s)
        |
        v
ChatGPT extracts plain text
        |
        v
custom_start.md (OpenAI instructions; no medical transformation)
        |
        v
Stages 0-5: unitize -> ground/glossary -> assemble -> review -> correct/fill -> finalize
        |
        +-----------------> 06_plan.final.json
        +-----------------> report.md
        |
        v
custom_end.md
  - present the native concise summary
  - attach/link JSON and Markdown
  - call render_simplify_med_report with the final JSON file only
  - offer report.html (render_html.py) and the audit trail (render_audit.py)
    as on-request follow-ups
        |
        v
static ChatGPT widget (inline, then user-requested fullscreen)
```

The two custom files are extension points, not new medical stages. Build code copies
blank defaults into a temporary staged skill and then applies the platform override.
It must not edit the source skill. OpenAI's `custom_end.md` is the only part that invokes
the viewer; the core finalizer and renderers remain unaware of MCP.

## Data flow and trust boundary

There is intentionally no second upload or file picker.

1. ChatGPT runs the skill and creates `06_plan.final.json` and `report.md` in
   the run folder (`report.html` is rendered later, only if requested).
2. ChatGPT invokes `render_simplify_med_report` with the final JSON artifact in the
   top-level `report` file parameter.
3. OpenAI sends the MCP endpoint a file object containing `file_id` and a temporary,
   access-capable `download_url`; it may also contain `mime_type` and `file_name`.
4. The handler validates only the parameter shape and permitted file type. It never
   dereferences the URL and returns generic status text plus the static UI resource.
5. The iframe receives the original tool input through the MCP Apps tool-input
   notification (or the `window.openai.toolInput` compatibility value).
6. The widget uses `file_id` with `window.openai.getFileDownloadUrl`, then fetches the
   fresh temporary URL directly from OpenAI in the user's browser/iframe.
7. The widget validates both the complete report schema and finalization-only evidence
   such as the readability score and complete final metadata; intermediate plans are rejected.
8. The widget renders the JSON locally. It does not send the parsed report
   to the MCP endpoint, another tool, analytics, or another network service.

The accurate privacy statement is:

> The developer-operated MCP endpoint does not download, process, store, or log the
> medical document or report bytes.

It is not accurate to say that no report-related data leaves ChatGPT or that the endpoint
receives no report data. The endpoint necessarily receives the report file ID and a
temporary download URL, plus ordinary service metadata. The URL is a temporary access
capability even though the application is designed never to use it.

OpenAI itself continues to process and store files according to the user's product,
workspace configuration, and applicable terms.

## Render-tool contract

The endpoint exposes exactly one model-visible tool:

```text
render_simplify_med_report(report: OpenAIFile)
```

The top-level input accepts only `report`. The file object declares all four OpenAI file
properties; only the first two are required:

| Property | Required | Use |
|---|---:|---|
| `download_url` | yes | Received but never logged, fetched, or returned. |
| `file_id` | yes | Delivered to the widget in the original tool input. |
| `mime_type` | no | Used only to reject an explicitly non-JSON input. |
| `file_name` | no | Used only to reject an explicitly non-JSON input. |

Both the outer object and file object reject additional properties. The descriptor sets
`readOnlyHint: true`, `destructiveHint: false`, and `openWorldHint: false`, declares
`_meta["openai/fileParams"]: ["report"]`, and binds the versioned
`ui://simplify-med/report-v1.html` resource through `_meta.ui.resourceUri`.

The result contains only generic text such as “Opening the completed report.” It does
not echo the input in `structuredContent`, `content`, result `_meta`, errors, or logs.
The UI resource uses `text/html;profile=mcp-app`.

The complete file-parameter rules are in the current
[OpenAI plugin reference](https://developers.openai.com/plugins/reference).

## Widget behavior

### Loading and validation

The widget:

1. waits for tool input;
2. validates the file-parameter shape;
3. feature-detects `getFileDownloadUrl`;
4. requests a fresh URL using `file_id`;
5. fetches it with omitted credentials and no cache;
6. validates the complete Simplify Med schema and supported schema version; and
7. renders only after validation succeeds.

It has distinct states for waiting/loading, unsupported file capability, failed or
expired download, malformed JSON, wrong schema version, and a valid report. Failure
copy points back to the native ChatGPT response and Markdown/HTML artifacts.

### Inline and fullscreen

The inline card summarizes the verified report: the most important next steps,
medication changes or questions stated in the source, tests/appointments/follow-up,
important uncertainty, and the reading-aid disclaimer. The final schema does not have
a structured source-document type or source-document date, so the widget must not infer
either. It may identify itself as a Simplify Med report and show the report creation
date.

The **Open full report** button calls `requestDisplayMode({ mode: "fullscreen" })` only
from the user's click or equivalent keyboard gesture. The returned mode is authoritative;
the host can deny fullscreen or grant another mode. The fullscreen view keeps ChatGPT's
composer available and uses the portable report's same seven-section order:

1. What you need to know
2. Why you were seen
3. What the doctor found
4. Your next steps
5. What to watch for
6. Questions to ask your doctor
7. Medical terms explained

This is a second renderer over the verified JSON, not a new medical pipeline. Contract
tests must keep its ordering and representative content aligned with `plan_view.py`.

### Host features and accessibility

- Presentation state can include open sections, checklist values, and a current filter.
  The full report must not be copied into widget state.
- Follow-up actions use the host messaging API. Model context contains only the minimum
  selected section/fact identifiers or text necessary for that question.
- File download, fullscreen, widget state, and follow-up support are detected
  independently; one missing capability must not disable the others.
- The UI responds to theme, locale, maximum height, safe areas, and the actual granted
  display mode.
- Keyboard navigation, semantic headings, visible focus, screen-reader labels,
  reduced-motion preferences, text resizing, and WCAG AA contrast are required.
- No analytics, telemetry pixels, external fonts, third-party runtime scripts, or
  third-party assets are allowed.

## Build and package

From the repository root:

```bash
python3 build.py openai
python3 build.py claude-code
python3 build.py claude-ai
```

Override the staged endpoint explicitly. Developer builds may use literal loopback;
use `--release` with the real production endpoint to require HTTPS, the exact `/mcp`
path, and a syntactically public, non-reserved host:

```bash
python3 build.py openai --mcp-url http://127.0.0.1:3000/mcp
python3 build.py openai --mcp-url https://mcp.yourdomain.com/mcp --release
```

Replace `mcp.yourdomain.com` with the endpoint you actually operate. The build performs
deterministic URL validation; it does not prove DNS resolution, TLS, reachability, or
that the host is under your control.

The compatibility form remains available:

```bash
python3 packaging/build.py --platform openai --out dist
```

For manual connector setup in ChatGPT (the owner adds the MCP connector by hand instead
of shipping it in the package), build with `--no-mcp` to omit all MCP connection info
from the archive: no root `mcp.json` or `.mcp.json` is written, the staged
`.codex-plugin/plugin.json` drops its `mcpServers` key, and the staged
`skills/simplify/agents/openai.yaml` drops its `dependencies` block (the MCP tool
declaration) while keeping `interface`/`policy` intact. `--no-mcp` cannot be combined
with `--mcp-url` (there is no endpoint to override); `--release` is still accepted and
simply skips endpoint validation, since there is no endpoint to validate. The build
asserts that no endpoint token or example/ngrok URL survives anywhere in the resulting
archive. The zip filename gets a distinct suffix so it never collides with the
default MCP build in the same `--out` directory: `simplify-med-0.1.0-openai-no-mcp.zip`.

```bash
python3 build.py openai --no-mcp --release --out dist
```

**EXPERIMENTAL: `--app-id`.** Instead of shipping MCP connection info, reference an
existing ChatGPT dev-mode app by ID:

```bash
python3 build.py openai --app-id plugin_asdk_app_6ab74031b9608191b6aa67d0ac5c1e55 --release --out dist
```

This is documented for the Codex `plugin-creator` workflow (a companion `.app.json` at
the plugin root, pointed to by the manifest's `apps` field) but is **not confirmed** to
be honored by ChatGPT's own plugin-zip ingestion path. `--app-id` is OpenAI-platform-only,
must match `^plugin_asdk_app_[0-9a-f]{32}$`, and cannot be combined with `--mcp-url`. It
implies the same no-MCP staging as `--no-mcp` (no `mcp.json`/`.mcp.json`, no
`mcpServers`, no `openai.yaml` `dependencies` block); combining it with `--no-mcp`
explicitly is allowed and redundant. It writes a staged `.app.json` at the plugin root
(`{"apps": {"simplify-med-ui": {"id": "<app-id>"}}}`) and adds `"apps": "./.app.json"`
to the staged `.codex-plugin/plugin.json`. The root portable `plugin.json` is left
unchanged: the `agent-plugins.org` 1.0.0 schema does not allow a top-level `apps` field,
and while `extensions.com.openai` accepts arbitrary content, there is no documented
OpenAI-ingestion meaning for an `apps` key placed there, so nothing is added speculatively.

After installing a `--no-mcp` package, connect the MCP endpoint manually in ChatGPT
developer mode. For the current dev tunnel, add:

```text
https://helene-unreconnoitred-overslowly.ngrok-free.dev/mcp
```

Builds run against a temporary staging tree. Shared build code checks the version,
installs blank default custom files, applies the platform overlay, processes exclusions,
and writes the ZIP. A build must leave `skills/simplify/` byte-for-byte unchanged.

The OpenAI archive contains this logical root:

```text
simplify-med/
  plugin.json
  mcp.json
  .mcp.json
  .codex-plugin/
    plugin.json
  assets/
    logo.png
    logo.svg
    composer-icon.png
  skills/simplify/
    SKILL.md
    custom_start.md
    custom_end.md
    agents/openai.yaml
    assets/
      icon-small.svg
      icon-large.png
    reference/
    schema/
    scripts/
    stages/
    templates/
```

The root portable manifest remains canonical. The compatibility manifest mirrors the
same identity and OpenAI interface metadata, and points legacy ingestion at `.mcp.json`.
The build derives `.mcp.json` from the same staged server map as root `mcp.json`, while
omitting the portable-only `$schema` field, so an endpoint override cannot make the two
declarations drift.

The plugin-root `assets/` directory (staged from `packaging/openai/assets/`) supplies the
`interface.logo` and `interface.composerIcon` images referenced by both `plugin.json` and
`.codex-plugin/plugin.json`. The skill-level `skills/simplify/assets/` directory
(staged from `packaging/openai/skill-assets/`) supplies the `icon_small`/`icon_large`
images referenced by `agents/openai.yaml`; the Codex ingestion validator resolves those
two paths relative to the skill directory, not the plugin root, so they cannot live in
the same `assets/` folder as the root logo. **The current logo/icon artwork is placeholder
art generated for this build** (see the [Owner action checklist](#owner-action-checklist)).

`interface.capabilities` is `["Interactive", "Write"]` in both `plugin.json` and
`.codex-plugin/plugin.json`, matching the only concrete example in the Codex
`plugin-creator` skill's `plugin-json-spec.md`. Neither the live `agent-plugins.org` JSON
schemas nor the Codex `validate_plugin.py` ingestion validator enforce an enum for this
field; treat any other capability value as unverified until confirmed in the real
ChatGPT/Codex developer-mode UI.

The endpoint must come from one build configuration source so the staged `mcp.json` and
`agents/openai.yaml` cannot drift. Developer builds may use an explicit loopback test
endpoint. A release build rejects the committed example, HTTP, loopback/private IPs,
reserved/example names, credentials, query strings, fragments, and paths other than
exactly `/mcp`.

Before distributing a ZIP, inspect its entries and validate root `plugin.json`,
`mcp.json`, and the `.codex-plugin` compatibility manifest. Root portable manifests are
canonical; the `.codex-plugin` manifest is a fallback for compatibility ingestion. See the official
[plugin packaging guide](https://developers.openai.com/plugins/build/plugins).

## Run locally

Install the MCP dependencies and build the UI using the commands in
`mcp/openai/README.md`. Start the streamable-HTTP endpoint, then exercise MCP initialize,
tool listing, resource listing/read, a valid synthetic render call, and invalid calls.

The server requires Node.js 20 or newer. The project-level commands are:

```bash
cd mcp/openai
npm ci
npm run typecheck
npm test
npm run build
npm start
```

It listens on `127.0.0.1:3000` by default, serves MCP at `/mcp`, and exposes the
non-sensitive health response at `/healthz`. Set `HOST` and `PORT` to change the bind;
a non-loopback bind also requires `ALLOWED_HOSTS` and `PUBLIC_ORIGIN` (the dedicated
HTTPS origin advertised as `_meta.ui.domain`). Set
`OPENAI_FILE_DOWNLOAD_ORIGINS` to a comma-separated list of exact, bare origins only
after the live prototype establishes which origin is needed. Wildcards are rejected.

For ChatGPT developer-mode testing, the endpoint must be reachable through public HTTPS
or OpenAI's Secure MCP Tunnel. Connect it in ChatGPT developer mode before installing
the complete plugin package. A localhost URL alone is not sufficient for ChatGPT.

If the server runs under a process supervisor (e.g. pm2) rather than a foreground
`npm start`, redeploy a code change with:

```bash
npm run build && pm2 restart simplify-med-mcp --update-env
```

The running process does not pick up a rebuilt `dist/`/`ui/dist/` until it is restarted.
The `/mcp` transport replies with a single `application/json` body per request
(`enableJsonResponse: true`) rather than the streamable-HTTP transport's default SSE
(`text/event-stream`) response, since this server is stateless and never streams more
than one response per request; this is spec-compliant and avoids proxies/tunnels that
buffer or truncate long-lived SSE responses. The HTTP layer's browser-`Origin` allowlist
is the same host list as `ALLOWED_HOSTS` (loopback by default), so the configured
`PUBLIC_ORIGIN` hostname is itself always allowed as a browser `Origin`, not only
loopback.

Always use the synthetic fixtures under `tests/fixtures/`; do not use a real medical
record to prove connectivity.

## Deploy

Production and review require a stable, publicly reachable HTTPS endpoint using
streamable HTTP, normally at `/mcp`. Deploy the immutable server/UI bundle separately
from the plugin ZIP.

Before enabling traffic:

- disable request-body, prompt, tool-argument, file-ID, temporary-URL, and filename
  capture in the application, reverse proxy, CDN, load balancer, APM, tracing, and error
  reporting;
- configure no cookies, user accounts, database, session store, analytics, or telemetry;
- allow no arbitrary outbound network access from the server process;
- set `_meta.ui.domain` to the dedicated production widget origin required for review;
- allow only the exact ChatGPT/OpenAI download origin proved by the prototype in the
  widget CSP; do not use a wildcard;
- serve the reviewed UI bundle immutably and record its SHA-256; and
- publish the privacy policy, terms, support contact, and listing assets required by the
  submission process.

The server can expose coarse aggregate health such as release version, status code, and
latency only after confirming that infrastructure defaults do not attach sensitive
request metadata. A health endpoint must not report user or request data.

Review the current [security and privacy guide](https://developers.openai.com/plugins/guides/security-privacy),
[plugin guidelines](https://developers.openai.com/plugins/app-guidelines), and
[remote MCP review requirements](https://developers.openai.com/plugins/deploy/app-review)
immediately before deployment and submission.

## Test and verify

### Repository tests

Run the complete project suite plus the MCP/widget tests documented by the server:

```bash
python3 -m unittest discover -s tests -v
```

The OpenAI-specific suite must cover:

- root build dispatch, unknown platforms, version agreement, blank defaults, overlay
  precedence, and no source mutation;
- portable manifest/schema validation, exact `mcp.json` staging, package contents, and
  exclusion of server/design files;
- the exact file schema, annotations, file-parameter metadata, resource URI, and MIME;
- invalid inputs, non-JSON files, zero server-side fetches, non-echoing results, and
  absence of canary secrets from logs;
- tool-input notifications and compatibility input, fresh URL acquisition, expired
  URLs, malformed reports, wrong schema versions, and capability fallbacks;
- user-gesture-only fullscreen and denial handling;
- minimal widget state/follow-up context, keyboard behavior, accessibility, and theme;
- no external runtime dependencies, analytics, or wildcard CSP; and
- continued Claude package compatibility and offline generated HTML.

Static and unit tests establish code properties; they cannot prove the configuration of
an operator's CDN/APM or ChatGPT's behavior. Those require the following live gates.

## Prototype gates

Record a dated pass, failure, or blocker for every gate:

1. ChatGPT represents the generated final JSON artifact as a file object that it can
   pass automatically to the `report` file parameter.
2. The iframe receives the original file parameter even though the handler does not
   echo it.
3. `getFileDownloadUrl` works for the generated artifact, not only a manually selected
   file.
4. The exact production download origin is recorded and is the only required
   `connectDomains` entry.
5. Maximum report size, parse/render time, iframe memory, expired-URL behavior, and long
   multi-page inputs are measured.
6. Every intended ChatGPT surface and workspace tier is tested directly.
7. Application and infrastructure settings prove bodies, arguments, file IDs, and URLs
   are not retained.
8. OpenAI provides explicit clarification before the plugin is positioned for public
   use with real PHI or clinical records.

If gates 1–3 fail, keep the direct native ChatGPT summary plus JSON, Markdown, and HTML
downloads. Do not silently add a second picker; that would change the approved product
flow.

## PHI, healthcare, and publication

OpenAI's current public plugin guidelines say plugins must not collect, solicit, or
process PHI. A client-rendered, presentation-only design does not create a documented
exception. Therefore:

- do not submit or demonstrate with real PHI;
- do not describe the public plugin as approved for clinical records;
- do not claim HIPAA compliance or medical-device status;
- do not infer availability in ChatGPT Health or ChatGPT for Healthcare; and
- obtain written OpenAI clarification before changing any of those statements.

Eligible regulated workspaces may operate under a separate BAA and configuration, but
that does not override public plugin rules or automatically approve a third-party MCP
server. The customer remains responsible for workspace controls, access, retention,
enabled plugins, connectors, and third parties.

Use synthetic or properly de-identified documents for development, screenshots,
evaluation, and submission testing.

## Troubleshooting

**The plugin builds but cannot connect.** Confirm the staged endpoint in `mcp.json` and
`agents/openai.yaml` is identical, uses HTTPS, ends at the streamable-HTTP route, is not
a placeholder, and is reachable from outside the local network.

**The tool does not appear or file handoff fails.** Inspect the advertised descriptor.
The top-level field must be named `report`; all four file properties must be declared;
only `download_url` and `file_id` are required; and `openai/fileParams` must contain
exactly `report`.

**The widget stays in loading state.** Verify it received a tool-input notification,
feature-detected `getFileDownloadUrl`, and requested a fresh URL with the snake-case
`file_id` passed as camel-case `fileId`. Check CSP errors without logging the URL.

**The report is rejected.** Confirm the selected file is the final
`06_plan.final.json`, its `schema_version` is supported, and it validates against the
bundled care-plan contract. Do not bypass validation or try an intermediate file.

**Fullscreen does not open.** The request must originate from the user's click or
keyboard activation. A denial or different returned mode is valid host behavior; the
inline report must remain usable.

**A privacy canary appears in logs.** Treat this as a release blocker. Remove the
retention path at the application or infrastructure layer, rotate/delete affected test
logs, and repeat the canary test before proceeding.

**The CSP blocks the report download.** Record the actual OpenAI download origin in the
target production surface and add only that exact origin. Do not use `*` or broaden
unrelated resource/frame domains.

**`resources/read` returns HTTP 200 with a matching `Content-Length` but delivers zero
bytes through a reverse proxy or tunnel.** This was reproduced through an ngrok tunnel:
the request succeeded identically against the loopback address, but the public URL
served a `text/event-stream` response that the tunnel hop truncated after headers. The
server now sets `enableJsonResponse: true` on the streamable-HTTP transport so a
single-response call like `resources/read` returns a complete `application/json` body
instead of SSE; confirm the fix by repeating `resources/read` for
`ui://simplify-med/report-v1.html` against the public endpoint and checking the full
body arrives every time. If it still fails, check the proxy/tunnel's own inspection or
buffering mode (e.g. ngrok's web inspector) and the built widget bundle size.

## Release record

For every candidate, record:

- plugin version and git commit;
- date the official OpenAI docs and changelog were reviewed;
- Agent Plugins `plugin.json` and `mcp.json` schema versions;
- MCP SDK, MCP Apps/UI, build-tool, and locked dependency versions;
- pinned OpenAI Apps SDK examples commit, if examples informed the implementation;
- production endpoint and dedicated widget origin;
- UI resource URI and built bundle SHA-256;
- ZIP SHA-256 and archive-content inspection result;
- Python, Node, widget, manifest, privacy-canary, and synthetic end-to-end results;
- each prototype gate's result; and
- the OpenAI policy clarification status for public distribution and PHI.

A UI code change requires a newly versioned resource rather than silently replacing an
already reviewed resource.

## Owner action checklist

Before production, the owner must:

- [ ] Choose the production domain and hosting provider.
- [ ] Deploy the immutable MCP server/UI bundle at a stable HTTPS `/mcp` endpoint.
- [ ] Disable sensitive capture at the proxy, CDN, load balancer, APM, tracing, and
  error-reporting layers.
- [ ] Provide public privacy-policy, terms, website/support, and required listing assets.
  Set the manifest's `interface.privacyPolicyURL` and `interface.termsOfServiceURL` fields
  (in both `packaging/openai/plugin.json` and `packaging/openai/.codex-plugin/plugin.json`)
  to the real hosted pages once they exist; both must be absolute `https://` URLs. Do not
  invent placeholder URLs.
- [ ] Replace the placeholder logo/icon artwork in `packaging/openai/assets/` (`logo.png`,
  `logo.svg`, `composer-icon.png`) and `packaging/openai/skill-assets/` (`icon-small.svg`,
  `icon-large.png`) with reviewed brand assets before submission.
- [ ] Replace the example endpoint and build the release archive.
- [ ] Connect the endpoint in ChatGPT developer mode and install the complete package.
- [ ] Run every prototype gate with synthetic data on each intended workspace tier.
- [ ] Approve the observed download origin, CSP, report limits, and release hashes.
- [ ] Obtain OpenAI's written policy clarification before any PHI/clinical positioning.

## Related documents

- [overview.md](overview.md) — user-facing behavior and limitations
- [architecture.md](architecture.md) — core stage graph and data contracts
- [plugins.md](plugins.md) — portable skill and platform packaging
- [OpenAI packaging brief](agent_files/2026-09-22-simplify-med-plugin-brief/openai.md) — full decision record
- [Implementation plan](agent_files/2026-09-22-simplify-med-plugin-brief/IMPLEMENTATION_PLAN.md) — acceptance criteria and verification matrix
