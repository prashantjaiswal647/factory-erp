import { AlertTriangle, Bell, Bot, Boxes, Check, Factory, IndianRupee, PackageCheck, RefreshCw, Trash2, UserRound, WalletCards, Wrench, X } from "lucide-react";
import axios from "axios";
import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { useAuth } from "../context/AuthContext";
import {
  getDashboardMachines,
  getDashboardMaterials,
  getDashboardCustomers,
  getDashboardWorkers,
  getInventory,
  getProductionAlerts,
  getAiDashboardInsights,
  deleteDashboardCustomer,
  deleteDashboardMachine,
  deleteDashboardRawMaterial,
  deleteDashboardWorker,
  getPendingSales,
  approveSalesOrder,
  rejectSalesOrder,
  getPendingPaymentDues,
  triggerPaymentReminders
} from "../lib/api";
import type { AiDashboardInsights, DashboardCustomer, DashboardMachine, DashboardMaterials, DashboardWorker, LiveStockRow, PendingDue, PendingSale, ProductionAlertsResponse } from "../lib/api";

export default function DashboardPage() {
  const [workers, setWorkers] = useState<DashboardWorker[]>([]);
  const [machines, setMachines] = useState<DashboardMachine[]>([]);
  const [customers, setCustomers] = useState<DashboardCustomer[]>([]);
  const [materials, setMaterials] = useState<DashboardMaterials>({ raw_material_metrics: [], packaging_metrics: [] });
  const [inventory, setInventory] = useState<LiveStockRow[]>([]);
  const [productionAlerts, setProductionAlerts] = useState<ProductionAlertsResponse | null>(null);
  const [pendingSales, setPendingSales] = useState<PendingSale[]>([]);
  const [pendingDues, setPendingDues] = useState<PendingDue[]>([]);
  const [isApprovalsOpen, setIsApprovalsOpen] = useState(false);
  const [isTriggeringReminders, setIsTriggeringReminders] = useState(false);
  const [aiInsights, setAiInsights] = useState<AiDashboardInsights | null>(null);
  const [typedInsight, setTypedInsight] = useState("");
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState("");
  const [toast, setToast] = useState<{ type: "success" | "error"; message: string } | null>(null);
  const { user } = useAuth();
  const navigate = useNavigate();

  useEffect(() => {
    void load();
  }, []);

  async function load() {
    setIsLoading(true);
    setError("");
    try {
      const [workerRes, machineRes, materialRes, customerRes, inventoryRes, alertRes, aiRes, pendingRes, duesRes] = await Promise.all([
        getDashboardWorkers(),
        getDashboardMachines(),
        getDashboardMaterials(),
        getDashboardCustomers(),
        getInventory(),
        getProductionAlerts(),
        getAiDashboardInsights(),
        user?.role === "Owner" ? getPendingSales() : Promise.resolve({ data: [] as PendingSale[] }),
        user?.role === "Owner" ? getPendingPaymentDues() : Promise.resolve({ data: [] as PendingDue[] })
      ]);
      setWorkers(workerRes.data);
      setMachines(machineRes.data);
      setMaterials(materialRes.data);
      setCustomers(customerRes.data);
      setInventory(inventoryRes.data);
      setProductionAlerts(alertRes.data);
      setAiInsights(aiRes.data);
      setPendingSales(pendingRes.data);
      setPendingDues(duesRes.data);
    } catch (caught) {
      if (axios.isAxiosError(caught) && caught.response?.status === 401) {
        localStorage.clear();
        setError("Session expired. Please log in again.");
        navigate("/login", { replace: true });
        return;
      }
      if (axios.isAxiosError(caught)) {
        const detail = caught.response?.data?.detail;
        setError(`Dashboard request failed (${caught.response?.status ?? "network"}): ${typeof detail === "string" ? detail : caught.message}`);
        return;
      }
      setError("Dashboard request failed: unexpected client error.");
    } finally {
      setIsLoading(false);
    }
  }

  async function handleDelete(type: "worker" | "machine" | "raw-material" | "customer", id: number) {
    if (!window.confirm("Delete this entry?")) return;

    try {
      if (type === "worker") {
        await deleteDashboardWorker(id);
        setWorkers((current) => current.filter((item) => item.id !== id));
      }
      if (type === "machine") {
        await deleteDashboardMachine(id);
        setMachines((current) => current.filter((item) => item.id !== id));
      }
      if (type === "raw-material") {
        await deleteDashboardRawMaterial(id);
        setMaterials((current) => ({
          ...current,
          raw_material_metrics: current.raw_material_metrics.filter((item) => item.id !== id)
        }));
      }
      if (type === "customer") {
        await deleteDashboardCustomer(id);
        setCustomers((current) => current.filter((item) => item.id !== id));
      }
      setToast({ type: "success", message: "Entry deleted" });
    } catch (caught) {
      const message = axios.isAxiosError(caught) ? caught.response?.data?.detail || caught.message : "Delete failed";
      setToast({ type: "error", message });
    }
  }

  async function handleApproval(orderId: number, action: "approve" | "reject") {
    try {
      const response = action === "approve" ? await approveSalesOrder(orderId) : await rejectSalesOrder(orderId);
      setPendingSales((current) => current.filter((sale) => sale.order_id !== orderId));
      setToast({
        type: "success",
        message: action === "approve" ? "Bill sent to Customer via WhatsApp." : response.data.message
      });
    } catch (caught) {
      const message = axios.isAxiosError(caught) ? caught.response?.data?.detail || caught.message : "Approval action failed";
      setToast({ type: "error", message });
    }
  }

  async function handleTriggerPaymentReminders() {
    setIsTriggeringReminders(true);
    try {
      const response = await triggerPaymentReminders();
      setToast({ type: "success", message: response.data.message });
    } catch (caught) {
      const message = axios.isAxiosError(caught) ? caught.response?.data?.detail || caught.message : "Payment reminder trigger failed";
      setToast({ type: "error", message });
    } finally {
      setIsTriggeringReminders(false);
    }
  }

  const stockStatus = useMemo(() => {
    if (inventory.length === 0) return "Not initialized";
    if (inventory.some((row) => Number(row.quantity) < 0)) return "Negative stock";
    return "Ready";
  }, [inventory]);

  const materialMappings = useMemo(() => {
    return materials.raw_material_metrics.map((metric) => {
      const machine = machines.find((item) => item.mould_size_ml === metric.size_ml_or_mm || item.bottom_size_mm === metric.size_ml_or_mm);
      return {
        id: metric.id,
        label: `${metric.size_ml_or_mm}${metric.material_type === "Blank" ? "ml" : "mm"} ${metric.material_type}`,
        target: machine?.machine_number || "Unmapped",
        percent: machine ? 100 : 35
      };
    });
  }, [machines, materials.raw_material_metrics]);

  const bottomStockRows = useMemo(() => inventory.filter((row) => row.stock_type === "Bottom"), [inventory]);

  useEffect(() => {
    if (!aiInsights?.insights) return;
    setTypedInsight("");
    let index = 0;
    const timer = window.setInterval(() => {
      index += 1;
      setTypedInsight(aiInsights.insights.slice(0, index));
      if (index >= aiInsights.insights.length) {
        window.clearInterval(timer);
      }
    }, 14);
    return () => window.clearInterval(timer);
  }, [aiInsights?.insights]);

  if (isLoading) {
    return <div className="rounded-lg border border-zinc-200 bg-white p-8 text-sm text-zinc-500">Loading live factory overview...</div>;
  }

  if (error) {
    return <div className="rounded-lg border border-red-200 bg-red-50 p-8 text-sm font-medium text-red-700">{error}</div>;
  }

  return (
    <div className="space-y-6">
      {toast ? <Toast type={toast.type} message={toast.message} onClose={() => setToast(null)} /> : null}
      <header className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-zinc-950">Live Factory Overview</h1>
          <p className="mt-1 text-sm text-zinc-500">Workers, machines, material mapping, and opening stock status.</p>
        </div>
        <button className="inline-flex h-10 items-center gap-2 rounded-md border border-zinc-200 bg-white px-4 text-sm font-semibold text-zinc-700 hover:bg-zinc-50" type="button" onClick={load}>
          <RefreshCw className="h-4 w-4" />
          Refresh
        </button>
      </header>

      {user?.role === "Owner" ? <section className="rounded-lg border border-amber-200 bg-amber-50 p-5 shadow-sm">
        <button className="flex w-full items-center justify-between gap-4 text-left" type="button" onClick={() => setIsApprovalsOpen((current) => !current)}>
          <span className="flex items-center gap-3">
            <span className="relative grid h-10 w-10 place-items-center rounded-md bg-amber-100 text-amber-800">
              <Bell className="h-5 w-5" />
              {pendingSales.length > 0 ? <span className="absolute -right-1 -top-1 grid h-5 min-w-5 place-items-center rounded-full bg-red-600 px-1 text-xs font-bold text-white">{pendingSales.length}</span> : null}
            </span>
            <span>
              <span className="block text-base font-semibold text-amber-950">Pending Approvals</span>
              <span className="text-sm text-amber-800">{pendingSales.length} sales waiting for owner confirmation</span>
            </span>
          </span>
          <span className="text-sm font-semibold text-amber-900">{isApprovalsOpen ? "Hide" : "View"}</span>
        </button>

        {isApprovalsOpen ? (
          <div className="mt-4 space-y-3">
            {pendingSales.length === 0 ? (
              <p className="rounded-md bg-white/70 p-4 text-sm text-amber-900">No pending sales.</p>
            ) : (
              pendingSales.map((sale) => (
                <div key={sale.order_id} className="rounded-md border border-amber-200 bg-white p-4">
                  <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
                    <div>
                      <p className="font-semibold text-zinc-950">Order #{sale.order_id} - {sale.customer_name}</p>
                      <p className="mt-1 text-sm text-zinc-600">{sale.customer_phone || "No phone"} · Rs {Number(sale.total_amount).toLocaleString("en-IN")}</p>
                      <div className="mt-2 space-y-1 text-sm text-zinc-600">
                        {sale.items.map((item, index) => (
                          <p key={`${sale.order_id}-${index}`}>
                            {item.product_size_ml || "-"}ml {item.variety || ""} {item.packaging_size_name || ""} · {item.boxes_sold} boxes {item.loose_packets_sold ? `+ ${item.loose_packets_sold} loose` : ""}
                          </p>
                        ))}
                      </div>
                    </div>
                    <div className="flex gap-2">
                      <button className="inline-flex h-9 items-center gap-2 rounded-md bg-emerald-600 px-3 text-sm font-semibold text-white hover:bg-emerald-700" type="button" onClick={() => handleApproval(sale.order_id, "approve")}>
                        <Check className="h-4 w-4" />
                        Approve
                      </button>
                      <button className="inline-flex h-9 items-center gap-2 rounded-md border border-red-200 bg-white px-3 text-sm font-semibold text-red-700 hover:bg-red-50" type="button" onClick={() => handleApproval(sale.order_id, "reject")}>
                        <X className="h-4 w-4" />
                        Reject
                      </button>
                    </div>
                  </div>
                </div>
              ))
            )}
          </div>
        ) : null}
      </section> : null}

      {user?.role === "Owner" ? (
        <section className="rounded-lg border border-zinc-200 bg-white p-5 shadow-sm">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <SectionTitle icon={WalletCards} title="Outstanding Payment Dues Tracker" />
            <button
              className="inline-flex h-10 items-center justify-center rounded-md bg-brand-600 px-4 text-sm font-semibold text-white hover:bg-brand-700 disabled:bg-zinc-300"
              disabled={isTriggeringReminders}
              type="button"
              onClick={handleTriggerPaymentReminders}
            >
              {isTriggeringReminders ? "Pushing reminders..." : "⚡ Trigger Automated WhatsApp Reminders Now"}
            </button>
          </div>

          <div className="mt-4 overflow-x-auto">
            <table className="min-w-full divide-y divide-zinc-200">
              <thead className="bg-zinc-50">
                <tr>
                  <Th>Customer Name</Th>
                  <Th>Phone</Th>
                  <Th>Invoice Reference</Th>
                  <Th align="right">Total Bill</Th>
                  <Th align="right">Pending Balance</Th>
                  <Th>Status</Th>
                </tr>
              </thead>
              <tbody className="divide-y divide-zinc-100">
                {pendingDues.length === 0 ? (
                  <tr>
                    <td className="px-4 py-5 text-sm text-zinc-500" colSpan={6}>No unpaid or half-paid invoices.</td>
                  </tr>
                ) : (
                  pendingDues.map((due) => (
                    <tr key={due.invoice_id} className="hover:bg-zinc-50">
                      <Td strong>{due.customer_name}</Td>
                      <Td>{due.customer_phone || "-"}</Td>
                      <Td>INV-{due.invoice_id}</Td>
                      <Td align="right">Rs {Number(due.total_amount || 0).toLocaleString("en-IN")}</Td>
                      <Td align="right">Rs {Number(due.pending_amount || 0).toLocaleString("en-IN")}</Td>
                      <Td>
                        <span className={`inline-flex rounded-full px-2 py-1 text-xs font-semibold ${due.payment_status === "Half-Paid" ? "bg-amber-100 text-amber-800" : "bg-red-100 text-red-700"}`}>
                          {due.payment_status}
                        </span>
                      </Td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </section>
      ) : null}

      <section className="overflow-hidden rounded-lg border border-[#004D40]/30 bg-[#07100f] text-white shadow-sm">
        <div className="grid gap-5 p-5 lg:grid-cols-[auto_1fr]">
          <div className="grid h-20 w-20 place-items-center rounded-lg border border-[#B2FF59]/30 bg-[#004D40] text-[#B2FF59] shadow-[0_0_30px_rgba(178,255,89,.25)]">
            <Bot className="h-10 w-10" />
          </div>
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="text-xl font-semibold">Munshi AI Advisor</h2>
              <span className="rounded-full border border-[#B2FF59]/30 px-2 py-1 text-xs font-semibold uppercase tracking-wide text-[#B2FF59]">
                {aiInsights?.source || "loading"}
              </span>
            </div>
            <pre className="mt-3 whitespace-pre-wrap font-sans text-sm leading-7 text-zinc-200">
              {typedInsight || "Malik, factory ke hisaab-kitab dekh raha hoon..."}
            </pre>
          </div>
        </div>
      </section>

      <section className="grid gap-4 md:grid-cols-3">
        <StatCard icon={IndianRupee} label="Total Revenue (7 days)" value={`Rs ${Number(aiInsights?.stats.total_sales_last_7_days || 0).toLocaleString("en-IN")}`} />
        <StatCard icon={WalletCards} label="Outstanding" value={`Rs ${Number(aiInsights?.stats.current_total_market_outstanding || 0).toLocaleString("en-IN")}`} />
        <StatCard icon={AlertTriangle} label="Raw Material Low Stock Alerts" value={aiInsights?.stats.raw_material_low_stock_alerts ?? 0} />
      </section>

      <section className="grid gap-4 md:grid-cols-3">
        <StatCard icon={UserRound} label="Total Workers" value={workers.length} />
        <StatCard icon={Factory} label="Active Machines" value={machines.length} />
        <StatCard icon={PackageCheck} label="Opening Stock Status" value={stockStatus} />
      </section>

      <section className={`rounded-lg border p-5 shadow-sm ${productionAlerts?.has_high_wastage ? "border-red-200 bg-red-50" : "border-emerald-200 bg-emerald-50"}`}>
        <div className="flex items-start gap-3">
          <div className={`grid h-10 w-10 place-items-center rounded-md ${productionAlerts?.has_high_wastage ? "bg-red-100 text-red-700" : "bg-emerald-100 text-emerald-700"}`}>
            <AlertTriangle className="h-5 w-5" />
          </div>
          <div>
            <h2 className={`text-base font-semibold ${productionAlerts?.has_high_wastage ? "text-red-950" : "text-emerald-950"}`}>Munshi Alert</h2>
            {productionAlerts?.has_high_wastage ? (
              <p className="mt-1 text-sm text-red-800">
                Last 24 hours mein {productionAlerts.high_wastage_count} high wastage entry mili. Production records check karein.
              </p>
            ) : (
              <p className="mt-1 text-sm text-emerald-800">Last 24 hours mein high wastage nahi mila.</p>
            )}
          </div>
        </div>
      </section>

      <section className="grid gap-6 xl:grid-cols-[minmax(0,1.1fr)_minmax(0,0.9fr)]">
        <div className="rounded-lg border border-zinc-200 bg-white p-5 shadow-sm">
          <SectionTitle icon={UserRound} title="Workers" />
          {workers.length === 0 ? (
            <EmptySetup title="No workers added" to="/onboarding" label="Add your first Worker" />
          ) : (
            <div className="mt-4 overflow-x-auto">
              <table className="min-w-full divide-y divide-zinc-200">
                <thead className="bg-zinc-50">
                  <tr>
                    <Th>Name</Th>
                    <Th>Phone</Th>
                    <Th>Shift</Th>
                    <Th align="right">Daily Wages</Th>
                    <Th align="right">Action</Th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-zinc-100">
                  {workers.map((worker) => (
                    <tr key={worker.id} className="hover:bg-zinc-50">
                      <Td strong>{worker.name}</Td>
                      <Td>{worker.phone || "-"}</Td>
                      <Td>{worker.shift_type || worker.shift_timing || `${worker.duty_hours} hrs`}</Td>
                      <Td align="right">Rs {worker.daily_wages}</Td>
                      <Td align="right">
                        <button className="inline-grid h-8 w-8 place-items-center rounded-md text-red-600 hover:bg-red-50" type="button" onClick={() => handleDelete("worker", worker.id)}>
                          <Trash2 className="h-4 w-4" />
                        </button>
                      </Td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        <div className="rounded-lg border border-zinc-200 bg-white p-5 shadow-sm">
          <SectionTitle icon={Factory} title="Machines" />
          {machines.length === 0 ? (
            <EmptySetup title="No machines added" to="/onboarding" label="Add your first Machine" />
          ) : (
            <div className="mt-4 grid gap-3 sm:grid-cols-2">
              {machines.map((machine) => (
                <div key={machine.id} className="rounded-lg border border-zinc-200 bg-zinc-50 p-4">
                  <div className="flex items-center justify-between gap-3">
                    <p className="font-semibold text-zinc-950">{machine.machine_number || `Machine ${machine.id}`}</p>
                    <div className="flex items-center gap-2">
                      <Wrench className="h-4 w-4 text-brand-700" />
                      <button className="grid h-8 w-8 place-items-center rounded-md text-red-600 hover:bg-red-50" type="button" onClick={() => handleDelete("machine", machine.id)}>
                        <Trash2 className="h-4 w-4" />
                      </button>
                    </div>
                  </div>
                  <p className="mt-1 text-sm text-zinc-500">{machine.machine_type}</p>
                  <div className="mt-4 grid grid-cols-2 gap-3 text-sm">
                    <Metric label="Speed" value={`${machine.speed_per_minute}/min`} />
                    <Metric label="Cup Size" value={`${machine.mould_size_ml || "-"}ml`} />
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </section>

      <section className="rounded-lg border border-zinc-200 bg-white p-5 shadow-sm">
        <SectionTitle icon={Boxes} title="Material Analytics" />
        {materialMappings.length === 0 ? (
          <EmptySetup title="No material metrics added" to="/onboarding" label="Add your first Material" />
        ) : (
          <div className="mt-4 grid gap-3 md:grid-cols-2">
            {materialMappings.map((mapping) => (
              <div key={mapping.id} className="rounded-md border border-zinc-200 p-4">
                <div className="flex items-center justify-between gap-3 text-sm">
                  <span className="font-semibold text-zinc-950">{mapping.label}</span>
                  <span className="flex items-center gap-2">
                    <span className="text-zinc-500">{mapping.target}</span>
                    <button className="grid h-8 w-8 place-items-center rounded-md text-red-600 hover:bg-red-50" type="button" onClick={() => handleDelete("raw-material", mapping.id)}>
                      <Trash2 className="h-4 w-4" />
                    </button>
                  </span>
                </div>
                <div className="mt-3 h-2 overflow-hidden rounded-full bg-zinc-100">
                  <div className={`h-full rounded-full ${mapping.percent === 100 ? "bg-emerald-600" : "bg-amber-500"}`} style={{ width: `${mapping.percent}%` }} />
                </div>
              </div>
            ))}
          </div>
        )}
      </section>

      <section className="rounded-lg border border-zinc-200 bg-white p-5 shadow-sm">
        <SectionTitle icon={Boxes} title="Bottom Stock Summary" />
        {bottomStockRows.length === 0 ? (
          <EmptySetup title="No bottom stock added" to="/onboarding" label="Add your first Bottom Stock" />
        ) : (
          <div className="mt-4 overflow-x-auto">
            <table className="min-w-full divide-y divide-zinc-200">
              <thead className="bg-zinc-50">
                <tr>
                  <Th>Size (mm)</Th>
                  <Th align="right">Total Weight (KG)</Th>
                  <Th align="right">Total Available Rolls</Th>
                </tr>
              </thead>
              <tbody className="divide-y divide-zinc-100">
                {bottomStockRows.map((row) => (
                  <tr key={row.id} className="hover:bg-zinc-50">
                    <Td strong>{row.size_mm ?? row.item_name.replace("mm Bottom", "")}</Td>
                    <Td align="right">{row.total_weight_kg ?? row.quantity}</Td>
                    <Td align="right">{row.total_rolls ?? 0}</Td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section className="rounded-lg border border-zinc-200 bg-white p-5 shadow-sm">
        <SectionTitle icon={UserRound} title="Customers" />
        {customers.length === 0 ? (
          <EmptySetup title="No customers added" to="/customers" label="Add your first Customer" />
        ) : (
          <div className="mt-4 overflow-x-auto">
            <table className="min-w-full divide-y divide-zinc-200">
              <thead className="bg-zinc-50">
                <tr>
                  <Th>Name</Th>
                  <Th>Phone</Th>
                  <Th align="right">Total Due</Th>
                  <Th align="right">Action</Th>
                </tr>
              </thead>
              <tbody className="divide-y divide-zinc-100">
                {customers.map((customer) => (
                  <tr key={customer.id} className="hover:bg-zinc-50">
                    <Td strong>{customer.name}</Td>
                    <Td>{customer.phone || "-"}</Td>
                    <Td align="right">Rs {customer.total_due}</Td>
                    <Td align="right">
                      <button className="inline-grid h-8 w-8 place-items-center rounded-md text-red-600 hover:bg-red-50" type="button" onClick={() => handleDelete("customer", customer.id)}>
                        <Trash2 className="h-4 w-4" />
                      </button>
                    </Td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}

function StatCard({ icon: Icon, label, value }: { icon: typeof UserRound; label: string; value: string | number }) {
  return (
    <div className="rounded-lg border border-zinc-200 bg-white p-4 shadow-sm">
      <div className="flex items-center justify-between gap-3">
        <p className="text-sm text-zinc-500">{label}</p>
        <Icon className="h-4 w-4 text-brand-700" />
      </div>
      <p className="mt-4 text-2xl font-semibold text-zinc-950">{value}</p>
    </div>
  );
}

function SectionTitle({ icon: Icon, title }: { icon: typeof UserRound; title: string }) {
  return (
    <h2 className="flex items-center gap-2 text-base font-semibold text-zinc-950">
      <Icon className="h-4 w-4 text-brand-700" />
      {title}
    </h2>
  );
}

function EmptySetup({ title, to, label }: { title: string; to: string; label: string }) {
  return (
    <div className="mt-4 rounded-md border border-dashed border-zinc-300 p-6 text-center">
      <p className="text-sm font-medium text-zinc-700">{title}</p>
      <Link className="mt-3 inline-flex h-10 items-center justify-center rounded-md bg-brand-600 px-4 text-sm font-semibold text-white hover:bg-brand-700" to={to}>
        {label}
      </Link>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-xs text-zinc-500">{label}</p>
      <p className="mt-1 font-semibold text-zinc-950">{value}</p>
    </div>
  );
}

function Th({ children, align = "left" }: { children: React.ReactNode; align?: "left" | "right" }) {
  return <th className={`px-4 py-3 text-${align} text-xs font-semibold uppercase text-zinc-500`}>{children}</th>;
}

function Td({ children, align = "left", strong = false }: { children: React.ReactNode; align?: "left" | "right"; strong?: boolean }) {
  return <td className={`whitespace-nowrap px-4 py-3 text-${align} text-sm ${strong ? "font-medium text-zinc-950" : "text-zinc-700"}`}>{children}</td>;
}

function Toast({ type, message, onClose }: { type: "success" | "error"; message: string; onClose: () => void }) {
  return (
    <button
      className={`fixed right-5 top-20 z-50 rounded-md px-4 py-3 text-sm font-semibold text-white shadow-lg ${type === "success" ? "bg-emerald-600" : "bg-red-600"}`}
      type="button"
      onClick={onClose}
    >
      {message}
    </button>
  );
}
