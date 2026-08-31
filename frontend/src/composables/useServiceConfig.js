import { onBeforeUnmount, onMounted, ref } from "vue";

import { api } from "../api.js";

const DEFAULT_LIMITS = Object.freeze({
  maxBases: 100_000_000,
  maxRecordBases: 0,
  maxRecords: 1_000,
  maxResidues: 100_000_000,
  maxRecordResidues: 0,
  maxProteinRecords: 1_000,
  maxRequestBytes: 105_000_000,
  maxCasOnlyRequestBytes: 105_000_000,
  maxCasOnlyBases: 100_000_000,
  maxCasOnlyRecords: 1_000,
  maxCasOnlyRecordBases: 0,
  maxArrayRequestBytes: 4_500_000,
  maxArrayBases: 2_000_000,
  maxArrayRecords: 20,
  maxArrayRecordBases: 0,
  maxArtifactBytes: 0,
  maxHeaderCharacters: 200,
});

export function useServiceConfig(client = api) {
  const service = ref({ state: "checking", message: "Checking analysis service" });
  const limits = ref({ ...DEFAULT_LIMITS });
  let controller;

  async function refresh() {
    controller?.abort();
    controller = new AbortController();
    try {
      const versionRequest = typeof client.version === "function"
        ? client.version({ signal: controller.signal }).catch((error) => {
          if (error.name === "AbortError") throw error;
          return null;
        })
        : Promise.resolve(null);
      const [health, config, version] = await Promise.all([
        client.health({ signal: controller.signal }),
        client.config({ signal: controller.signal }),
        versionRequest,
      ]);
      service.value = {
        state: health?.status === "degraded" ? "degraded" : "online",
        message: health?.status === "degraded" ? "Analysis service degraded" : "Analysis service ready",
        apiVersion: config?.api_version,
        casandraVersion: version?.casandra_model?.program_version
          || version?.casandra_program_version
          || config?.casandra_model?.program_version
          || config?.casandra_program_version,
        crispridentifyVersion: config?.crispridentify_version,
      };
      const casOnly = config?.input_policies?.cas_only;
      const withArrays = config?.input_policies?.with_crispr_arrays;
      limits.value = {
        maxBases: config?.max_total_bases || config?.max_sequence_bases || DEFAULT_LIMITS.maxBases,
        maxRecordBases: config?.max_record_bases || DEFAULT_LIMITS.maxRecordBases,
        maxRecords: config?.max_records || DEFAULT_LIMITS.maxRecords,
        maxResidues: config?.max_total_residues || config?.max_sequence_residues || config?.max_total_bases || DEFAULT_LIMITS.maxResidues,
        maxRecordResidues: config?.max_record_residues || config?.max_protein_residues || config?.max_record_bases || DEFAULT_LIMITS.maxRecordResidues,
        maxProteinRecords: config?.max_protein_records || config?.max_records || DEFAULT_LIMITS.maxProteinRecords,
        maxRequestBytes: config?.max_protein_request_bytes || config?.max_request_bytes || DEFAULT_LIMITS.maxRequestBytes,
        maxCasOnlyRequestBytes: casOnly?.max_request_bytes || config?.max_cas_only_request_bytes || config?.max_request_bytes || DEFAULT_LIMITS.maxCasOnlyRequestBytes,
        maxCasOnlyBases: casOnly?.max_total_bases || config?.max_cas_only_total_bases || config?.max_total_bases || DEFAULT_LIMITS.maxCasOnlyBases,
        maxCasOnlyRecords: casOnly?.max_records || config?.max_cas_only_records || config?.max_records || DEFAULT_LIMITS.maxCasOnlyRecords,
        maxCasOnlyRecordBases: casOnly?.max_record_bases || config?.max_cas_only_record_bases || config?.max_record_bases || DEFAULT_LIMITS.maxCasOnlyRecordBases,
        maxArrayRequestBytes: withArrays?.max_request_bytes || config?.max_array_request_bytes || config?.max_request_bytes || DEFAULT_LIMITS.maxArrayRequestBytes,
        maxArrayBases: withArrays?.max_total_bases || config?.max_array_total_bases || config?.max_total_bases || DEFAULT_LIMITS.maxArrayBases,
        maxArrayRecords: withArrays?.max_records || config?.max_array_records || config?.max_records || DEFAULT_LIMITS.maxArrayRecords,
        maxArrayRecordBases: withArrays?.max_record_bases || config?.max_array_record_bases || config?.max_record_bases || DEFAULT_LIMITS.maxArrayRecordBases,
        maxArtifactBytes: config?.max_artifact_bytes || config?.max_archive_bytes || 0,
        maxHeaderCharacters: config?.max_header_characters || DEFAULT_LIMITS.maxHeaderCharacters,
      };
    } catch (error) {
      if (error.name !== "AbortError") {
        service.value = {
          state: "offline",
          message: error.message || "The analysis API could not be reached.",
        };
      }
    }
  }

  onMounted(refresh);
  onBeforeUnmount(() => controller?.abort());
  return { service, limits, refresh };
}
