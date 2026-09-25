# OpenAI plugin implementation plan

Status: ready for implementation

Target version: `0.1.0`

Source requirements: [`openai.md`](openai.md)

Prepared: 2026-09-23

## Outcome

Ship an OpenAI package that preserves the existing Simplify Med pipeline and adds:

- portable OpenAI plugin packaging;
- a presentation-only MCP server with one render tool;
- an inline and user-initiated fullscreen ChatGPT report viewer;
- native JSON, Markdown, and self-contained HTML handoff instructions; and
- operator, privacy, deployment, and testing documentation.

The release is complete only when repository-local tests pass. Production readiness is
separate: the real ChatGPT handoff and hosting gates in this plan must also be verified
with synthetic data against the deployed endpoint.

## Core-pipeline invariants

These are hard constraints, not implementation preferences.

1. Do not change the order, prompts, data handoffs, validation, correction bounds,
   failure behavior, or medical-output logic of Stages 0–5.
2. Do not send source medical documents, source units, the fact ledger, reviews, audit
   files, or report bytes to the developer-operated MCP server.
3. The only generic pipeline change is to load `custom_start.md` after bundled paths are
   resolved and before Stage 0, and `custom_end.md` after finalization and before results
   are presented.
4. Default custom files are blank no-ops. Platform files are applied to a temporary
   staged copy. A build must never mutate `skills/simplify-med/`.
5. Existing Claude Code and Claude.ai packages keep their current behavior and archive
   contents, except for deliberate blank custom files when their package contract
   requires them.
6. The existing final care-plan JSON remains the viewer's source of truth. The Python
   Markdown and HTML renderers remain the portable canonical outputs.
7. All development, screenshots, and submission tests use synthetic or properly
   de-identified documents. No claim is made that the public plugin is approved for PHI.

## Decisions to implement

### Build and package

- Add `python build.py openai|claude-code|claude-ai` at the repository root.
- Preserve `python packaging/build.py --platform ...` as a compatibility entry point.
- Refactor shared behavior into staging code: version checks, temporary directories,
  default custom files, ignores, archive naming, and ZIP writing.
- Put platform behavior under `packaging/<platform>/`.
- Use one configured MCP endpoint value to render both OpenAI `mcp.json` and staged
  `agents/openai.yaml`; release builds fail while it is an example placeholder.
- Place portable `plugin.json`, `mcp.json`, `skills/`, and optional `assets/` at the
  OpenAI plugin root. A `.codex-plugin/plugin.json` may be included only as a
  compatibility fallback.
- Do not include `mcp/openai/` server source or tests in the distributable plugin ZIP.

### MCP contract

- Expose exactly one model-visible tool: `render_simplify_med_report`.
- Accept exactly one property, `report`, using the complete OpenAI file-parameter
  schema from the brief. Require `file_id` and `download_url`; allow only optional
  `mime_type` and `file_name`; reject additional properties and non-JSON report files.
- Mark the tool read-only, non-destructive, and closed-world. Declare
  `_meta["openai/fileParams"] = ["report"]` and bind the versioned UI resource.
- Never fetch, dereference, validate, echo, persist, trace, or log the supplied download
  URL or file object. Return generic status text and the static UI resource only.
- Serve the component as `text/html;profile=mcp-app` over streamable HTTP.
- Keep the server stateless: no accounts, cookies, database, analytics, telemetry,
  third-party assets, or durable per-user state.

### Widget contract

- Receive the original file parameter through MCP Apps tool-input notification, with
  `window.openai.toolInput` only as the ChatGPT compatibility path.
- Use only `file_id` with `getFileDownloadUrl`, then fetch the fresh URL in the iframe
  with `credentials: "omit"` and `cache: "no-store"`.
- Validate both the file-parameter shape and complete Simplify Med report JSON before
  rendering. Never send parsed report data to `callTool` or another endpoint.
- Render a compact inline summary and the same seven-section information architecture
  used by the portable report in fullscreen.
- Request fullscreen only from the **Open full report** user gesture and accept the
  host's returned display mode as authoritative.
- Persist only presentation state such as open sections and checklist values. Do not
  copy the complete report into widget state.
- Send follow-up prompts through host messaging and expose only the minimum selected
  section/fact identifiers or context needed for the request.
- Detect file download, fullscreen, state, and follow-up capabilities independently.
  Preserve the native response and downloadable artifacts as the fallback.
- Support keyboard use, semantic headings, visible focus, screen readers, reduced
  motion, text resizing, responsive layout, theme, locale, safe areas, and WCAG AA
  contrast.

### Native ChatGPT handoff

The OpenAI `custom_end.md` must require ChatGPT to:

1. provide the concise native summary;
2. attach or link final JSON, Markdown, and self-contained HTML;
3. immediately call `render_simplify_med_report` with the final report JSON file only;
4. never pass source or intermediate artifacts; and
5. never ask the user to select or upload the report again.

## Known constraint requiring an explicit fallback

The current final care-plan schema contains report creation time, but no structured
source-document type or source-document date. The initial widget must not infer either.
For `0.1.0`, it should identify the artifact honestly as a Simplify Med report and show
the report creation date when useful. Adding source-document metadata requires a
separate, explicitly reviewed pipeline/schema change and is not part of this work.

## Implementation sequence and TODOs

### 0. Baseline and current-spec pin

- [ ] Run the complete Python test suite and record the baseline.
- [ ] Re-check the official OpenAI plugin, MCP UI, reference, security, review, and
  submission documentation before coding.
- [ ] Record the documentation review date, Agent Plugins schema versions, MCP SDK/UI
  dependency versions, and the pinned Apps SDK example commit.
- [ ] Resolve the literal ZIP/plugin-root convention with the current package validator.

Acceptance:

- Baseline failures, if any, are recorded before feature changes.
- A release record identifies every external schema/example version used.

### 1. Refactor packaging without changing outputs

- [ ] Add the root dispatcher and per-platform builders.
- [ ] Add blank `packaging/default/custom_start.md` and `custom_end.md`.
- [ ] Add the two generic `SKILL.md` load points.
- [ ] Stage all builds in temporary directories and apply platform overlays there.
- [ ] Retain the legacy build command.
- [ ] Build and compare Claude package contents before adding OpenAI files.

Acceptance:

- Root dispatch and legacy commands both work.
- Unknown platforms fail clearly and nonzero.
- All version sources still agree at `0.1.0`.
- Defaults are blank; platform overrides win.
- A before/after source-tree hash proves builds do not mutate the source skill.
- Existing Claude tests and package-content assertions pass.

### 2. Add the OpenAI package profile

- [ ] Add portable `packaging/openai/plugin.json` with current
  `extensions.com.openai.interface` metadata.
- [ ] Add OpenAI ignores, staged `agents/openai.yaml`, `custom_end.md`, and required
  local assets.
- [ ] Add `mcp/openai/mcp.json` and copy it exactly to the staged plugin root.
- [ ] Generate `mcp.json` and `openai.yaml` endpoint fields from one configuration.
- [ ] Add the optional compatibility manifest only if current validation benefits from
  it; never make it the sole manifest.

Acceptance:

- The archive root, name, and version are correct.
- Root `plugin.json` and `mcp.json` validate against their schemas.
- The staged `mcp.json` is byte-for-byte equal to its generated source.
- `agents/openai.yaml` exists only in the OpenAI staged skill and matches the endpoint.
- Every file referenced by a manifest is present; design files and server source are
  absent.

### 3. Implement and test the presentation-only MCP server

- [ ] Add a locked Node/TypeScript project under `mcp/openai/`.
- [ ] Register the static versioned UI resource and the single render tool.
- [ ] Add strict runtime input checks without dereferencing the URL.
- [ ] Disable sensitive logging in application code and document equivalent reverse
  proxy, CDN, load-balancer, APM, tracing, and error-reporting controls.
- [ ] Expose local development and production start commands plus a non-sensitive
  health check.

Acceptance:

- Contract tests assert the exact file schema, annotations, metadata, MIME, and URI.
- Extra fields, missing fields, and wrong file types are rejected.
- A network trap proves the handler performs no outbound fetch.
- Tool results contain no input field, file ID, URL, filename, MIME value, or report
  data, including nested metadata.
- A canary request proves logs contain none of those values.
- Tool/resource listing exposes exactly the intended public surface.

### 4. Implement and test the report widget

- [ ] Add loading, error, compact, and fullscreen states.
- [ ] Bundle client-side validation for the supported report schema version.
- [ ] Port the existing report information architecture without changing the Python
  renderer or medical content.
- [ ] Add checklist/section state, print/download controls where supported, capability
  fallbacks, follow-up actions, theme/locale/responsive behavior, and accessibility.
- [ ] Produce an immutable bundle and record its SHA-256 in release documentation.

Acceptance:

- Synthetic fixture tests cover tool-input event and compatibility input paths.
- Tests cover fresh URL acquisition, expired/failed download, malformed JSON, wrong
  schema version, and missing bridge capabilities.
- No test observes report data sent to the MCP server or another third party.
- Fullscreen cannot be requested before a user event and denial is handled.
- Widget state excludes the report; follow-up/model-context payloads are minimal.
- Automated accessibility checks and keyboard tests pass.
- Static bundle inspection finds no analytics, external assets, runtime third-party
  script/font URLs, or wildcard CSP domains.
- Section ordering and representative content match the existing renderer contract.

### 5. Documentation and operator handoff

- [ ] Add `docs/openai.md`: components, pipeline placement, data flow, architecture,
  privacy boundary, package layout, build, deploy, test, troubleshooting, fallbacks,
  prototype gates, PHI constraints, and release verification.
- [ ] Add `mcp/openai/README.md` with the deployment/privacy contract.
- [ ] Update the root README, docs index, platform guide, architecture, and overview
  wherever their Claude-only or no-network statements become incomplete.
- [ ] Document exactly what the operator must host and configure.

Acceptance:

- A new contributor can build every platform and run all tests from the docs.
- The data-flow language says the endpoint receives a temporary file capability but
  does not download or process report bytes.
- No documentation claims PHI approval, HIPAA compliance, or universal ChatGPT Health
  availability.

### 6. Integrated verification

- [ ] Run Python, Node, widget, build, schema, archive, and static-network tests.
- [ ] Build all three platform archives and inspect their contents.
- [ ] Start the MCP server and exercise initialize, tool/resource listing, resource
  read, valid render, and invalid render calls with synthetic data.
- [ ] Test generated HTML for absence of external network dependencies.
- [ ] Run direct, indirect, irrelevant, incomplete, long-input, contradiction,
  medication, negation, uncertainty, units/dates, and prompt-injection evaluations.

Acceptance:

- All automated suites pass from a clean checkout.
- Claude outputs and pipeline behavior remain unchanged.
- Security/privacy canaries are absent from server output and logs.

### 7. Deployment and ChatGPT prototype gates

These require the operator's account and deployed infrastructure.

- [ ] Deploy the immutable MCP bundle to a stable HTTPS streamable-HTTP endpoint, or
  use Secure MCP Tunnel for developer-mode testing.
- [ ] Disable request-body and sensitive-argument capture at every hosting layer.
- [ ] Replace the example endpoint and rebuild the release archive.
- [ ] Connect the server in ChatGPT developer mode and install the complete plugin.
- [ ] Verify automatic generated-file handoff, iframe tool input, generated-artifact
  download URL retrieval, inline render, and user-initiated fullscreen without a second
  picker.
- [ ] Record the exact required download origin and narrow the CSP to it.
- [ ] Measure report-size limits, parsing/render time, iframe memory, expiry behavior,
  supported surfaces, and workspace tiers.
- [ ] Obtain written OpenAI clarification before public clinical-record/PHI positioning.

Acceptance:

- Gates 1–8 in `openai.md` have dated evidence or an explicit failed/blocked result.
- If file-handoff gates 1–3 fail, the release falls back to native ChatGPT output plus
  JSON/Markdown/HTML downloads; it does not add a second picker silently.

## Verification matrix

| Area | Automated evidence | Manual/external evidence |
|---|---|---|
| Pipeline isolation | Existing suite; Claude archive comparison; source hash | Synthetic Claude smoke run |
| Build/package | Dispatcher, staging, manifest/schema, exact-copy, exclusion tests | Install archive from local source |
| Tool contract | Schema snapshot; rejection cases; one-tool listing | ChatGPT shows correct tool metadata |
| Server privacy | Network trap; output scan; canary log tests | Hosting-stack log/config review |
| Widget loading | Mock bridge/event/file tests; schema failures | Generated ChatGPT artifact handoff |
| Fullscreen | User-event and denial tests | ChatGPT inline-to-fullscreen behavior |
| Accessibility | Automated checks; keyboard tests | Screen reader, zoom, theme smoke tests |
| Network policy | Static bundle/CSP/dependency scans | Observe production download origin |
| Native fallback | Missing-capability component tests | Disable/deny capabilities in ChatGPT |
| Medical behavior | Existing pipeline and adversarial fixtures | Synthetic end-to-end evaluation |
| Distribution | Manifest/package validation | Submission checks and policy clarification |

## Operator actions before production

The repository can provide code and tests, but the owner must:

1. choose the production domain and hosting provider;
2. deploy the MCP server at a stable HTTPS `/mcp` endpoint;
3. configure every infrastructure layer not to retain bodies, arguments, file IDs, or
   temporary URLs;
4. supply listing assets and public privacy/terms URLs required for submission;
5. run the developer-mode prototype and provide access to each target workspace tier;
6. approve the observed CSP download origin and performance limits; and
7. obtain OpenAI policy clarification before claiming support for real PHI or clinical
   records.

## Non-goals

- Changing medical extraction, assembly, review, correction, or finalization logic.
- Uploading or processing medical/report bytes on the MCP server.
- A second file picker.
- Multiple report layouts, term explorer, original-excerpt explorer, longitudinal
  history, cross-report comparison, or source-page navigation.
- New diagnoses, treatment advice, external medical enrichment, analytics, accounts,
  or server-side persistence.
- Claiming regulatory, HIPAA, PHI, medical-device, or universal ChatGPT Health approval.
