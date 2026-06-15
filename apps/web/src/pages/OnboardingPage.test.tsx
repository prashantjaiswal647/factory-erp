import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as api from "../lib/api";
import OnboardingPage from "./OnboardingPage";

vi.mock("../lib/api", async () => {
  const actual = await vi.importActual<typeof import("../lib/api")>("../lib/api");
  return {
    ...actual,
    getAuthorizedSignatures: vi.fn(),
    getFinalStockOptions: vi.fn().mockResolvedValue({ data: [] }),
    getMachineLimits: vi.fn().mockResolvedValue({ data: null }),
    getOnboardingOverview: vi.fn().mockResolvedValue({ data: { machines: [] } }),
    getFactoryProfile: vi.fn().mockResolvedValue({ data: null }),
  };
});

vi.mock("../components/ConfigurationOverview", () => ({
  default: () => <div>Configuration overview</div>,
}));

vi.mock("../components/BulkUploadSection", () => ({
  default: () => <div>Bulk upload</div>,
}));

vi.mock("../context/AuthContext", () => ({
  isOwnerLevelRole: () => true,
  useAuth: () => ({ updateUser: vi.fn(), user: { role: "Owner" } }),
}));

vi.mock("../context/UpgradeContext", () => ({
  useUpgrade: () => ({ showToast: vi.fn(), showUpgradeModal: vi.fn() }),
}));

describe("OnboardingPage authorized signatures", () => {
  beforeEach(() => vi.clearAllMocks());

  it("test_onboarding_signature_page_handles_empty_response", async () => {
    vi.mocked(api.getAuthorizedSignatures).mockResolvedValue({ data: [] } as never);

    render(<OnboardingPage />);

    expect(await screen.findAllByText("Not uploaded")).toHaveLength(3);
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("test_onboarding_signature_page_handles_object_response", async () => {
    vi.mocked(api.getAuthorizedSignatures).mockResolvedValue({
      data: { owner: null, sub_owner: null, supervisor: null },
    } as never);

    render(<OnboardingPage />);

    expect((await screen.findByRole("alert")).textContent).toContain("server returned an invalid response");
    expect(screen.getAllByText("Not uploaded")).toHaveLength(3);
  });

  it("test_onboarding_signature_page_handles_api_failure", async () => {
    vi.mocked(api.getAuthorizedSignatures).mockRejectedValue(new Error("API 500"));

    render(<OnboardingPage />);

    expect((await screen.findByRole("alert")).textContent).toContain("Unable to load authorized signatures");
    expect(screen.getAllByText("Not uploaded")).toHaveLength(3);
  });
});
