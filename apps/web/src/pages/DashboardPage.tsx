import type { LucideIcon } from "lucide-react";
import { AlertTriangle, Boxes, CalendarDays, Factory, IndianRupee, PackageCheck, RefreshCw, UserRound, Wrench } from "lucide-react";
import axios from "axios";
import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { useAuth } from "../context/AuthContext";
import { getDashboardMachines, getDashboardWorkers, getInventory, getProductionAlerts } from "../lib/api";
import type { DashboardMachine, DashboardWorker, LiveStockRow, ProductionAlertsResponse } from "../lib/api";

type StockStatus = "In Stock" | "Low Stock" | "Out of Stock";

type StockDisplayRow = {
  key: string;
  marker: string;
  productName: string;
  description: string;
  size: string;
  stockLabel: string;
  quantity: number;
  perBox: string;
  totalPieces: string;
  location: string;
  status: StockStatus;
};

const todayFormatter = new Intl.DateTimeFormat("en-IN", {
  weekday: "short",
  day: "2-digit",
  month: "short",
  year: "numeric"
});

export default function DashboardPage() {
  const [workers, setWorkers] = useState<DashboardWorker[]>([]);
  const [machines, setMachines] = useState<DashboardMachine[]>([]);
  const [inventory, setInventory] = useState<LiveStockRow[]>([]);
  const [productionAlerts, setProductionAlerts] = useState<ProductionAlertsResponse | null>(null);
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
        setError("Session expired. Please log in again.");
        navigate("/login", { replace: true });
        return;
      }

      const [workerRes, machineRes, inventoryRes, alertRes] = results;
      if (workerRes.status === "fulfilled") setWorkers(Array.isArray(workerRes.value.data) ? workerRes.value.data : []);
      if (machineRes.status === "fulfilled") setMachines(Array.isArray(machineRes.value.data) ? machineRes.value.data : []);
      if (inventoryRes.status === "fulfilled") setInventory(Array.isArray(inventoryRes.value.data) ? inventoryRes.value.data : []);
      if (alertRes.status === "fulfilled") setProductionAlerts(alertRes.value.data);

      if (rejected?.status === "rejected") {
        const detail = axios.isAxiosError(rejected.reason) ? rejected.reason.response?.data?.detail : null;
        setError(`Some dashboard data could not be refreshed: ${typeof detail === "string" ? detail : "showing available data."}`);
      }
    } catch (caught) {
      if (axios.isAxiosError(caught) && caught.response?.status === 401) {
        localStorage.clear();
        setError("Session expired. Please log in again.");
        navigate("/login", { replace: true });
        return;
      }
      setError("Dashboard request failed. Please refresh once.");
    } finally {
      setIsLoading(false);
    }
  }

  const stockRows = useMemo(() => buildDashboardStockRows(inventory), [inventory]);
  const finishedRows = stockRows.filter((row) => row.description === "Finished paper cup");
  const totalFinishedBoxes = finishedRows.reduce((sum, row) => sum + row.quantity, 0);
  const dailyWages = workers.reduce((sum, worker) => sum + Number(worker.daily_wages || 0), 0);
  const lowStockCount = stockRows.filter((row) => row.status !== "In Stock").length + (productionAlerts?.high_wastage_count || 0);
  const productionToday = finishedRows.length > 0 ? `${totalFinishedBoxes.toLocaleString("en-IN")} boxes ready` : "No finished stock";
  const factorySummary = `${workers.length} workers on floor · ${machines.length} machines active · ${inventory.length} stock rows tracked`;

  if (isLoading) {
    return <div className="rounded-lg border border-zinc-200 bg-white p-8 text-sm text-zinc-500">Loading factory dashboard...</div>;
  }

  return (
    <div className="min-w-0 space-y-6 overflow-x-hidden">
      <header className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <p className="text-sm font-medium text-brand-700">Munshi AI Factory Operations</p>
          <h1 className="mt-1 text-2xl font-semibold tracking-normal text-zinc-950" data-testid="dashboard-heading">
            Welcome back, {user?.username || "Owner"}!
          </h1>
          <p className="mt-1 text-sm text-zinc-500">{factorySummary}</p>
        </div>
        <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
          <div className="inline-flex h-10 items-center gap-2 rounded-lg border border-zinc-200 bg-white px-3 text-sm font-medium text-zinc-600">
            <CalendarDays className="h-4 w-4 text-brand-700" />
            Today, {todayFormatter.format(new Date())}
          </div>
          <button className="inline-flex h-10 items-center justify-center gap-2 rounded-lg border border-zinc-200 bg-white px-4 text-sm font-semibold text-zinc-700 hover:bg-brand-50" type="button" onClick={load}>
            <RefreshCw className="h-4 w-4" />
            Refresh
          </button>
        </div>
      </header>

      {error ? (
        <div className="rounded-lg border border-amber-200 bg-amber-50 p-4 text-sm font-medium text-amber-900">
          {error}
        </div>
      ) : null}

      <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-6">
        <MetricCard icon={Boxes} tone="purple" label="Boxes Available" value={totalFinishedBoxes.toLocaleString("en-IN")} helper="Finished goods ready" />
        <MetricCard icon={UserRound} tone="blue" label="Workers" value={workers.length} helper="On floor" />
        <MetricCard icon={Factory} tone="green" label="Machines" value={machines.length} helper="Active" />
        <MetricCard icon={IndianRupee} tone="amber" label="Daily Wages" value={`₹${dailyWages.toLocaleString("en-IN")}`} helper="Total today" />
        <MetricCard icon={PackageCheck} tone="rose" label="Production Today" value={productionToday} helper="Finished goods" />
        <MetricCard icon={AlertTriangle} tone={lowStockCount > 0 ? "amber" : "green"} label="Low Stock Alerts" value={lowStockCount} helper={lowStockCount > 0 ? "Needs review" : "All clear"} />
      </section>

      <section className="rounded-xl border border-zinc-200 bg-white p-4 shadow-sm sm:p-5">
        <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h2 className="text-lg font-semibold text-zinc-950">Finished Goods Stock</h2>
            <p className="mt-1 text-sm text-zinc-500">Readable live stock list. No charts, no overlapping graph layout.</p>
          </div>
          <Link className="inline-flex h-10 items-center justify-center rounded-lg bg-brand-600 px-4 text-sm font-semibold text-white hover:bg-brand-700" to="/inventory">
            View Inventory
          </Link>
        </div>

        <div className="mt-5 space-y-3">
          {stockRows.length === 0 ? (
            <EmptyState message="No inventory rows found yet. Add onboarding stock to see finished cups, bottom, blank, and packing material." />
          ) : (
            stockRows.map((row) => <StockListRow key={row.key} row={row} />)
          )}
        </div>
      </section>

      <section className="grid gap-4 lg:grid-cols-2">
        <SimpleTableCard
          icon={UserRound}
          title="Workers"
          empty="No workers added yet."
          rows={workers.slice(0, 6).map((worker) => [
            worker.name,
            worker.phone || "-",
            worker.shift_type || worker.shift_timing || `${worker.duty_hours || 8} hrs`,
            `₹${Number(worker.daily_wages || 0).toLocaleString("en-IN")}`
          ])}
          headers={["Name", "Phone", "Shift", "Daily Wages"]}
          to="/attendance"
        />
        <SimpleTableCard
          icon={Wrench}
          title="Machines"
          empty="No machines added yet."
          rows={machines.slice(0, 6).map((machine) => [
            machine.machine_number || `Machine ${machine.id}`,
            machine.machine_type || "-",
            `${machine.mould_size_ml || "-"}ml`,
            `${machine.speed_per_minute || "-"} / min`
          ])}
          headers={["Machine", "Type", "Cup Size", "Speed"]}
          to="/machine-setup"
        />
      </section>
    </div>
  );
}

function buildDashboardStockRows(rows: LiveStockRow[]): StockDisplayRow[] {
  const order = ["Final Product", "Bottom", "Blank", "Carton Box", "Box", "Polybag", "Inventory"];
  return [...rows]
    .sort((a, b) => order.indexOf(normalizedType(a)) - order.indexOf(normalizedType(b)))
    .map((row) => {
      const type = normalizedType(row);
      const quantity = Number(row.quantity || row.current_quantity || 0);
      const piecesPerPacket = Number(row.pieces_per_packet || 0);
      const packetsPerBox = Number(row.packets_per_box_limit || row.packets_per_box || 0);
      const piecesPerBox = type === "Final Product" ? piecesPerPacket * packetsPerBox : 0;
      const status = statusFor(quantity, type);
      return {
        key: `${row.stock_type}-${row.id}`,
        marker: markerFor(type),
        productName: readableProductName(row, type),
        description: descriptionFor(type),
        size: sizeFor(row, type),
        stockLabel: `${formatNumber(quantity)} ${unitLabel(row.unit)}`,
        quantity,
        perBox: piecesPerBox > 0 ? `${formatNumber(piecesPerBox)} pcs` : perBoxFallback(row, type),
        totalPieces: piecesPerBox > 0 ? `${formatNumber(quantity * piecesPerBox)} pcs` : "-",
        location: type === "Carton Box" || type === "Polybag" ? "Store Room" : "Main Warehouse",
        status
      };
    });
}

function StockListRow({ row }: { row: StockDisplayRow }) {
  return (
    <div className="grid gap-3 rounded-lg border border-zinc-200 bg-white p-4 transition hover:border-brand-200 hover:bg-brand-50/30 md:grid-cols-[minmax(180px,1.3fr)_repeat(5,minmax(110px,1fr))_auto] md:items-center">
      <div className="flex min-w-0 items-center gap-3">
        <span className="grid h-11 w-11 shrink-0 place-items-center rounded-xl bg-zinc-100 text-xl">{row.marker}</span>
        <div className="min-w-0">
          <p className="truncate text-sm font-semibold text-zinc-950">{row.productName}</p>
          <p className="text-xs text-zinc-500">{row.description}</p>
        </div>
      </div>
      <RowMetric label="Size" value={row.size} />
      <RowMetric label="Total Stock" value={row.stockLabel} />
      <RowMetric label="Per Box" value={row.perBox} />
      <RowMetric label="Total Pieces" value={row.totalPieces} />
      <RowMetric label="Location" value={row.location} />
      <div>
        <p className="mb-1 text-xs text-zinc-500 md:hidden">Status</p>
        <StatusBadge status={row.status} />
      </div>
    </div>
  );
}

function RowMetric({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0">
      <p className="text-xs text-zinc-500">{label}</p>
      <p className="mt-1 truncate text-sm font-semibold text-zinc-900">{value}</p>
    </div>
  );
}

function MetricCard({ icon: Icon, tone, label, value, helper }: { icon: LucideIcon; tone: "purple" | "blue" | "green" | "amber" | "rose"; label: string; value: string | number; helper: string }) {
  const tones = {
    purple: "border-brand-100 bg-white text-brand-700 shadow-brand-100/70",
    blue: "border-blue-100 bg-white text-blue-700 shadow-blue-100/70",
    green: "border-emerald-100 bg-white text-emerald-700 shadow-emerald-100/70",
    amber: "border-amber-100 bg-white text-amber-700 shadow-amber-100/70",
    rose: "border-rose-100 bg-white text-rose-700 shadow-rose-100/70"
  };
  const iconBg = {
    purple: "bg-brand-50",
    blue: "bg-blue-50",
    green: "bg-emerald-50",
    amber: "bg-amber-50",
    rose: "bg-rose-50"
  };
  return (
    <div className={`rounded-xl border p-4 shadow-sm ${tones[tone]}`}>
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-xs font-semibold text-zinc-600">{label}</p>
          <p className="mt-3 break-words text-xl font-semibold text-zinc-950">{value}</p>
          <p className="mt-2 text-xs text-zinc-500">{helper}</p>
        </div>
        <span className={`grid h-10 w-10 shrink-0 place-items-center rounded-full ${iconBg[tone]}`}>
          <Icon className="h-5 w-5" />
        </span>
      </div>
    </div>
  );
}

function SimpleTableCard({ icon: Icon, title, headers, rows, empty, to }: { icon: LucideIcon; title: string; headers: string[]; rows: string[][]; empty: string; to: string }) {
  return (
    <section className="rounded-xl border border-zinc-200 bg-white p-4 shadow-sm">
      <div className="flex items-center justify-between gap-3">
        <h2 className="flex items-center gap-2 text-base font-semibold text-zinc-950">
          <Icon className="h-4 w-4 text-brand-700" />
          {title}
        </h2>
        <Link className="text-sm font-semibold text-brand-700 hover:text-brand-800" to={to}>Open</Link>
      </div>
      {rows.length === 0 ? (
        <EmptyState message={empty} />
      ) : (
        <div className="mt-4 overflow-x-auto rounded-lg border border-zinc-100">
          <table className="min-w-full divide-y divide-zinc-100 text-sm">
            <thead className="bg-zinc-50 text-xs uppercase text-zinc-500">
              <tr>{headers.map((header) => <th key={header} className="px-4 py-3 text-left font-semibold">{header}</th>)}</tr>
            </thead>
            <tbody className="divide-y divide-zinc-100">
              {rows.map((row, index) => (
                <tr key={`${title}-${index}`} className="hover:bg-zinc-50">
                  {row.map((cell, cellIndex) => <td key={`${title}-${index}-${cellIndex}`} className="whitespace-nowrap px-4 py-3 text-zinc-700">{cell}</td>)}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

function EmptyState({ message }: { message: string }) {
  return <div className="mt-4 rounded-lg border border-dashed border-zinc-300 bg-zinc-50 p-6 text-center text-sm text-zinc-500">{message}</div>;
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

function markerFor(type: string) {
  if (type === "Final Product") return "🥤";
  if (type === "Bottom") return "◯";
  if (type === "Blank") return "○";
  if (type === "Carton Box") return "📦";
  if (type === "Polybag") return "▣";
  return "•";
}

function descriptionFor(type: string) {
  if (type === "Final Product") return "Finished paper cup";
  if (type === "Bottom") return "Paper cup bottom";
  if (type === "Blank") return "Paper cup blank";
  if (type === "Carton Box") return "Packing material";
  if (type === "Polybag") return "Packing material";
  return "Raw material";
}

function readableProductName(row: LiveStockRow, type: string) {
  if (type === "Final Product") return `${row.product_size_ml || ""}ml ${row.variety || "Plain White"}`.trim();
  if (type === "Bottom") return "Cup Bottom";
  if (type === "Blank") return "Cup Blank";
  if (type === "Carton Box") return "Corrugated Box";
  return row.item_name || "Inventory Item";
}

function sizeFor(row: LiveStockRow, type: string) {
  if (type === "Final Product") return row.product_size_ml ? `${row.product_size_ml}ml` : "-";
  if (type === "Bottom") return row.size_mm ? `${row.size_mm}mm` : "All Sizes";
  if (type === "Blank") {
    const match = String(row.item_name || "").match(/(\d+)\s*ml/i);
    return match ? `${match[1]}ml` : "All Sizes";
  }
  return row.packaging_size_name || row.packaging_size || "Standard";
}

function perBoxFallback(row: LiveStockRow, type: string) {
  if (type === "Bottom" && row.total_rolls) return `${formatNumber(row.total_rolls)} rolls`;
  if (type === "Blank") return "kg stock";
  return "-";
}

function statusFor(quantity: number, type: string): StockStatus {
  if (quantity <= 0) return "Out of Stock";
  const lowThreshold = type === "Final Product" || type === "Carton Box" ? 10 : 25;
  return quantity <= lowThreshold ? "Low Stock" : "In Stock";
}

function StatusBadge({ status }: { status: StockStatus }) {
  const classes = {
    "In Stock": "bg-emerald-100 text-emerald-700",
    "Low Stock": "bg-amber-100 text-amber-800",
    "Out of Stock": "bg-red-100 text-red-700"
  };
  return <span className={`inline-flex rounded-full px-2.5 py-1 text-xs font-semibold ${classes[status]}`}>{status}</span>;
}

function formatNumber(value: number) {
  return Number(value || 0).toLocaleString("en-IN");
}

function unitLabel(unit: string) {
  if (unit === "boxes") return "Boxes";
  if (unit === "pcs") return "Pcs";
  return unit || "Units";
}
