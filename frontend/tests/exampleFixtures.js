import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const ROOT = resolve(process.cwd(), "public/examples");

export function exampleText(mode, name) {
  return readFileSync(resolve(ROOT, mode, name), "utf-8");
}

export function exampleBytes(mode, name) {
  return readFileSync(resolve(ROOT, mode, name));
}

export function exampleJob(mode = "complete_genome") {
  return JSON.parse(exampleText(mode, "job.json"));
}

export function exampleFetch() {
  return async (input) => {
    const url = new URL(String(input), "https://example.test/casandra-web/");
    const marker = "/examples/";
    const index = url.pathname.indexOf(marker);
    if (index < 0) return { ok: false, status: 404 };
    const relative = url.pathname.slice(index + marker.length);
    if (!/^(complete_genome|annotate_cas_genes|classify_cassette|metagenomic)\/[A-Za-z0-9._/-]+$/.test(relative) || relative.includes("..")) {
      return { ok: false, status: 400 };
    }
    const content = readFileSync(resolve(ROOT, relative));
    return {
      ok: true,
      status: 200,
      text: async () => content.toString("utf-8"),
      json: async () => JSON.parse(content.toString("utf-8")),
      blob: async () => new Blob([content]),
    };
  };
}
