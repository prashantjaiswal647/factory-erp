import axios from "axios";

export const AUTH_TOKEN_KEYS = ["ai_erp_token", "token"] as const;

export function getAuthTokenFromResponse(data: {
  access_token?: string | null;
  token?: string | null;
  jwt?: string | null;
}): string | null {
  return data.access_token?.trim() || data.token?.trim() || data.jwt?.trim() || null;
}

export function getStoredAuthToken(): string | null {
  for (const key of AUTH_TOKEN_KEYS) {
    const token = localStorage.getItem(key)?.trim();
    if (token) return token;
  }
  return null;
}

export function storeAuthToken(token: string) {
  const normalized = token.trim();
  if (!normalized) {
    throw new Error("Login response did not include an access token.");
  }
  for (const key of AUTH_TOKEN_KEYS) {
    localStorage.setItem(key, normalized);
  }
}

export function clearStoredAuthToken() {
  for (const key of AUTH_TOKEN_KEYS) {
    localStorage.removeItem(key);
  }
}

const trimTrailingSlash = (value: string) => value.replace(/\/+$/, "");

const getBaseURL = () => {
  const configuredUrl = import.meta.env.VITE_API_URL;
  if (configuredUrl) {
    let base = trimTrailingSlash(configuredUrl);
    // Normalize: strip a trailing /api suffix so that API calls which
    // already prepend /api/... do not produce /api/api/... doubling.
    if (base.toLowerCase().endsWith("/api")) {
      base = base.slice(0, -4);
    }
    return base;
  }

  if (typeof window === "undefined") return "";

  const { hostname, origin, protocol } = window.location;
  if (hostname === "localhost" || hostname === "127.0.0.1") {
    return `${protocol}//127.0.0.1:8000`;
  }

  return origin;
};

// Exported base URL — usable by any component that needs the raw base
export const API_BASE_URL = getBaseURL();

export const api = axios.create({
  baseURL: API_BASE_URL,
  timeout: 10000
});

export const superAdminApi = axios.create({
  baseURL: API_BASE_URL,
  timeout: 10000
});

export type UpgradeRequiredDetail = {
  code: "UPGRADE_REQUIRED";
  message: string;
  used: number;
  limit: number;
  plan: string;
};

// Interceptor: Har request ke sath Token bhejne ke liye (Security)
api.interceptors.request.use((config) => {
  const token = getStoredAuthToken();
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  
  if (config.url) {
    const storefrontMatch = config.url.match(/\/api\/storefront\/([^\/]+)/);
    if (storefrontMatch && storefrontMatch[1]) {
      const storeToken = storefrontMatch[1];
      const sessionToken = sessionStorage.getItem(`storefront_session_${storeToken}`);
      if (sessionToken) {
        config.headers["X-Storefront-Session"] = sessionToken;
      }
    }
  }
  return config;
});

api.interceptors.response.use(
  (response) => response,
  (error) => {
    const detail = error?.response?.data?.detail;
    const status = error?.response?.status;
    if (status === 403 && detail?.code === "UPGRADE_REQUIRED" && typeof window !== "undefined") {
      window.dispatchEvent(new CustomEvent<UpgradeRequiredDetail>("upgrade-required", { detail }));
    }
    // 401 Unauthorized: Token missing/expired. Dispatch event so AuthContext can react.
    // Do NOT throw to console — silently reject so callers can handle gracefully.
    if (status === 401 && getStoredAuthToken() && typeof window !== "undefined") {
      window.dispatchEvent(new CustomEvent("auth-unauthorized", { detail: { url: error?.config?.url } }));
    }
    return Promise.reject(error);
  }
);

superAdminApi.interceptors.request.use((config) => {
  const token = sessionStorage.getItem("munshi_super_admin_token");
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

export type WorkerCreate = {
  name: string;
  country_code?: string;
  phone?: string;
  daily_wages: number;
  duty_hours: number;
  opening_attendance?: OpeningAttendancePayload;
};

export type MachineCreate = {
  machine_type: string;
  machine_number: string;
  mould_size_ml?: number | null;
  bottom_size_mm?: number | null;
  speed_per_minute: number;
  machine_name?: string;
  default_speed?: number;
  target_output_per_shift?: number;
  raw_materials_mapped?: string[];
  is_active?: boolean;
};

export type DynamicMachineSetupPayload = {
  machine_name: string;
  default_speed: number;
  target_output_per_shift: number;
  raw_materials_mapped: string[];
  is_active?: boolean;
};

export type DynamicMachineSetupRecord = DynamicMachineSetupPayload & {
  id: number;
  factory_id: number;
};

export type MachineLimitUsage = {
  used: number;
  limit: number;
  plan: string;
  nearing_limit: boolean;
  limit_reached: boolean;
};

export type MachineOnboardingPayload = {
  machine_type: string;
  base_config: Record<string, string | number | boolean>;
  custom_fields: Record<string, string>;
};

export type MachineOnboardingRecord = MachineOnboardingPayload & {
  id: number;
  factory_id: number;
};

export type TemplateStatus = "processing" | "pending" | "approved" | "rejected";

export type MachineTemplateRecord = MachineOnboardingPayload & {
  id: number;
  creator_id: number;
  status: TemplateStatus;
  ai_confidence?: number | null;
  ai_review?: Record<string, unknown>;
};

export async function createMachineOnboarding(payload: MachineOnboardingPayload) {
  const response = await api.post<MachineOnboardingRecord>("/api/machine-onboardings", payload);
  return response.data;
}

export async function listMachineOnboardings(params?: {
  custom_field_key?: string;
  custom_field_value?: string;
}) {
  const response = await api.get<MachineOnboardingRecord[]>("/api/machine-onboardings", { params });
  return response.data;
}

export async function submitMachineTemplate(payload: MachineOnboardingPayload) {
  const response = await api.post<MachineTemplateRecord>("/api/templates/submit", payload);
  return response.data;
}

export async function listMachineTemplates() {
  const response = await api.get<MachineTemplateRecord[]>("/api/templates");
  return response.data;
}

export async function getMachineTemplate(templateId: number) {
  const response = await api.get<MachineTemplateRecord>(`/api/templates/${templateId}`);
  return response.data;
}

export async function setupDynamicMachine(payload: DynamicMachineSetupPayload) {
  const response = await api.post<DynamicMachineSetupRecord>("/api/machines/setup", payload);
  return response.data;
}

export async function listActiveMachines() {
  const response = await api.get<DynamicMachineSetupRecord[]>("/api/machines/active");
  return response.data;
}

export async function approveMachineTemplate(templateId: number) {
  const response = await api.patch<MachineTemplateRecord>(`/api/admin/templates/${templateId}/approve`);
  return response.data;
}

export type Step3MaterialsCreate = {
  raw_material_metrics: Array<{
    material_type: "Blank" | "Bottom";
    size: number;
    kg_per_sack: number;
    total_sacks: number;
    total_weight_kg: number;
  }>;
  packaging_metrics: Array<{
    cup_size_ml: number;
    kg_per_box: number;
    cups_per_box: number;
  }>;
};

export type DailyProductionCreate = {
  factory_id?: string | null;
  date: string;
  operator_id?: number | null;
  worker_id: number;
  machine_id: number;
  product_id?: number | null;
  product_size_ml?: number | null;
  variety: string;
  packaging_size?: string | null;
  packaging_size_name: string;
  pieces_per_packet: number;
  packets_per_box_limit: number;
  shift: "Day" | "Night" | "Custom";
  total_boxes_made: number;
  loose_packets_made: number;
  blank_used_bori: number;
  bottom_used_rolls: number;
  wastage_kg: number;
  remarks?: string | null;
};

export type ProductionAlertsResponse = {
  high_wastage_count: number;
  has_high_wastage: boolean;
  alerts: Array<{
    production_id: number;
    date: string;
    product_size_ml: number;
    variety: string;
    wastage_kg: number;
    total_raw_material_kg: number;
    production_cost: number;
  }>;
};

export type ProductionBatchCreate = {
  date: string;
  shift: string;
  machine_id: number;
  finished_good_id: number;
  product_size_ml: number;
  variety_design: string;
  packaging_size_name: string;
  carton_type: string;
  pcs_per_packet: number;
  packets_per_box: number;
  worker_rows: Array<{
    worker_id: number;
    boxes_made: number;
    loose_packets_made: number;
    blank_used_bora: number;
    bottom_used_roll: number;
    note?: string | null;
  }>;
  shift_wastage_kg: number;
  wastage_note?: string | null;
};

export type ProductionHistoryEntry = {
  id: number;
  date: string;
  worker_id: number | null;
  worker_name: string;
  product_size_ml: number;
  product_type: string;
  packaging_size_name: string;
  quantity_boxes: number;
  loose_packets_made: number;
  blank_used_bora: number;
  blank_used_kg: number;
  blank_weight_per_bora_kg: number | null;
  bottom_used_rolls: number;
  quantity_pieces: number;
  machine_id: number;
  machine_name: string;
  shift: string | null;
  status: "ACTIVE" | "REJECTED";
  created_by: string | null;
  created_at: string | null;
  updated_at: string | null;
  rejected_by: string | null;
  rejected_at: string | null;
  rejection_reason: string | null;
};

export type ProductionWorkerSummary = {
  date: string;
  total_quantity: number;
  workers: Array<{
    worker_id: number | null;
    worker_name: string;
    total_quantity: number;
    products: Array<{
      production_id: number;
      product_size_ml: number;
      product_type: string;
      quantity: number;
      packaging_size_name: string;
    }>;
  }>;
};

export type AiDashboardInsights = {
  stats: {
    total_sales_last_7_days: string;
    total_collection_last_7_days: string;
    current_total_market_outstanding: string;
    average_wastage_percent_last_7_days: string;
    raw_material_low_stock_alerts: number;
  };
  insights: string;
  source: string;
};

export type BillingStatus = {
  subscription_status: "trial_active" | "trial_expired" | "active" | "expired" | "cancelled" | "payment_pending" | "trial";
  trial_start_date?: string | null;
  trial_end_date?: string | null;
  trial_days_remaining: number;
  is_access_allowed: boolean;
  access_allowed?: boolean;
  is_owner: boolean;
  active_plan?: string | null;
  plan_name?: string | null;
  plan_expires_at?: string | null;
  billing_cycle?: "monthly" | "yearly" | null;
  subscription_start_date?: string | null;
  subscription_end_date?: string | null;
  payment_status?: string | null;
  days_left?: number;
  server_time?: string;
  is_manual_override?: boolean;
  effective_plan?: string | null;
  effective_status?: string | null;
  effective_expires_at?: string | null;
};

export type DashboardSubscriptionStatus = {
  access_allowed: boolean;
  alert_state: "none" | "warning" | "critical" | "expired";
  should_warn: boolean;
  is_expired: boolean;
  days_left: number;
  plan_name: string;
  subscription_status?: string | null;
  payment_status?: string | null;
  subscription_start?: string | null;
  subscription_end?: string | null;
  server_time: string;
  role: string;
};

export type BillingHistoryItem = {
  id: number;
  plan_code: string;
  billing_cycle: string;
  amount_paise: number;
  currency: string;
  payment_status: string;
  provider?: string | null;
  provider_payment_id?: string | null;
  subscription_start_date: string;
  subscription_end_date: string;
  created_at: string;
};

export type PricingPlan = {
  code: string;
  name: string;
  machine_limit_label: string;
  monthly_label: string;
  yearly_label?: string | null;
  features: string[];
  price: {
    monthly: number;
    yearly_original?: number | null;
    yearly_discounted?: number | null;
    starts_from?: number | null;
  };
  is_custom: boolean;
};

export type StaffRoleCreate = "sub_owner" | "supervisor" | "worker";

export type StaffCreate = {
  full_name: string;
  country_code?: string;
  phone_number: string;
  password: string;
  role: StaffRoleCreate;
};

export type OpeningAttendancePayload = {
  period_start: string;
  period_end: string;
  present_days: number;
  half_days: number;
  absent_days: number;
  paid_leave_days: number;
  overtime_hours: number;
  advance_paid: number;
  deductions: number;
  notes?: string;
};

export type OpeningAttendanceResponse = {
  id: number;
  worker_id: number;
  period_start: string;
  period_end: string;
  present_days: number;
  half_days: number;
  absent_days: number;
  paid_leave_days: number;
  overtime_hours: number;
  advance_paid: number;
  deductions: number;
  notes?: string | null;
  created_at?: string;
};

export type StaffMember = {
  id: number;
  user_id?: string | null;
  full_name?: string | null;
  phone_number?: string | null;
  role: "Owner" | "Sub-Owner" | "Supervisor" | "Operator";
  is_active?: boolean;
  factory_id?: number | null;
  last_login_at?: string | null;
  opening_attendance?: OpeningAttendanceResponse | null;
  worker_id?: number | null;
};

export type FactoryExpenseCreate = {
  expense_name: string;
  amount: number;
  category?: string;
};

export type FactoryExpense = {
  id: number;
  factory_id: number;
  expense_name: string;
  amount: string;
  category: string;
  timestamp: string;
};

export type RazorpayOrder = {
  key_id: string;
  order_id: string;
  amount: number;
  currency: string;
  plan_code: string;
  billing_cycle: "monthly" | "yearly";
  cashfree_mode?: string;
  payment_session_id?: string;
};

export type ExpiringSoonSubscription = BillingStatus;

export type TelegramIntegration = {
  telegram_bot_token?: string | null;
  is_configured: boolean;
};

export type DailySaleCreate = {
  date: string;
  customer_id: number;
  amount_paid: number;
  legal_invoice_type: "tax_invoice" | "bill_of_supply" | "BILL_OF_SUPPLY_SIMPLE" | "bill_of_supply_simple";
  legal_invoice_number?: string | null;
  rough_bill_enabled: boolean;
  rough_bill_number?: string | null;
  // B2B Tax Invoice optional fields
  buyer_gstin?: string | null;
  transport_mode?: string | null;
  vehicle_number?: string | null;
  state_code?: string | null;
  place_of_supply?: string | null;
  items: Array<{
    product_id?: number | null;
    product_size_ml: number;
    variety: string;
    packaging_size?: string | null;
    packaging_size_name: string;
    boxes_sold: number;
    loose_packets_sold?: number;
    rate_per_box: number;
    rate_per_packet: number;
    packets_per_box: number;
    description?: string | null;
    // Tax Invoice optional item fields
    hsn_code?: string | null;
    tax_rate?: number | null;
  }>;
};

export type DailySaleResponse = {
  order_id?: number;
  sale_ids: number[];
  customer_id: number;
  bill_total: string;
  amount_paid: string;
  customer_total_due: string;
  invoice_document_id?: number | null;
  status?: string;
};

export type InvoicePaymentSummary = {
  payment_date: string;
  amount_paid: string;
  payment_mode: string;
};

export type InvoiceDocumentSummary = {
  id: number;
  invoice_number: string;
  invoice_date: string;
  customer_id?: number | null;
  customer_name: string;
  customer_phone?: string | null;
  customer_email?: string | null;
  payment_method: string;
  bill_total: string;
  amount_paid: string;
  customer_total_due: string;
  status: string;
  pdf_generated_count: number;
  created_at: string;
  payments?: InvoicePaymentSummary[];
  payment_collections?: InvoicePaymentSummary[];
};

export type InvoiceDeliveryHistoryItem = {
  id: number;
  channel: "DOWNLOAD" | "REPRINT" | "TELEGRAM" | "EMAIL";
  destination_masked?: string | null;
  status: "SENT" | "FAILED" | "COMPLETED";
  error_message?: string | null;
  created_at: string;
};

export type InvoiceDashboardResponse = {
  total_invoices: number;
  total_billed: string;
  total_paid: string;
  total_due: string;
  invoices: InvoiceDocumentSummary[];
};

export type FinalStockOption = {
  id: number;
  product_size_ml: number;
  variety: string;
  packaging_size?: string | null;
  pieces_per_packet?: number | null;
  packets_per_box?: number | null;
  packaging_size_name: string;
  carton_type?: string | null;
  current_quantity: number;
  total_boxes: number;
  loose_packets: number;
  packets_per_box_limit: number;
};

export type FinalProductOpeningStockCreate = {
  product_id?: number | null;
  product_size_ml?: number | null;
  variety?: string;
  packaging_size?: string | null;
  packaging_size_name?: string | null;
  initial_quantity?: number;
  current_quantity?: number | null;
  total_boxes?: number | null;
  loose_packets?: number;
  pieces_per_packet?: number;
  packets_per_box?: number | null;
  packets_per_box_limit?: number | null;
  category?: string | null;
  factory_id?: string;
};

export type FinishedGoodVariantCreate = {
  product_size_ml: number;
  variety?: string;
  packaging_size_name: string;
  pieces_per_packet: number;
  packets_per_box_limit: number;
  opening_stock_boxes?: number;
  opening_stock_loose_packets?: number;
};

export type FinishedGoodVariantResponse = {
  id: number;
  factory_id: number;
  product_size_ml: number;
  variety: string;
  packaging_size_name: string;
  pieces_per_packet: number;
  packets_per_box_limit: number;
  current_quantity: number;
  total_boxes: number;
  loose_packets: number;
  created_existing: boolean;
  status?: string;
  message?: string;
  variant_id?: number;
};

export type FinishedGoodVariantDuplicateError = {
  message: string;
  existing_product_id: number;
  existing: {
    id: number;
    product_size_ml: number;
    variety: string;
    packaging_size_name: string;
    pieces_per_packet: number;
    packets_per_box_limit: number;
    current_quantity: number;
  };
};

export type LiveStockRow = {
  id: number | string;
  factory_id?: number;
  product_id?: number | null;
  product_size_ml?: number | null;
  variety?: string | null;
  stock_type: "Blank" | "Bottom" | "Box" | "Carton Box" | "Polybag" | "Inventory" | "Final Product";
  item_name: string;
  bucket?: string | null;
  category?: string | null;
  packaging_size?: string | null;
  packaging_size_name?: string | null;
  pieces_per_packet?: number | null;
  packets_per_box?: number | null;
  packets_per_box_limit?: number | null;
  current_quantity?: number | null;
  total_boxes?: number | null;
  loose_packets?: number | null;
  quantity: number;
  unit: string;
  price_per_unit?: number | null;
  price_per_box?: number | null;
  price_per_kg?: number | null;
  box_type?: string | null;
  size_ml?: number | null;
  size_mm?: number | null;
  kg_per_sack?: number | null;
  total_weight_kg?: number | null;
  total_rolls?: number | null;
  total_boras?: number | null;
  weight_per_bora_kg?: number | null;
  cup_size_ml?: number | null;
  image_url?: string | null;
  variant_name?: string | null;
};

export type BottomStockCreate = {
  bottom_size_mm: number;
  bag_weight_kg?: number | null;
  rolls_per_bag?: number | null;
  total_bags?: number | null;
  total_rolls?: number | null;
  total_weight_kg?: number | null;
};

export type BlankStockCreate = {
  material_name: string;
  size_ml: number;
  kg_per_sack: number | null;
  total_sacks: number;
};

export type BoxPackagingStockCreate = {
  box_type: string;
  box_quantity: number;
  price_per_box: number;
};

export type PlasticStockCreate = {
  plastic_size_name: string;
  cup_size_ml: number;
  total_boras: number;
  weight_per_bora_kg: number;
  price_per_kg: number;
};

export type CustomerBalance = {
  customer_id: number;
  customer_name: string;
  previous_due: number;
  total_due: number;
};

export type OnboardingOverview = {
  workers: Array<{
    id: number;
    name: string;
    daily_wages: string;
    duty_hours: number;
    previous_attendance?: number;
  }>;
  machines: Array<{
    id: number;
    machine_type: string;
    machine_number: string | null;
    mould_size_ml: number | null;
    bottom_size_mm: number | null;
    speed_per_minute: number;
    machine_name?: string | null;
    default_speed?: number;
    target_output_per_shift?: number;
    raw_materials_mapped?: string[];
    is_active?: boolean;
  }>;
  raw_material_metrics: Array<{
    id: number;
    material_type: "Blank" | "Bottom";
    size_ml_or_mm: number;
    weight_per_sack_kg: string;
    pieces_per_sack: number;
  }>;
  packaging_metrics: Array<{
    id: number;
    cup_size_ml: number;
    kg_per_box: string;
    cups_per_box: number;
  }>;
};

export type DashboardWorker = OnboardingOverview["workers"][number] & {
  phone?: string | null;
  shift_timing?: string | null;
  shift_type?: string | null;
};

export type DashboardMachine = OnboardingOverview["machines"][number];

export type DashboardMaterials = {
  raw_material_metrics: OnboardingOverview["raw_material_metrics"];
  packaging_metrics: OnboardingOverview["packaging_metrics"];
};

export type DashboardCustomer = {
  id: number;
  name: string;
  phone: string | null;
  total_due: string;
};

export type CustomerCreate = {
  name: string;
  company_name: string;
  phone_number: string;
  email?: string | null;
  place: string;
  gst_number?: string | null;
  previous_due: number;
  total_due: number;
  opening_balance?: number;
  legacy_dues?: number;
  opening_outstanding?: number;
  opening_outstanding_note?: string | null;
  opening_outstanding_date?: string | null;
  advance_balance?: number;
  advance_balance_note?: string | null;
  advance_balance_date?: string | null;
};

export type CustomerSearchResult = {
  id: number;
  name: string;
  company_name?: string | null;
  place: string;
  phone_number: string;
  email?: string | null;
  gst_number?: string | null;
  previous_due?: number;
  opening_outstanding?: number;
  current_outstanding?: number;
  opening_outstanding_remaining?: number;
  invoice_outstanding_remaining?: number;
  manual_adjustment_remaining?: number;
  opening_outstanding_note?: string | null;
  opening_outstanding_date?: string | null;
  advance_balance?: number;
  advance_balance_note?: string | null;
  advance_balance_date?: string | null;
};

export type BillCustomerOption = {
  id: number;
  name: string;
  phone_number: string;
  place: string;
  telegram_id?: string | null;
};

export type BillOrderOption = {
  id: number;
  order_date: string;
  status: string;
  total_amount: string;
  payment_method: string;
};

export type BillNotificationResponse = {
  message: string;
  order_id: number;
  customer_id: number;
  owner_channel: string;
  customer_channel: string;
  bill_summary: string;
};

export type PendingSaleItem = {
  product_size_ml?: number | null;
  variety?: string | null;
  packaging_size_name?: string | null;
  boxes_sold: number;
  loose_packets_sold: number;
  rate_per_box: string;
  rate_per_packet: string;
};

export type PendingSale = {
  order_id: number;
  customer_id: number;
  customer_name: string;
  customer_phone: string;
  total_amount: string;
  status: string;
  order_date: string;
  items: PendingSaleItem[];
};

export type OutstandingCustomer = {
  id?: number | string;
  customer_id: number;
  customer_name: string;
  customer_phone: string;
  place?: string;
  total_bill_amount: string;
  total_paid: string;
  current_pending_balance: string;
  opening_outstanding?: number;
  advance_balance?: number;
  last_reminded_at?: string | null;
  bills?: OutstandingBill[];
};

export type BillPaymentLog = {
  id: number;
  amount_allocated: string;
  payment_date: string;
  received_by_name?: string | null;
  received_by_role?: string | null;
};

export type OutstandingBill = {
  bill_id?: number | null;
  order_id?: number | null;
  order_date: string;
  bill_amount: string;
  amount_paid: string;
  remaining_balance: string;
  status: string;
  source_type?: "opening_outstanding" | "invoice" | "manual_adjustment" | string;
  source_label?: string;
  stock_impact?: boolean;
  note?: string | null;
  payments?: BillPaymentLog[];
};

export type OutstandingResponse = {
  grand_total_outstanding: string;
  source_totals?: {
    opening_outstanding: string;
    invoice: string;
    manual_adjustment: string;
  };
  customers: OutstandingCustomer[];
};

export type PendingDue = {
  customer_name: string;
  customer_phone: string;
  invoice_id: number;
  date: string;
  total_amount: string;
  pending_amount: string;
  payment_status: "Paid" | "Half-Paid" | "Unpaid" | string;
};

export type PaymentReminderTriggerResponse = {
  message: string;
  reminders_pushed: number;
  webhook_url: string;
};

export type PaymentCreate = {
  customer_phone?: string;
  customer_id?: number;
  amount_paid: number;
  payment_mode: "Cash" | "UPI" | "Bank Transfer";
  date?: string;
  sale_id?: number;
  save_extra_as_advance?: boolean;
};

export type AttendanceSummaryRow = {
  worker_id: number;
  worker_name: string;
  phone?: string | null;
  daily_wage_rate: string;
  previous_attendance?: number;
  duty_days: string;
  uncleared_advance: string;
  net_current_balance: string;
};

export type AttendanceSummaryResponse = {
  month: string;
  workers: AttendanceSummaryRow[];
};

export type WorkerProfile = {
  id: number;
  name: string;
  phone?: string | null;
  daily_wage_rate?: number | null;
  daily_wages?: number | null;
  duty_hours?: number | null;
  previous_attendance?: number;
  previous_attendance_count?: number;
  opening_attendance_count?: number;
  shift_timing?: string | null;
  shift_type?: string | null;
  is_active: boolean;
};

export type WorkerUpdatePayload = {
  name?: string;
  phone_number?: string;
  daily_wage_rate?: number;
  daily_wages?: number;
  duty_hours?: number;
  previous_attendance?: number;
  previous_attendance_count?: number;
  opening_attendance_count?: number;
  shift_timing?: string | null;
  shift_type?: string | null;
};

export type WorkerLedgerDay = {
  date: string;
  attendance_id?: number | null;
  status: "Present" | "Absent" | "Weekly Off" | "Paid Holiday" | "Paid Leave" | "Half Day";
  production_qty?: string | null;
  duty_amount: string;
  advance_amount: string;
};

export type WorkerLedgerResponse = {
  worker_id: number;
  worker_name: string;
  month: string;
  days: WorkerLedgerDay[];
  opening_attendance?: OpeningAttendanceResponse | null;
};

export type SettlementRequest = {
  worker_id: number;
  duty_from_date: string;
  duty_to_date: string;
  advance_cutoff_date: string;
  confirm: boolean;
};

export type SettlementResponse = {
  worker_id: number;
  total_duty_amount: string;
  total_advance_deducted: string;
  net_payable: string;
  settlement_id?: number | null;
  attendance_count: number;
  advance_count: number;
};

export function createWorker(payload: WorkerCreate) {
  return api.post("/api/onboarding/step1/workers", payload);
}

export function createMachines(machines: MachineCreate[]) {
  return api.post("/api/onboarding/step2/machines", {
    machines: machines.map((machine) => ({
      machine_sequence_number: machine.machine_number,
      name: machine.machine_name || machine.machine_type || machine.machine_number,
      cup_size_ml: machine.mould_size_ml || 1,
      bottom_size_mm: machine.bottom_size_mm || 1,
      speed_cups_per_minute: machine.speed_per_minute,
      can_swap_moulds: false
    }))
  });
}

export function getMachineLimits() {
  return api.get<MachineLimitUsage>("/api/onboarding/machines/limits");
}

export function saveMaterialMetrics(payload: Step3MaterialsCreate) {
  return api.post("/api/onboarding/step3/materials", payload);
}

export function createDailyProduction(payload: DailyProductionCreate) {
  return api.post("/api/production/daily", payload);
}

export function getProductionAlerts() {
  return api.get<ProductionAlertsResponse>("/api/production/alerts");
}

export function getAiDashboardInsights() {
  return api.get<AiDashboardInsights>("/api/dashboard/ai-insights");
}

export type DashboardSummary = {
  total_sales_last_7_days: number | string;
  total_collection_last_7_days: number | string;
  current_total_market_outstanding: number | string;
  average_wastage_percent_last_7_days: number | string;
  raw_material_low_stock_alerts: number;
  today_day_wastage_kg?: number;
  today_night_wastage_kg?: number;
  today_total_wastage_kg?: number;
  attendance_breakdown?: Record<string, number>;
};

export function getDashboardSummary() {
  return api.get<DashboardSummary>("/api/dashboard/summary");
}

export type FinancialBIStatsRow = {
  day: string;
  Sales: number;
  Collection: number;
  Expense: number;
};

export type CostBreakdownRow = {
  name: string;
  value: number;
  color: string;
};

export type WastageBIRow = {
  machine: string;
  wastage: number;
};

export type AnalyticsBIResponse = {
  financial_data: FinancialBIStatsRow[];
  cost_breakdown: CostBreakdownRow[];
  wastage_data: WastageBIRow[];
};

export function getDashboardAnalytics() {
  return api.get<AnalyticsBIResponse>("/api/dashboard/analytics");
}

export function createDailySale(payload: DailySaleCreate) {
  return api.post<DailySaleResponse>("/api/sales/invoice", payload);
}

export function getNextInvoiceNumber(invoiceType?: string) {
  const params = invoiceType ? `?invoice_type=${encodeURIComponent(invoiceType)}` : "";
  return api.get<{ invoice_number: string }>(`/api/sales/next-invoice-number${params}`);
}

export function getInvoiceDocuments() {
  return api.get<InvoiceDashboardResponse>("/api/sales/invoices");
}

export function downloadInvoicePdf(invoiceId: number, inline?: boolean) {
  return api.get<Blob>(`/api/sales/invoices/${invoiceId}/pdf`, { 
    responseType: "blob", 
    params: inline ? { inline: true } : undefined 
  });
}

export function createDailyProductionBatch(payload: ProductionBatchCreate) {
  return api.post("/api/production/daily-batch", payload);
}

export function deleteInvoice(
  invoiceId: number,
  confirmation: string,
  action?: "reverse" | "archive" | "cancel",
) {
  return api.delete<{ status: string; invoice_id: number; invoice_number: string }>(
    `/api/sales/invoices/${invoiceId}`,
    { data: { confirmation, action } },
  );
}

export function hardDeleteInvoice(
  invoiceId: number,
  payload: {
    reason: string;
    confirm_invoice_number: string;
    confirm_test_invoice: boolean;
    reverse_payments: boolean;
  }
) {
  return api.delete<{ status: string; invoice_id: number; invoice_number: string }>(
    `/api/sales/invoices/${invoiceId}/hard-delete`,
    { data: payload }
  );
}

export function downloadMonthlyInvoices(
  month: number,
  year: number,
  type: "all" | "tax_invoice" | "bill_of_supply" | "simple_bill_of_supply",
) {
  return api.get<Blob>("/api/sales/invoices/bulk-download", {
    responseType: "blob",
    params: { month, year, type },
  });
}

export function reprintInvoice(invoiceId: number) {
  return api.post(`/api/invoices/${invoiceId}/reprint`);
}

export function sendInvoiceTelegram(invoiceId: number, destination: "owner" | "customer" = "owner") {
  return api.post(`/api/invoices/${invoiceId}/telegram`, { destination });
}

export function sendInvoiceEmail(invoiceId: number, email: string) {
  return api.post(`/api/invoices/${invoiceId}/email`, { email });
}

export function getInvoiceDeliveryHistory(invoiceId: number) {
  return api.get<InvoiceDeliveryHistoryItem[]>(`/api/invoices/${invoiceId}/history`);
}

export function createPendingSaleOrder(payload: DailySaleCreate) {
  return api.post<DailySaleResponse>("/api/sales/order", payload);
}

export function createSalesCustomer(payload: CustomerCreate) {
  return api.post("/api/sales/customers", payload);
}

export function generateCustomerPortalLink(customerId: number) {
  return api.post<{
    customer_id: number;
    portal_access_token: string;
    storefront_url: string;
    is_portal_approved: boolean;
  }>(`/api/automation/customers/${customerId}/portal-link`);
}

export function searchCustomers(q: string) {
  return api.get<CustomerSearchResult[]>("/api/customers/search", { params: { q } });
}

export type CustomerUpdate = {
  email?: string | null;
  name?: string;
  phone_number?: string;
  place?: string;
  gst_number?: string;
  company_name?: string;
  previous_due?: number;
  opening_outstanding?: number;
  opening_outstanding_note?: string | null;
  opening_outstanding_date?: string | null;
  advance_balance?: number;
  advance_balance_note?: string | null;
  advance_balance_date?: string | null;
};

export function updateSalesCustomer(customerId: number, payload: CustomerUpdate) {
  return api.patch<CustomerSearchResult>(`/api/sales/customers/${customerId}`, payload);
}

export function getBillCustomers() {
  return api.get<BillCustomerOption[]>("/api/sales/bill-customers");
}

export function getCustomerOrders(customerId: number) {
  return api.get<BillOrderOption[]>(`/api/sales/customers/${customerId}/orders`);
}

export function sendBillNotification(payload: { order_id: number; customer_id: number }) {
  return api.post<BillNotificationResponse>("/api/sales/send-bill-notification", payload);
}

export function getPendingSales() {
  return api.get<PendingSale[]>("/api/sales/pending");
}

export function approveSalesOrder(orderId: number) {
  return api.post<{ message: string; order_id: number; status: string }>(`/api/sales/order/${orderId}/approve`);
}

export function rejectSalesOrder(orderId: number) {
  return api.post<{ message: string; order_id: number; status: string }>(`/api/sales/order/${orderId}/reject`);
}

export function getInventory() {
  return api.get<LiveStockRow[]>("/api/inventory/");
}

export function getFinalStockOptions(
  search?: string,
  productionReadyOnly = false,
  filters?: { machineId?: number; productSizeMl?: number; variety?: string },
) {
  return api.get<FinalStockOption[]>("/api/inventory/final-stock", {
    params: {
      ...(search && search.trim() ? { search: search.trim() } : {}),
      ...(productionReadyOnly ? { production_ready_only: true } : {}),
      ...(filters?.machineId ? { machine_id: filters.machineId } : {}),
      ...(filters?.productSizeMl ? { product_size_ml: filters.productSizeMl } : {}),
      ...(filters?.variety?.trim() ? { variety: filters.variety.trim() } : {}),
    },
  });
}

export function saveFinalProductOpeningStock(payload: FinalProductOpeningStockCreate) {
  return api.post<FinalStockOption>("/api/onboarding/final-stock", payload);
}

export function createFinishedGoodVariant(payload: FinishedGoodVariantCreate) {
  return api.post<FinishedGoodVariantResponse>(
    "/api/inventory/finished-goods/variants",
    payload
  );
}

export function exportFinishedGoodsSnapshot(
  date?: string,
  format: "xlsx" | "csv" = "xlsx"
) {
  return api.get("/api/inventory/finished-goods/export", {
    params: { date, format },
    responseType: "blob",
  });
}

export function getCustomerBalance(customerId: number) {
  return api.get<CustomerBalance>(`/api/sales/customers/${customerId}/balance`);
}

export function getOutstandingDues() {
  return api.get<OutstandingResponse>("/api/sales/outstanding");
}

export function getPendingPaymentDues() {
  return api.get<PendingDue[]>("/api/sales/dues/pending");
}

export function triggerPaymentReminders() {
  return api.post<PaymentReminderTriggerResponse>("/api/automation/trigger-payment-reminders");
}

export function recordPayment(payload: PaymentCreate) {
  return api.post("/api/accounts/payments", payload);
}

export function clearOutstandingBill(billId: number, reason?: string) {
  return api.delete(`/api/sales/outstanding/${billId}`, { params: { confirm: true, reason } });
}

export function sendOutstandingReminder(customerId: number) {
  return api.post(`/api/accounts/reminders/${customerId}`);
}

export type CustomerLedgerAdjustmentCreate = {
  adjustment_type: "add_balance" | "reduce_balance";
  amount: number;
  reason: string;
};

export type CustomerLedgerAdjustmentResponse = {
  adjustment_id: number;
  previous_outstanding: string;
  adjustment_amount: string;
  new_outstanding: string;
  adjustment_type: "add_balance" | "reduce_balance";
  reason: string;
};

export function createCustomerLedgerAdjustment(customerId: number, payload: CustomerLedgerAdjustmentCreate) {
  return api.post<CustomerLedgerAdjustmentResponse>(
    `/api/sales/customers/${customerId}/ledger-adjustments`,
    payload,
  );
}

// ---------------------------------------------------------------------------
// Collection War Room (P4.5 D2)
// ---------------------------------------------------------------------------

export interface CollectionWarRoomAgingBucket {
  "0_7_days": number;
  "8_15_days": number;
  "16_30_days": number;
  "31_60_days": number;
  "60_plus_days": number;
}

export interface CollectionWarRoomTopCustomer {
  customer_id: number;
  customer_name: string;
  total_due: number;
  days_old: number;
}

export interface CollectionWarRoomDueTrendPoint {
  date: string;
  outstanding: number;
}

export interface CollectionWarRoomResponse {
  total_outstanding: number;
  overdue_amount: number;
  top_customers: CollectionWarRoomTopCustomer[];
  aging_buckets: CollectionWarRoomAgingBucket;
  high_risk_customers: number;
  due_trend: CollectionWarRoomDueTrendPoint[];
  total_due_customers?: number;
  source_totals?: {
    opening_outstanding: number;
    invoice: number;
    manual_adjustment: number;
  };
  customer_advances?: number;
  verification_items?: Array<{
    source_type: string;
    source_id: number;
    customer_name: string;
    original_due: number;
    total_collected: number;
    remaining: number;
    collected_by: string;
    payment_dates: string[];
    status: string;
  }>;
}

export type CustomerLedgerEntry = {
  date_time: string;
  type: string;
  debit: string;
  credit: string;
  amount: string;
  running_balance: string;
  source: string;
  created_by?: string | null;
  notes?: string | null;
  stock_impact: boolean;
};

export function getCustomerLedger(customerId: number) {
  return api.get<{ customer_id: number; customer_name: string; current_balance: string; entries: CustomerLedgerEntry[] }>(
    `/api/sales/customers/${customerId}/ledger`,
  );
}

export function updateOpeningOutstanding(customerId: number, openingId: number, newAmount: number, reason: string) {
  return api.patch(`/api/sales/customers/${customerId}/opening-outstanding/${openingId}`, {
    new_amount: newAmount,
    reason,
  });
}

export function deleteOpeningOutstanding(customerId: number, openingId: number, reason: string) {
  return api.delete(`/api/sales/customers/${customerId}/opening-outstanding/${openingId}`, {
    params: { reason },
  });
}

export function getCollectionWarRoom() {
  return api.get<CollectionWarRoomResponse>("/api/dashboard/collection-war-room");
}

export function sendCollectionWarRoomTelegramAlert() {
  return api.post<{ status: string; message?: string }>(
    "/api/dashboard/collection-war-room/telegram-alert"
  );
}

// Collection War Room action helpers
export function getRecoverySuggestions() {
  return api.get<{ suggestions: string[] }>("/api/dashboard/collection-war-room/suggestions");
}

export function copyReminder(customerId: number) {
  return api.post<{ message: string }>(
    `/api/dashboard/collection-war-room/actions/copy-reminder/${customerId}`
  );
}

export function markDone(customerId: number) {
  return api.post<{ message: string }>(
    `/api/dashboard/collection-war-room/actions/mark-done/${customerId}`
  );
}

export function confirmWarRoomPaid(sourceType: string, sourceId: number) {
  return api.post(`/api/dashboard/collection-war-room/${sourceType}/${sourceId}/confirm-paid`);
}

export function uploadInvoiceSignature(file: File) {
  const data = new FormData();
  data.append("file", file);
  return api.post<{ digital_signature_url: string }>("/api/onboarding/factory-profile/signature", data);
}

export function removeInvoiceSignature() {
  return api.delete("/api/onboarding/factory-profile/signature");
}

export function snoozeCustomer(customerId: number, days = 3) {
  return api.post<{ message: string }>(
    `/api/dashboard/collection-war-room/actions/snooze/${customerId}`,
    { days }
  );
}

export function getAttendanceSummary(month: string) {
  return api.get<AttendanceSummaryResponse>("/api/workers/attendance/summary", { params: { month } });
}

export function getWorkerLedger(workerId: number, month: string) {
  return api.get<WorkerLedgerResponse>(`/api/workers/${workerId}/attendance-ledger`, { params: { month } });
}

export function updateWorkerProfile(workerId: number, payload: WorkerUpdatePayload) {
  return api.put<WorkerProfile>(`/api/workers/${workerId}`, payload);
}

export function upsertWorkerAttendance(workerId: number, payload: { date: string; status: WorkerLedgerDay["status"]; production_qty?: number | null }) {
  return api.post<WorkerLedgerDay>(`/api/workers/${workerId}/attendance`, payload);
}

export function markAllActiveWorkersWeeklyOff(date: string) {
  return api.post<{ date: string; status: string; workers_updated: number }>(
    "/api/workers/attendance/weekly-off/all",
    { date },
  );
}

export function addWorkerAdvance(workerId: number, payload: { date: string; amount: number }) {
  return api.post(`/api/workers/${workerId}/advance`, payload);
}

export function settleWorkerHisab(payload: SettlementRequest) {
  return api.post<SettlementResponse>("/api/workers/settle", payload);
}

export function getPaymentDues() {
  return api.get<OutstandingResponse>("/api/sales/outstanding");
}

export function addPayment(payload: PaymentCreate) {
  return api.post("/api/payments/add", payload);
}

export function createBottomStock(payload: BottomStockCreate) {
  return api.post("/api/onboarding/raw-material/bottom", payload);
}

export function createBlankStock(payload: BlankStockCreate) {
  return api.post("/api/onboarding/raw-material/blank", payload);
}

export function createBoxPackagingStock(payload: BoxPackagingStockCreate) {
  return api.post("/api/onboarding/raw-material/box", {
    box_type: payload.box_type,
    quantity: payload.box_quantity,
    price_per_box: payload.price_per_box
  });
}

export function createPlasticStock(payload: PlasticStockCreate) {
  return api.post("/api/onboarding/raw-material/plastic", payload);
}

export function getOnboardingOverview() {
  return api.get<OnboardingOverview>("/api/onboarding/overview");
}

export type FactoryProfile = {
  id: number;
  factory_name: string;
  address?: string;
  gst_number?: string;
  advance_payment_discount_percentage?: number;
  invoice_prefix?: string;
  digital_signature_url?: string;
  bill_of_supply_start_seq: number;
  tax_invoice_start_seq: number;
  bill_of_supply_simple_start_seq: number;
  next_tax_invoice_number: number;
  next_bill_of_supply_number: number;
  next_bill_of_supply_simple_number: number;
};

export type FactoryProfileUpdate = {
  factory_name: string;
  address?: string;
  gst_number?: string;
  advance_payment_discount_percentage?: number;
  invoice_prefix?: string;
  digital_signature_url?: string;
  bill_of_supply_start_seq?: number;
  tax_invoice_start_seq?: number;
  bill_of_supply_simple_start_seq?: number;
};

export function getFactoryProfile() {
  return api.get<FactoryProfile>("/api/onboarding/factory-profile");
}

export function updateFactoryProfile(payload: FactoryProfileUpdate) {
  return api.post<FactoryProfile>("/api/onboarding/factory-profile", payload);
}

export type CustomerVerificationResponse = {
  status: string;
  message: string;
  customer_id?: number;
  customer_name?: string;
  storefront_session_token?: string | null;
};

export function verifyStorefrontCustomer(store_token: string, phone_number: string) {
  return api.post<CustomerVerificationResponse>("/api/store/verify-customer", {
    store_token,
    phone_number
  });
}

export function getAccountantSummary(month: number, year: number, download: boolean = false) {
  if (download) {
    return api.get(`/api/sales/invoices/accountant-summary`, {
      params: { month, year, download },
      responseType: "blob"
    });
  }
  return api.get(`/api/sales/invoices/accountant-summary`, {
    params: { month, year }
  });
}

export function getDashboardWorkers() {
  return api.get<DashboardWorker[]>("/api/onboarding/workers");
}

export function getDashboardMachines() {
  return api.get<DashboardMachine[]>("/api/onboarding/machines");
}

export function getDashboardMaterials() {
  return api.get<DashboardMaterials>("/api/onboarding/materials");
}

export type OnboardingBulkUploadType =
  | "factory_profile"
  | "worker"
  | "machine"
  | "raw_material"
  | "packaging_material";

export type OnboardingBulkUploadResponse = {
  message: string;
  overall_status?: "success" | "partial" | "failed" | "ok";
  rows_inserted: number;
  created_count?: number;
  updated_count?: number;
  unchanged_count?: number;
  archived_skipped_count?: number;
  inserted_counts?: Partial<Record<OnboardingBulkUploadType | "master_onboarding", number>>;
  operation_counts?: {
    inserted?: number;
    updated?: number;
    unchanged?: number;
    skipped?: number;
    failed?: number;
    warnings?: number;
  };
  validation_report?: {
    fatal_count: number;
    warning_count: number;
    info_count: number;
    successful_rows: number;
    total_rows_attempted: number;
    fatal_errors: BulkValidationIssue[];
    warnings: BulkValidationIssue[];
    info: BulkValidationIssue[];
  };
  failed_rows: Array<Record<string, unknown>>;
};

export type BulkValidationIssue = {
  row: number | null;
  field: string;
  error: string;
  severity: "fatal" | "warning" | "info";
  suggested_correction?: string | null;
  sheet?: string | null;
  section?: string | null;
  raw_value?: unknown;
  action_type?: "created" | "updated" | "unchanged" | "skipped" | "error" | null;
};

export function downloadMasterOnboardingTemplate() {
  return api.get<Blob>("/api/v1/onboarding/template/master", { responseType: "blob" });
}

export function uploadMasterOnboardingSheet(file: File) {
  const formData = new FormData();
  formData.append("file", file);
  return api.post<OnboardingBulkUploadResponse>("/api/v1/onboarding/bulk-upload/master", formData, {
    headers: { "Content-Type": "multipart/form-data" }
  });
}

export function getDashboardCustomers() {
  return api.get<DashboardCustomer[]>("/api/onboarding/customers");
}

export function deleteDashboardMachine(id: number) {
  return api.delete(`/api/onboarding/machine/${id}`);
}

export function updateMachine(machineId: number, payload: Partial<MachineCreate>) {
  return api.patch(`/api/setup/machines/${machineId}`, payload);
}

export function deleteDashboardWorker(id: number) {
  return api.delete(`/api/onboarding/worker/${id}`);
}

export function deleteDashboardRawMaterial(id: number) {
  return api.delete(`/api/onboarding/raw-material/${id}`);
}

export function deleteDashboardCustomer(id: number) {
  return api.delete(`/api/onboarding/customer/${id}`);
}

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

export type IdealCostRequest = {
  blank_size_ml: number;
  pieces_per_box: number;
  yield_pieces_per_kg_blank: number;
  blank_price_per_kg: number;
  bottom_price_per_kg?: number | null;
  bottom_yield_pieces_per_kg?: number | null;
  direct_bottom_cost_per_cup?: number | null;
  daily_labor_cost: number;
  expected_daily_production_pieces: number;
  packaging_box_price?: number | null;
  packaging_cost_per_piece?: number | null;
  plastic_price_per_box?: number | null;
  plastic_price_per_piece?: number | null;
  electricity_flat_cost_per_box?: number | null;
  electricity_cost_per_piece?: number | null;
  desired_profit_per_box: number;
};

export type IdealCostResponse = {
  blank_size_ml: number;
  pieces_per_box: number;
  per_piece_blank_cost: string;
  per_piece_bottom_cost: string;
  labor_cost_per_piece: string;
  total_raw_cost_per_box: string;
  packaging_box_price: string;
  plastic_price_per_box: string;
  electricity_flat_cost_per_box: string;
  final_cost_per_box: string;
  desired_profit_per_box: string;
  suggested_selling_price: string;
  profit_margin_percent: string;
  breakdown: Record<string, string>;
};

export type ActualMonthlyData = {
  month_start: string;
  production_entries: number;
  actual_boxes_made: number;
  loose_packets_made: number;
  boxes_from_loose: number;
  estimated_pieces_made: number;
  blank_used_kg: number;
  bottom_used_kg: number;
  actual_blank_kg_per_box: number;
  actual_bottom_kg_per_box: number;
  final_stock_boxes: number;
};

export type AiCompareResponse = {
  ai_insights: string;
  comparison_table_data: Array<{
    metric: string;
    ideal_value: string;
    actual_value: string;
    difference: string;
  }>;
  actual_monthly_data: ActualMonthlyData;
};

export function completeOnboarding(payload: OnboardingPayload) {
  return api.post("/api/onboarding/complete", payload);
}

export function calculateProfit(payload: { product_name_ml: number; selling_price_per_box: number }) {
  return api.post<ProfitResult>("/api/calculator/profit", payload);
}

export function calculateIdealCost(payload: IdealCostRequest) {
  return api.post<IdealCostResponse>("/api/calculator/ideal-cost", payload);
}

export function getActualMonthlyData() {
  return api.get<ActualMonthlyData>("/api/calculator/actual-monthly");
}

export function compareIdealWithActual(payload: { ideal_calculation_results: IdealCostResponse; actual_monthly_data: ActualMonthlyData }) {
  return api.post<AiCompareResponse>("/api/calculator/ai-compare", payload);
}

export function getBillingStatus(t?: number) {
  const url = t ? `/api/billing/status?t=${t}` : "/api/billing/status";
  return api.get<BillingStatus>(url);
}

export function getBillingHistory() {
  return api.get<BillingHistoryItem[]>("/api/billing/history");
}

export function getPricingPlans() {
  return api.get<PricingPlan[]>("/api/billing/plans");
}

export function getStaffMembers() {
  return api.get<StaffMember[]>("/api/v1/staff/list");
}

export function createStaffMember(payload: {
  name: string;
  phone: string;
  password: string;
  role: string;
  email?: string;
  confirm_password?: string;
  status?: string;
  notes?: string;
  opening_attendance?: OpeningAttendancePayload;
}) {
  return api.post<StaffMember>("/api/v1/staff/create", payload);
}

export function updateStaffMember(id: number, payload: {
  name?: string;
  phone?: string;
  password?: string;
  confirm_password?: string;
  role?: string;
  email?: string;
  status?: string;
  notes?: string;
}) {
  return api.put<StaffMember>(`/api/v1/staff/${id}/update`, payload);
}

export function deleteStaffMember(id: number) {
  return api.delete(`/api/v1/staff/${id}/delete`);
}

export function deleteWorker(id: number) {
  return api.delete(`/api/workers/${id}`);
}

export function getStaffOpeningAttendance(staffId: number) {
  return api.get<OpeningAttendanceResponse>(`/api/v1/staff/${staffId}/opening-attendance`);
}

export function createStaffOpeningAttendance(staffId: number, payload: OpeningAttendancePayload) {
  return api.post<OpeningAttendanceResponse>(`/api/v1/staff/${staffId}/opening-attendance`, payload);
}

export function updateStaffOpeningAttendance(staffId: number, payload: Partial<OpeningAttendancePayload>) {
  return api.patch<OpeningAttendanceResponse>(`/api/v1/staff/${staffId}/opening-attendance`, payload);
}

export function deleteStaffOpeningAttendance(staffId: number) {
  return api.delete(`/api/v1/staff/${staffId}/opening-attendance`);
}

export type OpeningAttendanceSummary = {
  period_start: string;
  period_end: string;
  payable_days: number;
  present_days: number;
  half_days: number;
  absent_days: number;
  overtime_hours: number;
  advance_paid: number;
  deductions: number;
};

export type DailyAttendanceSummary = {
  payable_days: number;
  present_days: number;
  half_days: number;
  absent_days: number;
  overtime_hours: number;
};

export type FinalPayrollSummary = {
  total_payable_days: number;
  gross_salary: number;
  overtime_pay: number;
  total_advance: number;
  total_deductions: number;
  net_payable: number;
};

export type PayrollSummaryResponse = {
  worker_id: number;
  worker_name: string;
  month: string;
  daily_wage_rate: number;
  opening_attendance?: OpeningAttendanceSummary | null;
  daily_attendance: DailyAttendanceSummary;
  final: FinalPayrollSummary;
};

export function getWorkerPayrollSummary(workerId: number, month: string) {
  return api.get<PayrollSummaryResponse>(`/api/workers/${workerId}/payroll-summary?month=${month}`);
}

export function changePassword(payload: {
  current_password?: string;
  new_password: string;
  confirm_password: string;
  user_id?: number;
}) {
  return api.patch<{ message: string }>("/api/v1/profile/change-password", payload);
}

export function requestFactoryId(payload: { phone_number: string; country_code?: string }) {
  return api.post<{ message: string; phone_number: string }>("/api/v1/security/request-factory-id", payload);
}

export function verifyFactoryId(payload: { phone_number: string; country_code?: string; otp_code: string }) {
  return api.post<string>("/api/v1/security/verify-factory-id", payload, { responseType: "text" });
}

export function getFactoryExpenses() {
  return api.get<FactoryExpense[]>("/api/expenses");
}

export function createFactoryExpense(payload: FactoryExpenseCreate) {
  return api.post<FactoryExpense>("/api/expenses", payload);
}

export function createBillingOrder(payload: { plan_code: string; billing_cycle: "monthly" | "yearly" }) {
  return api.post<RazorpayOrder>("/api/billing/create-order", payload);
}

export function startFreeTrial(payload: { plan_code?: string } = { plan_code: "basic" }) {
  return api.post<BillingStatus>("/api/billing/start-free-trial", payload);
}

export function verifyBillingPayment(payload: {
  razorpay_order_id: string;
  razorpay_payment_id: string;
  razorpay_signature: string;
  plan_code: string;
  billing_cycle: "monthly" | "yearly";
}) {
  return api.post<BillingStatus & { razorpay_payment_id: string }>("/api/billing/verify", payload);
}

export function activateSubscription(payload: {
  plan_code: string;
  billing_cycle: "monthly" | "yearly";
  provider_payment_id?: string;
  payment_status?: "paid" | "payment_pending";
}) {
  return api.post<BillingStatus>("/api/billing/activate", payload);
}

export function getExpiringSoonSubscriptions() {
  return api.get<ExpiringSoonSubscription[]>("/api/billing/expiring-soon");
}

export function submitCustomPlanEnquiry(payload: {
  owner_name: string;
  factory_name: string;
  country_code?: string;
  phone: string;
  email: string;
  number_of_machines: number;
  requirement_details: string;
}) {
  return api.post<{ id: number; message: string }>("/api/billing/custom-enquiry", payload);
}

export function submitDemoBooking(payload: {
  owner_name: string;
  factory_name?: string;
  country_code?: string;
  phone: string;
  email: string;
  preferred_plan?: string;
  message?: string;
}) {
  return api.post<{ id: number; message: string }>("/api/billing/demo-booking", payload);
}

export function getTelegramIntegration() {
  return api.get<TelegramIntegration>("/api/integrations/telegram");
}

export function saveTelegramIntegration(payload: { telegram_bot_token: string }) {
  return api.post<TelegramIntegration>("/api/integrations/telegram", payload);
}

export type TelegramConnectionStatus = {
  connected: boolean;
  role: "Owner" | "Sub-Owner";
  telegram_username?: string | null;
  telegram_first_name?: string | null;
  chat_id_verified: boolean;
  connected_at?: string | null;
  welcome_sent_at?: string | null;
  last_message_at?: string | null;
  last_message_status?: "sent" | "failed" | null;
  last_webhook_event_at?: string | null;
};

export type TelegramConnectCode = {
  code: string;
  deep_link: string;
  bot_username: string;
  expires_at: string;
};

export function createTelegramConnectLink() {
  return api.post<{ telegram_url: string; expires_at: string; status: "pending" }>(
    "/api/integrations/telegram/connect-link"
  );
}

export function createTelegramConnectCode() {
  return api.post<TelegramConnectCode>("/api/integrations/telegram/connect-code");
}

export function getTelegramConnectionStatus() {
  return api.get<TelegramConnectionStatus>("/api/integrations/telegram/status");
}export function getTelegramDiagnostics() {
  return api.get<{
    bot_token_configured: boolean;
    bot_username_configured: boolean;
    telegram_bot_username?: string | null;
    webhook_secret_configured: boolean;
    expected_webhook_url?: string;
    pending_bind_count: number;
    last_binding_success_count: number;
    last_binding_failure_count: number;
    last_binding_success_at?: string | null;
    last_binding_failure_at?: string | null;
  }>("/api/integrations/telegram/diagnostics");
}

export function registerTelegramWebhook(
  useDefault: boolean = true,
  botToken?: string,
  webhookSecret?: string
) {
  return api.post<{
    success: boolean;
    message: string;
    webhook_url: string;
  }>("/api/integrations/telegram/register-webhook", {
    use_default: useDefault,
    bot_token: botToken,
    webhook_secret: webhookSecret,
  });
}


export function sendTelegramTestMessage() {
  return api.post<{ status: string; message: string }>("/api/integrations/telegram/test-message");
}

export function disconnectTelegramIntegration() {
  return api.post<{ status: string; message: string }>("/api/integrations/telegram/disconnect");
}

export function updateUserProfile(payload: {
  full_name: string;
  country_code: string;
  phone_number: string;
  preferred_language: "en" | "hi" | "hinglish";
}) {
  return api.put<{
    id: number;
    user_id?: string | null;
    username: string;
    phone_number?: string | null;
    full_name?: string | null;
    role: string;
    factory_id: number;
    factory_name?: string | null;
    preferred_language: "en" | "hi" | "hinglish";
  }>("/api/v1/users/me/profile", payload);
}

export type UserSubscriptionResponse = {
  active_plan?: string | null;
  plan_name: string;
  plan_expires_at: string | null;
  trial_end_date?: string | null;
  subscription_end_date?: string | null;
  days_left: number;
  last_login: string | null;
  server_time: string;
  subscription_status?: string | null;
  billing_cycle?: string | null;
  payment_status?: string | null;
  is_manual_override?: boolean;
  is_trial?: boolean;
  access_allowed?: boolean;
  raw_active_plan?: string | null;
  raw_plan_name?: string | null;
  raw_subscription_end_date?: string | null;
  raw_plan_expires_at?: string | null;
  raw_trial_end_date?: string | null;
  effective_plan?: string | null;
  effective_status?: string | null;
  effective_expires_at?: string | null;
};

export async function getUserSubscription(t?: number) {
  const url = t ? `/api/v1/users/me/subscription?t=${t}` : "/api/v1/users/me/subscription";
  const response = await api.get<UserSubscriptionResponse>(url);
  return response.data;
}

export function deleteDailyProductionLog(logId: number) {
  return api.delete(`/api/production/daily/${logId}`);
}

export function getDailyProductionHistory(date?: string) {
  return api.get<ProductionHistoryEntry[]>("/api/production/daily", {
    params: date ? { date } : undefined,
  });
}

export function getProductionWorkerSummary(date: string) {
  return api.get<ProductionWorkerSummary>("/api/production/worker-summary", { params: { date } });
}

export function rejectDailyProduction(productionId: number, reason: string) {
  return api.post<ProductionHistoryEntry>(`/api/production/daily/${productionId}/reject`, { reason });
}

export function updateDailyProduction(productionId: number, payload: Partial<DailyProductionCreate>) {
  return api.patch<ProductionHistoryEntry>(`/api/production/daily/${productionId}`, payload);
}

export type MasterBackupValidation = {
  restore_id: string;
  can_restore: boolean;
  new_records: Record<string, number>;
  existing_records: Record<string, number>;
  updated_records: Record<string, number>;
  errors: Array<{ sheet: string; error: string }>;
};

export function downloadMasterBackup() {
  return api.get<Blob>("/api/backup/master", { responseType: "blob" });
}

export function validateMasterBackup(file: File) {
  const form = new FormData();
  form.append("file", file);
  return api.post<MasterBackupValidation>("/api/backup/master/validate", form);
}

export function confirmMasterRestore(restoreId: string) {
  return api.post<{ inserted: number; updated: number; skipped: number }>("/api/backup/master/restore", {
    restore_id: restoreId,
    confirmation: "RESTORE",
  });
}

export function downloadMasterBackupValidationReport(restoreId: string) {
  return api.get<Blob>(`/api/backup/master/validation-report/${restoreId}`, { responseType: "blob" });
}

export function deleteOnboardingEntry(entryId: string, type?: string) {
  const normalizedType = normalizeOnboardingDeleteType(entryId, type);
  return api.delete(`/api/onboarding/entry/${entryId}`, {
    params: normalizedType ? { type: normalizedType } : undefined
  });
}

export function deleteOnboardingItem(itemId: number, type: string) {
  const normalizedType = normalizeOnboardingDeleteType(String(itemId), type) || type;
  return api.delete(`/api/v1/onboarding/items/${itemId}`, {
    params: { type: normalizedType }
  });
}

function normalizeOnboardingDeleteType(entryId: string, type?: string) {
  const raw = String(type || "").trim().toLowerCase();
  const id = String(entryId || "").toLowerCase();
  if (id.startsWith("blank-") || raw.includes("blank")) return "blankstock";
  if (id.startsWith("bottom-") || raw.includes("bottom")) return "bottomstock";
  if (id.startsWith("box-") || raw.includes("box") || raw.includes("carton") || raw.includes("packaging")) return "boxstock";
  if (id.startsWith("plastic-") || raw.includes("plastic")) return "plasticstock";
  if (id.startsWith("polybag-") || raw.includes("polybag")) return "polybagstock";
  if (id.startsWith("final-") || raw.includes("final") || raw.includes("cup")) return "final";
  return type;
}

export type ActivityLog = {
  id: number;
  factory_id: number;
  event_type: "production" | "attendance" | "expense" | "payment" | "machine_telemetry";
  description: string;
  log_date?: string | null;
  created_at: string;
  created_time?: string | null;
  user_role?: string | null;
  action_type?: string | null;
};

export function getOperationsSequence(dateString?: string) {
  const url = dateString ? `/api/operations/sequence?date=${dateString}` : "/api/operations/sequence";
  return api.get<ActivityLog[]>(url);
}

export function createManualActivityLog(payload: { event_type: string; description: string }) {
  return api.post<ActivityLog>("/api/operations/sequence", payload);
}

export function updateActivityLog(logId: number, payload: { event_type: string; description: string }) {
  return api.put<ActivityLog>(`/api/operations/sequence/${logId}`, payload);
}

export function deleteActivityLog(logId: number) {
  return api.delete(`/api/operations/sequence/${logId}`);
}

export function reportMachineBreakdown(payload: { machine_id: number; issue_category: string; custom_notes?: string }) {
  return api.post<ActivityLog>("/api/operations/breakdown", payload);
}

export type FinishedGoodsOnboardPayload = {
  product_size_ml: number;
  variety_design: string;
  packaging_size_name?: string;
  pcs_per_packet: number;
  packets_per_box: number;
  initial_quantity_boxes: number;
};

export async function onboardFinishedGoods(payload: FinishedGoodsOnboardPayload) {
  const response = await api.post<FinalStockOption>("/api/inventory/finished-goods/onboard", payload);
  return response.data;
}

export type DailySequenceLogItem = {
  id: number;
  time: string;
  action_type: string;
  action_summary: string;
  entity_type: string;
  entity_id: number | null;
  user_name: string;
  user_role: string;
  relative_day: string;
};

export type DailySequenceGroup = {
  date: string;
  logs: DailySequenceLogItem[];
};

export async function getDailySequenceLogs(date?: string) {
  const response = await api.get<DailySequenceLogItem[]>("/api/daily-sequence", {
    params: date ? { date } : undefined,
  });
  return response.data;
}

export async function uploadCustomersSeed(file: File) {
  const formData = new FormData();
  formData.append("file", file);
  const response = await api.post<{ status: string; message: string; imported_count: number; skipped_count: number }>("/api/v1/customers/upload-seed", formData, {
    headers: {
      "Content-Type": "multipart/form-data",
    },
  });
  return response.data;
}

export function connectTelegram() {
  return api.post<{ code: string; expires_at: string }>("/api/telegram/connect");
}

export function disconnectTelegram() {
  return api.post<{ status: string }>("/api/telegram/disconnect");
}

export type BriefingExplanation = {
  cost_explanation: string;
  health_explanation: string;
  wastage_explanation: string;
  profit_explanation: string;
  per_size_explanation: string;
  action_items: string[];
  model_version: string;
  tokens_used: number;
};

export type MorningBriefingResponse = {
  message_text: string;
  missing_data: string[];
  language: "en" | "hi" | "hinglish";
  risk_items: Array<{
    severity: "critical" | "warning" | "info";
    type: "low_stock" | "outstanding";
    label: string;
    days_left?: number;
    pending_amount?: number;
    message: string;
  }>;
  ai_explanation?: BriefingExplanation | null;
  ai_observability?: {
    model_name: string | null;
    token_usage: number;
    cache_hit: boolean;
    generation_time: number;
    fallback_reason: string | null;
  } | null;
};

export async function getMorningBriefing() {
  const response = await api.get<MorningBriefingResponse>("/briefings/today");
  return response.data;
}

export type CostDailyResponse = {
  production_date: string;
  cups_produced_total: number;
  total_production_cost: string;
  total_loaded_cost: string;
  cost_per_cup: string;
  loaded_cost_per_cup: string;
  source_quality: "complete" | "partial";
  missing_fields: string[];
};

export type CostWindowResponse = {
  days: 7 | 30;
  start_date: string;
  end_date: string;
  cups_produced_total: number;
  total_production_cost: string;
  weighted_cost_per_cup: string;
  weighted_loaded_cost_per_cup: string;
  source_quality: "complete" | "partial";
  missing_fields: string[];
};

export async function getTodayCost() {
  const response = await api.get<CostDailyResponse>("/cost/today");
  return response.data;
}

export async function getCostWindow(days: 7 | 30) {
  const response = await api.get<CostWindowResponse>("/cost/window", { params: { days } });
  return response.data;
}

export type CostVarianceResponse = {
  snapshot_date: string;
  today_cpc: string;
  today_loaded_cpc: string;
  seven_day_cpc: string;
  seven_day_loaded_cpc: string;
  thirty_day_cpc: string;
  thirty_day_loaded_cpc: string;
  variance_percent: string;
  variance_level: "NORMAL" | "WARNING" | "CRITICAL";
  primary_driver: string;
  material_change_percent: string;
  labour_change_percent: string;
  electricity_change_percent: string;
  overhead_change_percent: string;
  today: CostDailyResponse;
  seven_day: CostWindowResponse;
  thirty_day: CostWindowResponse;
};

export async function getTodayCostVariance() {
  const response = await api.get<CostVarianceResponse>("/cost/variance/today");
  const data = response.data || {};
  return {
    ...data,
    today: data.today ? {
      ...data.today,
      missing_fields: data.today.missing_fields ?? []
    } : { missing_fields: [] },
    seven_day: data.seven_day ? {
      ...data.seven_day,
      missing_fields: data.seven_day.missing_fields ?? []
    } : { missing_fields: [] },
    thirty_day: data.thirty_day ? {
      ...data.thirty_day,
      missing_fields: data.thirty_day.missing_fields ?? []
    } : { missing_fields: [] }
  } as CostVarianceResponse;
}

export type WastageResponse = {
  snapshot_date: string;
  cups_produced: number;
  blank_used_kg: number;
  bottom_used_kg: number;
  actual_wastage_kg: number;
  expected_wastage_kg: number;
  wastage_percentage: number;
  expected_wastage_percentage: number;
  extra_wastage_percentage: number;
  estimated_loss_paise: number;
  estimated_loss: number;
  wastage_status: "NORMAL" | "WARNING" | "CRITICAL";
  primary_wastage_source: "Blank" | "Bottom" | "Mixed";
  baseline_source: "factory_30_day" | "onboarding_default";
  seven_day_trend: number | null;
  thirty_day_trend: number | null;
};

export async function getTodayWastage() {
  const response = await api.get<WastageResponse>("/wastage/today");
  return response.data;
}

export async function getWastageHistory(days = 30) {
  const response = await api.get<{ days: number; items: WastageResponse[] }>("/wastage/history", { params: { days } });
  return response.data;
}

export type ProfitResponse = {
  snapshot_date: string;
  revenue_paise: number;
  material_cost_paise: number;
  labour_cost_paise: number;
  electricity_cost_paise: number;
  overhead_cost_paise: number;
  total_cost_paise: number;
  gross_profit_paise: number;
  revenue: number | "Data not available";
  total_cost: number | "Data not available";
  gross_profit: number | "Data not available";
  profit_margin_percent: number | "Data not available";
  profit_status: "EXCELLENT" | "GOOD" | "WARNING" | "CRITICAL" | "DATA_NOT_AVAILABLE";
  largest_profit_risk: string;
  seven_day_margin: number | null;
  thirty_day_margin: number | null;
  data_available: boolean;
};

export async function getTodayProfit() {
  const response = await api.get<ProfitResponse>("/profit/today");
  return response.data;
}

export async function getProfitHistory(days = 30) {
  const response = await api.get<{ days: number; items: ProfitResponse[] }>("/profit/history", { params: { days } });
  return response.data;
}

export type PerSizeProfitItem = {
  size_ml: number;
  revenue_paise: number;
  cost_paise: number | "Data not available";
  gross_profit_paise: number | "Data not available";
  margin_percent: number | "Data not available";
  units_sold: number;
  units_produced: number;
  status: "EXCELLENT" | "GOOD" | "WARNING" | "CRITICAL" | "DATA_NOT_AVAILABLE";
  data_available: boolean;
  cost_source: "CostPerCupDaily" | "DailyProduction" | "Data not available";
};

export type PerSizeProfitResponse = {
  date: string;
  sizes: PerSizeProfitItem[];
  best_size: PerSizeProfitItem | null;
  worst_size: PerSizeProfitItem | null;
  total_revenue: number;
  total_profit: number | "Data not available";
  weighted_margin: number | "Data not available";
  data_available: boolean;
};

export async function getPerSizeProfit(date?: string) {
  const response = await api.get<PerSizeProfitResponse>("/profit/per-size", { params: date ? { date } : undefined });
  return response.data;
}

export async function getPerSizeProfitHistory(days = 30) {
  const response = await api.get<{ days: number; items: PerSizeProfitResponse[] }>("/profit/per-size/history", { params: { days } });
  return response.data;
}

export type WeeklyDigestResponse = {
  week_start: string;
  week_end: string;
  revenue: number;
  profit: number;
  margin: number | null;
  health_score: number | null;
  best_day: string;
  worst_day: string;
  largest_risk: string;
  generated_at: string;
  message_text: string;
  language: "en" | "hi" | "hinglish";
  days_available: number;
};

export async function getLatestWeeklyDigest() {
  const response = await api.get<WeeklyDigestResponse>("/weekly-digest/latest");
  return response.data;
}

export type FactoryHealthResponse = {
  id: number;
  snapshot_date: string;
  production_score: number;
  attendance_score: number;
  collections_score: number;
  inventory_score: number;
  cost_score: number;
  overall_score: number;
  health_status: "CRITICAL" | "WARNING" | "GOOD" | "EXCELLENT";
  largest_strength: string;
  largest_risk: string;
  trend?: number | null;
};

export async function getTodayFactoryHealth() {
  const response = await api.get<FactoryHealthResponse>("/api/factory-health/today");
  return response.data;
}

export type FactoryHealthHistoryItem = {
  date: string;
  overall_score: number;
  health_status: "CRITICAL" | "WARNING" | "GOOD" | "EXCELLENT";
  production_score: number;
  attendance_score: number;
  collections_score: number;
  inventory_score: number;
  cost_score: number;
  largest_strength: string;
  largest_risk: string;
};

export type FactoryHealthHistoryResponse = {
  days: number;
  items: FactoryHealthHistoryItem[];
  summary: {
    current_score: number | null;
    previous_score: number | null;
    seven_day_average: number | null;
    thirty_day_average: number | null;
    best_day: FactoryHealthHistoryItem | null;
    worst_day: FactoryHealthHistoryItem | null;
    trend_direction: "IMPROVING" | "STABLE" | "DECLINING";
  };
};

export async function getFactoryHealthHistory(days = 30) {
  const response = await api.get<FactoryHealthHistoryResponse>("/api/factory-health/history", { params: { days } });
  return response.data;
}

export type UnifiedAlert = {
  id: number;
  title: string;
  message: string;
  severity: "INFO" | "WARNING" | "CRITICAL";
  status: "OPEN" | "ACKNOWLEDGED" | "RESOLVED";
  source_module: string;
  related_entity_type: string | null;
  related_entity_id: string | null;
  related_route: string | null;
  suggested_action: string | null;
  assigned_role: string;
  first_detected_at: string;
  last_detected_at: string;
};

export async function getAlerts(params?: { severity?: string; module?: string; status?: string }) {
  const response = await api.get<{ items: UnifiedAlert[] }>("/api/alerts", { params });
  return response.data;
}

export async function getTopAlerts(limit = 5) {
  const response = await api.get<{ items: UnifiedAlert[] }>("/api/alerts/top", { params: { limit } });
  return response.data;
}

export async function acknowledgeAlert(alertId: number) {
  const response = await api.patch<UnifiedAlert>(`/api/alerts/${alertId}/acknowledge`);
  return response.data;
}

export async function resolveAlert(alertId: number) {
  const response = await api.patch<UnifiedAlert>(`/api/alerts/${alertId}/resolve`);
  return response.data;
}

export function getCashfreeOrderStatus(orderId: string) {
  return api.get<{ subscription_active: boolean; payment_status?: string | null }>(`/billing/cashfree/orders/${orderId}`);
}

export function generateInvoiceFromSale(
  saleId: number,
  payload: {
    invoice_type: "tax_invoice" | "bill_of_supply";
    tax_rate: number;
    payment_method: string;
  }
) {
  return api.post<{ invoice_id: number; invoice_number: string }>(
    `/invoices/from-sale/${saleId}`,
    payload
  );
}

export type ShiftWastageCreate = {
  date: string;
  shift: string;
  wastage_kg: number;
  note?: string | null;
};

export type ShiftWastageResponse = {
  id: number;
  factory_id: number;
  date: string;
  shift: string;
  wastage_kg: number;
  note?: string | null;
};

export function saveShiftWastage(payload: ShiftWastageCreate) {
  return api.post<ShiftWastageResponse>("/api/production/wastage", payload);
}

export function getShiftWastage(date: string, shift: string) {
  return api.get<ShiftWastageResponse | null>("/api/production/wastage", {
    params: { date, shift }
  });
}

