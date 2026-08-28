import { onBeforeUnmount, onMounted, ref } from "vue";

import { api } from "../api.js";

const DEFAULT_LIMITS = Object.freeze({
  maxBases: 100_000_000,
  maxRecordBases: 0,
  maxRecords: 1_000,
  maxRequestBytes: 105_000_000,
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
      const [health, config] = await Promise.all([
        client.health({ signal: controller.signal }),
        client.config({ signal: controller.signal }),
      ]);
      service.value = {
        state: health?.status === "degraded" ? "degraded" : "online",
        message: health?.status === "degraded" ? "Analysis service degraded" : "Analysis service ready",
        crispridentifyVersion: config?.crispridentify_version,
      };
      limits.value = {
        maxBases: config?.max_total_bases || config?.max_sequence_bases || DEFAULT_LIMITS.maxBases,
        maxRecordBases: config?.max_record_bases || DEFAULT_LIMITS.maxRecordBases,
        maxRecords: config?.max_records || DEFAULT_LIMITS.maxRecords,
        maxRequestBytes: config?.max_request_bytes || DEFAULT_LIMITS.maxRequestBytes,
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
