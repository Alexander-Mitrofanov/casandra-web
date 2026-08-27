import { onBeforeUnmount, ref, watch } from "vue";

import { api } from "../api.js";
import { normalizeJobCredential } from "../jobStore.js";
import { TERMINAL_STATUSES } from "../science.js";
import { revealSection } from "../utils/formatting.js";

export function useJobSession(client = api) {
  const credential = ref(null);
  const job = ref(null);
  const sampleJob = ref(null);
  const pollError = ref("");
  const cancelling = ref(false);
  let cancellingLatch = false;
  let pollTimer;
  let pollController;

  function stopPolling() {
    window.clearTimeout(pollTimer);
    pollController?.abort();
    pollController = undefined;
  }

  async function poll() {
    const current = credential.value;
    if (!current) return;
    pollController = new AbortController();
    try {
      const response = await client.getJob(current.jobId, current.accessToken, { signal: pollController.signal });
      if (credential.value !== current) return;
      const latest = response?.job || response;
      job.value = latest;
      pollError.value = "";
      if (latest?.expires_at && latest.expires_at !== current.expiresAt) {
        credential.value = normalizeJobCredential({ ...current, expiresAt: latest.expires_at });
        return;
      }
      if (!TERMINAL_STATUSES.has(latest?.status)) {
        pollTimer = window.setTimeout(poll, 2_500);
      }
    } catch (error) {
      if (error.name === "AbortError" || credential.value !== current) return;
      const gone = [401, 403, 404, 410].includes(error.status);
      if (gone) {
        credential.value = null;
        job.value = null;
      }
      pollError.value = error.message || "Job status could not be refreshed.";
      if (!gone) pollTimer = window.setTimeout(poll, 5_000);
    }
  }

  watch(credential, (next) => {
    stopPolling();
    if (next) void poll();
  });

  function onSubmitted(nextCredential, initialJob) {
    sampleJob.value = null;
    credential.value = nextCredential;
    job.value = initialJob;
    pollError.value = "";
    window.setTimeout(() => revealSection("job-status", "#job-heading"), 50);
  }

  function onResumed(nextCredential) {
    sampleJob.value = null;
    credential.value = nextCredential;
    job.value = null;
    pollError.value = "";
    window.setTimeout(() => revealSection("job-status", "#job-heading"), 50);
  }

  function onSampleLoaded(snapshot) {
    sampleJob.value = snapshot;
    window.setTimeout(() => revealSection("sample-result", "#results-heading"), 50);
  }

  async function cancel() {
    if (!credential.value || cancellingLatch) return;
    cancellingLatch = true;
    cancelling.value = true;
    pollError.value = "";
    try {
      const response = await client.cancelJob(credential.value.jobId, credential.value.accessToken);
      job.value = response?.job || response;
    } catch (error) {
      pollError.value = error.message || "The cancellation request failed.";
    } finally {
      cancellingLatch = false;
      cancelling.value = false;
    }
  }

  function forget() {
    credential.value = null;
    job.value = null;
    pollError.value = "";
  }

  onBeforeUnmount(stopPolling);
  return {
    credential,
    job,
    sampleJob,
    pollError,
    cancelling,
    onSubmitted,
    onResumed,
    onSampleLoaded,
    cancel,
    forget,
  };
}
