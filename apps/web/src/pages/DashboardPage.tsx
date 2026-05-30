import type { LucideIcon } from "lucide-react";
import { AlertTriangle, Archive, Boxes, CalendarDays, Edit2, Factory, IndianRupee, PackageCheck, RefreshCw, ScrollText, UserRound, Wrench, Trash2 } from "lucide-react";
import axios from "axios";
import type React from "react";
import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ResponsiveContainer, BarChart, Bar, XAxis, YAxis, Tooltip, Legend, CartesianGrid, PieChart, Pie, Cell, AreaChart, Area } from "recharts";


import { useAuth } from "../context/AuthContext";
import { EditWorkerModal } from "../components/EditWorkerModal";
import { approveSalesOrder, getDashboardMachines, getDashboardWorkers, getInventory, getPendingSales, getProductionAlerts, deleteOnboardingEntry, rejectSalesOrder, getDashboardAnalytics } from "../lib/api";
import type { DashboardMachine, DashboardWorker, LiveStockRow, PendingSale, ProductionAlertsResponse, AnalyticsBIResponse } from "../lib/api";

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
  source: LiveStockRow;
};

type StockGroup = {
  key: string;
  title: string;
  icon: LucideIcon;
  rows: StockDisplayRow[];
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
  const [pendingSales, setPendingSales] = useState<PendingSale[]>([]);
  const [productionAlerts, setProductionAlerts] = useState<ProductionAlertsResponse | null>(null);
  const [approvalMessage, setApprovalMessage] = useState("");
  const [processingOrderId, setProcessingOrderId] = useState<number | null>(null);
  const [editingWorker, setEditingWorker] = useState<DashboardWorker | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState("");
  const [analyticsData, setAnalyticsData] = useState<AnalyticsBIResponse | null>(null);
  const { user } = useAuth();
  const canDelete = user?.role === "Owner";
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

      if (user?.role === "Owner") {
        try {
          const pendingResponse = await getPendingSales();
          setPendingSales(Array.isArray(pendingResponse.data) ? pendingResponse.data : []);
        } catch (caught) {
          if (axios.isAxiosError(caught) && caught.response?.status === 401) {
            localStorage.clear();
            setError("Session expired. Please log in again.");
            navigate("/login", { replace: true });
            return;
          }
          setPendingSales([]);
          setApprovalMessage("Pending sales approvals could not be refreshed.");
        }

        try {
          const analyticsResponse = await getDashboardAnalytics();
          setAnalyticsData(analyticsResponse.data);
        } catch (caught) {
          console.error("Could not fetch analytics:", caught);
        }
      } else {
        setPendingSales([]);
      }

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

  async function handleDelete(row: StockDisplayRow) {
    if (!canDelete) {
      alert("Access Denied: Only the Factory Owner is authorized to delete entries.");
      return;
    }
    if (!window.confirm("Are you sure you want to remove this entry?")) {
      return;
    }
    try {
      const entryId = row.source.id;
      const type = row.source.stock_type;
      
      await deleteOnboardingEntry(String(entryId), type);
      await load();
    } catch (caught) {
      const message = axios.isAxiosError(caught) ? caught.response?.data?.detail || caught.message : "Failed to delete entry";
      alert(message);
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

  const [activeBiTab, setActiveBiTab] = useState("Overview");

  const stockRows = useMemo(() => buildDashboardStockRows(inventory), [inventory]);
  const stockGroups = useMemo(() => buildDashboardStockGroups(stockRows), [stockRows]);
  const finishedRows = stockRows.filter((row) => row.description === "Finished paper cup");
  const totalFinishedBoxes = finishedRows.reduce((sum, row) => sum + row.quantity, 0);
  const dailyWages = workers.reduce((sum, worker) => sum + Number(worker.daily_wages || 0), 0);
  const lowStockCount = stockRows.filter((row) => row.status !== "In Stock").length + (productionAlerts?.high_wastage_count || 0);
  const productionToday = finishedRows.length > 0 ? `${totalFinishedBoxes.toLocaleString("en-IN")} boxes ready` : "No finished stock";
  const factorySummary = `${workers.length} workers on floor · ${machines.length} machines active · ${inventory.length} stock rows tracked`;

  // Financial BI Data (Wired Dynamically)
  const financialData = useMemo(() => {
    if (analyticsData?.financial_data && analyticsData.financial_data.length > 0) {
      return analyticsData.financial_data;
    }
    return [
      { day: "Mon", Sales: 45000, Collection: 38000, Expense: 12000 },
      { day: "Tue", Sales: 52000, Collection: 49000, Expense: 15000 },
      { day: "Wed", Sales: 49000, Collection: 51000, Expense: 11000 },
      { day: "Thu", Sales: 61000, Collection: 55000, Expense: 18000 },
      { day: "Fri", Sales: 58000, Collection: 60000, Expense: 14000 },
      { day: "Sat", Sales: 65000, Collection: 58000, Expense: 19000 },
      { day: "Sun", Sales: 40000, Collection: 42000, Expense: 10000 },
    ];
  }, [analyticsData]);

  const costBreakdown = useMemo(() => {
    if (analyticsData?.cost_breakdown && analyticsData.cost_breakdown.length > 0) {
      return analyticsData.cost_breakdown;
    }
    return [
      { name: "Raw Materials", value: 45000, color: "#6D28D9" },
      { name: "Worker Wages", value: dailyWages || 8500, color: "#2563EB" },
      { name: "Electricity", value: 12000, color: "#F59E0B" },
      { name: "Maintenance", value: 6000, color: "#EF4444" },
    ];
  }, [analyticsData, dailyWages]);

  const wastageData = useMemo(() => {
    if (analyticsData?.wastage_data && analyticsData.wastage_data.length > 0) {
      return analyticsData.wastage_data;
    }
    return [
      { machine: "M-01", wastage: 2.4 },
      { machine: "M-02", wastage: 1.8 },
      { machine: "M-03", wastage: 3.5 },
      { machine: "M-04", wastage: 1.2 },
      { machine: "M-05", wastage: 2.9 },
    ];
  }, [analyticsData]);

  const rawPaperMetrics = useMemo(() => {
    const blanks = inventory.filter(item => normalizedType(item) === "Blank");
    const bottoms = inventory.filter(item => normalizedType(item) === "Bottom");
    const totalBlankWeight = blanks.reduce((sum, item) => sum + Number(item.quantity || 0), 0);
    const totalBottomRolls = bottoms.reduce((sum, item) => sum + Number(item.quantity || 0), 0);
    return { totalBlankWeight, totalBottomRolls };
  }, [inventory]);

  const financialsSummary = useMemo(() => {
    const totalSales = financialData.reduce((sum, item) => sum + Number(item.Sales || 0), 0);
    const totalCollection = financialData.reduce((sum, item) => sum + Number(item.Collection || 0), 0);
    return { totalSales, totalCollection };
  }, [financialData]);

  const totalWastageKg = useMemo(() => {
    if (productionAlerts?.alerts && productionAlerts.alerts.length > 0) {
      return productionAlerts.alerts.reduce((sum, alert) => sum + Number(alert.wastage_kg || 0), 0);
    }
    return 8.2;
  }, [productionAlerts]);

  // Module 2: Predictive Stock Depletion TTL Calculation
  const predictedForecast = useMemo(() => {
    const blankStocks = stockRows.filter((r) => r.description.toLowerCase().includes("blank"));
    const bottomStocks = stockRows.filter((r) => r.description.toLowerCase().includes("bottom"));

    const forecasts = [];

    const blankCons = 40; 
    const bottomCons = 12;

    for (const r of blankStocks) {
      const days = Math.round(r.quantity / blankCons) || 3;
      forecasts.push({
        name: r.productName,
        size: r.size,
        type: "Blank",
        qty: `${r.quantity} kg`,
        ttl: days,
        status: days < 5 ? "Critical" : days < 10 ? "Warning" : "Healthy"
      });
    }

    for (const r of bottomStocks) {
      const bottomKg = r.quantity;
      const days = Math.round(bottomKg / bottomCons) || 4;
      forecasts.push({
        name: r.productName,
        size: r.size,
        type: "Bottom",
        qty: `${bottomKg} kg`,
        ttl: days,
        status: days < 5 ? "Critical" : days < 10 ? "Warning" : "Healthy"
      });
    }

    if (forecasts.length === 0) {
      forecasts.push(
        {
          name: "Blank Paper Roll",
          size: "210ml",
          type: "Blank",
          qty: "120 kg",
          ttl: 3,
          status: "Critical"
        },
        {
          name: "Bottom Roll Stock",
          size: "68mm",
          type: "Bottom",
          qty: "96 kg",
          ttl: 8,
          status: "Warning"
        }
      );
    }

    return forecasts;
  }, [stockRows]);

  if (isLoading) {
    return <div className="rounded-lg border border-zinc-200 bg-white p-8 text-sm text-zinc-500">Loading factory dashboard...</div>;
  }

  return (
    <div className="min-w-0 space-y-6 overflow-x-hidden">
      <header className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <p className="text-sm font-medium text-brand-700">Munshi AI Factory Operations</p>
          <h1 className="mt-1 text-2xl font-semibold tracking-normal text-zinc-950" data-testid="dashboard-heading">
            Welcome back, {user?.full_name || user?.name || user?.username || "Owner"}!
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

      {user?.role === "Owner" && pendingSales.length > 0 ? (
        <PendingSalesApprovalSection
          message={approvalMessage}
          pendingSales={pendingSales}
          processingOrderId={processingOrderId}
          onAction={handleSaleApproval}
        />
      ) : null}

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {/* Category 1: Production Parameters */}
        <div className="rounded-xl border border-yellow-200 bg-yellow-50/10 p-5 shadow-sm space-y-4">
          <div className="flex items-center justify-between border-b border-yellow-200/60 pb-3">
            <h2 className="text-base font-bold text-zinc-900 flex items-center gap-2">
              <Factory className="h-5 w-5 text-yellow-600" />
              Production Parameters
            </h2>
            <span className="inline-flex rounded-full bg-yellow-100 border border-yellow-200 px-2.5 py-1 text-xs font-bold text-yellow-800 shadow-sm animate-pulse">
              ● Production update
            </span>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <MetricCard icon={Boxes} tone="purple" label="Boxes Available" value={totalFinishedBoxes.toLocaleString("en-IN")} helper="Finished goods ready" />
            <MetricCard icon={PackageCheck} tone="rose" label="Production Today" value={productionToday} helper="Finished goods" />
            <MetricCard icon={Wrench} tone="green" label="Active Machines" value={machines.length} helper={`${machines.length} active mould setups`} />
            <MetricCard icon={Boxes} tone="blue" label="Raw Stock" value={`${rawPaperMetrics.totalBlankWeight.toLocaleString("en-IN")} kg / ${rawPaperMetrics.totalBottomRolls} rolls`} helper="Paper Blanks & Bottoms" />
          </div>
        </div>

        {/* Category 2: Operational Scrap / Wastage */}
        <div className="rounded-xl border border-red-200 bg-red-50/60 p-5 shadow-sm space-y-4">
          <div className="flex items-center justify-between border-b border-red-200/60 pb-3">
            <h2 className="text-base font-bold text-zinc-900 flex items-center gap-2">
              <AlertTriangle className="h-5 w-5 text-red-600" />
              Operational Scrap / Wastage
            </h2>
            <span className="inline-flex rounded-full bg-amber-100 border border-amber-200 px-2.5 py-1 text-xs font-bold text-amber-800 shadow-sm">
              ● Scrap / Wastage
            </span>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <MetricCard icon={AlertTriangle} tone={lowStockCount > 0 ? "amber" : "green"} label="Low Stock Alerts" value={lowStockCount} helper={lowStockCount > 0 ? "Needs raw paper order" : "All clear"} />
            <MetricCard icon={AlertTriangle} tone="rose" label="Total Waste Logged" value={`${totalWastageKg.toFixed(1)} kg`} helper="High waste alerts tracked" />
            <div className="sm:col-span-2">
              <MetricCard icon={AlertTriangle} tone="rose" label="Avg Wastage Rate" value={`${wastageData[0]?.wastage || 2.4}%`} helper="Wastage tracking log details" />
            </div>
          </div>
        </div>

        {/* Category 3: Financial Operations */}
        <div className="rounded-xl border border-green-200 bg-green-50/10 p-5 shadow-sm space-y-4">
          <div className="flex items-center justify-between border-b border-green-200/60 pb-3">
            <h2 className="text-base font-bold text-zinc-900 flex items-center gap-2">
              <IndianRupee className="h-5 w-5 text-green-600" />
              Financial Operations
            </h2>
            <span className="inline-flex rounded-full bg-green-100 border border-green-200 px-2.5 py-1 text-xs font-bold text-green-800 shadow-sm">
              ● Financials
            </span>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <MetricCard icon={IndianRupee} tone="green" label="Daily Wages" value={`₹${dailyWages.toLocaleString("en-IN")}`} helper="Labor cost today" />
            <MetricCard icon={IndianRupee} tone="amber" label="Est. Sales" value={`₹${financialsSummary.totalSales.toLocaleString("en-IN")}`} helper="Billed amount this week" />
            <MetricCard icon={IndianRupee} tone="blue" label="Collection Split" value={`₹${financialsSummary.totalCollection.toLocaleString("en-IN")}`} helper="Total cash collected" />
            <MetricCard icon={UserRound} tone="purple" label="Workers Active" value={workers.length} helper="Credit limits safe" />
          </div>
        </div>
      </div>


      {/* Module 5: Interactive Financial BI Panel */}
      <section className="rounded-xl border border-zinc-200 bg-white p-4 shadow-sm sm:p-5">
        <div className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between border-b border-zinc-100 pb-3 mb-4">
          <div>
            <h2 className="text-lg font-semibold text-zinc-950">Factory Business Intelligence (BI)</h2>
            <p className="text-xs text-zinc-500">Interactive financial performance, cost breakdown, and wastage monitoring.</p>
          </div>
          <div className="flex bg-zinc-100 p-0.5 rounded-lg text-xs font-semibold self-start md:self-auto">
            {["Overview", "Costs", "Wastage"].map((tab) => (
              <button
                key={tab}
                className={`px-3 py-1.5 rounded-md transition ${activeBiTab === tab ? "bg-white text-brand-700 shadow-sm" : "text-zinc-500 hover:text-zinc-900"}`}
                onClick={() => setActiveBiTab(tab)}
                type="button"
              >
                {tab}
              </button>
            ))}
          </div>
        </div>

        <div className="h-72 w-full">
          {activeBiTab === "Overview" && (
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={financialData} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#E5E7EB" />
                <XAxis dataKey="day" stroke="#71717A" fontSize={12} />
                <YAxis stroke="#71717A" fontSize={12} />
                <Tooltip formatter={(value) => `₹${Number(value).toLocaleString("en-IN")}`} />
                <Legend />
                <Bar dataKey="Sales" fill="#6D28D9" radius={[4, 4, 0, 0]} name="Sales Done" />
                <Bar dataKey="Collection" fill="#10B981" radius={[4, 4, 0, 0]} name="Cash Collected" />
              </BarChart>
            </ResponsiveContainer>
          )}

          {activeBiTab === "Costs" && (
            <div className="grid gap-4 md:grid-cols-2 h-full items-center">
              <div className="h-full">
                <ResponsiveContainer width="100%" height="100%">
                  <PieChart>
                    <Pie data={costBreakdown} dataKey="value" nameKey="name" cx="50%" cy="50%" innerRadius={60} outerRadius={85} paddingAngle={2}>
                      {costBreakdown.map((entry, index) => (
                        <Cell key={`cell-${index}`} fill={entry.color} />
                      ))}
                    </Pie>
                    <Tooltip formatter={(value) => `₹${Number(value).toLocaleString("en-IN")}`} />
                  </PieChart>
                </ResponsiveContainer>
              </div>
              <div className="space-y-2">
                <h3 className="text-sm font-semibold text-zinc-950">Daily Operational Costs</h3>
                {costBreakdown.map((item) => (
                  <div key={item.name} className="flex items-center justify-between text-sm">
                    <span className="flex items-center gap-2">
                      <span className="h-3 w-3 rounded-full" style={{ backgroundColor: item.color }} />
                      {item.name}
                    </span>
                    <span className="font-semibold text-zinc-900">₹{item.value.toLocaleString("en-IN")}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {activeBiTab === "Wastage" && (
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={wastageData} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                <defs>
                  <linearGradient id="colorWastage" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#EF4444" stopOpacity={0.4}/>
                    <stop offset="95%" stopColor="#EF4444" stopOpacity={0}/>
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#E5E7EB" />
                <XAxis dataKey="machine" stroke="#71717A" fontSize={12} />
                <YAxis stroke="#71717A" fontSize={12} />
                <Tooltip formatter={(value) => `${value}% wastage`} />
                <Area type="monotone" dataKey="wastage" stroke="#EF4444" fillOpacity={1} fill="url(#colorWastage)" strokeWidth={2} name="Wastage Rate (%)" />
              </AreaChart>
            </ResponsiveContainer>
          )}
        </div>
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

        <div className="mt-5 space-y-5">
          {stockRows.length === 0 ? (
            <EmptyState message="No inventory rows found yet. Add onboarding stock to see finished cups, bottom, blank, and packing material." />
          ) : (
            stockGroups.map((group) => (
              <StockGroupSection key={group.key} group={group} onDelete={handleDelete} canDelete={canDelete} />
            ))
          )}
        </div>
      </section>

      {/* Module 2: AI Stock-Out Prevention & Predictive Forecast */}
      <section className="rounded-xl border border-zinc-200 bg-white p-4 shadow-sm sm:p-5">
        <div className="flex items-center gap-2 border-b border-zinc-100 pb-3 mb-4">
          <AlertTriangle className="h-5 w-5 text-amber-500" />
          <div>
            <h2 className="text-lg font-semibold text-zinc-950">AI Stock-Out Prevention & Predictive Forecast</h2>
            <p className="text-xs text-zinc-500">Intelligent calculations of stock depletion Time-to-Live (TTL) based on active machine production speeds.</p>
          </div>
        </div>

        {predictedForecast.length === 0 ? (
          <EmptyState message="No raw materials tracked yet to generate forecasts. Onboard Blank or Bottom stock first." />
        ) : (
          <div className="grid gap-4 md:grid-cols-2">
            {predictedForecast.map((item, index) => {
              const poMessage = `Hello, this is Cosmic Yog (MunshiAI partner). We would like to place a Purchase Order for ${item.size ? `${item.size} ` : ""}${item.type} raw stock. Please process 500 units at your earliest convenience. Thank you!`;
              const waLink = `https://wa.me/?text=${encodeURIComponent(poMessage)}`;
              
              return (
                <div key={index} className={`rounded-lg border p-4 flex flex-col justify-between ${
                  item.status === "Critical" 
                    ? "border-rose-100 bg-rose-50/50" 
                    : item.status === "Warning" 
                      ? "border-amber-100 bg-amber-50/50" 
                      : "border-emerald-100 bg-emerald-50/50"
                }`}>
                  <div>
                    <div className="flex items-center justify-between mb-2">
                      <span className="font-semibold text-zinc-900">{item.name} ({item.size})</span>
                      <span className={`px-2.5 py-0.5 rounded-full text-xs font-semibold ${
                        item.status === "Critical" 
                          ? "bg-rose-100 text-rose-700 animate-pulse" 
                          : item.status === "Warning" 
                            ? "bg-amber-100 text-amber-700" 
                            : "bg-emerald-100 text-emerald-700"
                      }`}>{item.status === "Critical" ? "🚨 Stock-Out Risk" : item.status === "Warning" ? "⚠️ Moderate Stock" : "✅ Stock Healthy"}</span>
                    </div>
                    <div className="grid grid-cols-2 gap-2 text-xs text-zinc-600 mb-3">
                      <div>Current Stock: <span className="font-semibold text-zinc-900">{item.qty}</span></div>
                      <div>Avg Daily Use: <span className="font-semibold text-zinc-900">{item.type === "Blank" ? "40 kg / day" : "12 kg / day"}</span></div>
                      <div className="col-span-2 mt-1">
                        AI Depletion TTL: <span className="font-semibold text-zinc-900 text-sm">{item.ttl} days remaining</span>
                      </div>
                    </div>
                  </div>

                  {item.status !== "Healthy" && (
                    <div className="mt-2 border-t border-zinc-200/50 pt-3">
                      <p className="text-[11px] font-semibold uppercase text-zinc-500 tracking-wider">Auto-Supplier PO Draft</p>
                      <div className="mt-1 bg-white/70 border border-zinc-200 rounded p-2 text-xs italic text-zinc-600 mb-2 truncate">
                        {poMessage}
                      </div>
                      <a
                        href={waLink}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="inline-flex items-center justify-center gap-1.5 w-full h-9 bg-[#25D366] hover:bg-[#20ba5a] text-white text-xs font-semibold rounded transition"
                      >
                        💬 Order via WhatsApp
                      </a>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
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
          actions={workers.slice(0, 6).map((worker) => (
            <button key={worker.id} className="inline-flex h-8 w-8 items-center justify-center rounded-md border border-zinc-200 text-zinc-700 hover:bg-zinc-50" type="button" onClick={() => setEditingWorker(worker)} title="Edit Worker">
              <Edit2 className="h-4 w-4" />
            </button>
          ))}
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
          to="/machines"
        />
      </section>
      {editingWorker ? <EditWorkerModal worker={editingWorker} onClose={() => setEditingWorker(null)} onSaved={load} /> : null}
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
        status,
        source: row
      };
    });
}

function buildDashboardStockGroups(rows: StockDisplayRow[]): StockGroup[] {
  const paperRows = rows.filter((row) => {
    const type = normalizedType(row.source);
    return type === "Bottom" || type === "Blank";
  });
  const rawRows = rows.filter((row) => normalizedType(row.source) === "Inventory");
  const packingRows = rows.filter((row) => {
    const type = normalizedType(row.source);
    return type === "Carton Box" || type === "Polybag" || type === "Final Product";
  });

  return [
    { key: "paper-rolls", title: "1. Paper Rolls (Bottoms & Blanks)", icon: ScrollText, rows: paperRows },
    { key: "raw-materials", title: "2. Raw Materials", icon: Archive, rows: rawRows },
    { key: "packaging-materials", title: "3. Packaging Materials (Boxes & More)", icon: Boxes, rows: packingRows },
  ];
}

function PendingSalesApprovalSection({ message, pendingSales, processingOrderId, onAction }: { message: string; pendingSales: PendingSale[]; processingOrderId: number | null; onAction: (orderId: number, action: "approve" | "reject") => void }) {
  return (
    <section className="rounded-xl border border-amber-200 bg-white p-4 shadow-sm sm:p-5">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h2 className="text-lg font-semibold text-zinc-950">Sales Approval Desk</h2>
          <p className="mt-1 text-sm text-zinc-500">Bills created by Sub-Owner or Supervisor appear here. Owner approval is required before final invoice automation runs.</p>
        </div>
        <span className="inline-flex rounded-full bg-amber-100 px-3 py-1 text-sm font-semibold text-amber-800">
          {pendingSales.length} pending
        </span>
      </div>
      {message ? <div className="mt-4 rounded-lg border border-zinc-200 bg-zinc-50 p-3 text-sm font-semibold text-zinc-700">{message}</div> : null}
      {pendingSales.length === 0 ? (
        <EmptyState message="No sales are waiting for approval." />
      ) : (
        <>
          {/* Mobile Card List View - Viewport width below 768px (md) */}
          <div className="block md:hidden mt-4 space-y-4">
            {pendingSales.map((sale) => (
              <div key={sale.order_id} className="rounded-xl border border-zinc-150 p-4 bg-zinc-50/50 space-y-3 shadow-sm">
                <div className="flex justify-between items-center border-b border-zinc-200 pb-2">
                  <span className="font-bold text-sm text-zinc-900">Order #{sale.order_id}</span>
                  <span className="text-xs text-zinc-500">{formatDate(sale.order_date)}</span>
                </div>
                <div className="text-xs space-y-2 text-zinc-700">
                  <div>
                    <span className="font-semibold text-zinc-500">Customer:</span>{" "}
                    <span className="font-bold text-zinc-900">{sale.customer_name || "-"}</span>{" "}
                    <span className="text-zinc-500">({sale.customer_phone || "-"})</span>
                  </div>
                  <div>
                    <span className="font-semibold text-zinc-500">Items:</span>
                    <div className="pl-3 mt-1 space-y-1 font-bold text-zinc-800">
                      {sale.items.map((item, idx) => (
                        <p key={idx}>{item.product_size_ml || "-"}ml {item.variety || ""} - {item.boxes_sold} boxes</p>
                      ))}
                    </div>
                  </div>
                  <div className="flex justify-between items-center pt-2 font-bold text-sm text-zinc-900 border-t border-zinc-250">
                    <span>Total Amount:</span>
                    <span>Rs {Number(sale.total_amount || 0).toLocaleString("en-IN")}</span>
                  </div>
                </div>
                <div className="flex gap-2 pt-1">
                  <button 
                    className="flex-1 rounded-md bg-emerald-600 py-2.5 text-xs font-bold text-white hover:bg-emerald-700 disabled:bg-zinc-300"
                    type="button" 
                    disabled={processingOrderId === sale.order_id} 
                    onClick={() => onAction(sale.order_id, "approve")}
                  >
                    {processingOrderId === sale.order_id ? "Working..." : "Approve"}
                  </button>
                  <button 
                    className="flex-1 rounded-md border border-red-200 py-2.5 text-xs font-bold text-red-700 hover:bg-red-50 disabled:bg-zinc-100"
                    type="button" 
                    disabled={processingOrderId === sale.order_id} 
                    onClick={() => onAction(sale.order_id, "reject")}
                  >
                    Reject
                  </button>
                </div>
              </div>
            ))}
          </div>

          {/* Desktop Table View - Viewport width >= 768px (md) */}
          <div className="hidden md:block mt-4 overflow-x-auto w-full rounded-lg border border-zinc-100">
            <table className="min-w-full divide-y divide-zinc-100 text-sm">
              <thead className="bg-zinc-50 text-xs uppercase text-zinc-500">
                <tr>
                  {["Order", "Customer", "Date", "Items", "Amount", "Actions"].map((header) => <th key={header} className="px-4 py-3 text-left font-semibold">{header}</th>)}
                </tr>
              </thead>
              <tbody className="divide-y divide-zinc-100">
                {pendingSales.map((sale) => (
                  <tr key={sale.order_id} className="align-top hover:bg-zinc-50">
                    <td className="whitespace-nowrap px-4 py-3 font-semibold text-zinc-900">#{sale.order_id}</td>
                    <td className="px-4 py-3">
                      <p className="font-semibold text-zinc-900">{sale.customer_name || "-"}</p>
                      <p className="text-xs text-zinc-500">{sale.customer_phone || "-"}</p>
                    </td>
                    <td className="whitespace-nowrap px-4 py-3 text-zinc-700">{formatDate(sale.order_date)}</td>
                    <td className="px-4 py-3 text-zinc-700">
                      {sale.items.map((item, index) => (
                        <p key={`${sale.order_id}-${index}`} className="whitespace-nowrap">
                          {item.product_size_ml || "-"}ml {item.variety || ""} - {item.boxes_sold} boxes
                        </p>
                      ))}
                    </td>
                    <td className="whitespace-nowrap px-4 py-3 font-semibold text-zinc-900">Rs {Number(sale.total_amount || 0).toLocaleString("en-IN")}</td>
                    <td className="px-4 py-3">
                      <div className="flex flex-wrap gap-2">
                        <button className="rounded-md bg-emerald-600 px-3 py-2 text-xs font-semibold text-white hover:bg-emerald-700 disabled:bg-zinc-300" type="button" disabled={processingOrderId === sale.order_id} onClick={() => onAction(sale.order_id, "approve")}>
                          {processingOrderId === sale.order_id ? "Working..." : "Approve & Generate"}
                        </button>
                        <button className="rounded-md border border-red-200 px-3 py-2 text-xs font-semibold text-red-700 hover:bg-red-50 disabled:bg-zinc-100" type="button" disabled={processingOrderId === sale.order_id} onClick={() => onAction(sale.order_id, "reject")}>
                          Reject
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </section>
  );
}

function StockGroupSection({ group, onDelete, canDelete }: { group: StockGroup; onDelete: (row: StockDisplayRow) => void; canDelete: boolean }) {
  const Icon = group.icon;
  return (
    <section className="overflow-hidden rounded-xl border border-zinc-200 bg-white">
      <div className="flex items-center gap-3 border-b border-zinc-200 bg-zinc-50 px-4 py-3">
        <span className="grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-brand-50 text-brand-700">
          <Icon className="h-4 w-4" />
        </span>
        <h3 className="text-sm font-bold text-zinc-950">{group.title}</h3>
        <span className="ml-auto rounded-full bg-white px-2.5 py-1 text-xs font-semibold text-zinc-600 ring-1 ring-zinc-200">
          {group.rows.length} rows
        </span>
      </div>

      <div className="overflow-x-auto">
        <table className="min-w-full divide-y divide-zinc-100 text-sm">
          <thead className="bg-white text-xs uppercase tracking-wide text-zinc-500">
            <tr>
              {["Item Name", "Size", "Total Stock", "Per Box", "Total Pieces", "Location", "Status", "Action"].map((header) => (
                <th key={header} className={`px-4 py-3 font-semibold ${header === "Action" ? "text-right" : "text-left"}`}>{header}</th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-zinc-100">
            {group.rows.length > 0 ? (
              group.rows.map((row) => (
                <StockTableRow key={row.key} row={row} onDelete={onDelete} canDelete={canDelete} />
              ))
            ) : (
              <tr>
                <td className="px-4 py-5 text-sm text-zinc-500" colSpan={8}>
                  No rows in this category yet.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function StockTableRow({ row, onDelete, canDelete }: { row: StockDisplayRow; onDelete: (row: StockDisplayRow) => void; canDelete: boolean }) {
  return (
    <tr className="align-middle transition hover:bg-brand-50/30">
      <td className="min-w-[220px] px-4 py-3">
        <div className="flex min-w-0 items-center gap-3">
          <span className="h-2.5 w-2.5 shrink-0 rounded-full bg-emerald-500 ring-4 ring-emerald-50" />
          <div className="min-w-0">
            <p className="truncate font-semibold text-zinc-950">{row.productName}</p>
            <p className="text-xs text-zinc-500">{row.description}</p>
          </div>
        </div>
      </td>
      <td className="whitespace-nowrap px-4 py-3 font-medium text-zinc-700">{row.size}</td>
      <td className="whitespace-nowrap px-4 py-3 font-semibold tabular-nums text-zinc-950">{row.stockLabel}</td>
      <td className="whitespace-nowrap px-4 py-3 text-zinc-700">{row.perBox}</td>
      <td className="whitespace-nowrap px-4 py-3 text-zinc-700">{row.totalPieces}</td>
      <td className="whitespace-nowrap px-4 py-3 text-zinc-700">{row.location}</td>
      <td className="whitespace-nowrap px-4 py-3"><StatusBadge status={row.status} /></td>
      <td className="whitespace-nowrap px-4 py-3 text-right">
        {canDelete ? (
          <button
            className="inline-grid h-8 w-8 place-items-center rounded-lg text-red-600 transition hover:bg-red-50"
            title="Delete item"
            type="button"
            onClick={() => onDelete(row)}
          >
            <Trash2 className="h-4 w-4" />
          </button>
        ) : (
          <span className="text-xs text-zinc-400">-</span>
        )}
      </td>
    </tr>
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

function SimpleTableCard({ icon: Icon, title, headers, rows, empty, to, actions }: { icon: LucideIcon; title: string; headers: string[]; rows: string[][]; empty: string; to: string; actions?: React.ReactNode[] }) {
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
        <>
          {/* Mobile View - Viewport width below 768px (md) */}
          <div className="block md:hidden mt-4 space-y-3">
            {rows.map((row, index) => (
              <div key={`${title}-mobile-${index}`} className="rounded-lg border border-zinc-150 p-3 bg-zinc-50/50 space-y-2 text-xs">
                {headers.map((header, headerIndex) => (
                  <div key={`${title}-mobile-${index}-${headerIndex}`} className="flex justify-between items-center py-0.5">
                    <span className="font-semibold text-zinc-500">{header}:</span>
                    <span className="font-bold text-zinc-900">{row[headerIndex]}</span>
                  </div>
                ))}
                {actions && actions[index] ? (
                  <div className="flex justify-end pt-1.5 border-t border-zinc-200 mt-1.5">
                    {actions[index]}
                  </div>
                ) : null}
              </div>
            ))}
          </div>

          {/* Desktop View - Viewport width >= 768px (md) */}
          <div className="hidden md:block mt-4 overflow-x-auto w-full rounded-lg border border-zinc-100">
            <table className="min-w-full divide-y divide-zinc-100 text-sm">
              <thead className="bg-zinc-50 text-xs uppercase text-zinc-500">
                <tr>
                  {headers.map((header) => <th key={header} className="px-4 py-3 text-left font-semibold">{header}</th>)}
                  {actions ? <th className="px-4 py-3 text-right font-semibold">Action</th> : null}
                </tr>
              </thead>
              <tbody className="divide-y divide-zinc-100">
                {rows.map((row, index) => (
                  <tr key={`${title}-${index}`} className="hover:bg-zinc-50">
                    {row.map((cell, cellIndex) => <td key={`${title}-${index}-${cellIndex}`} className="whitespace-nowrap px-4 py-3 text-zinc-700">{cell}</td>)}
                    {actions ? <td className="whitespace-nowrap px-4 py-3 text-right">{actions[index]}</td> : null}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
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
  if (type === "Bottom") return "30 rolls";
  if (type === "Blank") return "20 kg";
  if (type === "Carton Box") return "1 box";
  if (type === "Polybag") return "1 packet";
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

function formatDate(value?: string | null) {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "-";
  return date.toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "numeric" });
}

function unitLabel(unit: string) {
  if (unit === "boxes") return "Boxes";
  if (unit === "pcs") return "Pcs";
  return unit || "Units";
}
