import { render, screen, waitFor } from "@testing-library/vue";
import { defineComponent } from "vue";
import { describe, expect, it, vi } from "vitest";

import SiteFooter from "../src/components/shell/SiteFooter.vue";
import { useServiceConfig } from "../src/composables/useServiceConfig.js";

const ServiceFooterHarness = defineComponent({
  components: { SiteFooter },
  props: { client: { type: Object, required: true } },
  setup(props) {
    return useServiceConfig(props.client);
  },
  template: '<SiteFooter :service="service"/>',
});

describe("service configuration", () => {
  it("shows the API version supplied by the public config response", async () => {
    const client = {
      health: vi.fn().mockResolvedValue({ status: "ok" }),
      config: vi.fn().mockResolvedValue({ api_version: "1.1.0" }),
    };

    render(ServiceFooterHarness, { props: { client } });

    await waitFor(() => expect(screen.getByText(/API 1\.1\.0/)).toBeInTheDocument());
    expect(screen.queryByText(/API version unavailable/)).not.toBeInTheDocument();
    expect(client.health).toHaveBeenCalledOnce();
    expect(client.config).toHaveBeenCalledOnce();
  });
});
