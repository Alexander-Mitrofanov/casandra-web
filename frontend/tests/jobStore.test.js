import { describe, expect, it } from "vitest";

import {
  buildJobRecoveryLink,
  clearJobRecoveryLink,
  clearSessionCredential,
  loadSessionCredential,
  normalizeJobCredential,
  parseJobCredential,
  parseJobRecoveryLink,
  saveSessionCredential,
  serializeJobCredential,
} from "../src/jobStore.js";

const credential = {
  jobId: "0123456789abcdef0123456789abcdef",
  accessToken: "abcdefghijklmnopqrstuvwxyzABCDEFGH123456789_-",
  expiresAt: "2099-01-01T00:00:00Z",
};

describe("private job recovery", () => {
  it("round-trips the versioned recovery schema", () => {
    expect(parseJobCredential(serializeJobCredential(credential), Date.parse("2026-01-01"))).toEqual(credential);
  });

  it("rejects expired credentials", () => {
    expect(() => normalizeJobCredential({ ...credential, expiresAt: "2020-01-01T00:00:00Z" })).toThrow(/expired/i);
  });

  it("rejects extra fields instead of silently accepting secrets", () => {
    const payload = JSON.parse(serializeJobCredential(credential));
    payload.api_url = "https://attacker.example";
    expect(() => parseJobCredential(JSON.stringify(payload), Date.parse("2026-01-01"))).toThrow(/exactly/i);
  });

  it("does not permit a token in a malformed job identifier", () => {
    expect(() => normalizeJobCredential({ ...credential, jobId: "../job" })).toThrow(/job ID/i);
  });

  it("round-trips a GitHub Pages-safe private analysis link", () => {
    const link = buildJobRecoveryLink(credential, "https://example.org/casandra-web/?stale=1#workflow");
    const parsed = new URL(link);
    expect(parsed.origin).toBe("https://example.org");
    expect(parsed.pathname).toBe("/casandra-web/");
    expect(parsed.search).toBe("");
    expect(parsed.hash).toContain("#recover=v1.");
    expect(`${parsed.origin}${parsed.pathname}${parsed.search}`).not.toContain(credential.accessToken);
    expect(parseJobRecoveryLink(link, Date.parse("2026-01-01"))).toEqual({ ...credential, expiresAt: null });
  });

  it("ignores ordinary anchors and rejects malformed private links", () => {
    expect(parseJobRecoveryLink("https://example.org/casandra-web/#workflow")).toBeNull();
    expect(() => parseJobRecoveryLink("https://example.org/casandra-web/#recover=v2.bad.bad")).toThrow(/not supported/i);
    expect(() => parseJobRecoveryLink(`https://example.org/#recover=v1.${"a".repeat(1_100)}`)).toThrow(/too long/i);
  });

  it("scrubs only private recovery fragments from the address bar", () => {
    const link = buildJobRecoveryLink(credential, "https://example.org/casandra-web/");
    const replaceState = vi.fn();
    const browserWindow = { location: { href: link }, history: { state: { test: true }, replaceState } };
    expect(clearJobRecoveryLink(browserWindow)).toBe(true);
    expect(replaceState).toHaveBeenCalledWith({ test: true }, "", "/casandra-web/");
    browserWindow.location.href = "https://example.org/casandra-web/#workflow";
    expect(clearJobRecoveryLink(browserWindow)).toBe(false);
  });

  it("keeps the active credential in session storage and clears it", () => {
    const key = "casandra:test:active";
    expect(saveSessionCredential(sessionStorage, key, credential)).toBe(true);
    expect(loadSessionCredential(sessionStorage, key, Date.parse("2026-01-01"))).toEqual(credential);
    expect(clearSessionCredential(sessionStorage, key)).toBe(true);
    expect(loadSessionCredential(sessionStorage, key)).toBeNull();
  });
});
