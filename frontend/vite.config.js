import { defineConfig, loadEnv } from "vite";
import vue from "@vitejs/plugin-vue";

function normalizeBase(value) {
  const trimmed = String(value || "/").trim();
  if (!trimmed || trimmed === "/") return "/";
  return `/${trimmed.replace(/^\/+|\/+$/g, "")}/`;
}

function apiOrigin(value) {
  const raw = String(value || "").trim();
  if (!raw) return "";
  let parsed;
  try {
    parsed = new URL(raw);
  } catch {
    throw new Error("VITE_API_BASE_URL must be a valid URL origin.");
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
    throw new Error("VITE_API_BASE_URL must be an exact HTTPS origin (HTTP is accepted only for localhost).");
  }
  return parsed.origin;
}

function contentSecurityPolicy(command, origin) {
  if (command !== "build") return null;
  const connectSources = origin ? `'self' ${origin}` : "'self'";
  const policy = [
    "default-src 'none'",
    "base-uri 'none'",
    "object-src 'none'",
    "script-src 'self'",
    "script-src-attr 'none'",
    "style-src 'self'",
    "style-src-attr 'none'",
    "img-src 'self' data:",
    "font-src 'self'",
    `connect-src ${connectSources}`,
    "media-src 'none'",
    "frame-src 'none'",
    "worker-src 'none'",
    "manifest-src 'self'",
    "form-action 'none'",
    "upgrade-insecure-requests",
  ].join("; ");

  return {
    name: "casandra-content-security-policy",
    enforce: "post",
    transformIndexHtml() {
      return [{
        tag: "meta",
        attrs: { "http-equiv": "Content-Security-Policy", content: policy },
        injectTo: "head-prepend",
      }];
    },
  };
}

export default defineConfig(({ command, mode }) => {
  const env = loadEnv(mode, process.cwd(), "VITE_");
  const origin = apiOrigin(process.env.VITE_API_BASE_URL || env.VITE_API_BASE_URL);
  const csp = contentSecurityPolicy(command, origin);
  return {
    base: normalizeBase(process.env.VITE_BASE_PATH || env.VITE_BASE_PATH),
    plugins: [vue(), ...(csp ? [csp] : [])],
    test: {
      environment: "jsdom",
      globals: true,
      setupFiles: "./tests/setup.js",
      css: true,
    },
  };
});
