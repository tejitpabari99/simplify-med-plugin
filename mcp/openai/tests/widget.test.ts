import { readFileSync } from "node:fs";

import { JSDOM } from "jsdom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ReportController, bindToolInputs, fetchReport, validateCarePlan, validateFileParam } from "../ui/src/report-viewer.js";

const fixture = JSON.parse(readFileSync(new URL("./fixtures/final-report.json", import.meta.url), "utf8"));
let dom: JSDOM;

beforeEach(() => {
  dom = new JSDOM("<!doctype html><main id=app></main>", { url: "https://widget.example.test" });
  Object.assign(globalThis, {
    window: dom.window,
    document: dom.window.document,
    Blob: dom.window.Blob,
    URL: dom.window.URL,
  });
});

afterEach(() => { vi.restoreAllMocks(); dom.window.close(); });

describe("widget validation and private loading", () => {
  it("requires the exact OpenAI file parameter shape", () => {
    expect(validateFileParam({ report: { download_url: "opaque", file_id: "file-1" } }).file_id).toBe("file-1");
    expect(() => validateFileParam({ report: { download_url: "opaque", file_id: "file-1", extra: 1 } })).toThrow();
    expect(() => validateFileParam({ report: { download_url: "opaque", file_id: "file-1", file_name: "x.pdf" } })).toThrow();
  });

  it("validates the complete final schema and supported version", () => {
    expect(validateCarePlan(fixture)).toEqual(fixture);
    expect(() => validateCarePlan({ ...fixture, diagnosis: { details: [] } })).toThrow();
    expect(() => validateCarePlan({ ...fixture, schema_version: "2.0" })).toThrow("not supported");
  });

  it("uses file_id for a fresh URL and never fetches the input download_url", async () => {
    const bridge = { getFileDownloadUrl: vi.fn().mockResolvedValue({ downloadUrl: "https://files.example.test/fresh" }) };
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify(fixture), { status: 200, headers: { "content-type": "application/json" } }));
    vi.stubGlobal("fetch", fetchMock);
    await expect(fetchReport({ file_id: "file-1", download_url: "https://secret.example.test/canary" }, bridge)).resolves.toEqual(fixture);
    expect(bridge.getFileDownloadUrl).toHaveBeenCalledWith({ fileId: "file-1" });
    expect(fetchMock).toHaveBeenCalledWith("https://files.example.test/fresh", { method: "GET", credentials: "omit", cache: "no-store" });
    expect(JSON.stringify(fetchMock.mock.calls)).not.toContain("secret.example.test");
  });

  it("reports failed, expired, malformed, and oversized downloads", async () => {
    const bridge = { getFileDownloadUrl: vi.fn().mockResolvedValue({ downloadUrl: "https://files.example.test/fresh" }) };
    vi.stubGlobal("fetch", vi.fn().mockResolvedValueOnce(new Response("gone", { status: 403 })));
    await expect(fetchReport({ file_id: "f", download_url: "x" }, bridge)).rejects.toThrow("expired");
    vi.stubGlobal("fetch", vi.fn().mockResolvedValueOnce(new Response("not-json", { status: 200 })));
    await expect(fetchReport({ file_id: "f", download_url: "x" }, bridge)).rejects.toThrow("malformed");
    vi.stubGlobal("fetch", vi.fn().mockResolvedValueOnce(new Response("{}", { status: 200, headers: { "content-length": "6000000" } })));
    await expect(fetchReport({ file_id: "f", download_url: "x" }, bridge)).rejects.toThrow("too large");
  });
});

describe("widget rendering and capability fallbacks", () => {
  function controllerWithBridge(overrides: Record<string, unknown> = {}) {
    const bridge = {
      getFileDownloadUrl: vi.fn().mockResolvedValue({ downloadUrl: "https://files.example.test/fresh" }),
      setWidgetState: vi.fn(),
      ...overrides,
    } as any;
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify(fixture), { status: 200 })));
    const root = document.getElementById("app")!;
    return { controller: new ReportController(root, bridge), bridge, root };
  }

  it("renders the seven canonical sections in order", async () => {
    const { controller, root } = controllerWithBridge();
    await controller.receiveToolInput({ report: { file_id: "file-1", download_url: "opaque" } });
    expect(Array.from(root.querySelectorAll("details[data-section]")).map((node) => (node as HTMLElement).dataset.section)).toEqual([
      "summary", "reason", "findings", "next_steps", "watch", "questions", "glossary",
    ]);
    expect(root.textContent).toContain("Your visit, explained");
    expect(root.textContent).toContain("not a new diagnosis or treatment instruction");
  });

  it("accepts both standard MCP Apps notifications and the compatibility input", async () => {
    const receiveToolInput = vi.fn().mockResolvedValue(undefined);
    const app: any = {};
    const compatibility = { report: { file_id: "compat", download_url: "opaque" } };
    bindToolInputs(app, { receiveToolInput }, compatibility);
    expect(receiveToolInput).toHaveBeenCalledWith(compatibility);
    const standard = { report: { file_id: "standard", download_url: "opaque" } };
    app.ontoolinput({ arguments: standard });
    expect(receiveToolInput).toHaveBeenCalledWith(standard);
  });

  it("requests fullscreen only after the user clicks and expands on denial", async () => {
    const requestDisplayMode = vi.fn().mockResolvedValue({ mode: "inline" });
    const { controller, root } = controllerWithBridge({ requestDisplayMode });
    await controller.receiveToolInput({ report: { file_id: "file-1", download_url: "opaque" } });
    expect(requestDisplayMode).not.toHaveBeenCalled();
    (root.querySelector("button.primary") as HTMLButtonElement).click();
    await vi.waitFor(() => expect(requestDisplayMode).toHaveBeenCalledWith({ mode: "fullscreen" }));
    expect(root.textContent).toContain("Fullscreen was unavailable");
    expect(root.querySelector("section[aria-label='Complete Simplify Med report']")?.classList.contains("hidden")).toBe(false);
  });

  it("persists only presentation keys, never report content", async () => {
    const { controller, bridge, root } = controllerWithBridge();
    await controller.receiveToolInput({ report: { file_id: "file-1", download_url: "opaque" } });
    (root.querySelector('input[type="checkbox"]') as HTMLInputElement).click();
    const saved = bridge.setWidgetState.mock.calls.at(-1)?.[0];
    expect(Object.keys(saved).sort()).toEqual(["checkedItems", "openSections"]);
    expect(JSON.stringify(saved)).not.toContain(fixture.summary);
  });

  it("sends only a section identifier in a contextual follow-up", async () => {
    const sendFollowUpMessage = vi.fn().mockResolvedValue({});
    const { controller } = controllerWithBridge({ sendFollowUpMessage });
    await controller.receiveToolInput({ report: { file_id: "file-1", download_url: "opaque" } });
    await controller.followUp("watch");
    const payload = sendFollowUpMessage.mock.calls[0][0];
    expect(payload.prompt).toContain('section "watch"');
    expect(JSON.stringify(payload)).not.toContain(fixture.summary);
  });

  it("passes an automated accessibility scan for rendered structure", async () => {
    const { controller, root } = controllerWithBridge();
    await controller.receiveToolInput({ report: { file_id: "file-1", download_url: "opaque" } });
    const axe = (await import("axe-core")).default;
    const results = await axe.run(root, {
      rules: {
        "color-contrast": { enabled: false },
        region: { enabled: false }
      }
    });
    expect(results.violations).toEqual([]);
  });

  it("shows a native-output fallback when the file API is absent", async () => {
    const root = document.getElementById("app")!;
    const controller = new ReportController(root, {});
    await controller.receiveToolInput({ report: { file_id: "file-1", download_url: "opaque" } });
    expect(root.textContent).toContain("file download is unavailable");
    expect(root.textContent).toContain("native ChatGPT response");
  });
});
