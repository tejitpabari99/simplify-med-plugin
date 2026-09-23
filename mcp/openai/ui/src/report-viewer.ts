import { App, applyHostStyleVariables } from "@modelcontextprotocol/ext-apps";

import validateReport from "../generated/validate-report.js";

const MAX_REPORT_BYTES = 5 * 1024 * 1024;
const SECTION_ORDER = ["summary", "reason", "findings", "next_steps", "watch", "questions", "glossary"];

type JsonObject = Record<string, unknown>;
type FileParam = {
  download_url: string;
  file_id: string;
  mime_type?: string;
  file_name?: string;
};
type PresentationState = { openSections: string[]; checkedItems: Record<string, boolean> };
type HostCapabilities = NonNullable<ReturnType<App["getHostCapabilities"]>>;
type HostContext = NonNullable<ReturnType<App["getHostContext"]>>;

export const APP_CAPABILITIES = { availableDisplayModes: ["inline", "fullscreen"] as const };

type OpenAiBridge = {
  toolInput?: unknown;
  widgetState?: unknown;
  displayMode?: string;
  getFileDownloadUrl?: (input: { fileId: string }) => Promise<{ downloadUrl: string }>;
  requestDisplayMode?: (input: { mode: "fullscreen" | "inline" }) => Promise<{ mode: string }>;
  setWidgetState?: (state: PresentationState) => void;
  sendFollowUpMessage?: (input: { prompt: string; scrollToBottom?: boolean }) => Promise<unknown>;
};

declare global {
  interface Window {
    openai?: OpenAiBridge;
    __SIMPLIFY_MED_DISABLE_AUTOBOOT__?: boolean;
  }
}

function obj(value: unknown): JsonObject {
  return value !== null && typeof value === "object" && !Array.isArray(value)
    ? (value as JsonObject)
    : {};
}
function list(value: unknown): JsonObject[] {
  return Array.isArray(value) ? value.map(obj) : [];
}
function strings(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === "string") : [];
}
function booleans(value: unknown): Record<string, boolean> {
  const input = obj(value);
  return Object.fromEntries(Object.entries(input).filter((entry): entry is [string, boolean] => typeof entry[1] === "boolean"));
}
function text(value: unknown): string {
  return typeof value === "string" ? value : "";
}
function present(values: unknown[], separator = ", "): string {
  return values.map(text).filter(Boolean).join(separator);
}
function element<K extends keyof HTMLElementTagNameMap>(
  tag: K,
  options: { className?: string; text?: string; attrs?: Record<string, string> } = {},
): HTMLElementTagNameMap[K] {
  const node = document.createElement(tag);
  if (options.className) node.className = options.className;
  if (options.text !== undefined) node.textContent = options.text;
  for (const [key, value] of Object.entries(options.attrs ?? {})) node.setAttribute(key, value);
  return node;
}
function appendText(parent: HTMLElement, tag: keyof HTMLElementTagNameMap, value: string, className?: string) {
  if (value) parent.append(element(tag, { text: value, className }));
}

export function validateFileParam(input: unknown): FileParam {
  const top = obj(input);
  if (Object.keys(top).length !== 1 || !("report" in top)) throw new Error("A final report JSON file is required");
  const report = obj(top.report);
  const keys = Object.keys(report);
  if (keys.some((key) => !["download_url", "file_id", "mime_type", "file_name"].includes(key))) {
    throw new Error("The report file reference is malformed");
  }
  if (typeof report.file_id !== "string" || !report.file_id) throw new Error("The report file ID is missing");
  if (typeof report.download_url !== "string") throw new Error("The report download reference is missing");
  if (report.mime_type !== undefined && typeof report.mime_type !== "string") throw new Error("Invalid report MIME type");
  if (report.file_name !== undefined && typeof report.file_name !== "string") throw new Error("Invalid report filename");
  if (typeof report.mime_type === "string" && !/^(application\/json|[^/]+\/[^;]+\+json)(?:\s*;.*)?$/i.test(report.mime_type)) {
    throw new Error("The selected file is not JSON");
  }
  if (typeof report.file_name === "string" && !report.file_name.toLowerCase().endsWith(".json")) {
    throw new Error("The selected file is not a JSON report");
  }
  return report as FileParam;
}

export function validateCarePlan(value: unknown): JsonObject {
  if (!validateReport(value)) {
    const detail = (validateReport.errors ?? []).slice(0, 3)
      .map((error) => `${error.instancePath || "report"} ${error.message || "is invalid"}`)
      .join("; ");
    throw new Error(`This file is not a valid Simplify Med report${detail ? `: ${detail}` : ""}`);
  }
  const plan = value as JsonObject;
  if (plan.schema_version !== "1.0") throw new Error("This report schema version is not supported");
  const meta = obj(plan.meta);
  const score = obj(plan.score);
  const requiredMeta = ["run_id", "plugin_version", "schema_version", "level", "created_at"];
  const finalMeta = requiredMeta.every((key) => typeof meta[key] === "string" && text(meta[key]).length > 0);
  const finalScore = Object.hasOwn(score, "before_grade") && Object.hasOwn(score, "after_grade") &&
    [score.before_grade, score.after_grade].every((item) => item === null || typeof item === "number");
  if (!finalMeta || !finalScore || !Array.isArray(plan.notices) || plan.terms === null || typeof plan.terms !== "object" || Array.isArray(plan.terms)) {
    throw new Error("This is not a finalized Simplify Med report");
  }
  if (meta.plugin_version !== plan.plugin_version || meta.schema_version !== plan.schema_version) {
    throw new Error("The finalized report metadata is inconsistent");
  }
  return plan;
}

async function readLimitedBody(response: Response): Promise<string> {
  if (!response.body) {
    const raw = await response.text();
    if (new TextEncoder().encode(raw).byteLength > MAX_REPORT_BYTES) throw new Error("This report is too large to display safely");
    return raw;
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let size = 0;
  let output = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    size += value.byteLength;
    if (size > MAX_REPORT_BYTES) {
      await reader.cancel();
      throw new Error("This report is too large to display safely");
    }
    output += decoder.decode(value, { stream: true });
  }
  return output + decoder.decode();
}

export async function fetchReport(file: FileParam, bridge: OpenAiBridge): Promise<JsonObject> {
  if (!bridge.getFileDownloadUrl) throw new Error("ChatGPT file download is unavailable in this view");
  const { downloadUrl } = await bridge.getFileDownloadUrl({ fileId: file.file_id });
  if (!downloadUrl) throw new Error("ChatGPT did not provide a report download URL");
  const response = await fetch(downloadUrl, { method: "GET", credentials: "omit", cache: "no-store" });
  if (!response.ok) throw new Error("The report could not be loaded. Its temporary link may have expired");
  const declaredSize = Number(response.headers.get("content-length") || "0");
  if (declaredSize > MAX_REPORT_BYTES) throw new Error("This report is too large to display safely");
  const raw = await readLimitedBody(response);
  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch {
    throw new Error("The report file contains malformed JSON");
  }
  return validateCarePlan(parsed);
}

function rowTitle(item: JsonObject): string {
  const title = text(item.title) || "Untitled item";
  const plain = text(item.plain_name);
  return plain && plain !== title ? `${title} (${plain})` : title;
}

function allNextSteps(plan: JsonObject) {
  const definitions: Array<[string, string, (item: JsonObject) => string, (item: JsonObject) => string[]]> = [
    ["medications", "Medication", rowTitle, (item) => [present([item.dosage, item.frequency, item.timing, item.duration]), `Why: ${text(item.why) || "not stated in your note"}`, text(item.instructions) ? `Instructions: ${text(item.instructions)}` : "", text(item.side_effects_to_watch) ? `Side effects to watch for: ${text(item.side_effects_to_watch)}` : "", text(item.change) ? `Change: ${text(item.change)}` : ""]],
    ["tests", "Test", rowTitle, (item) => [text(item.description), `Why: ${text(item.why) || "not stated in your note"}`, text(item.preparation) ? `How to prepare: ${text(item.preparation)}` : ""]],
    ["procedures", "Procedure", rowTitle, (item) => [text(item.what_to_expect), `Why: ${text(item.why) || "not stated in your note"}`, text(item.timeframe) ? `When: ${text(item.timeframe)}` : ""]],
    ["follow_up", "Appointment", () => "Appointment", (item) => [present([item.time_frame, item.description], " — ")]],
    ["other", "Instruction", (item) => text(item.title) || "Instruction", (item) => [text(item.description), `Why: ${text(item.why) || "not stated in your note"}`, ...strings(item.steps).map((step, index) => `Step ${index + 1}: ${step}`), text(item.frequency) ? `How often: ${text(item.frequency)}` : "", text(item.duration) ? `For how long: ${text(item.duration)}` : ""]],
  ];
  return definitions.flatMap(([field, type, title, details]) =>
    list(plan[field]).map((item, index) => ({
      key: `${field}-${index}`,
      type,
      title: title(item),
      details: details(item).filter(Boolean),
      done: item.status === "done",
      factIds: Array.isArray(item.source_fact_ids) ? item.source_fact_ids.filter(Number.isInteger) : [],
    })),
  );
}

function sectionShell(id: string, heading: string, state: PresentationState): { root: HTMLDetailsElement; body: HTMLDivElement } {
  const root = element("details", { className: "report-section", attrs: { "data-section": id } });
  root.open = state.openSections.includes(id) || id !== "glossary";
  root.append(element("summary", { text: heading }));
  const body = element("div");
  root.append(body);
  return { root, body };
}

function followButton(id: string, controller: ReportController): HTMLButtonElement {
  const button = element("button", { className: "follow", text: "Explain this section" });
  button.type = "button";
  button.addEventListener("click", () => void controller.followUp(id));
  return button;
}

export function renderFullReport(plan: JsonObject, state: PresentationState, controller: ReportController): HTMLElement {
  const container = element("section", { attrs: { "aria-label": "Complete Simplify Med report" } });
  const sections: Record<string, HTMLElement | null> = {};

  if (text(plan.summary)) {
    const { root, body } = sectionShell("summary", "What you need to know", state);
    appendText(body, "p", text(plan.summary)); body.append(followButton("summary", controller)); sections.summary = root;
  }
  const reasons = list(plan.reason_for_visit);
  if (reasons.length) {
    const { root, body } = sectionShell("reason", "Why you were seen", state); const ul = element("ul");
    for (const item of reasons) ul.append(element("li", { text: present([item.reason, item.description], ": ") }));
    body.append(ul, followButton("reason", controller)); sections.reason = root;
  }
  const diagnosis = obj(plan.diagnosis); const findings = list(diagnosis.details);
  if (findings.length || text(diagnosis.changed_since_last_visit)) {
    const { root, body } = sectionShell("findings", "What the doctor found", state);
    const severityLabels: Record<string, string> = { high: "Serious", medium: "Moderate", low: "Minor" };
    for (const item of findings) { const card = element("article", { className: "finding" }); const heading = element("h3", { text: rowTitle(item) }); const severity = severityLabels[text(item.severity)]; if (severity) heading.append(element("span", { className: "tag", text: severity })); card.append(heading); appendText(card, "p", text(item.description)); appendText(card, "p", text(item.what_it_means_for_you), "details"); body.append(card); }
    appendText(body, "p", text(diagnosis.changed_since_last_visit) ? `What changed since last time: ${text(diagnosis.changed_since_last_visit)}` : ""); body.append(followButton("findings", controller)); sections.findings = root;
  }
  const steps = allNextSteps(plan);
  if (steps.length) {
    const { root, body } = sectionShell("next_steps", "Your next steps", state);
    for (const group of [[false, "To do"], [true, "Already done"]] as const) {
      const rows = steps.filter((step) => step.done === group[0]); if (!rows.length) continue; body.append(element("h3", { text: group[1] }));
      for (const step of rows) { const card = element("article", { className: "row" }); const label = element("label"); const box = element("input") as HTMLInputElement; box.type = "checkbox"; box.checked = state.checkedItems[step.key] ?? step.done; box.dataset.key = step.key; box.addEventListener("change", () => controller.saveState()); const content = element("span"); appendText(content, "strong", step.title); content.append(element("span", { className: "tag", text: step.type })); for (const detail of step.details) appendText(content, "span", detail, "details"); label.append(box, content); card.append(label); body.append(card); }
    }
    body.append(followButton("next_steps", controller)); sections.next_steps = root;
  }
  const urgencyOrder = ["emergency", "call_doctor", "monitor", "normal_side_effect"];
  const urgencyLabels: Record<string, string> = { emergency: "Emergency", call_doctor: "Call your doctor", monitor: "Keep an eye on it", normal_side_effect: "Normal side effect" };
  const urgencyRank = (value: unknown) => { const rank = urgencyOrder.indexOf(text(value)); return rank < 0 ? urgencyOrder.length : rank; };
  const warnings = list(plan.warning_signs).map((item, index) => ({ item, index })).sort((a, b) => urgencyRank(a.item.urgency) - urgencyRank(b.item.urgency) || a.index - b.index);
  if (warnings.length) {
    const { root, body } = sectionShell("watch", "What to watch for", state);
    for (const { item } of warnings) { const card = element("article", { className: "warning" }); const heading = element("h3", { text: text(item.symptom) }); const urgency = urgencyLabels[text(item.urgency)]; if (urgency) heading.append(element("span", { className: "tag", text: urgency })); card.append(heading); appendText(card, "p", text(item.what_to_do)); appendText(card, "p", text(item.what_it_might_mean), "details"); appendText(card, "p", text(item.related_to) ? `Related to: ${text(item.related_to)}` : "", "details"); body.append(card); }
    body.append(followButton("watch", controller)); sections.watch = root;
  }
  const questions = strings(plan.questions);
  if (questions.length) { const { root, body } = sectionShell("questions", "Questions to ask your doctor", state); const ol = element("ol"); for (const question of questions) ol.append(element("li", { text: question })); body.append(ol, followButton("questions", controller)); sections.questions = root; }
  const terms = obj(plan.terms); const termNames = Object.keys(terms).sort((a, b) => a.localeCompare(b));
  if (termNames.length) { const { root, body } = sectionShell("glossary", "Medical terms explained", state); const dl = element("dl"); for (const term of termNames) { dl.append(element("dt", { text: term }), element("dd", { text: text(obj(terms[term]).definition) })); } body.append(dl); sections.glossary = root; }
  for (const key of SECTION_ORDER) if (sections[key]) container.append(sections[key]!);
  return container;
}

export class ReportController {
  private plan: JsonObject | null = null;
  private state: PresentationState;
  private app: App | null = null;
  private appConnected = false;
  private hostCapabilities: HostCapabilities = {};
  private hostContext: HostContext = {};
  private loadedFileId = "";

  constructor(private readonly root: HTMLElement, private readonly bridge: OpenAiBridge = window.openai ?? {}) {
    const saved = obj(bridge.widgetState);
    const legacyChecked = strings(saved.checkedItems);
    this.state = {
      openSections: strings(saved.openSections),
      checkedItems: legacyChecked.length ? Object.fromEntries(legacyChecked.map((key) => [key, true])) : booleans(saved.checkedItems),
    };
  }

  attachApp(app: App) { this.app = app; }
  markAppConnected(capabilities: HostCapabilities = {}, context: HostContext = {}) {
    this.appConnected = true;
    this.hostCapabilities = capabilities;
    this.hostContext = context;
  }

  showStatus(message: string, error = false) {
    this.root.replaceChildren();
    const section = element("section", { className: `status${error ? " error" : ""}`, attrs: { role: error ? "alert" : "status" } });
    section.append(element("h1", { text: error ? "Report unavailable" : "Simplify Med report" }), element("p", { text: message }));
    section.append(element("p", { className: "muted", text: "The native ChatGPT response and downloadable report files remain available." }));
    this.root.append(section);
  }

  async receiveToolInput(input: unknown) {
    try {
      const file = validateFileParam(input);
      if (file.file_id === this.loadedFileId) return;
      this.loadedFileId = file.file_id;
      this.showStatus("Loading and checking the completed report…");
      this.plan = await fetchReport(file, this.bridge);
      this.render();
    } catch (error) {
      this.loadedFileId = "";
      this.showStatus(error instanceof Error ? error.message : "The report could not be loaded", true);
    }
  }

  render(expanded = false) {
    if (!this.plan) return;
    this.root.replaceChildren();
    const header = element("header"); header.append(element("h1", { text: "Your visit, explained" }));
    const created = text(obj(this.plan.meta).created_at);
    header.append(element("p", { className: "sub", text: created ? `Simplify Med report created ${created}.` : "Simplify Med report." }));
    this.root.append(header);
    for (const notice of strings(this.plan.notices)) this.root.append(element("p", { className: "notice", text: notice }));
    const score = obj(this.plan.score); const before = score.before_grade; const after = score.after_grade;
    if (typeof after === "number") {
      const scoreText = typeof before === "number" ? `Reading level: grade ${before} before, grade ${after} after.` : `Reading level: about grade ${after}.`;
      this.root.append(element("p", { className: "muted", text: scoreText }));
    }
    const overview = element("section", { className: "overview", attrs: { "aria-label": "Report highlights" } });
    const cards: Array<[string, string]> = [
      ["What you need to know", text(this.plan.summary)],
      ["Next actions", allNextSteps(this.plan).filter((step) => !step.done).slice(0, 3).map((step) => step.title).join("; ") || "No next action is listed."],
      ["Medication notes", list(this.plan.medications).slice(0, 3).map((item) => present([item.title, item.change], ": ")).join("; ") || "No medication item is listed."],
      ["Follow-up", [...list(this.plan.tests), ...list(this.plan.follow_up)].slice(0, 3).map((item) => text(item.title) || present([item.time_frame, item.description], " — ")).filter(Boolean).join("; ") || "No test or follow-up item is listed."],
      ["Procedures", list(this.plan.procedures).slice(0, 3).map((item) => present([item.title, item.timeframe], " — ")).filter(Boolean).join("; ") || "No procedure is listed."],
      ["Important uncertainty", strings(this.plan.notices).slice(0, 2).join("; ") || "No uncertainty notice is listed in the report."],
    ];
    for (const [heading, body] of cards) { const card = element("article"); card.append(element("h2", { text: heading }), element("p", { text: body })); overview.append(card); }
    this.root.append(overview);
    const toolbar = element("div", { className: "toolbar" });
    const open = element("button", { className: "primary", text: expanded ? "Collapse report" : "Open full report" }); open.type = "button";
    open.addEventListener("click", () => expanded ? this.render(false) : void this.openFullReport()); toolbar.append(open);
    const download = element("button", { text: "Download JSON" }); download.type = "button"; download.addEventListener("click", () => this.downloadJson()); toolbar.append(download);
    const print = element("button", { text: "Print" }); print.type = "button"; print.addEventListener("click", () => window.print()); toolbar.append(print);
    this.root.append(toolbar);
    const full = renderFullReport(this.plan, this.state, this); full.classList.toggle("hidden", !expanded); this.root.append(full);
    this.root.append(element("footer", { text: "This simplifies the supplied documents; it is not a new diagnosis or treatment instruction. The presentation endpoint receives a temporary OpenAI file reference but does not download or process the report." }));
    this.root.querySelectorAll<HTMLDetailsElement>("details[data-section]").forEach((details) => details.addEventListener("toggle", () => this.saveState()));
  }

  async openFullReport() {
    let mode = "inline";
    let standardAttempted = false;
    try {
      const available = this.hostContext.availableDisplayModes;
      if (this.appConnected && this.app && (!available || available.includes("fullscreen"))) {
        standardAttempted = true;
        mode = (await this.app.requestDisplayMode({ mode: "fullscreen" })).mode;
      }
    } catch { mode = "inline"; }
    if (mode !== "fullscreen" && this.bridge.requestDisplayMode) {
      try { mode = (await this.bridge.requestDisplayMode({ mode: "fullscreen" })).mode; }
      catch { mode = "inline"; }
    }
    this.render(true);
    if (mode !== "fullscreen") {
      this.showActionNotice(`${standardAttempted ? "Fullscreen was denied or unavailable" : "Fullscreen was unavailable"}, so the complete report is expanded here.`);
    }
  }

  private showActionNotice(message: string) {
    this.root.querySelector(".action-notice")?.remove();
    const note = element("p", { className: "notice action-notice", text: message, attrs: { role: "status" } });
    this.root.querySelector("header")?.after(note);
  }

  saveState() {
    const openSections = Array.from(this.root.querySelectorAll<HTMLDetailsElement>("details[data-section]"))
      .filter((item) => item.open).map((item) => item.dataset.section || "").filter(Boolean);
    const checkedItems = Object.fromEntries(Array.from(this.root.querySelectorAll<HTMLInputElement>('input[type="checkbox"][data-key]'))
      .map((item) => [item.dataset.key || "", item.checked]).filter(([key]) => Boolean(key)));
    this.state = { openSections, checkedItems };
    this.bridge.setWidgetState?.(this.state);
  }

  async followUp(sectionId: string) {
    const prompt = `Explain the Simplify Med report section "${sectionId}" using only the completed report already in this conversation.`;
    try {
      if (this.appConnected && this.app) {
        if (this.hostCapabilities.updateModelContext) {
          await this.app.updateModelContext({ structuredContent: { simplifyMedSection: sectionId } });
        }
        if (this.hostCapabilities.message) {
          await this.app.sendMessage({ role: "user", content: [{ type: "text", text: prompt }] });
          return;
        }
      }
    } catch { /* Try the ChatGPT compatibility extension below. */ }
    if (this.bridge.sendFollowUpMessage) {
      try { await this.bridge.sendFollowUpMessage({ prompt }); return; }
      catch { /* Preserve the report and show a local fallback. */ }
    }
    this.showActionNotice("ChatGPT follow-up messaging is unavailable. Ask about this section in the composer instead.");
  }

  downloadJson() {
    if (!this.plan) return;
    const url = URL.createObjectURL(new Blob([JSON.stringify(this.plan, null, 2)], { type: "application/json" }));
    const anchor = element("a") as HTMLAnchorElement; anchor.href = url; anchor.download = "simplify-med-report.json"; anchor.click(); URL.revokeObjectURL(url);
  }
}

export function bindToolInputs(
  app: Pick<App, "ontoolinput">,
  controller: Pick<ReportController, "receiveToolInput">,
  compatibilityInput?: unknown,
) {
  app.ontoolinput = (params) => void controller.receiveToolInput(params.arguments);
  if (compatibilityInput) void controller.receiveToolInput(compatibilityInput);
}

export function applyHostContext(context: HostContext) {
  if (context.theme === "light" || context.theme === "dark") document.documentElement.dataset.theme = context.theme;
  if (context.locale) document.documentElement.lang = context.locale;
  if (context.displayMode) document.documentElement.dataset.displayMode = context.displayMode;
  if (context.styles?.variables) applyHostStyleVariables(context.styles.variables);
  const dimensions = context.containerDimensions;
  const maxHeight = dimensions && "maxHeight" in dimensions ? dimensions.maxHeight : undefined;
  if (typeof maxHeight === "number" && maxHeight > 0) document.documentElement.style.setProperty("--host-max-height", `${maxHeight}px`);
  else document.documentElement.style.removeProperty("--host-max-height");
}

export async function bootstrap() {
  const root = document.getElementById("app");
  if (!root) throw new Error("Missing widget root");
  const controller = new ReportController(root, window.openai ?? {});
  const app = new App(
    { name: "simplify-med-report-viewer", version: "0.1.0" },
    APP_CAPABILITIES,
    { autoResize: true },
  );
  controller.attachApp(app);
  app.onhostcontextchanged = applyHostContext;
  const compatibilityInput = window.openai?.toolInput;
  bindToolInputs(app, controller, compatibilityInput);
  try {
    await app.connect();
    const capabilities = app.getHostCapabilities() ?? {};
    const context = app.getHostContext() ?? {};
    controller.markAppConnected(capabilities, context);
    applyHostContext(context);
  }
  catch { if (!compatibilityInput) controller.showStatus("Waiting for ChatGPT to provide the completed report…"); }
  return controller;
}

if (typeof window !== "undefined" && !window.__SIMPLIFY_MED_DISABLE_AUTOBOOT__) void bootstrap();
