import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as billingApi from "../../api/billing";
import SubscriptionStatusWidget from "./SubscriptionStatusWidget";

vi.mock("../../api/billing");

const response = {
  subscription_status: "active" as const,
  trial_end: null,
  current_period_start: null,
  current_period_end: "2026-07-05T00:00:00Z",
  next_billing_at: null,
  cancelled_at: null,
  plan_code: "monthly",
  is_payable: false,
  hosted_payment_url: null,
};

describe("SubscriptionStatusWidget", () => {
  beforeEach(() => vi.resetAllMocks());

  it("renders active status and refetches on focus", async () => {
    vi.mocked(billingApi.getBillingMe).mockResolvedValue(response);
    render(<SubscriptionStatusWidget />);
    expect(await screen.findByText("active")).toBeTruthy();
    fireEvent.focus(window);
    await waitFor(() => expect(billingApi.getBillingMe).toHaveBeenCalledTimes(2));
  });

  it("renders payable and error states", async () => {
    vi.mocked(billingApi.getBillingMe).mockResolvedValueOnce({
      ...response,
      subscription_status: "past_due",
      is_payable: true,
    });
    const view = render(<SubscriptionStatusWidget />);
    expect(await screen.findByText("past due")).toBeTruthy();
    view.unmount();
    vi.mocked(billingApi.getBillingMe).mockRejectedValueOnce(new Error("offline"));
    render(<SubscriptionStatusWidget />);
    expect(await screen.findByText("Unable to load subscription status.")).toBeTruthy();
  });
});
