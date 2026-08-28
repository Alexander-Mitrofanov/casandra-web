import { defineComponent } from "vue";
import { flushPromises, mount } from "@vue/test-utils";
import { describe, expect, it, vi } from "vitest";

import { useJobSession } from "../src/composables/useJobSession.js";
import { serializeJobCredential } from "../src/jobStore.js";

const credential = {
  jobId: "0123456789abcdef0123456789abcdef",
  accessToken: "abcdefghijklmnopqrstuvwxyzABCDEFGH123456789_-",
  expiresAt: null,
};

function mountSession(client, options) {
  return mount(defineComponent({
    setup() {
      return useJobSession(client, options);
    },
    template: "<div />",
  }));
}

describe("asynchronous job session", () => {
  it("cancels a pending reveal when the session is disposed", () => {
    vi.useFakeTimers();
    const wrapper = mountSession({ getJob: vi.fn() });
    wrapper.vm.onExampleCompleted({ status: "completed" });
    expect(vi.getTimerCount()).toBe(1);

    wrapper.unmount();

    expect(vi.getTimerCount()).toBe(0);
    vi.useRealTimers();
  });

  it("stores and clears a completed built-in analysis without creating a private credential", () => {
    const wrapper = mountSession({ getJob: vi.fn() });
    const completed = { status: "completed", summary: { analysis_mode: "metagenomic" } };
    wrapper.vm.onExampleCompleted(completed);
    expect(wrapper.vm.exampleJob).toEqual(completed);
    expect(wrapper.vm.credential).toBeNull();
    wrapper.vm.clearExample();
    expect(wrapper.vm.exampleJob).toBeNull();
    wrapper.unmount();
  });

  it("polls with the private credential and adopts the terminal result", async () => {
    const completed = { job_id: credential.jobId, status: "completed", phase: "completed", summary: { schema_version: "1.0.0" } };
    const client = { getJob: vi.fn().mockResolvedValue({ job: completed }) };
    const wrapper = mountSession(client);
    wrapper.vm.onSubmitted(credential, { status: "queued", phase: "queued" });
    await flushPromises();
    expect(client.getJob).toHaveBeenCalledWith(credential.jobId, credential.accessToken, expect.objectContaining({ signal: expect.any(AbortSignal) }));
    expect(wrapper.vm.job).toEqual(completed);
    wrapper.unmount();
  });

  it("forgets an unauthorized or expired remote job", async () => {
    const error = Object.assign(new Error("Results expired"), { status: 410 });
    const client = { getJob: vi.fn().mockRejectedValue(error) };
    const wrapper = mountSession(client);
    wrapper.vm.onResumed(credential);
    await flushPromises();
    expect(wrapper.vm.credential).toBeNull();
    expect(wrapper.vm.pollError).toBe("Results expired");
    wrapper.unmount();
  });

  it("restores the active analysis after a same-tab reload", async () => {
    const storageKey = "casandra:test:reload";
    sessionStorage.setItem(storageKey, serializeJobCredential(credential));
    const completed = { job_id: credential.jobId, status: "completed", phase: "completed" };
    const client = { getJob: vi.fn().mockResolvedValue({ job: completed }) };
    const wrapper = mountSession(client, { storage: sessionStorage, storageKey });
    await flushPromises();
    expect(wrapper.vm.credential).toEqual(credential);
    expect(client.getJob).toHaveBeenCalledWith(credential.jobId, credential.accessToken, expect.objectContaining({ signal: expect.any(AbortSignal) }));
    wrapper.vm.forget();
    await flushPromises();
    expect(sessionStorage.getItem(storageKey)).toBeNull();
    wrapper.unmount();
  });
});
