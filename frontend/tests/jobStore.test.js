import { describe, expect, it } from "vitest";

import { normalizeJobCredential, parseJobCredential, serializeJobCredential } from "../src/jobStore.js";

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
});
