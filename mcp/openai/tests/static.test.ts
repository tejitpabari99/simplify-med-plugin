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
});
