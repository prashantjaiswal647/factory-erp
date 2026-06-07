import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import InventoryPage from "../src/pages/InventoryPage";
import * as api from "../src/lib/api";

vi.mock("../src/lib/api", async () => {
  const actual = await vi.importActual("../src/lib/api");
  return {
    ...actual,
    getInventory: vi.fn(),
  };
});

vi.mock("../src/context/AuthContext", () => ({
  useAuth: () => ({
    user: { role: "Owner", factory_id: 1 }
  })
}));

describe("InventoryPage Packaging Cleanup", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("filters out packaging items (polybags_packing) from presentation layer", async () => {
    const mockInventoryData = [
      {
        id: 1,
        stock_type: "Blank",
        bucket: "cup_blanks",
        item_name: "Cup Blank 100ml",
        quantity: 100,
        unit: "kg",
        category: "Raw Materials",
        current_quantity: 100,
      },
      {
        id: 2,
        stock_type: "Polybag",
        bucket: "polybags_packing",
        item_name: "100ml Polybag",
        quantity: 0,
        unit: "pcs",
        category: "Packing Materials",
        current_quantity: 0,
      },
    ];

    vi.mocked(api.getInventory).mockResolvedValue({
      data: mockInventoryData as any,
      status: 200,
      statusText: "OK",
      headers: {},
      config: {} as any,
    });

    render(
      <MemoryRouter>
        <InventoryPage />
      </MemoryRouter>
    );

    // Wait for data to load using header or count
    expect(await screen.findByText("Live Inventory")).toBeInTheDocument();

    // Verify raw material is shown
    expect(screen.getAllByText("Cup Blank 100ml")[0]).toBeInTheDocument();

    // Verify polybag packaging item is NOT rendered
    expect(screen.queryByText("100ml Polybag")).not.toBeInTheDocument();

    // Verify packaging headers/tabs are not shown
    expect(screen.queryByRole("button", { name: "Packaging" })).not.toBeInTheDocument();
    expect(screen.queryByText("Packaging KPIs")).not.toBeInTheDocument();
  });
});


