import { useEffect, useState } from "react";
import { AlertCircle, CalendarDays, History } from "lucide-react";
import axios from "axios";

import { getDailySequenceLogs } from "../lib/api";

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
  const [selectedDate, setSelectedDate] = useState(todayInputValue);
  const [logs, setLogs] = useState<DailySequenceLogItem[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    async function loadLogs() {
      setIsLoading(true);
      setError("");
      try {
        const data = await getDailySequenceLogs(selectedDate);
        if (active) setLogs(data);
      } catch (caught) {
        if (active) {
          setError(errorMessage(caught));
          setLogs([]);
        }
      } finally {
        if (active) setIsLoading(false);
      }
    }
    void loadLogs();
    return () => {
      active = false;
    };
  }, [selectedDate]);

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
    </div>
  );
}
