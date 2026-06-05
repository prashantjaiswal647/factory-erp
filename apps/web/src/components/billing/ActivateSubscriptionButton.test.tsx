import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import * as billingApi from "../../api/billing";
import ActivateSubscriptionButton from "./ActivateSubscriptionButton";

vi.mock("../../api/billing");

describe("ActivateSubscriptionButton", () => {
  it("opens the modal and shows the Cashfree authorization URL", async () => {
    vi.mocked(billingApi.createCashfreeSubscription).mockResolvedValue({
      cashfree_customer_id: "customer",
      cashfree_subscription_id: "subscription",
      hosted_payment_url: "https://cashfree.test/authorize",
      subscription_status: "pending",
    });
    render(<ActivateSubscriptionButton factoryId={7} />);
    fireEvent.click(screen.getByText("Activate Cashfree"));
    fireEvent.click(screen.getByText("Create subscription"));
    expect((await screen.findByText("Open authorization")).getAttribute("href")).toBe(
      "https://cashfree.test/authorize",
    );
    expect(billingApi.createCashfreeSubscription).toHaveBeenCalledWith(7, "monthly");
  });

  it("shows an API error", async () => {
    vi.mocked(billingApi.createCashfreeSubscription).mockRejectedValue(new Error("failed"));
    render(<ActivateSubscriptionButton factoryId={7} />);
    fireEvent.click(screen.getByText("Activate Cashfree"));
    fireEvent.click(screen.getByText("Create subscription"));
    expect(await screen.findByText("Cashfree activation failed.")).toBeTruthy();
  });
});
