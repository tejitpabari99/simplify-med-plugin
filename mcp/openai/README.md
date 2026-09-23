# Simplify Med presentation MCP server

This directory contains the OpenAI-specific presentation service. It exposes one
read-only MCP tool and one versioned MCP Apps resource. It does not run any medical
pipeline stage.

## Privacy boundary

ChatGPT calls `render_simplify_med_report` with an OpenAI file parameter for the final
`06_plan.final.json` artifact. The MCP request necessarily contains `file_id` and a
temporary `download_url`, and may contain `file_name` and `mime_type`. The service:

- validates only the shape and optional JSON filename/MIME metadata;
- never dereferences or fetches `download_url`;
- never returns or echoes the file object;
- never stores report state, cookies, accounts, or user data; and
- returns only generic status text plus a static UI resource.

The iframe receives the original tool input from ChatGPT. In the user's browser it uses
only `file_id` with `window.openai.getFileDownloadUrl`, downloads the JSON from OpenAI,
validates the complete bundled `care_plan.schema.json`, and renders it locally. Parsed
report data is never sent to this MCP service or to another tool.

This boundary does not mean that no data leaves ChatGPT: the endpoint sees a temporary
file capability and ordinary HTTP metadata. It also does not establish PHI, HIPAA,
medical-device, or ChatGPT Health approval. OpenAI's published plugin guidelines
currently prohibit public plugins from collecting, soliciting, or processing PHI. Use
only synthetic or properly de-identified data until OpenAI gives written clarification.

## Runtime and source layout

- `src/mcp.ts` registers the exact one-tool/one-resource surface.
- `src/http.ts` provides stateless streamable HTTP at `/mcp` and a non-sensitive
  `/healthz` response.
- `ui/src/report-viewer.ts` implements the MCP Apps bridge, ChatGPT file download,
  validation, compact view, fullscreen request, canonical seven sections, minimal
  widget state, accessibility, and fallbacks.
- `scripts/generate-validator.mjs` compiles the repository's final care-plan schema into
  a CSP-safe standalone validator; validation does not use `eval` at runtime.
- `ui/dist/report-viewer.js` is the reviewable, fully bundled component served inside
  the MCP resource. It has no external runtime assets or analytics.
- `mcp.json` is the portable package endpoint source. Packaging may override its
  placeholder in a temporary stage but must not mutate it.

Node 20 or newer is required. Dependencies are pinned in `package-lock.json`.

## Build and test

```bash
cd mcp/openai
npm ci
npm run build
npm run typecheck
npm test
npm audit --omit=dev
```

The test suite uses only synthetic report data and covers:

- exact tool schema, annotations, file metadata, URI, MIME, and resource CSP;
- invalid/extra/non-JSON inputs;
- an outbound-network trap and output/log canaries proving no fetch or echo;
- initialization through a real streamable-HTTP MCP client;
- complete report-schema validation and size/error behavior;
- canonical section ordering, click-only fullscreen, denial fallback, and minimal state;
- absence of external scripts, styles, frames, and analytics.

The development-only Vitest dependency may have advisories that do not affect the
production dependency tree; `npm audit --omit=dev` must pass before deployment.

## Local development

```bash
cd mcp/openai
npm ci
npm run build
npm start
```

Defaults are `HOST=127.0.0.1` and `PORT=3000`. Inspect the MCP endpoint with:

```bash
npx @modelcontextprotocol/inspector
```

Choose Streamable HTTP and connect to `http://127.0.0.1:3000/mcp`. Confirm initialize,
one listed tool, one listed resource, resource read, a valid synthetic render call, and
invalid calls. `/healthz` returns only status and release version.

For ChatGPT developer-mode testing, use a supported secure tunnel or deploy a test
endpoint, register its `/mcp` URL, and use synthetic files. A tunnel is not acceptable
for public submission.

## Production configuration

| Variable | Required | Purpose |
|---|---:|---|
| `HOST` | Yes | Bind address, usually `0.0.0.0` in a container. |
| `PORT` | Yes | HTTP port. |
| `ALLOWED_HOSTS` | For non-loopback | Comma-separated exact Host names accepted by the service. |
| `PUBLIC_ORIGIN` | For non-loopback | Dedicated HTTPS UI/MCP origin advertised as `_meta.ui.domain`. |
| `OPENAI_FILE_DOWNLOAD_ORIGINS` | After prototype | Comma-separated exact bare origins observed for ChatGPT file downloads. |

Wildcard CSP origins are rejected. Do not guess the file-download origin: run the
developer-mode prototype, record the actual production origin, then set the narrow
allowlist and rescan the MCP metadata. The public endpoint must use stable HTTPS and
support unbuffered streamable HTTP.

The process intentionally has no request logger. The operator must also disable request
bodies, MCP arguments, file IDs, temporary URLs, and error payload capture in the reverse
proxy, CDN, load balancer, APM, tracing, and error-reporting layers. Coarse status,
latency, availability, and release-version metrics are sufficient. Verify this with a
unique canary before release. Configure body-size limits, timeouts, rate limiting, TLS,
rollbacks, and dependency monitoring at the hosting layer.

Install only production dependencies in the runtime image and run the already-built
service:

```bash
npm ci --omit=dev --ignore-scripts
node dist/server.js
```

The build stage must run `npm run build` first and copy `dist/`, `ui/dist/`,
`package.json`, and `package-lock.json` into the runtime image.

## ChatGPT prototype gates

Repository tests cannot prove host behavior. Before production, verify in every intended
ChatGPT surface and workspace tier that:

1. the skill-generated final JSON becomes an automatically passable file object;
2. the iframe receives tool input when the handler does not echo it;
3. `getFileDownloadUrl` works for that generated artifact without a second picker;
4. inline rendering, a user-initiated fullscreen request, and composer follow-up work;
5. denied capabilities leave the native response and JSON/Markdown/HTML downloads usable;
6. expired links, maximum report size, render time, and iframe memory are acceptable; and
7. application and infrastructure logs retain none of the canary file capability.

If gates 1–3 fail, retain native ChatGPT output plus the downloadable JSON, Markdown, and
self-contained HTML. Do not silently add a second file picker.
