import { useState, useEffect } from "react";
import { ArrowLeft, Loader, Eye, RefreshCw, BarChart2, ShieldAlert } from "lucide-react";
import { useAuth } from "../context/AuthContext";
import { api, getDailyProductionHistory } from "../lib/api";
import type { ProductionHistoryEntry } from "../lib/api";
import { toNumber } from "../lib/format";

type BriefingHistoryItem = {
  id: number;
  date: string;
  status: string;
  role_version: string;
  message_text: string;
  health_score: number | null;
  production_total: number | null;
  sales_total: number | null;
  collections_total: number | null;
  outstanding_total: number | null;
  top_warning: string | null;
  sent_at: string | null;
};

type BriefingDetail = {
  id: number;
  factory_id: number;
  user_id: number | null;
  role: string;
  briefing_date: string;
  message_text: string;
  snapshot_json: any;
  health_score: number | null;
  status: string;
  sent_at: string | null;
  created_at: string | null;
};

function formatDate(dateStr: string): string {
  try {
    const d = new Date(dateStr);
    return d.toLocaleDateString("en-IN", { day: "2-digit", month: "long", year: "numeric" });
  } catch {
    return dateStr;
  }
}

function formatDateShort(dateStr: string): string {
  try {
    const d = new Date(dateStr);
    return d.toLocaleDateString("en-IN", { day: "2-digit", month: "short" });
  } catch {
    return dateStr;
  }
}

export default function BriefingHistoryPage() {
  const { user } = useAuth();
  const isOwner = user?.role === "Owner";
  
  const [history, setHistory] = useState<BriefingHistoryItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  
  const [selectedBriefing, setSelectedBriefing] = useState<BriefingDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [productionEntries, setProductionEntries] = useState<ProductionHistoryEntry[]>([]);

  async function fetchHistory() {
    try {
      setLoading(true);
      setError(null);
      const [res, productionRes] = await Promise.all([
        api.get("/api/briefings/history?days=30"),
        getDailyProductionHistory(),
      ]);
      setHistory(res.data);
      setProductionEntries(productionRes.data);
    } catch (err: any) {
      setError(err?.response?.data?.detail || err.message || "Something went wrong.");
    } finally {
      setLoading(false);
    }
  }

  async function loadDetail(id: number) {
    try {
      setDetailLoading(true);
      const res = await api.get(`/api/briefings/history/${id}`);
      setSelectedBriefing(res.data);
    } catch (err: any) {
      alert(err?.response?.data?.detail || err.message || "Error loading details.");
    } finally {
      setDetailLoading(false);
    }
  }

  useEffect(() => {
    fetchHistory();
  }, []);

  if (loading) {
    return (
      <div className="flex h-64 items-center justify-center">
        <Loader className="h-8 w-8 animate-spin text-[#6D28D9]" />
      </div>
    );
  }

  if (selectedBriefing) {
    return (
      <div className="mx-auto max-w-4xl p-4">
        <button
          onClick={() => setSelectedBriefing(null)}
          className="mb-4 flex items-center gap-2 text-sm font-medium text-[#4C1D95] hover:underline"
        >
          <ArrowLeft className="h-4 w-4" /> Back to History
        </button>

        <div className="rounded-lg border border-[#E5E7EB] bg-white p-6 shadow-sm">
          <div className="mb-6 flex flex-wrap items-center justify-between gap-4 border-b border-[#F3F4F6] pb-4">
            <div>
              <h2 className="text-xl font-bold text-[#111827]">
                Briefing for {formatDate(selectedBriefing.briefing_date)}
              </h2>
              <p className="text-sm text-[#4B5563]">
                Version: <span className="font-semibold text-[#6D28D9]">{selectedBriefing.role}</span>
              </p>
            </div>
            {selectedBriefing.health_score !== null && (
              <div className="text-center">
                <span className="text-xs font-semibold uppercase text-[#4B5563]">Health Score</span>
                <div className="text-3xl font-extrabold text-[#6D28D9]">
                  {selectedBriefing.health_score}/100
                </div>
              </div>
            )}
          </div>

          <div className="mb-6 rounded-lg bg-[#F9FAFB] p-4 font-mono text-sm leading-relaxed whitespace-pre-wrap text-[#111827]">
            {selectedBriefing.message_text}
          </div>

          <div>
            <h3 className="mb-3 text-lg font-semibold text-[#111827]">Data Snapshot Details</h3>
            <pre className="overflow-x-auto rounded-lg bg-[#F3F4F6] p-4 text-xs text-[#374151]">
              {JSON.stringify(selectedBriefing.snapshot_json, null, 2)}
            </pre>
          </div>
        </div>
      </div>
    );
  }

  // Calculate Last 7 Days metrics summary
  const last7 = history.slice(0, 7);
  const avgHealth = last7.filter(x => x.health_score !== null).reduce((acc, x) => acc + (x.health_score || 0), 0) / (last7.filter(x => x.health_score !== null).length || 1);
  const totalProduction = last7.reduce((acc, x) => acc + (x.production_total || 0), 0);
  const totalCollections = last7.reduce((acc, x) => acc + (x.collections_total || 0), 0);

  return (
    <div className="mx-auto max-w-6xl p-4">
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-[#111827]">Daily Briefing History</h1>
          <p className="text-sm text-[#4B5563]">View daily trends, production metrics, and historical context.</p>
        </div>
        <button
          onClick={fetchHistory}
          className="flex items-center gap-2 rounded-md bg-[#F3E8FF] px-3 py-2 text-sm font-semibold text-[#6D28D9] hover:bg-[#E9D5FF] transition"
        >
          <RefreshCw className="h-4 w-4" /> Refresh
        </button>
      </div>

      {error && (
        <div className="mb-6 flex items-center gap-3 rounded-lg border border-[#FCA5A5] bg-[#FEF2F2] p-4 text-sm text-[#991B1B]">
          <ShieldAlert className="h-5 w-5 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {/* Summary Section - Last 7 Days Metrics */}
      <div className="mb-8 grid grid-cols-1 gap-4 sm:grid-cols-3">
        <div className="rounded-lg border border-[#E5E7EB] bg-white p-5 shadow-sm">
          <div className="flex items-center justify-between">
            <span className="text-sm font-medium text-[#4B5563]">Avg Health Score (7d)</span>
            <BarChart2 className="h-5 w-5 text-[#6D28D9]" />
          </div>
          <div className="mt-2 text-2xl font-bold text-[#6D28D9]">
            {avgHealth ? `${toNumber(avgHealth).toFixed(1)}/100` : "--"}
          </div>
        </div>

        <div className="rounded-lg border border-[#E5E7EB] bg-white p-5 shadow-sm">
          <div className="flex items-center justify-between">
            <span className="text-sm font-medium text-[#4B5563]">Total Production (7d)</span>
            <BarChart2 className="h-5 w-5 text-[#6D28D9]" />
          </div>
          <div className="mt-2 text-2xl font-bold text-[#6D28D9]">
            {totalProduction ? `${totalProduction.toLocaleString()} boxes` : "0 boxes"}
          </div>
        </div>

        <div className="rounded-lg border border-[#E5E7EB] bg-white p-5 shadow-sm">
          <div className="flex items-center justify-between">
            <span className="text-sm font-medium text-[#4B5563]">Total Collections (7d)</span>
            <BarChart2 className="h-5 w-5 text-[#6D28D9]" />
          </div>
          <div className="mt-2 text-2xl font-bold text-[#6D28D9]">
            {isOwner ? `₹${totalCollections.toLocaleString(undefined, { minimumFractionDigits: 2 })}` : "Masked"}
          </div>
        </div>
      </div>

      <div className="mb-8 overflow-hidden rounded-lg border border-[#E5E7EB] bg-white shadow-sm">
        <div className="border-b bg-[#FAFAFA] px-6 py-4">
          <h2 className="text-lg font-bold text-[#111827]">Production Entry History</h2>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="bg-[#F9FAFB] text-xs uppercase text-[#4B5563]"><tr><th className="px-4 py-3">Date</th><th>Worker</th><th>Product</th><th>Production</th><th>Raw Material</th><th>Machine</th><th>Shift</th><th>Created By</th><th>Status</th><th>Timestamp</th></tr></thead>
            <tbody>
              {productionEntries.map((entry) => (
                <tr key={entry.id} className="border-t">
                  <td className="px-4 py-3">{formatDateShort(entry.date)}</td>
                  <td>{entry.worker_name}</td>
                  <td>{entry.product_size_ml}ml {entry.product_type}</td>
                  <td>{entry.quantity_boxes.toLocaleString()} boxes / {entry.loose_packets_made.toLocaleString()} loose</td>
                  <td>Blank: {entry.blank_used_bora} bora / {entry.blank_used_kg} KG<br />Bottom: {entry.bottom_used_rolls} roll</td>
                  <td>{entry.machine_name}</td>
                  <td>{entry.shift || "--"}</td>
                  <td>{entry.created_by || "--"}</td>
                  <td className={entry.status === "REJECTED" ? "font-semibold text-red-700" : "font-semibold text-green-700"}>{entry.status}</td>
                  <td>{entry.created_at ? new Date(entry.created_at).toLocaleString("en-IN") : "--"}</td>
                </tr>
              ))}
              {!productionEntries.length ? <tr><td colSpan={10} className="px-6 py-8 text-center text-zinc-500">No production entries found.</td></tr> : null}
            </tbody>
          </table>
        </div>
      </div>

      {/* 30 Day List */}
      <div className="rounded-lg border border-[#E5E7EB] bg-white shadow-sm overflow-hidden">
        <div className="border-b border-[#F3F4F6] bg-[#FAFAFA] px-6 py-4">
          <h2 className="text-lg font-bold text-[#111827]">Last 30 Days</h2>
        </div>

        <div className="divide-y divide-[#F3F4F6] overflow-x-auto">
          <table className="w-full text-left text-sm text-[#374151]" data-test-id="briefing-history-list">
            <thead className="bg-[#F9FAFB] text-xs font-semibold uppercase text-[#4B5563]">
              <tr>
                <th className="px-6 py-3">Date</th>
                <th className="px-6 py-3">Health Score</th>
                <th className="px-6 py-3">Production (Boxes)</th>
                {isOwner && <th className="px-6 py-3">Collections</th>}
                {isOwner && <th className="px-6 py-3">Outstanding</th>}
                <th className="px-6 py-3">Top Warning</th>
                <th className="px-6 py-3 text-center">Action</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[#F3F4F6]">
              {history.length === 0 ? (
                <tr>
                  <td colSpan={isOwner ? 7 : 5} className="px-6 py-12 text-center text-[#9CA3AF]">
                    Briefing not generated.
                  </td>
                </tr>
              ) : (
                history.map((item) => (
                  <tr key={item.id} className="hover:bg-[#FFF7ED] transition-colors">
                    <td className="px-6 py-4 font-semibold text-[#111827] whitespace-nowrap">
                      {formatDateShort(item.date)}
                    </td>
                    <td className="px-6 py-4">
                      {item.health_score !== null ? (
                        <span className="inline-flex items-center rounded-full bg-[#F3E8FF] px-2.5 py-0.5 text-xs font-semibold text-[#6D28D9]">
                          {item.health_score}
                        </span>
                      ) : (
                        "--"
                      )}
                    </td>
                    <td className="px-6 py-4">
                      {item.production_total !== null ? item.production_total.toLocaleString() : "--"}
                    </td>
                    {isOwner && (
                      <td className="px-6 py-4 text-[#10B981] font-medium">
                        {item.collections_total !== null ? `₹${item.collections_total.toLocaleString(undefined, { minimumFractionDigits: 2 })}` : "--"}
                      </td>
                    )}
                    {isOwner && (
                      <td className="px-6 py-4 text-[#EF4444] font-medium">
                        {item.outstanding_total !== null ? `₹${item.outstanding_total.toLocaleString(undefined, { minimumFractionDigits: 2 })}` : "--"}
                      </td>
                    )}
                    <td className="px-6 py-4 text-[#D97706] italic">
                      {item.top_warning || "None"}
                    </td>
                    <td className="px-6 py-4 text-center">
                      <button
                        onClick={() => loadDetail(item.id)}
                        disabled={detailLoading}
                        className="inline-flex items-center gap-1 text-[#4C1D95] hover:text-[#6D28D9] font-medium"
                      >
                        <Eye className="h-4 w-4" /> View Detail
                      </button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
