export const API_PREFIX = "/casandra/api/v1";
const DEFAULT_API_BASE = String(import.meta.env.VITE_API_BASE_URL || "").trim();
const PRIVATE_REQUEST_POLICY = Object.freeze({
  cache: "no-store",
  credentials: "omit",
  referrerPolicy: "no-referrer",
});

export class ApiError extends Error {
  constructor(message, status = 0, code = "request_failed") {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
  }
}

export function normalizeApiBase(value) {
  const raw = String(value || "").trim().replace(/\/+$/, "");
  if (!raw) return "";
  let parsed;
  try {
    parsed = new URL(raw);
  } catch {
    throw new ApiError("The analysis API address is not a valid URL.", 0, "invalid_api_base");
  }
  const local = ["localhost", "127.0.0.1", "[::1]"].includes(parsed.hostname);
  if (
    (parsed.protocol !== "https:" && !(local && parsed.protocol === "http:"))
    || parsed.username
    || parsed.password
    || parsed.pathname !== "/"
    || parsed.search
    || parsed.hash
  ) {
    throw new ApiError("The analysis API must be an exact HTTPS origin.", 0, "insecure_api_base");
  }
  return parsed.origin;
}

function endpoint(baseUrl, path) {
  const base = normalizeApiBase(baseUrl);
  const suffix = path.startsWith("/") ? path : `/${path}`;
  return `${base}${API_PREFIX}${suffix}`;
}

async function parseJson(response) {
  let payload = null;
  try {
    payload = await response.json();
  } catch {
    // Preserve a controlled error rather than exposing a parser detail.
  }
  if (!response.ok) {
    const detail = payload?.detail;
    const message = typeof detail === "string" ? detail : detail?.message;
    throw new ApiError(
      message || payload?.message || `The analysis service returned status ${response.status}.`,
      response.status,
      detail?.code || payload?.code,
    );
  }
  return payload;
}

export function createApiClient(baseUrl = DEFAULT_API_BASE, fetchImpl = globalThis.fetch) {
  const jobHeaders = (accessToken, extra = {}) => ({
    Accept: "application/json",
    Authorization: `Bearer ${accessToken}`,
    ...extra,
  });
  const request = (path, options) => fetchImpl(endpoint(baseUrl, path), options);

  return {
    configured: true,
    explicitlyConfigured: Boolean(String(baseUrl || "").trim()),
    displayBase: String(baseUrl || "").trim().replace(/\/+$/, "") || "same origin",

    async health({ signal } = {}) {
      return parseJson(await request("/health", {
        ...PRIVATE_REQUEST_POLICY,
        headers: { Accept: "application/json" },
        signal,
      }));
    },

    async config({ signal } = {}) {
      return parseJson(await request("/config", {
        ...PRIVATE_REQUEST_POLICY,
        headers: { Accept: "application/json" },
        signal,
      }));
    },

    async version({ signal } = {}) {
      return parseJson(await request("/version", {
        ...PRIVATE_REQUEST_POLICY,
        headers: { Accept: "application/json" },
        signal,
      }));
    },

    async submit(payload, { signal } = {}) {
      return parseJson(await request("/jobs", {
        ...PRIVATE_REQUEST_POLICY,
        method: "POST",
        headers: { Accept: "application/json", "Content-Type": "application/json" },
        body: JSON.stringify(payload),
        signal,
      }));
    },

    async getJob(jobId, accessToken, { signal } = {}) {
      return parseJson(await request(`/jobs/${encodeURIComponent(jobId)}`, {
        ...PRIVATE_REQUEST_POLICY,
        headers: jobHeaders(accessToken),
        signal,
      }));
    },

    async cancelJob(jobId, accessToken, { signal } = {}) {
      return parseJson(await request(`/jobs/${encodeURIComponent(jobId)}`, {
        ...PRIVATE_REQUEST_POLICY,
        method: "DELETE",
        headers: jobHeaders(accessToken),
        signal,
      }));
    },

    async downloadArtifact(jobId, artifactId, accessToken, { signal } = {}) {
      const response = await request(
        `/jobs/${encodeURIComponent(jobId)}/artifacts/${encodeURIComponent(artifactId)}`,
        {
          ...PRIVATE_REQUEST_POLICY,
          headers: jobHeaders(accessToken, { Accept: "application/octet-stream" }),
          signal,
        },
      );
      if (!response.ok) return parseJson(response);
      return response.blob();
    },

    async downloadBundle(jobId, accessToken, { signal } = {}) {
      const response = await request(`/jobs/${encodeURIComponent(jobId)}/result`, {
        ...PRIVATE_REQUEST_POLICY,
        headers: jobHeaders(accessToken, { Accept: "application/zip, application/octet-stream" }),
        signal,
      });
      if (!response.ok) return parseJson(response);
      return response.blob();
    },
  };
}

export const api = createApiClient();
