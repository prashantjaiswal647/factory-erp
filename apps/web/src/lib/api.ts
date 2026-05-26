import axios from "axios";

const trimTrailingSlash = (value: string) => value.replace(/\/+$/, "");

const getBaseURL = () => {
  const configuredUrl = import.meta.env.VITE_API_URL;
  if (configuredUrl) return trimTrailingSlash(configuredUrl);

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
  const token = localStorage.getItem("token") || localStorage.getItem("ai_erp_token");
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
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
    if (status === 401 && typeof window !== "undefined") {
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
  machine_type: "Paper Cup" | "Dona" | "Paper Bag";
  machine_number: string;
  mould_size_ml: number;
  bottom_size_mm: number;
  speed_per_minute: number;
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
  shift: "Day" | "Night";
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
  role: "Sub-Owner" | "Supervisor" | "Operator";
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
  legal_invoice_type: "tax_invoice" | "bill_of_supply";
  legal_invoice_number?: string | null;
  rough_bill_enabled: boolean;
  rough_bill_number?: string | null;
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

export type InvoiceDocumentSummary = {
  id: number;
  invoice_number: string;
  invoice_date: string;
  customer_id?: number | null;
  customer_name: string;
  customer_phone?: string | null;
  payment_method: string;
  bill_total: string;
  amount_paid: string;
  customer_total_due: string;
  status: string;
  pdf_generated_count: number;
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

export type LiveStockRow = {
  id: number | string;
  factory_id?: number;
  product_id?: number | null;
  product_size_ml?: number | null;
  variety?: string | null;
  stock_type: "Blank" | "Bottom" | "Box" | "Final Product";
  item_name: string;
  category?: string | null;
  packaging_size?: string | null;
  packaging_size_name?: string | null;
  pieces_per_packet?: number | null;
  packets_per_box?: number | null;
  packets_per_box_limit?: number | null;
  current_quantity?: number | null;
  quantity: number;
  unit: string;
  size_mm?: number | null;
  total_weight_kg?: number | null;
  total_rolls?: number | null;
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
  kg_per_sack: number;
  total_sacks: number;
};

export type BoxPackagingStockCreate = {
  box_type: "Small Box" | "Big Box";
  quantity: number;
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
  place: string;
  gst_number?: string | null;
  previous_due: number;
  total_due: number;
};

export type CustomerSearchResult = {
  id: number;
  name: string;
  company_name?: string | null;
  place: string;
  phone_number: string;
  gst_number?: string | null;
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
  customer_id: number;
  customer_name: string;
  customer_phone: string;
  place?: string;
  total_bill_amount: string;
  total_paid: string;
  current_pending_balance: string;
  last_reminded_at?: string | null;
  bills?: OutstandingBill[];
};

export type OutstandingBill = {
  order_id: number;
  order_date: string;
  bill_amount: string;
  amount_paid: string;
  remaining_balance: string;
  status: string;
};

export type OutstandingResponse = {
  grand_total_outstanding: string;
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
  customer_phone: string;
  amount_paid: number;
  payment_mode: "Cash" | "UPI" | "Bank Transfer";
  date?: string;
  sale_id?: number;
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
  shift_timing?: string | null;
  shift_type?: string | null;
};

export type WorkerLedgerDay = {
  date: string;
  attendance_id?: number | null;
  status: "Present" | "Absent" | "Half-day";
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
      name: machine.machine_number,
      cup_size_ml: machine.mould_size_ml,
      bottom_size_mm: machine.bottom_size_mm,
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

export function createDailySale(payload: DailySaleCreate) {
  return api.post<DailySaleResponse>("/api/sales/invoice", payload);
}

export function getInvoiceDocuments() {
  return api.get<InvoiceDashboardResponse>("/api/sales/invoices");
}

export function downloadInvoicePdf(invoiceId: number) {
  return api.get<Blob>(`/api/sales/invoices/${invoiceId}/pdf`, { responseType: "blob" });
}

export function createPendingSaleOrder(payload: DailySaleCreate) {
  return api.post<DailySaleResponse>("/api/sales/order", payload);
}

export function createSalesCustomer(payload: CustomerCreate) {
  return api.post("/api/sales/customers", payload);
}

export function searchCustomers(q: string) {
  return api.get<CustomerSearchResult[]>("/api/customers/search", { params: { q } });
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

export function getFinalStockOptions() {
  return api.get<FinalStockOption[]>("/api/inventory/final-stock");
}

export function saveFinalProductOpeningStock(payload: FinalProductOpeningStockCreate) {
  return api.post<FinalStockOption>("/api/onboarding/final-stock", payload);
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

export function clearOutstandingBill(orderId: number) {
  return api.delete(`/api/sales/outstanding/${orderId}`, { params: { confirm: true } });
}

export function sendOutstandingReminder(customerId: number) {
  return api.post(`/api/accounts/reminders/${customerId}`);
}

export function getAttendanceSummary(month: string) {
  return api.get<AttendanceSummaryResponse>("/api/workers/attendance/summary", { params: { month } });
}

export function getWorkerLedger(workerId: number, month: string) {
  return api.get<WorkerLedgerResponse>(`/api/workers/${workerId}/attendance-ledger`, { params: { month } });
}

export function updateWorkerProfile(workerId: number, payload: WorkerUpdatePayload) {
  return api.patch<WorkerProfile>(`/api/workers/${workerId}`, payload);
}

export function upsertWorkerAttendance(workerId: number, payload: { date: string; status: WorkerLedgerDay["status"]; production_qty?: number | null }) {
  return api.post<WorkerLedgerDay>(`/api/workers/${workerId}/attendance`, payload);
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
  return api.post("/api/onboarding/raw-material/box", payload);
}

export function createPlasticStock(payload: PlasticStockCreate) {
  return api.post("/api/onboarding/raw-material/plastic", payload);
}

export function getOnboardingOverview() {
  return api.get<OnboardingOverview>("/api/onboarding/overview");
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

export function getDashboardCustomers() {
  return api.get<DashboardCustomer[]>("/api/onboarding/customers");
}

export function deleteDashboardMachine(id: number) {
  return api.delete(`/api/onboarding/machine/${id}`);
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

export function updateUserProfile(payload: {
  full_name: string;
  country_code: string;
  phone_number: string;
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

export function deleteOnboardingEntry(entryId: string, type?: string) {
  return api.delete(`/api/onboarding/entry/${entryId}`, {
    params: type ? { type } : undefined
  });
}

