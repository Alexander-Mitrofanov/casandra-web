import { describe, expect, it, vi } from "vitest";

import { API_PREFIX, ApiError, createApiClient, normalizeApiBase } from "../src/api.js";

const jsonResponse = (payload, status = 200) => ({
  ok: status >= 200 && status < 300,
  status,
  json: vi.fn().mockResolvedValue(payload),
});

describe("API client", () => {
  it("uses the fixed CasAndra API prefix", () => {
    expect(API_PREFIX).toBe("/casandra/api/v1");
  });

  it("normalizes secure origins and permits localhost HTTP", () => {
    expect(normalizeApiBase("https://api.example.org/ ")).toBe("https://api.example.org");
    expect(normalizeApiBase("http://localhost:8080")).toBe("http://localhost:8080");
  });

  it.each([
    "http://api.example.org",
    "https://user:pass@api.example.org",
    "https://api.example.org/path",
    "https://api.example.org?token=x",
  ])("rejects unsafe API base %s", (value) => {
    expect(() => normalizeApiBase(value)).toThrow(ApiError);
  });

  it("posts the exact job payload with private request policy", async () => {
    const fetch = vi.fn().mockResolvedValue(jsonResponse({ job: { job_id: "a" }, access_token: "b" }, 202));
    const client = createApiClient("https://api.example.org", fetch);
    const payload = { sequence: ">a\nACGT\n", filename: "a.fna", gene_mode: "auto" };
    await client.submit(payload);
    expect(fetch).toHaveBeenCalledWith("https://api.example.org/casandra/api/v1/jobs", expect.objectContaining({
      method: "POST",
      credentials: "omit",
      referrerPolicy: "no-referrer",
      body: JSON.stringify(payload),
    }));
  });

  it("keeps the bearer token in the Authorization header", async () => {
    const fetch = vi.fn().mockResolvedValue(jsonResponse({ status: "running" }));
    const client = createApiClient("https://api.example.org", fetch);
    await client.getJob("job/with spaces", "private-token");
    const [url, options] = fetch.mock.calls[0];
    expect(url).toBe("https://api.example.org/casandra/api/v1/jobs/job%2Fwith%20spaces");
    expect(options.headers.Authorization).toBe("Bearer private-token");
    expect(url).not.toContain("private-token");
  });

  it("uses relative same-origin URLs when no origin is configured", async () => {
    const fetch = vi.fn().mockResolvedValue(jsonResponse({ status: "ok" }));
    await createApiClient("", fetch).health();
    expect(fetch.mock.calls[0][0]).toBe("/casandra/api/v1/health");
  });

  it("surfaces structured service errors", async () => {
    const fetch = vi.fn().mockResolvedValue(jsonResponse({ detail: { message: "Queue full", code: "queue_full" } }, 429));
    await expect(createApiClient("https://api.example.org", fetch).submit({})).rejects.toMatchObject({
      message: "Queue full",
      status: 429,
      code: "queue_full",
    });
  });
});
