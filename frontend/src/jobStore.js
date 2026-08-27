const RECOVERY_SCHEMA = "casandra-job-recovery-v1";
const JOB_ID_PATTERN = /^[A-Za-z0-9][A-Za-z0-9_-]{15,127}$/;
const TOKEN_PATTERN = /^[A-Za-z0-9_-]{24,512}$/;

export function normalizeJobCredential(value, now = Date.now()) {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error("Recovery credential must be a JSON object.");
  }
  const expected = ["accessToken", "expiresAt", "jobId"];
  const actual = Object.keys(value).sort();
  if (actual.length !== expected.length || actual.some((key, index) => key !== expected[index])) {
    throw new Error("Recovery credential must contain exactly the supported fields.");
  }
  if (typeof value.jobId !== "string" || !JOB_ID_PATTERN.test(value.jobId)) {
    throw new Error("Recovery credential has an invalid job ID.");
  }
  if (typeof value.accessToken !== "string" || !TOKEN_PATTERN.test(value.accessToken)) {
    throw new Error("Recovery credential has an invalid access token.");
  }
  if (value.expiresAt !== null) {
    if (typeof value.expiresAt !== "string") throw new Error("Recovery credential has an invalid expiry.");
    const expiry = Date.parse(value.expiresAt);
    if (!Number.isFinite(expiry)) throw new Error("Recovery credential has an invalid expiry.");
    if (expiry <= now) throw new Error("Recovery credential has expired.");
  }
  return { jobId: value.jobId, accessToken: value.accessToken, expiresAt: value.expiresAt };
}

export function serializeJobCredential(value) {
  const credential = normalizeJobCredential(value, 0);
  return `${JSON.stringify({
    schema: RECOVERY_SCHEMA,
    job_id: credential.jobId,
    access_token: credential.accessToken,
    expires_at: credential.expiresAt,
  }, null, 2)}\n`;
}

export function parseJobCredential(text, now = Date.now()) {
  if (typeof text !== "string" || new TextEncoder().encode(text).byteLength > 16_384) {
    throw new Error("Recovery file must be a small JSON document.");
  }
  let value;
  try {
    value = JSON.parse(text);
  } catch {
    throw new Error("Recovery file is not valid JSON.");
  }
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error("Recovery file must contain a JSON object.");
  }
  const expected = ["access_token", "expires_at", "job_id", "schema"];
  const actual = Object.keys(value).sort();
  if (actual.length !== expected.length || actual.some((key, index) => key !== expected[index])) {
    throw new Error("Recovery file must contain exactly the supported fields.");
  }
  if (value.schema !== RECOVERY_SCHEMA) throw new Error("Recovery file schema is not supported.");
  return normalizeJobCredential({
    jobId: value.job_id,
    accessToken: value.access_token,
    expiresAt: value.expires_at,
  }, now);
}
