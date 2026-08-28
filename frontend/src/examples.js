const MODES = Object.freeze({
  complete_genome: { filename: "input.fna", sourceName: "input.fna", includeCrisprArrays: false },
  annotate_cas_genes: { filename: "input.faa", sourceName: "input.faa", includeCrisprArrays: false },
  classify_cassette: { filename: "input.faa", sourceName: "input.faa", includeCrisprArrays: false },
  metagenomic: { filename: "input.fna", sourceName: "input.fna", includeCrisprArrays: false },
});

function isObject(value) {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function isCrisprArtifact(artifact) {
  return [artifact?.name, artifact?.scope, artifact?.role]
    .some((value) => /crispr/i.test(String(value || "")));
}

function summaryMatchesArrayOption(summary, includeCrisprArrays, analysisMode) {
  if (
    !isObject(summary)
    || summary.analysis_mode !== analysisMode
    || summary.include_crispr_arrays !== includeCrisprArrays
    || !Array.isArray(summary.crispr_arrays)
  ) return false;

  const provenance = summary.provenance;
  const arrayDetection = provenance?.array_detection;
  if (
    !isObject(provenance)
    || !isObject(arrayDetection)
    || arrayDetection.requested !== includeCrisprArrays
    || arrayDetection.status !== (includeCrisprArrays ? "completed" : "not_requested")
  ) return false;

  if (analysisMode === "complete_genome") {
    if (provenance.array_overlay_role !== (includeCrisprArrays ? "independent_coordinate_overlay" : "not_requested")) return false;
    if (includeCrisprArrays) {
      if (!String(provenance.crispridentify_version || "").trim()) return false;
    } else if (provenance.crispridentify_version != null || provenance.crispridentify_version_attestation != null) {
      return false;
    }
  }

  if (includeCrisprArrays) return true;
  return (
    summary.crispr_arrays.length === 0
    && Number(summary.overview?.crispr_array_count || 0) === 0
    && summary.detail_truncated?.crispr_arrays !== true
    && (!Array.isArray(summary.cassettes) || summary.cassettes.every((row) => row?.nearest_array == null))
  );
}

function jobMatchesArrayOption(job, includeCrisprArrays, analysisMode) {
  const details = job?.interactive_results;
  if (
    !summaryMatchesArrayOption(job?.summary, includeCrisprArrays, analysisMode)
    || !isObject(details)
    || details.analysis_mode !== analysisMode
    || !Array.isArray(details.features)
    || !Array.isArray(details.sources)
    || !summaryMatchesArrayOption(details.summary, includeCrisprArrays, analysisMode)
    || !Array.isArray(job?.artifacts)
  ) return false;

  if (includeCrisprArrays) return true;
  return (
    !details.features.some((row) => row?.kind === "crispr_array" || row?.nearest_array != null)
    && Number(details.feature_counts?.crispr_array || 0) === 0
    && !job.artifacts.some(isCrisprArtifact)
  );
}

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
    || job?.options?.include_crispr_arrays !== definition.includeCrisprArrays
    || job?.input?.filename !== definition.sourceName
    || !jobMatchesArrayOption(job, definition.includeCrisprArrays, analysisMode)
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
