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
  it("shows only the canonical CasAndra program version in the footer", async () => {
    const client = {
      health: vi.fn().mockResolvedValue({ status: "ok" }),
      config: vi.fn().mockResolvedValue({ api_version: "1.1.0" }),
      version: vi.fn().mockResolvedValue({
        casandra_program_version: "legacy-value",
        casandra_model: { program_version: "0.3.0.dev0" },
      }),
    };

    render(ServiceFooterHarness, { props: { client } });

    const footer = await screen.findByRole("contentinfo");
    await waitFor(() => expect(footer).toHaveTextContent(/^CasAndra v0\.3\.0\.dev0$/));
    expect(footer.querySelector("img, svg, a, .brand-mark")).toBeNull();
    expect(footer).not.toHaveTextContent(/Research software|Results require expert review|API|Makarova|CC BY|Back to top/i);
    expect(client.health).toHaveBeenCalledOnce();
    expect(client.config).toHaveBeenCalledOnce();
    expect(client.version).toHaveBeenCalledOnce();
  });
});
