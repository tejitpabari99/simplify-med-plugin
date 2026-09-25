import { readFileSync } from "node:fs";
import { createHash } from "node:crypto";

import { describe, expect, it } from "vitest";

import { buildWidgetHtml } from "../src/widget-html.js";

describe("static UI privacy", () => {
  it("has no external runtime assets, frames, analytics, or wildcard CSP", () => {
    const bundle = readFileSync(new URL("../ui/dist/report-viewer.js", import.meta.url), "utf8");
    const html = buildWidgetHtml(bundle);
    expect(html).not.toMatch(/<script[^>]+src=/i);
    expect(html).not.toMatch(/<link[^>]+(?:stylesheet|preload)/i);
    expect(html).not.toMatch(/@import\s/i);
    expect(html).not.toMatch(/<iframe/i);
    expect(html).not.toMatch(/google-analytics|segment\.com|sentry\.io|mixpanel/i);
    expect(html).toContain("<script>");
  });

  it("escapes a closing script sequence in the embedded bundle", () => {
    expect(buildWidgetHtml("const x='</script><script>bad()</script>';"))
      .not.toContain("</script><script>bad");
  });

  it("matches the recorded immutable release hash", () => {
    const bundle = readFileSync(new URL("../ui/dist/report-viewer.js", import.meta.url));
    const release = JSON.parse(readFileSync(new URL("../release.json", import.meta.url), "utf8"));
    expect(bundle.byteLength).toBe(release.ui_bundle.bytes);
    expect(createHash("sha256").update(bundle).digest("hex")).toBe(release.ui_bundle.sha256);
  });

  it("keeps primary button colors above WCAG AA contrast in both themes", () => {
    const luminance = (hex: string) => {
      const channels = hex.match(/[0-9a-f]{2}/gi)!.map((part) => Number.parseInt(part, 16) / 255)
        .map((value) => value <= 0.04045 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4);
      return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2];
    };
    const contrast = (a: string, b: string) => {
      const [bright, dark] = [luminance(a), luminance(b)].sort((x, y) => y - x);
      return (bright + 0.05) / (dark + 0.05);
    };
    expect(contrast("#165dba", "#ffffff")).toBeGreaterThanOrEqual(4.5);
    expect(contrast("#0b63ce", "#ffffff")).toBeGreaterThanOrEqual(4.5);
  });
});
