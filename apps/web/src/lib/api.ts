import axios from "axios";

export const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000",
  timeout: 10000
});

api.interceptors.request.use((config) => {
  const token = localStorage.getItem("ai_erp_token");
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

export type OnboardingPayload = {
  machines: Array<{
    name: string;
    speed_bpm: number;
    current_mould_size?: string | null;
    current_bottom_size?: string | null;
    can_swap_moulds: boolean;
  }>;
  raw_materials: Array<{
    name?: string | null;
    type: "Paper Blank" | "Bottom Roll" | "Polybag" | "Carton Box";
    size_ml?: number | null;
    gsm?: number | null;
    stock_quantity: number;
    price_per_unit: number;
    unit?: "kg" | "pieces" | null;
  }>;
  packaging_profiles: Array<{
    product_name_ml: number;
    cups_per_polybag: number;
    polybags_per_box: number;
    box_size_name?: string | null;
  }>;
  material_yields: Array<{
    material_type: "Blank" | "Bottom";
    size_ml: number;
    gsm?: number | null;
    pieces_per_kg: number;
  }>;
  costing_master: {
    paper_price_per_kg: number;
    bottom_roll_price_per_kg: number;
    polybag_price: number;
    carton_price: number;
    labour_cost_per_box: number;
    electricity_cost_per_box: number;
  };
  workers: Array<{
    name: string;
    daily_salary: number;
    shift_type?: string | null;
  }>;
  customers: Array<{
    name?: string | null;
    firm_name: string;
    contact_number?: string | null;
    pending_balance: number;
  }>;
};

export type ProfitResult = {
  product_name_ml: number;
  cups_per_box: number;
  cost_per_box: string;
  cost_per_piece: string;
  profit_per_box: string;
  profit_per_piece: string;
  profit_margin_percent: string;
};

export function completeOnboarding(payload: OnboardingPayload) {
  return api.post("/api/onboarding/complete", payload);
}

export function calculateProfit(payload: { product_name_ml: number; selling_price_per_box: number }) {
  return api.post<ProfitResult>("/api/calculator/profit", payload);
}
