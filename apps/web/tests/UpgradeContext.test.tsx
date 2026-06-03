import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import { UpgradeProvider } from "../src/context/UpgradeContext";

describe("UpgradeProvider", () => {
  it("opens the upgrade modal when a 403 UPGRADE_REQUIRED event is emitted", async () => {
    render(
      <MemoryRouter>
        <UpgradeProvider>
          <div>App content</div>
        </UpgradeProvider>
      </MemoryRouter>
    );

    window.dispatchEvent(
      new CustomEvent("upgrade-required", {
        detail: {
          code: "UPGRADE_REQUIRED",
          message: "You have reached your limit of 7 machines.",
          used: 7,
          limit: 7,
          plan: "trial"
        }
      })
    );

    expect(await screen.findByText("Upgrade Required")).toBeInTheDocument();
    expect(screen.getByText("You have reached your limit of 7 machines.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Upgrade Now" })).toBeInTheDocument();
  });
});
