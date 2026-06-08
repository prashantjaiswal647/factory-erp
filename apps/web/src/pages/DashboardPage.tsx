import axios from "axios";
import {
  AlertTriangle,
  Boxes,
  CalendarDays,
  CheckCircle2,
  IndianRupee,
  PackageCheck,
  RefreshCw,
  UserRound,
  Wrench
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { useAuth } from "../context/AuthContext";
import BriefingCard from "../components/BriefingCard";
import FactoryHealthCard from "../components/FactoryHealthCard";
import FactoryHealthHistoryCard from "../components/FactoryHealthHistoryCard";
import WastageIntelligenceCard from "../components/WastageIntelligenceCard";
import ProfitIntelligenceCard from "../components/ProfitIntelligenceCard";
import PerSizeProfitCard from "../components/PerSizeProfitCard";
import WeeklyDigestCard from "../components/WeeklyDigestCard";
import { WidgetErrorBoundary } from "../components/ErrorBoundary";
import {
  approveSalesOrder,
  getDashboardAnalytics,
  getDashboardMachines,
  getDashboardWorkers,
  getInventory,
  getPendingSales,
  getProductionAlerts,
  rejectSalesOrder
} from "../lib/api";
import type {
  AnalyticsBIResponse,
  DashboardMachine,
  DashboardWorker,
  LiveStockRow,
  PendingSale,
  ProductionAlertsResponse
} from "../lib/api";

type StockRisk = {
  key: string;
  name: string;
  size: string;
  quantity: number;
  unit: string;
  dailyUse: number;
  ttl: number;
  status: "Critical" | "Warning";
};

const todayFormatter = new Intl.DateTimeFormat("en-IN", {
  weekday: "short",
  day: "2-digit",
  month: "short",
  year: "numeric"
});

const safeArray = <T,>(arr: T[] | undefined | null): T[] => Array.isArray(arr) ? arr : [];

export default function DashboardPage() {
  const [workers, setWorkers] = useState<DashboardWorker[]>([]);
  const [machines, setMachines] = useState<DashboardMachine[]>([]);
  const [inventory, setInventory] = useState<LiveStockRow[]>([]);
  const [pendingSales, setPendingSales] = useState<PendingSale[]>([]);
  const [productionAlerts, setProductionAlerts] = useState<ProductionAlertsResponse | null>(null);
  const [analyticsData, setAnalyticsData] = useState<AnalyticsBIResponse | null>(null);
  const [approvalMessage, setApprovalMessage] = useState("");
  const [processingOrderId, setProcessingOrderId] = useState<number | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState("");
  const { user } = useAuth();
  const navigate = useNavigate();

  useEffect(() => {
    void load();
  }, []);

  async function load() {
    setIsLoading(true);
    setError("");
    try {
      const results = await Promise.allSettled([
        getDashboardWorkers(),
        getDashboardMachines(),
        getInventory(),
        getProductionAlerts()
      ]);
      const rejected = results.find((result) => result.status === "rejected");
      if (rejected?.status === "rejected" && axios.isAxiosError(rejected.reason) && rejected.reason.response?.status === 401) {
        localStorage.clear();
        navigate("/login", { replace: true });
        return;
      }

      const [workerRes, machineRes, inventoryRes, alertRes] = results;
      if (workerRes.status === "fulfilled") setWorkers(Array.isArray(workerRes.value.data) ? workerRes.value.data : []);
      if (machineRes.status === "fulfilled") setMachines(Array.isArray(machineRes.value.data) ? machineRes.value.data : []);
      if (inventoryRes.status === "fulfilled") setInventory(Array.isArray(inventoryRes.value.data) ? inventoryRes.value.data : []);
      if (alertRes.status === "fulfilled") setProductionAlerts(alertRes.value.data);

      if (user?.role === "Owner" || user?.role === "Sub-Owner") {
        const ownerResults = await Promise.allSettled([getPendingSales(), getDashboardAnalytics()]);
        if (ownerResults[0].status === "fulfilled") {
          setPendingSales(Array.isArray(ownerResults[0].value.data) ? ownerResults[0].value.data : []);
        }
        if (ownerResults[1].status === "fulfilled") setAnalyticsData(ownerResults[1].value.data);
      }

      if (rejected) setError("Some dashboard data could not be refreshed. Showing available data.");
    } catch (caught) {
      if (axios.isAxiosError(caught) && caught.response?.status === 401) {
        localStorage.clear();
        navigate("/login", { replace: true });
        return;
      }
      setError("Dashboard request failed. Please refresh once.");
    } finally {
      setIsLoading(false);
    }
  }

  async function handleSaleApproval(orderId: number, action: "approve" | "reject") {
    setProcessingOrderId(orderId);
    setApprovalMessage("");
    try {
      const response = action === "approve" ? await approveSalesOrder(orderId) : await rejectSalesOrder(orderId);
      setApprovalMessage(response.data.message || `Order ${action === "approve" ? "approved" : "rejected"}.`);
      await load();
    } catch (caught) {
      const message = axios.isAxiosError(caught) ? caught.response?.data?.detail || caught.message : "Approval action failed";
      setApprovalMessage(String(message));
    } finally {
      setProcessingOrderId(null);
    }
  }

  const finishedBoxes = useMemo(
    () => safeArray(inventory)
      .filter((row) => normalizedType(row) === "Final Product")
      .reduce((sum, row) => sum + Number(row.quantity || row.current_quantity || 0), 0),
    [inventory]
  );
  const shiftTarget = useMemo(
    () => safeArray(machines).reduce((sum, machine) => sum + Number(machine.target_output_per_shift || 0), 0),
    [machines]
  );
  const targetProgress = shiftTarget > 0 ? Math.min(100, Math.round((finishedBoxes / shiftTarget) * 100)) : 0;
  const activeMachines = safeArray(machines).filter((machine) => machine.is_active !== false).length;
  const dailyWages = safeArray(workers).reduce((sum, worker) => sum + Number(worker.daily_wages || 0), 0);
  const totalWastage = safeArray(productionAlerts?.alerts).reduce((sum, alert) => sum + Number(alert.wastage_kg || 0), 0);
  const stockRisks = useMemo(() => buildStockRisks(inventory).slice(0, 3), [inventory]);
  const financials = useMemo(() => {
    const rows = safeArray(analyticsData?.financial_data);
    return {
      sales: rows.reduce((sum, row) => sum + Number(row.Sales || 0), 0),
      collections: rows.reduce((sum, row) => sum + Number(row.Collection || 0), 0),
      expenses: rows.reduce((sum, row) => sum + Number(row.Expense || 0), 0)
    };
  }, [analyticsData]);
  const hasAlerts = stockRisks.length > 0 || Number(productionAlerts?.high_wastage_count || 0) > 0;

  if (isLoading) {
    return <div className="rounded-lg border border-zinc-200 bg-white p-6 text-sm text-zinc-500">Loading factory dashboard...</div>;
  }

  return (
    <div className="min-w-0 space-y-3 overflow-x-hidden">
      <header className="flex items-center justify-between gap-3">
        <div className="min-w-0">
          <p className="text-xs font-semibold uppercase tracking-wide text-brand-700">Factory owner dashboard</p>
          <h1 className="truncate text-xl font-bold text-zinc-950" data-testid="dashboard-heading">
            Today&apos;s operational summary
          </h1>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <span className="hidden text-xs font-medium text-zinc-500 sm:inline">{todayFormatter.format(new Date())}</span>
          <button
            className="inline-flex h-9 items-center gap-2 rounded-lg border border-zinc-200 bg-white px-3 text-xs font-semibold text-zinc-700 hover:bg-zinc-50"
            type="button"
            onClick={load}
          >
            <RefreshCw className="h-4 w-4" />
            Refresh
          </button>
        </div>
      </header>

      {error ? <div className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs font-medium text-amber-900">{error}</div> : null}

      {(user?.role === "Owner" || user?.role === "Sub-Owner") && (
        <>
          <WidgetErrorBoundary name="Morning Briefing">
            <BriefingCard />
          </WidgetErrorBoundary>
          <WidgetErrorBoundary name="Weekly Review">
            <WeeklyDigestCard />
          </WidgetErrorBoundary>
          <WidgetErrorBoundary name="Factory Health">
            <FactoryHealthCard />
          </WidgetErrorBoundary>
          <WidgetErrorBoundary name="Health History">
            <FactoryHealthHistoryCard />
          </WidgetErrorBoundary>
          <WidgetErrorBoundary name="Wastage Intelligence">
            <WastageIntelligenceCard />
          </WidgetErrorBoundary>
          <WidgetErrorBoundary name="Profit Intelligence">
            <ProfitIntelligenceCard />
          </WidgetErrorBoundary>
          <WidgetErrorBoundary name="Per-Size Profit">
            <PerSizeProfitCard />
          </WidgetErrorBoundary>
        </>
      )}

      <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
        <Link className="rounded-xl border-2 border-brand-300 bg-brand-50 p-4 shadow-sm sm:col-span-2 xl:col-span-2" to="/production">
          <div className="flex items-start justify-between gap-3">
            <div>
              <p className="text-xs font-bold uppercase tracking-wide text-brand-700">Target vs Achievement</p>
              <p className="mt-1 text-3xl font-bold text-zinc-950">{targetProgress}%</p>
              <p className="mt-1 text-xs text-zinc-600">
                {formatNumber(finishedBoxes)} recorded boxes against {formatNumber(shiftTarget)} configured shift target
              </p>
            </div>
            <PackageCheck className="h-6 w-6 text-brand-700" />
          </div>
          <div className="mt-3 h-2 overflow-hidden rounded-full bg-white">
            <div className="h-full rounded-full bg-brand-600" style={{ width: `${targetProgress}%` }} />
          </div>
        </Link>
        <KpiCard icon={AlertTriangle} label="Stock risks" value={stockRisks.length} helper="Top urgent items" tone={stockRisks.length ? "amber" : "green"} href="/inventory" />
        <KpiCard icon={Wrench} label="Machines active" value={`${activeMachines}/${machines.length}`} helper="Configured machines" tone="blue" href="/machine-onboarding" />
        <KpiCard icon={UserRound} label="Workers" value={workers.length} helper={`Daily wages Rs ${formatNumber(dailyWages)}`} tone="purple" href="/staff" />
      </section>

      <section
        className={`flex flex-col gap-2 rounded-xl border px-4 py-3 sm:flex-row sm:items-center sm:justify-between ${
          hasAlerts ? "border-amber-200 bg-amber-50" : "border-emerald-200 bg-emerald-50"
        }`}
        role="alert"
        aria-live="polite"
      >
        <div className="flex items-start gap-2">
          {hasAlerts ? <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-amber-700" /> : <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-emerald-700" />}
          <div>
            <p className="text-sm font-bold text-zinc-900">{hasAlerts ? "Action needed today" : "All critical checks are clear"}</p>
            <p className="text-xs text-zinc-600">
              {hasAlerts
                ? `${stockRisks.length} stock risk${stockRisks.length === 1 ? "" : "s"} and ${productionAlerts?.high_wastage_count || 0} wastage alert${productionAlerts?.high_wastage_count === 1 ? "" : "s"}.`
                : "No urgent stock or wastage alerts in the current data."}
            </p>
          </div>
        </div>
        <div className="flex gap-2">
          <Link className="rounded-md bg-zinc-900 px-3 py-2 text-xs font-semibold text-white" to="/production">Log production</Link>
          <Link className="rounded-md border border-zinc-300 bg-white px-3 py-2 text-xs font-semibold text-zinc-700" to="/inventory">Check inventory</Link>
        </div>
      </section>

      <section className="rounded-xl border border-zinc-200 bg-white p-4 shadow-sm">
        <div className="flex items-center justify-between gap-3">
          <div>
            <h2 className="text-sm font-bold text-zinc-950">AI Stock-Out Prevention</h2>
            <p className="text-xs text-zinc-500">Top 3 risks by estimated depletion time.</p>
          </div>
          <Link className="text-xs font-semibold text-brand-700" to="/inventory">View inventory</Link>
        </div>
        {stockRisks.length === 0 ? (
          <p className="mt-3 rounded-lg bg-emerald-50 px-3 py-3 text-xs font-medium text-emerald-800">No urgent stock risks found.</p>
        ) : (
          <div className="mt-3 grid gap-2 lg:grid-cols-3">
            {stockRisks.map((item) => (
              <div key={item.key} className={`rounded-lg border px-3 py-3 ${item.status === "Critical" ? "border-red-200 bg-red-50" : "border-amber-200 bg-amber-50"}`}>
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <p className="truncate text-sm font-bold text-zinc-900">{item.name} {item.size}</p>
                    <p className="mt-1 text-xs text-zinc-600">{formatNumber(item.quantity)} {item.unit} available · {item.ttl} days left</p>
                  </div>
                  <span className={`shrink-0 rounded-full px-2 py-1 text-[10px] font-bold ${item.status === "Critical" ? "bg-red-100 text-red-700" : "bg-amber-100 text-amber-800"}`}>
                    {item.status}
                  </span>
                </div>
                <p className="mt-2 text-[11px] text-zinc-500">Estimated use: {item.dailyUse} {item.unit}/day. Review purchasing on Inventory.</p>
              </div>
            ))}
          </div>
        )}
      </section>

      <section className="rounded-xl border border-zinc-200 bg-white p-4 shadow-sm">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-sm font-bold text-zinc-950">Collections</h2>
            <p className="text-xs text-zinc-500">Current financial snapshot from existing dashboard analytics.</p>
          </div>
          <Link className="text-xs font-semibold text-brand-700" to="/outstanding">View outstanding</Link>
        </div>
        <div className="mt-3 grid grid-cols-2 gap-2 lg:grid-cols-4">
          <CompactMetric icon={IndianRupee} label="Collected" value={`Rs ${formatNumber(financials.collections)}`} />
          <CompactMetric icon={Boxes} label="Sales" value={`Rs ${formatNumber(financials.sales)}`} />
          <CompactMetric icon={CalendarDays} label="Expenses" value={`Rs ${formatNumber(financials.expenses)}`} />
          <CompactMetric icon={AlertTriangle} label="Wastage" value={`${totalWastage.toFixed(1)} kg`} />
        </div>
      </section>

      {(user?.role === "Owner" || user?.role === "Sub-Owner") && safeArray(pendingSales).length > 0 ? (
        <PendingSalesApprovalSection
          message={approvalMessage}
          pendingSales={pendingSales}
          processingOrderId={processingOrderId}
          onAction={handleSaleApproval}
        />
      ) : null}
    </div>
  );
}

function KpiCard({ icon: Icon, label, value, helper, tone, href }: {
  icon: typeof Boxes;
  label: string;
  value: string | number;
  helper: string;
  tone: "amber" | "green" | "blue" | "purple";
  href: string;
}) {
  const tones = {
    amber: "border-amber-200 bg-amber-50 text-amber-700",
    green: "border-emerald-200 bg-emerald-50 text-emerald-700",
    blue: "border-blue-200 bg-blue-50 text-blue-700",
    purple: "border-brand-200 bg-brand-50 text-brand-700"
  };
  return (
    <Link className={`rounded-xl border p-3 shadow-sm ${tones[tone]}`} to={href}>
      <div className="flex items-center justify-between">
        <p className="text-[11px] font-bold uppercase tracking-wide">{label}</p>
        <Icon className="h-4 w-4" />
      </div>
      <p className="mt-2 text-2xl font-bold text-zinc-950">{value}</p>
      <p className="mt-1 text-xs text-zinc-600">{helper}</p>
    </Link>
  );
}

function CompactMetric({ icon: Icon, label, value }: { icon: typeof Boxes; label: string; value: string }) {
  return (
    <div className="rounded-lg bg-zinc-50 px-3 py-3">
      <div className="flex items-center gap-2 text-xs font-semibold text-zinc-500"><Icon className="h-4 w-4" />{label}</div>
      <p className="mt-1 text-base font-bold text-zinc-950">{value}</p>
    </div>
  );
}

function PendingSalesApprovalSection({ message, pendingSales, processingOrderId, onAction }: {
  message: string;
  pendingSales: PendingSale[];
  processingOrderId: number | null;
  onAction: (orderId: number, action: "approve" | "reject") => void;
}) {
  const list = safeArray(pendingSales);
  return (
    <section className="rounded-xl border border-amber-200 bg-white p-4 shadow-sm">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-sm font-bold text-zinc-950">Sales approvals</h2>
          <p className="text-xs text-zinc-500">{list.length} orders require owner action.</p>
        </div>
        <span className="rounded-full bg-amber-100 px-2.5 py-1 text-xs font-bold text-amber-800">{list.length} pending</span>
      </div>
      {message ? <p className="mt-3 rounded-lg bg-zinc-50 p-2 text-xs font-medium text-zinc-700">{message}</p> : null}
      <div className="mt-3 space-y-2">
        {list.slice(0, 3).map((sale) => (
          <div key={sale.order_id} className="flex flex-col gap-2 rounded-lg border border-zinc-200 p-3 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <p className="text-sm font-bold text-zinc-900">#{sale.order_id} · {sale.customer_name || "Customer"}</p>
              <p className="text-xs text-zinc-500">Rs {formatNumber(Number(sale.total_amount || 0))}</p>
            </div>
            <div className="flex gap-2">
              <button className="rounded-md bg-emerald-600 px-3 py-2 text-xs font-bold text-white disabled:opacity-50" disabled={processingOrderId === sale.order_id} onClick={() => onAction(sale.order_id, "approve")} type="button">Approve</button>
              <button className="rounded-md border border-red-200 px-3 py-2 text-xs font-bold text-red-700 disabled:opacity-50" disabled={processingOrderId === sale.order_id} onClick={() => onAction(sale.order_id, "reject")} type="button">Reject</button>
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}

function buildStockRisks(rows: LiveStockRow[]): StockRisk[] {
  return safeArray(rows)
    .filter((row) => ["Blank", "Bottom", "Carton Box", "Polybag"].includes(normalizedType(row)))
    .map((row) => {
      const type = normalizedType(row);
      const quantity = Number(row.quantity || row.current_quantity || 0);
      const dailyUse = type === "Blank" ? 40 : type === "Bottom" ? 12 : 25;
      const ttl = quantity <= 0 ? 0 : Math.ceil(quantity / dailyUse);
      return {
        key: `${row.stock_type}-${row.id}`,
        name: type === "Blank" ? "Cup Blank" : type === "Bottom" ? "Cup Bottom" : row.item_name || type,
        size: sizeFor(row, type),
        quantity,
        unit: row.unit || (type === "Carton Box" || type === "Polybag" ? "pcs" : "kg"),
        dailyUse,
        ttl,
        status: ttl <= 3 ? "Critical" as const : "Warning" as const
      };
    })
    .filter((item) => item.ttl < 10)
    .sort((a, b) => a.ttl - b.ttl);
}

function normalizedType(row: LiveStockRow): string {
  const raw = `${row.stock_type || ""} ${row.category || ""} ${row.item_name || ""}`.toLowerCase();
  if (raw.includes("final")) return "Final Product";
  if (raw.includes("bottom")) return "Bottom";
  if (raw.includes("blank")) return "Blank";
  if (raw.includes("carton") || raw.includes("box")) return "Carton Box";
  if (raw.includes("poly") || raw.includes("plastic") || raw.includes("packing")) return "Polybag";
  return "Inventory";
}

function sizeFor(row: LiveStockRow, type: string) {
  if (type === "Bottom") return row.size_mm ? `${row.size_mm}mm` : "";
  if (type === "Blank") {
    const match = String(row.item_name || "").match(/(\d+)\s*ml/i);
    return match ? `${match[1]}ml` : "";
  }
  return row.packaging_size_name || row.packaging_size || "";
}

function formatNumber(value: number) {
  return Number(value || 0).toLocaleString("en-IN");
}
