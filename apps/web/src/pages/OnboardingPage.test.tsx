import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as api from "../lib/api";
import OnboardingPage from "./OnboardingPage";

vi.mock("../lib/api", async () => {
  const actual = await vi.importActual<typeof import("../lib/api")>("../lib/api");
  return {
    ...actual,
    getAuthorizedSignatures: vi.fn(),
    getAuthorizedSignatureFile: vi.fn().mockResolvedValue({
      data: new Blob(["signature"], { type: "image/png" }),
    }),
    uploadAuthorizedSignature: vi.fn(),
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
    vi.mocked(api.getAuthorizedSignatures).mockResolvedValue({
      data: {
        owner: { uploaded: false, role: "owner", file_url: null, original_filename: null, updated_at: null, created_at: null },
        sub_owner: { uploaded: false, role: "sub_owner", file_url: null, original_filename: null, updated_at: null, created_at: null },
        supervisor: { uploaded: false, role: "supervisor", file_url: null, original_filename: null, updated_at: null, created_at: null },
      },
    } as never);

    render(<OnboardingPage />);

    expect(await screen.findAllByText("Not uploaded")).toHaveLength(3);
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("test_onboarding_signature_page_handles_uploaded_signature", async () => {
    vi.mocked(api.getAuthorizedSignatures).mockResolvedValue({
      data: {
        owner: {
          uploaded: true,
          role: "owner",
          file_url: "/api/onboarding/signatures/owner/file",
          original_filename: "owner.png",
          updated_at: "2026-06-15T12:00:00+00:00",
          created_at: "2026-06-15T12:00:00+00:00",
        },
        sub_owner: { uploaded: false, role: "sub_owner", file_url: null, original_filename: null, updated_at: null, created_at: null },
        supervisor: { uploaded: false, role: "supervisor", file_url: null, original_filename: null, updated_at: null, created_at: null },
      },
    } as never);

    render(<OnboardingPage />);

    const image = await screen.findByAltText("Owner Signature");
    expect(image.getAttribute("src")).toContain("data:image/png");
    expect(screen.queryByRole("alert")).toBeNull();
    expect(screen.getAllByText("Not uploaded")).toHaveLength(2);
  });

  it("test_onboarding_signature_page_rejects_invalid_schema", async () => {
    vi.mocked(api.getAuthorizedSignatures).mockResolvedValue({
      data: { owner: null, sub_owner: null, supervisor: null },
    } as never);

    render(<OnboardingPage />);

    expect((await screen.findByRole("alert")).textContent).toContain("server returned an invalid response");
  });

  it("test_onboarding_signature_page_handles_api_failure", async () => {
    vi.mocked(api.getAuthorizedSignatures).mockRejectedValue(new Error("API 500"));

    render(<OnboardingPage />);

    expect((await screen.findByRole("alert")).textContent).toContain("Unable to load authorized signatures");
    expect(screen.getAllByText("Not uploaded")).toHaveLength(3);
  });

  it("test_onboarding_signature_preview_updates_after_upload", async () => {
    const empty = {
      owner: { uploaded: false, role: "owner", file_url: null, original_filename: null, updated_at: null, created_at: null },
      sub_owner: { uploaded: false, role: "sub_owner", file_url: null, original_filename: null, updated_at: null, created_at: null },
      supervisor: { uploaded: false, role: "supervisor", file_url: null, original_filename: null, updated_at: null, created_at: null },
    };
    const uploaded = {
      ...empty,
      owner: {
        uploaded: true,
        role: "owner",
        file_url: "/api/onboarding/signatures/owner/file",
        original_filename: "signature.png",
        updated_at: "2026-06-15T12:00:00+00:00",
        created_at: "2026-06-15T12:00:00+00:00",
      },
    };
    vi.mocked(api.getAuthorizedSignatures)
      .mockResolvedValueOnce({ data: empty } as never)
      .mockResolvedValueOnce({ data: uploaded } as never);
    vi.mocked(api.uploadAuthorizedSignature).mockResolvedValue({ data: {} } as never);

    render(<OnboardingPage />);
    await screen.findAllByText("Not uploaded");
    const inputs = document.querySelectorAll('input[type="file"]');
    expect(inputs.length).toBeGreaterThan(0);
    fireEvent.change(inputs[0] as HTMLInputElement, {
      target: {
        files: [new File(["image"], "signature.png", { type: "image/png" })],
      },
    });

    expect(await screen.findByAltText("Owner Signature")).not.toBeNull();
    expect(screen.queryByText("server returned an invalid response")).toBeNull();
  });
});
