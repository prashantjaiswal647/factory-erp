import { useEffect, useState } from "react";
import { AlertCircle, CalendarDays, History } from "lucide-react";
import axios from "axios";

import {
  getDailySequenceActionEvents,
  getDailySequenceLogs,
  getProductionReviewEntries,
  rollbackActionEvent,
  reverseProductionEntry,
  verifyActionEvent,
  verifyProductionEntry,
  type ActionEventReview,
  type ProductionReviewEntry,
} from "../lib/api";
import { useAuth } from "../context/AuthContext";

interface DailySequenceLogItem {
  id: number;
  time: string;
  action_type: string;
  action_summary: string;
  entity_type: string;
  entity_id: number | null;
  user_name: string;
  user_role: string;
  relative_day: string;
}

const entityChipClasses: Record<string, string> = {
  invoice: "bg-blue-100 text-blue-800 border-blue-200",
  payment: "bg-emerald-100 text-emerald-800 border-emerald-200",
  production: "bg-purple-100 text-purple-800 border-purple-200",
  expense: "bg-red-100 text-red-800 border-red-200",
  attendance: "bg-zinc-100 text-zinc-700 border-zinc-200",
  sale: "bg-blue-100 text-blue-800 border-blue-200",
  onboarding: "bg-amber-100 text-amber-800 border-amber-200",
};

function todayInputValue() {
  const now = new Date();
  const offsetMs = now.getTimezoneOffset() * 60 * 1000;
  return new Date(now.getTime() - offsetMs).toISOString().slice(0, 10);
}

function errorMessage(error: unknown) {
  if (axios.isAxiosError(error)) {
    const detail = error.response?.data?.detail;
    return typeof detail === "string" ? detail : error.message;
  }
  return "Failed to load activity logs.";
}

function entityClass(entityType: string) {
  return entityChipClasses[entityType.toLowerCase()] || "bg-zinc-100 text-zinc-700 border-zinc-200";
}

function SkeletonCards() {
  return (
    <div className="space-y-4">
      {[0, 1, 2].map((item) => (
        <div key={item} className="grid gap-3 rounded-lg border border-zinc-100 bg-zinc-50 p-4 md:grid-cols-[110px_1fr_120px]">
          <div className="h-8 animate-pulse rounded-full bg-zinc-200" />
          <div className="space-y-2">
            <div className="h-4 w-3/4 animate-pulse rounded bg-zinc-200" />
            <div className="h-3 w-1/2 animate-pulse rounded bg-zinc-100" />
          </div>
          <div className="h-7 animate-pulse rounded-full bg-zinc-200" />
        </div>
      ))}
    </div>
  );
}

export default function DailySequencePage() {
  const { user } = useAuth();
  const [selectedDate, setSelectedDate] = useState(todayInputValue);
  const [logs, setLogs] = useState<DailySequenceLogItem[]>([]);
  const [actionEvents, setActionEvents] = useState<ActionEventReview[]>([]);
  const [actionStatusFilter, setActionStatusFilter] = useState("active");
  const [rollbackTarget, setRollbackTarget] = useState<ActionEventReview | null>(null);
  const [rollbackReason, setRollbackReason] = useState("");
  const [productionEntries, setProductionEntries] = useState<ProductionReviewEntry[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState("");
  const [actionError, setActionError] = useState("");
  const [productionError, setProductionError] = useState("");

  useEffect(() => {
    let active = true;
    async function loadLogs() {
      setIsLoading(true);
      setError("");
      setActionError("");
      setProductionError("");
      try {
        const [logData, actionData, productionData] = await Promise.all([
          getDailySequenceLogs(selectedDate),
          getDailySequenceActionEvents(selectedDate, undefined, actionStatusFilter),
          getProductionReviewEntries(selectedDate),
        ]);
        if (active) {
          setLogs(logData);
          setActionEvents(actionData.events);
          setProductionEntries(productionData.entries);
        }
      } catch (caught) {
        if (active) {
          setError(errorMessage(caught));
          setLogs([]);
          setActionEvents([]);
          setProductionEntries([]);
        }
      } finally {
        if (active) setIsLoading(false);
      }
    }
    void loadLogs();
    return () => {
      active = false;
    };
  }, [selectedDate, actionStatusFilter]);

  async function refreshActionEvents() {
    const data = await getDailySequenceActionEvents(selectedDate, undefined, actionStatusFilter);
    setActionEvents(data.events);
  }

  async function handleActionVerify(eventId: number) {
    setActionError("");
    try {
      await verifyActionEvent(eventId);
      await refreshActionEvents();
      await refreshProductionReview();
    } catch (caught) {
      setActionError(errorMessage(caught));
    }
  }

  async function submitActionRollback() {
    if (!rollbackTarget) return;
    setActionError("");
    try {
      await rollbackActionEvent(rollbackTarget.id, rollbackReason);
      setRollbackTarget(null);
      setRollbackReason("");
      await refreshActionEvents();
      await refreshProductionReview();
    } catch (caught) {
      setActionError(errorMessage(caught));
    }
  }

  async function refreshProductionReview() {
    const data = await getProductionReviewEntries(selectedDate);
    setProductionEntries(data.entries);
  }

  async function handleVerify(entryId: number) {
    setProductionError("");
    try {
      await verifyProductionEntry(entryId);
      await refreshProductionReview();
    } catch (caught) {
      setProductionError(errorMessage(caught));
    }
  }

  async function handleReverse(entryId: number) {
    const reason = window.prompt("Reason for reversing this production entry?");
    if (reason === null) return;
    setProductionError("");
    try {
      await reverseProductionEntry(entryId, reason || "Supervisor reversed own recent production mistake");
      await refreshProductionReview();
    } catch (caught) {
      setProductionError(errorMessage(caught));
    }
  }

  return (
    <div className="space-y-6">
      <header className="flex flex-col gap-4 rounded-lg border border-zinc-150 bg-white p-5 shadow-sm sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-3">
          <div className="grid h-11 w-11 place-items-center rounded-lg bg-purple-100 text-purple-700">
            <History className="h-5 w-5" />
          </div>
          <div>
            <h1 className="text-xl font-bold text-zinc-950">Daily Activity Sequence</h1>
            <p className="text-xs text-zinc-500">Automated transaction log for factory activity.</p>
          </div>
        </div>
        <label className="flex items-center gap-2 text-sm font-semibold text-zinc-700">
          <CalendarDays className="h-4 w-4 text-zinc-400" />
          <input
            className="h-10 rounded-md border border-zinc-200 bg-white px-3 text-sm font-semibold text-zinc-800 outline-none focus:border-purple-600"
            type="date"
            value={selectedDate}
            onChange={(event) => setSelectedDate(event.target.value)}
          />
        </label>
      </header>

      <section className="rounded-lg border border-zinc-150 bg-white p-5 shadow-sm">
        <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h2 className="text-base font-bold text-zinc-900">Action Review & Rollback</h2>
            <p className="text-xs text-zinc-500">Universal daily action cards. Phase 1 rollback is live for production entries.</p>
          </div>
          <div className="flex flex-wrap gap-2">
            {["active", "pending", "verified", "rolled_back", "all"].map((statusValue) => (
              <button
                key={statusValue}
                type="button"
                className={`rounded-full border px-3 py-1.5 text-xs font-bold capitalize ${
                  actionStatusFilter === statusValue
                    ? "border-purple-600 bg-purple-50 text-purple-700"
                    : "border-zinc-200 bg-white text-zinc-600"
                }`}
                onClick={() => setActionStatusFilter(statusValue)}
              >
                {statusValue.replace("_", " ")}
              </button>
            ))}
          </div>
        </div>
        {actionError ? (
          <div className="mb-3 rounded-md border border-red-100 bg-red-50 px-3 py-2 text-sm text-red-600">{actionError}</div>
        ) : null}
        {!isLoading && actionEvents.length === 0 ? (
          <p className="rounded-lg border border-dashed border-zinc-200 bg-zinc-50 p-5 text-sm text-zinc-500">No reviewable actions for this date.</p>
        ) : null}
        {actionEvents.length > 0 ? (
          <div className="grid gap-4 xl:grid-cols-2">
            {actionEvents.map((event) => {
              const impact = event.impact_summary_json || {};
              const before = event.before_payload_json || {};
              const after = event.after_payload_json || {};
              return (
                <article key={event.id} className="rounded-lg border border-zinc-100 bg-zinc-50/60 p-4 shadow-sm">
                  <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                    <div>
                      <p className="text-xs font-bold uppercase tracking-wide text-purple-700">{event.module}</p>
                      <h3 className="mt-1 text-sm font-bold text-zinc-950">{event.action_type.replace(/_/g, " ")}</h3>
                      <p className="mt-1 text-xs text-zinc-500">
                        Entered by: {event.created_by_name || "Unknown"} ({event.created_by_role || "Unknown"})
                      </p>
                      <p className="text-xs text-zinc-400">{event.created_at ? new Date(event.created_at).toLocaleString() : ""}</p>
                    </div>
                    <span className="w-fit rounded-full bg-white px-3 py-1 text-xs font-bold capitalize text-zinc-700 ring-1 ring-zinc-200">
                      {event.status.replace("_", " ")}
                    </span>
                  </div>

                  <div className="mt-4 grid gap-3 text-xs text-zinc-600 sm:grid-cols-2">
                    <div className="rounded-md bg-white p-3 ring-1 ring-zinc-100">
                      <p className="font-bold text-zinc-900">Action Details</p>
                      <p>Worker: {impact.worker_name || "-"}</p>
                      <p>Machine: {impact.machine_name || "-"}</p>
                      <p>Product: {impact.product_name || "-"}</p>
                      <p>Packaging: {impact.packaging_size_name || "-"}</p>
                      <p>Made: {impact.boxes_made ?? 0} boxes + {impact.loose_packets_made ?? 0} loose</p>
                      <p>Raw used: {impact.blank_used_bora ?? 0} bora, {impact.bottom_used_rolls ?? 0} roll</p>
                    </div>
                    <div className="rounded-md bg-white p-3 ring-1 ring-zinc-100">
                      <p className="font-bold text-zinc-900">Stock Impact</p>
                      <p>Finished: {before.finished_goods?.boxes ?? "-"} to {after.finished_goods?.boxes ?? "-"} boxes</p>
                      <p>Blank: {before.blank_stock?.total_boras ?? "-"} to {after.blank_stock?.total_boras ?? "-"} bora</p>
                      <p>Bottom: {before.bottom_stock?.total_rolls ?? "-"} to {after.bottom_stock?.total_rolls ?? "-"} rolls</p>
                      <p>Box: {before.box_stock?.total_boxes ?? "-"} to {after.box_stock?.total_boxes ?? "-"} cartons</p>
                    </div>
                  </div>

                  {event.status === "rolled_back" ? (
                    <div className="mt-3 rounded-md border border-red-100 bg-red-50 p-3 text-xs text-red-700">
                      Rolled back by {event.rolled_back_by_name || "Unknown"} on {event.rolled_back_at ? new Date(event.rolled_back_at).toLocaleString() : "-"}.
                      <br />Reason: {event.rollback_reason || "-"}
                    </div>
                  ) : null}
                  {event.status === "verified" ? (
                    <div className="mt-3 rounded-md border border-emerald-100 bg-emerald-50 p-3 text-xs text-emerald-700">
                      Verified by {event.verified_by_name || "Unknown"} on {event.verified_at ? new Date(event.verified_at).toLocaleString() : "-"}.
                    </div>
                  ) : null}

                  <div className="mt-4 flex flex-wrap gap-2">
                    {event.allowed_actions?.can_verify ? (
                      <button className="rounded-md bg-emerald-600 px-3 py-1.5 text-xs font-bold text-white" type="button" onClick={() => void handleActionVerify(event.id)}>
                        Confirm Correct
                      </button>
                    ) : null}
                    {event.allowed_actions?.can_rollback ? (
                      <button
                        className="rounded-md border border-red-200 px-3 py-1.5 text-xs font-bold text-red-700"
                        type="button"
                        onClick={() => {
                          setRollbackTarget(event);
                          setRollbackReason("");
                        }}
                      >
                        {user?.role === "Supervisor" ? "Reverse My Entry" : "Rollback Action"}
                      </button>
                    ) : null}
                    <span className="rounded-md border border-zinc-200 px-3 py-1.5 text-xs font-bold text-zinc-600">View Audit</span>
                  </div>
                </article>
              );
            })}
          </div>
        ) : null}
      </section>

      <section className="rounded-lg border border-zinc-150 bg-white p-5 shadow-sm">
        <div className="mb-4 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h2 className="text-base font-bold text-zinc-900">Production Entries Review</h2>
            <p className="text-xs text-zinc-500">Review production stock impact before owner verification or reversal.</p>
          </div>
        </div>
        {productionError ? (
          <div className="mb-3 rounded-md border border-red-100 bg-red-50 px-3 py-2 text-sm text-red-600">{productionError}</div>
        ) : null}
        {!isLoading && productionEntries.length === 0 ? (
          <p className="rounded-lg border border-dashed border-zinc-200 bg-zinc-50 p-5 text-sm text-zinc-500">No production entries for this date.</p>
        ) : null}
        {productionEntries.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-zinc-100 text-sm">
              <thead className="bg-zinc-50 text-left text-xs font-bold uppercase tracking-wide text-zinc-500">
                <tr>
                  <th className="px-3 py-2">Entry Audit</th>
                  <th className="px-3 py-2">Product</th>
                  <th className="px-3 py-2">Qty</th>
                  <th className="px-3 py-2">Raw Used</th>
                  <th className="px-3 py-2">Stock Impact</th>
                  <th className="px-3 py-2">Status</th>
                  <th className="px-3 py-2">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-zinc-100">
                {productionEntries.map((entry) => {
                  const before = entry.stock_before_json as Record<string, any>;
                  const after = entry.stock_after_json as Record<string, any>;
                  return (
                    <tr key={entry.id} className="align-top">
                      <td className="px-3 py-3">
                        <p className="font-semibold text-zinc-900">#{entry.id} · {entry.shift || "-"}</p>
                        <p className="text-xs text-zinc-500">Worker: {entry.worker_name}</p>
                        <p className="text-xs text-zinc-500">Entered by: {entry.created_by || "Unknown"} ({entry.created_by_role || "Unknown"})</p>
                        <p className="text-xs text-zinc-400">{entry.created_at ? new Date(entry.created_at).toLocaleString() : ""}</p>
                      </td>
                      <td className="px-3 py-3">
                        <p className="font-semibold text-zinc-900">{entry.product_size_ml}ml {entry.product_type}</p>
                        <p className="text-xs text-zinc-500">Machine: {entry.machine_name}</p>
                        <p className="text-xs text-zinc-500">Packaging: {entry.packaging_size_name}</p>
                      </td>
                      <td className="px-3 py-3">{entry.quantity_boxes} boxes<br /><span className="text-xs text-zinc-500">{entry.loose_packets_made} loose packets</span></td>
                      <td className="px-3 py-3">{entry.blank_used_bora} bora / {entry.blank_used_kg} kg<br /><span className="text-xs text-zinc-500">{entry.bottom_used_rolls} bottom rolls</span></td>
                      <td className="px-3 py-3 text-xs text-zinc-600">
                        FG: {before.finished_goods?.boxes ?? "-"} → {after.finished_goods?.boxes ?? "-"} boxes<br />
                        Blank: {before.blank_stock?.total_boras ?? "-"} → {after.blank_stock?.total_boras ?? "-"} bora<br />
                        Bottom: {before.bottom_stock?.total_rolls ?? "-"} → {after.bottom_stock?.total_rolls ?? "-"} rolls
                      </td>
                      <td className="px-3 py-3">
                        <span className="rounded-full bg-zinc-100 px-2 py-1 text-xs font-bold capitalize text-zinc-700">{entry.status.replace("_", " ")}</span>
                        {entry.verified_by ? (
                          <p className="mt-2 text-xs text-emerald-700">Verified by {entry.verified_by}<br />{entry.verified_at ? new Date(entry.verified_at).toLocaleString() : ""}</p>
                        ) : null}
                        {entry.reversed_by ? (
                          <p className="mt-2 text-xs text-red-700">Reversed by {entry.reversed_by}<br />{entry.reversed_at ? new Date(entry.reversed_at).toLocaleString() : ""}<br />Reason: {entry.reversal_reason || "-"}</p>
                        ) : null}
                      </td>
                      <td className="px-3 py-3">
                        <div className="flex flex-wrap gap-2">
                          {entry.allowed_actions?.can_verify ? (
                            <button className="rounded-md bg-emerald-600 px-3 py-1.5 text-xs font-bold text-white" type="button" onClick={() => void handleVerify(entry.id)}>Verify</button>
                          ) : null}
                          {entry.allowed_actions?.can_reverse ? (
                            <button className="rounded-md border border-red-200 px-3 py-1.5 text-xs font-bold text-red-700" type="button" onClick={() => void handleReverse(entry.id)}>
                              {user?.role === "Supervisor" ? "Reverse My Entry" : "Reverse Entry"}
                            </button>
                          ) : null}
                          {user?.role === "Supervisor" && entry.status === "pending_review" && entry.allowed_actions?.can_reverse ? (
                            <span className="rounded-md border border-zinc-200 px-3 py-1.5 text-xs font-bold text-zinc-600">Confirm Correct</span>
                          ) : null}
                          <span className="rounded-md border border-zinc-200 px-3 py-1.5 text-xs font-bold text-zinc-600">View Audit</span>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        ) : null}
      </section>

      <section className="rounded-lg border border-zinc-150 bg-white p-5 shadow-sm">
        {isLoading ? <SkeletonCards /> : null}

        {!isLoading && error ? (
          <div className="flex flex-col items-center justify-center rounded-lg border border-red-100 bg-red-50 p-10 text-center text-sm text-red-600">
            <AlertCircle className="mb-2 h-7 w-7" />
            {error}
          </div>
        ) : null}

        {!isLoading && !error && logs.length === 0 ? (
          <div className="flex flex-col items-center justify-center rounded-lg border border-dashed border-zinc-200 bg-zinc-50 p-12 text-center">
            <History className="mb-2 h-8 w-8 text-zinc-300" />
            <p className="text-sm font-semibold text-zinc-600">No activities recorded for this date</p>
            <p className="mt-1 max-w-sm text-xs text-zinc-400">Successful sales, payments, production, attendance, onboarding, and expense actions will appear here automatically.</p>
          </div>
        ) : null}

        {!isLoading && !error && logs.length > 0 ? (
          <div className="relative ml-3 border-l-2 border-zinc-100 pl-6">
            <div className="space-y-4">
              {logs.map((log) => (
                <article key={log.id} className="relative rounded-lg border border-zinc-100 bg-zinc-50/60 p-4 shadow-sm">
                  <span className="absolute -left-[33px] top-5 h-4 w-4 rounded-full border-2 border-purple-600 bg-white" />
                  <div className="grid gap-3 md:grid-cols-[110px_1fr_auto] md:items-start">
                    <div className="w-fit rounded-full bg-white px-3 py-1 text-xs font-bold text-zinc-600 ring-1 ring-zinc-200">
                      {log.time}
                    </div>
                    <div>
                      <p className="text-sm font-bold leading-6 text-zinc-900">{log.action_summary}</p>
                      <p className="mt-1 text-xs text-zinc-500">
                        {log.user_name} · {log.user_role} · {log.relative_day}
                      </p>
                    </div>
                    <span className={`w-fit rounded-full border px-3 py-1 text-xs font-bold capitalize ${entityClass(log.entity_type)}`}>
                      {log.entity_type}
                    </span>
                  </div>
                </article>
              ))}
            </div>
          </div>
        ) : null}
      </section>

      {rollbackTarget ? (
        <div className="fixed inset-0 z-50 grid place-items-center bg-zinc-950/40 p-4">
          <div className="w-full max-w-lg rounded-lg bg-white p-5 shadow-xl">
            <h2 className="text-base font-bold text-zinc-950">Confirm Rollback</h2>
            <p className="mt-2 text-sm text-zinc-600">
              This will reverse the stock impact for action #{rollbackTarget.id}. The original record is kept for audit.
            </p>
            <label className="mt-4 block text-xs font-bold text-zinc-700">
              Reason
              <textarea
                className="mt-2 min-h-[100px] w-full rounded-md border border-zinc-200 p-3 text-sm font-normal outline-none focus:border-red-500"
                value={rollbackReason}
                onChange={(event) => setRollbackReason(event.target.value)}
                placeholder="Explain why this action is being rolled back"
              />
            </label>
            <div className="mt-4 flex justify-end gap-2">
              <button
                type="button"
                className="rounded-md border border-zinc-200 px-4 py-2 text-sm font-bold text-zinc-700"
                onClick={() => {
                  setRollbackTarget(null);
                  setRollbackReason("");
                }}
              >
                Cancel
              </button>
              <button
                type="button"
                className="rounded-md bg-red-600 px-4 py-2 text-sm font-bold text-white disabled:cursor-not-allowed disabled:opacity-50"
                disabled={rollbackReason.trim().length < 3}
                onClick={() => void submitActionRollback()}
              >
                Rollback
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
