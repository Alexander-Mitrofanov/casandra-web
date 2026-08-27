import { readFileSync } from "node:fs";

import { describe, expect, it } from "vitest";

import { applyFrameBootPolicy } from "../src/frameGuard.js";

function installMarkup() {
  document.body.innerHTML = '<a id="skip-link" hidden>Skip</a><main id="frame-blocked-message" hidden>Blocked</main><div id="root" hidden></div>';
}

describe("GitHub Pages frame boot policy", () => {
  it("ships every boot target hidden before JavaScript runs", () => {
    const html = readFileSync("index.html", "utf8");
    const parsed = new DOMParser().parseFromString(html, "text/html");
    expect(parsed.getElementById("root")?.hasAttribute("hidden")).toBe(true);
    expect(parsed.getElementById("skip-link")?.hasAttribute("hidden")).toBe(true);
    expect(parsed.getElementById("frame-blocked-message")?.hasAttribute("hidden")).toBe(true);
  });

  it("reveals the application only at the top level", () => {
    installMarkup();
    const top = {};
    top.self = top;
    top.top = top;
    expect(applyFrameBootPolicy(top, document)).toBe(true);
    expect(document.getElementById("root")).not.toHaveAttribute("hidden");
    expect(document.getElementById("frame-blocked-message")).toHaveAttribute("hidden");
  });

  it("fails closed in a frame", () => {
    installMarkup();
    expect(applyFrameBootPolicy({ self: {}, top: {} }, document)).toBe(false);
    expect(document.getElementById("root")).toHaveAttribute("hidden");
    expect(document.getElementById("frame-blocked-message")).not.toHaveAttribute("hidden");
  });
});
