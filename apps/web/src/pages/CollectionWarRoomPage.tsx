import { useCallback, useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  Bell,
  IndianRupee,
  Loader2,
  RefreshCcw,
  Send,
  TrendingDown,
  Users,
} from "lucide-react";

import {
  getCollectionWarRoom,
  sendCollectionWarRoomTelegramAlert,
  copyReminder,
  markDone,
  snoozeCustomer,
  type CollectionWarRoomResponse,
} from "../lib/api";
import { useDataRefresh } from "../context/DataRefreshContext";
import { useAuth } from "../context/AuthContext";

// ----------------------------------------------------------------------------
// Helpers
// ----------------------------------------------------------------------------

function inr(value: number | string | null | undefined): string {
  const n = Number(value || 0);
  return `Rs ${n.toLocaleString("en-IN", { maximumFractionDigits: 0 })}`;
}

function inrShort(value: number | string | null | undefined): string {
  const n = Number(value || 0);
  if (n >= 10000000) return `Rs ${(n / 10000000).toFixed(1)}Cr`;
  if (n >= 100000) return `Rs ${(n / 100000).toFixed(1)}L`;
  if (n >= 1000) return `Rs ${(n / 1000).toFixed(1)}K`;
  return `Rs ${Math.round(n)}`;
}

function trendDelta(trend: { date: string; outstanding: number }[]): number {
  if (trend.length < 2) return 0;
  const first = trend[0].outstanding;
  const last = trend[trend.length - 1].outstanding;
  if (!first) return 0;
  return Math.round(((last - first) / first) * 100);
}

function MiniSparkline({ data }: { data: { outstanding: number }[] }) {
  if (!data.length) return null;
  const max = Math.max(...data.map((p) => p.outstanding), 1);
  const width = 220;
  const height = 48;
  const stepX = data.length > 1 ? width / (data.length - 1) : width;
  const points = data
    .map((point, idx) => {
      const x = idx * stepX;
      const y = height - (point.outstanding / max) * (height - 4) - 2;
      return `${x},${y}`;
    })
    .join(" ");

  return (
    <svg
      viewBox={`0 0 ${width} ${height}`}
      preserveAspectRatio="none"
      className="h-12 w-full text-rose-500"
      role="img"
      aria-label="7-day due trend"
    >
      <polyline
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
        points={points}
      />
    </svg>
  );
}

function Card({
  label,
  value,
  hint,
  tone = "default",
  icon,
}: {
  label: string;
  value: string;
  hint?: string;
  tone?: "default" | "danger" | "warning" | "success";
  icon?: React.ReactNode;
}) {
  const toneClass =
    tone === "danger"
      ? "text-rose-700"
      : tone === "warning"
      ? "text-amber-700"
      : tone === "success"
      ? "text-emerald-700"
      : "text-zinc-900";
  return (
    <div className="flex flex-col gap-1 rounded-2xl border border-zinc-200 bg-white p-4 shadow-sm">
      <div className="flex items-center justify-between text-xs font-medium uppercase tracking-wide text-zinc-500">
        <span>{label}</span>
        {icon}
      </div>
      <div className={`text-xl font-semibold ${toneClass}`}>{value}</div>
      {hint ? <div className="text-xs text-zinc-500">{hint}</div> : null}
    </div>
  );
}

function AgingBar({ label, value, total, tone }: {
  label: string;
  value: number;
  total: number;
  tone: string;
}) {
  const pct = total > 0 ? Math.max(2, (value / total) * 100) : 0;
  return (
    <div className="flex flex-col gap-1 text-sm">
      <div className="flex items-center justify-between">
        <span className="font-medium text-zinc-700">{label}</span>
        <span className="font-mono text-zinc-900">{inrShort(value)}</span>
      </div>
      <div className="h-2 w-full overflow-hidden rounded-full bg-zinc-100">
        <div
          className={`h-full ${tone} rounded-full transition-all`}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}

// ----------------------------------------------------------------------------
// Page
// ----------------------------------------------------------------------------

export default function CollectionWarRoomPage() {
  const [data, setData] = useState<CollectionWarRoomResponse | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string>("");
  const [sendingAlert, setSendingAlert] = useState(false);
  const [toast, setToast] = useState<{ kind: "ok" | "err"; text: string } | null>(null);
  const [customerActionLoading, setCustomerActionLoading] = useState<number | null>(null);
  const { refreshVersion, triggerDataRefresh } = useDataRefresh();
  const { user } = useAuth();

  const load = useCallback(async () => {
    setIsLoading(true);
    setError("");
    try {
      const res = await getCollectionWarRoom();
      setData(res.data);
    } catch (err) {
      const msg = (err as { response?: { data?: { detail?: string } }; message?: string })
        ?.response?.data?.detail ?? (err as { message?: string })?.message ?? "Failed to load war room";
      setError(String(msg));
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load, refreshVersion]);

  const sendTelegram = useCallback(async () => {
    setSendingAlert(true);
    try {
      const res = await sendCollectionWarRoomTelegramAlert();
      setToast({
        kind: "ok",
        text: res.data?.message || "Collection alert sent to your Telegram.",
      });
    } catch (err) {
      const msg = (err as { response?: { data?: { detail?: string } }; message?: string })
        ?.response?.data?.detail ?? (err as { message?: string })?.message ?? "Failed to send alert";
      setToast({ kind: "err", text: String(msg) });
    } finally {
      setSendingAlert(false);
      setTimeout(() => setToast(null), 4000);
    }
  }, []);

  const handleCopyReminder = useCallback(async (customerId: number, customerName: string) => {
    setCustomerActionLoading(customerId);
    try {
      const res = await copyReminder(customerId);
      const text = res.data?.message || `Reminder text for ${customerName} copied to clipboard`;
      try {
        await navigator.clipboard.writeText(text);
      } catch {
        // Fallback: prompt the user to copy manually
        prompt("Copy this reminder text:", text);
      }
      setToast({ kind: "ok", text: "Reminder text copied to clipboard" });
    } catch (err) {
      const msg = (err as { response?: { data?: { detail?: string } }; message?: string })
        ?.response?.data?.detail ?? (err as { message?: string })?.message ?? "Failed to copy reminder";
      setToast({ kind: "err", text: String(msg) });
    } finally {
      setCustomerActionLoading(null);
      setTimeout(() => setToast(null), 4000);
    }
  }, []);

  const handleMarkDone = useCallback(async (customerId: number, customerName: string) => {
    if (!window.confirm(`Mark ${customerName} as done? This will remove them from the due list.`)) return;
    setCustomerActionLoading(customerId);
    try {
      const res = await markDone(customerId);
      setToast({ kind: "ok", text: res.data?.message || `${customerName} marked as done.` });
      // Refresh the war room data to reflect the change
      load();
    } catch (err) {
      const msg = (err as { response?: { data?: { detail?: string } }; message?: string })
        ?.response?.data?.detail ?? (err as { message?: string })?.message ?? "Failed to mark as done";
      setToast({ kind: "err", text: String(msg) });
    } finally {
      setCustomerActionLoading(null);
      setTimeout(() => setToast(null), 4000);
    }
  }, [load]);

  const handleSnoozeCustomer = useCallback(async (customerId: number, customerName: string) => {
    setCustomerActionLoading(customerId);
    try {
      const res = await snoozeCustomer(customerId, 3);
      setToast({ kind: "ok", text: res.data?.message || `${customerName} snoozed for 3 days.` });
      // Refresh the war room data to reflect the change
      load();
    } catch (err) {
      const msg = (err as { response?: { data?: { detail?: string } }; message?: string })
        ?.response?.data?.detail ?? (err as { message?: string })?.message ?? "Failed to snooze customer";
      setToast({ kind: "err", text: String(msg) });
    } finally {
      setCustomerActionLoading(null);
      setTimeout(() => setToast(null), 4000);
    }
  }, [load]);

  const trendDeltaPct = useMemo(() => trendDelta(data?.due_trend || []), [data]);
  const isUp = trendDeltaPct > 0;

  const totalAging = useMemo(() => {
    if (!data) return 0;
    const a = data.aging_buckets;
    return a["0_7_days"] + a["8_15_days"] + a["16_30_days"] + a["31_60_days"] + a["60_plus_days"];
  }, [data]);

  if (isLoading && !data) {
    return (
      <div className="flex h-64 items-center justify-center text-zinc-500">
        <Loader2 className="mr-2 h-5 w-5 animate-spin" /> Loading war room...
      </div>
    );
  }

  if (error && !data) {
    return (
      <div className="rounded-xl border border-rose-200 bg-rose-50 p-6 text-rose-700">
        <div className="font-semibold">War room unavailable</div>
        <div className="mt-1 text-sm">{error}</div>
        <button
          type="button"
          onClick={load}
          className="mt-3 inline-flex items-center gap-2 rounded-md border border-rose-200 bg-white px-3 py-1.5 text-sm text-rose-700 hover:bg-rose-100"
        >
          <RefreshCcw className="h-4 w-4" /> Retry
        </button>
      </div>
    );
  }

  if (!data) return null;

  const highRiskThreshold = Number(
    (import.meta as unknown as { env?: Record<string, string> })?.env?.VITE_HIGH_RISK_THRESHOLD || 100000
  );
  const topCustomers = data.top_customers || [];

  return (
    <div className="flex flex-col gap-5 p-4 md:p-6">
      {/* Header */}
      <div className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-zinc-900">Collection War Room</h1>
          <p className="text-sm text-zinc-500">
            Where is the money stuck? Owner-only overview, refreshed live.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={load}
            className="inline-flex items-center gap-2 rounded-md border border-zinc-200 bg-white px-3 py-2 text-sm text-zinc-700 hover:bg-zinc-50"
          >
            <RefreshCcw className={`h-4 w-4 ${isLoading ? "animate-spin" : ""}`} /> Refresh
          </button>
          {user?.role === "Owner" && (
            <button
              type="button"
              onClick={sendTelegram}
              disabled={sendingAlert}
              className="inline-flex items-center gap-2 rounded-md bg-rose-600 px-3 py-2 text-sm font-medium text-white hover:bg-rose-700 disabled:opacity-60"
            >
              {sendingAlert ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Send className="h-4 w-4" />
              )}
              Send to Telegram
            </button>
          )}
        </div>
      </div>

      {toast && (
        <div
          className={`rounded-md px-3 py-2 text-sm ${
            toast.kind === "ok"
              ? "bg-emerald-50 text-emerald-700"
              : "bg-rose-50 text-rose-700"
          }`}
        >
          {toast.text}
        </div>
      )}

      {/* Summary cards */}
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Card
          label="Total Outstanding"
          value={inr(data.total_outstanding)}
          tone="danger"
          icon={<IndianRupee className="h-4 w-4 text-rose-500" />}
        />
        <Card
          label="Overdue (15+ days)"
          value={inr(data.overdue_amount)}
          hint={`${inrShort(data.overdue_amount)} pending`}
          tone="warning"
          icon={<AlertTriangle className="h-4 w-4 text-amber-500" />}
        />
        <Card
          label="High Risk Customers"
          value={String(data.high_risk_customers)}
          hint={`Outstanding > Rs ${(highRiskThreshold / 100000).toFixed(1)}L`}
          tone="warning"
          icon={<Users className="h-4 w-4 text-amber-500" />}
        />
        <Card
          label="7-day Trend"
          value={`${isUp ? "+" : ""}${trendDeltaPct}%`}
          tone={isUp ? "danger" : "success"}
          icon={
            <TrendingDown
              className={`h-4 w-4 ${isUp ? "rotate-180 text-rose-500" : "text-emerald-500"}`}
            />
          }
        />
      </div>

      {/* Due trend chart */}
      <div className="rounded-2xl border border-zinc-200 bg-white p-4 shadow-sm">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-semibold text-zinc-700">Last 7 days</h2>
          <span className="text-xs text-zinc-500">Daily outstanding balance</span>
        </div>
        <div className="mt-2">
          <MiniSparkline data={data.due_trend} />
        </div>
        <div className="mt-2 flex justify-between text-[10px] text-zinc-400">
          {data.due_trend.map((p) => (
            <span key={p.date}>{p.date.slice(5)}</span>
          ))}
        </div>
      </div>

      {/* Top due customers + aging buckets */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-5">
        <div className="rounded-2xl border border-zinc-200 bg-white p-4 shadow-sm lg:col-span-3">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold text-zinc-700">Top 10 Due Customers</h2>
            <span className="text-xs text-zinc-500">
              {topCustomers.length} customers
            </span>
          </div>
          {topCustomers.length === 0 ? (
            <div className="mt-6 flex flex-col items-center justify-center gap-2 rounded-md border border-dashed border-zinc-200 p-8 text-center text-sm text-zinc-500">
              <Bell className="h-5 w-5 text-zinc-400" />
              No outstanding customers. All bills settled.
            </div>
          ) : (
            <div className="mt-3 overflow-x-auto">
              <table className="min-w-full text-left text-sm">
                <thead className="text-xs uppercase tracking-wide text-zinc-500">
                  <tr>
                    <th className="py-2 pr-3">Customer</th>
                    <th className="py-2 pr-3 text-right">Outstanding</th>
                    <th className="py-2 pr-3 text-right">Days Due</th>
                    <th className="py-2 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-zinc-100">
                  {topCustomers.map((c, idx) => {
                    const highRisk = c.total_due >= highRiskThreshold;
                    return (
                      <tr key={`${c.customer_name}-${idx}`} className="hover:bg-zinc-50">
                        <td className="py-2 pr-3">
                          <div className="flex flex-wrap items-center gap-2">
                            <span className="font-medium text-zinc-900">
                              {c.customer_name}
                            </span>
                            {highRisk && (
                              <span className="rounded-full bg-rose-100 px-2 py-0.5 text-[10px] font-semibold text-rose-700">
                                High Risk
                              </span>
                            )}
                          </div>
                        </td>
                        <td className="py-2 pr-3 text-right font-mono text-zinc-900">
                          {inr(c.total_due)}
                        </td>
                        <td className="py-2 pr-3 text-right">
                          <span
                            className={
                              c.days_old > 30
                                ? "font-semibold text-rose-700"
                                : c.days_old > 15
                                ? "text-amber-700"
                                : "text-zinc-700"
                            }
                          >
                            {c.days_old} days
                          </span>
                        </td>
                        <td className="py-2 text-right">
                          <div className="flex items-center justify-end gap-1">
                            <button
                              type="button"
                              onClick={() => handleCopyReminder(c.customer_id, c.customer_name)}
                              disabled={customerActionLoading === c.customer_id}
                              className="rounded px-1.5 py-0.5 text-xs font-medium text-blue-600 hover:bg-blue-50 disabled:opacity-40"
                              data-test-id="copy-recovery-reminder-button"
                              title="Copy reminder text"
                            >
                              {customerActionLoading === c.customer_id ? "..." : "Copy Reminder"}
                            </button>
                            <button
                              type="button"
                              onClick={() => handleMarkDone(c.customer_id, c.customer_name)}
                              disabled={customerActionLoading === c.customer_id}
                              className="rounded px-1.5 py-0.5 text-xs font-medium text-emerald-600 hover:bg-emerald-50 disabled:opacity-40"
                              title="Mark as done"
                            >
                              {customerActionLoading === c.customer_id ? "..." : "Mark Done"}
                            </button>
                            <button
                              type="button"
                              onClick={() => handleSnoozeCustomer(c.customer_id, c.customer_name)}
                              disabled={customerActionLoading === c.customer_id}
                              className="rounded px-1.5 py-0.5 text-xs font-medium text-amber-600 hover:bg-amber-50 disabled:opacity-40"
                              title="Snooze for 3 days"
                            >
                              {customerActionLoading === c.customer_id ? "..." : "Snooze 3d"}
                            </button>
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>

        <div className="rounded-2xl border border-zinc-200 bg-white p-4 shadow-sm lg:col-span-2">
          <h2 className="text-sm font-semibold text-zinc-700">Aging Buckets</h2>
          <p className="text-xs text-zinc-500">Where does the money age?</p>
          <div className="mt-3 flex flex-col gap-3">
            <AgingBar
              label="0–7 days"
              value={data.aging_buckets["0_7_days"]}
              total={totalAging}
              tone="bg-emerald-500"
            />
            <AgingBar
              label="8–15 days"
              value={data.aging_buckets["8_15_days"]}
              total={totalAging}
              tone="bg-sky-500"
            />
            <AgingBar
              label="16–30 days"
              value={data.aging_buckets["16_30_days"]}
              total={totalAging}
              tone="bg-amber-500"
            />
            <AgingBar
              label="31–60 days"
              value={data.aging_buckets["31_60_days"]}
              total={totalAging}
              tone="bg-orange-500"
            />
            <AgingBar
              label="60+ days"
              value={data.aging_buckets["60_plus_days"]}
              total={totalAging}
              tone="bg-rose-600"
            />
          </div>
        </div>
      </div>

      <p className="text-center text-[11px] text-zinc-400">
        Refreshed on every payment entry. Click <em>Refresh</em> for a manual pull.
      </p>
      {/* Trigger data refresh subscription to keep counts live */}
      <DataRefreshBridge onRefresh={triggerDataRefresh} />
    </div>
  );
}

function DataRefreshBridge({ onRefresh }: { onRefresh: () => void }) {
  useEffect(() => {
    const timer = window.setInterval(() => onRefresh(), 60_000);
    return () => window.clearInterval(timer);
  }, [onRefresh]);
  return null;
}
