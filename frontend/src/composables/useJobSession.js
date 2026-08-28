import { onBeforeUnmount, ref, watch } from "vue";

import { api } from "../api.js";
import {
  clearSessionCredential,
  loadSessionCredential,
  normalizeJobCredential,
  saveSessionCredential,
} from "../jobStore.js";
import { TERMINAL_STATUSES } from "../science.js";
import { revealSection } from "../utils/formatting.js";

const SESSION_KEY = `casandra:${import.meta.env.BASE_URL}:active-analysis-v1`;

function availableSessionStorage() {
  try {
    return window.sessionStorage;
  } catch {
    return null;
  }
}

export function useJobSession(client = api, options = {}) {
  const storage = options.storage === undefined ? availableSessionStorage() : options.storage;
  const storageKey = options.storageKey || SESSION_KEY;
  const credential = ref(loadSessionCredential(storage, storageKey));
  const job = ref(null);
  const sampleJob = ref(null);
  const pollError = ref("");
  const cancelling = ref(false);
  let cancellingLatch = false;
  let pollTimer;
  let pollController;
  let revealTimer;

  function stopPolling() {
    window.clearTimeout(pollTimer);
    pollController?.abort();
    pollController = undefined;
  }

  function scheduleReveal(id, focusSelector) {
    window.clearTimeout(revealTimer);
    revealTimer = window.setTimeout(() => {
      revealTimer = undefined;
      revealSection(id, focusSelector);
    }, 50);
  }

  function dispose() {
    stopPolling();
    window.clearTimeout(revealTimer);
    revealTimer = undefined;
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
    if (next) {
      saveSessionCredential(storage, storageKey, next);
      void poll();
    } else {
      clearSessionCredential(storage, storageKey);
    }
  }, { immediate: true });

  function onSubmitted(nextCredential, initialJob) {
    sampleJob.value = null;
    credential.value = nextCredential;
    job.value = initialJob;
    pollError.value = "";
    scheduleReveal("job-status", "#job-heading");
  }

  function onResumed(nextCredential) {
    sampleJob.value = null;
    credential.value = nextCredential;
    job.value = null;
    pollError.value = "";
    scheduleReveal("job-status", "#job-heading");
  }

  function onSampleLoaded(snapshot) {
    sampleJob.value = snapshot;
    scheduleReveal("sample-result", "#results-heading");
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
    window.clearTimeout(revealTimer);
    revealTimer = undefined;
    credential.value = null;
    job.value = null;
    pollError.value = "";
  }

  onBeforeUnmount(dispose);
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
