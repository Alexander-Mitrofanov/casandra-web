const MODES = Object.freeze({
  complete_genome: { filename: "input.fna", sourceName: "input.fna", includeCrisprArrays: true },
  annotate_cas_genes: { filename: "input.faa", sourceName: "input.faa", includeCrisprArrays: false },
  classify_cassette: { filename: "input.faa", sourceName: "input.faa", includeCrisprArrays: false },
  metagenomic: { filename: "input.fna", sourceName: "input.fna", includeCrisprArrays: false },
});

function assetPath(path) {
  const base = String(import.meta.env.BASE_URL || "/").replace(/\/?$/, "/");
  return `${base}${String(path).replace(/^\/+/, "")}`;
}

async function fetchAsset(path, responseType) {
  const response = await fetch(assetPath(path), { credentials: "same-origin" });
  if (!response.ok) throw new Error(`The selected example could not be loaded (${response.status}).`);
  return responseType === "json" ? response.json() : response.text();
}

export function exampleDefinition(analysisMode) {
  const definition = MODES[analysisMode];
  if (!definition) throw new Error("The selected analysis mode has no example.");
  return {
    ...definition,
    analysisMode,
    inputPath: `examples/${analysisMode}/${definition.sourceName}`,
    jobPath: `examples/${analysisMode}/job.json`,
  };
}

export async function loadExampleInput(analysisMode) {
  const definition = exampleDefinition(analysisMode);
  return { ...definition, sequence: await fetchAsset(definition.inputPath, "text") };
}

export async function loadExampleJob(analysisMode) {
  const definition = exampleDefinition(analysisMode);
  const job = await fetchAsset(definition.jobPath, "json");
  if (
    job?.status !== "completed"
    || job?.options?.analysis_mode !== analysisMode
    || Boolean(job?.options?.include_crispr_arrays) !== definition.includeCrisprArrays
    || job?.summary?.analysis_mode !== analysisMode
    || job?.input?.filename !== definition.sourceName
    || !Array.isArray(job?.interactive_results?.features)
    || !Array.isArray(job?.artifacts)
  ) {
    throw new Error("The selected example result is inconsistent with its analysis mode.");
  }
  return job;
}

export function bundledArtifactPath(value) {
  const path = String(value || "");
  if (!/^examples\/(complete_genome|annotate_cas_genes|classify_cassette|metagenomic)\/artifacts\/[A-Za-z0-9._-]+$/.test(path)) {
    throw new Error("The bundled artifact path is invalid.");
  }
  return assetPath(path);
}
