import React, { useState, useEffect } from "react";
import { 
  CalendarDays, 
  Clock, 
  History,
  AlertCircle,
  ShieldCheck
} from "lucide-react";
import { getDailySequenceLogs, type DailySequenceLogItem } from "../lib/api";

export default function DailySequencePage() {
  const [date, setDate] = useState(() => new Date().toISOString().split("T")[0]);
  const [logs, setLogs] = useState<DailySequenceLogItem[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    void fetchLogs(date);
  }, [date]);

  async function fetchLogs(targetDate: string) {
    setIsLoading(true);
    setError("");
    try {
      const data = await getDailySequenceLogs(targetDate);
      setLogs(data);
    } catch (err: any) {
      console.error("Failed to load daily sequence logs:", err);
      setError(err?.response?.data?.detail || "Failed to load activity logs.");
      setLogs([]);
    } finally {
      setIsLoading(false);
    }
  }

  const getRoleBadgeColor = (role?: string | null) => {
    const r = (role || "").toLowerCase().trim();
    if (r === "owner") return "bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-400 border border-blue-200";
    if (r === "sub-owner") return "bg-purple-100 text-purple-800 dark:bg-purple-900/30 dark:text-purple-400 border border-purple-200";
    if (r === "supervisor") return "bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-400 border border-amber-200";
    return "bg-zinc-100 text-zinc-800 dark:bg-zinc-800 dark:text-zinc-400 border border-zinc-200";
  };

  return (
    <div className="space-y-6">
      {/* Top Header Panel */}
      <header className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between rounded-2xl bg-white p-5 border border-zinc-150 shadow-sm">
        <div className="flex items-center gap-3">
          <div className="grid h-12 w-12 place-items-center rounded-xl bg-purple-100 text-purple-700">
            <History className="h-6 w-6" />
          </div>
          <div>
            <h1 className="text-xl font-black text-zinc-950">Daily Activity Sequence</h1>
            <p className="text-xs text-zinc-500">Automated chronological event sequence tracking committed logs</p>
          </div>
        </div>

        {/* Date Filter Datepicker */}
        <div className="flex items-center gap-2">
          <CalendarDays className="h-4 w-4 text-zinc-400" />
          <input
            type="date"
            value={date}
            onChange={(e) => setDate(e.target.value)}
            className="h-10 rounded-lg border border-zinc-200 px-3 text-sm font-semibold text-zinc-800 focus:border-purple-600 outline-none bg-white shadow-sm"
          />
        </div>
      </header>

      {/* Timeline Section */}
      <section className="rounded-2xl bg-white p-6 border border-zinc-150 shadow-sm min-h-[400px]">
        {isLoading ? (
          <div className="flex flex-col items-center justify-center p-12 text-sm text-zinc-400">
            <div className="h-8 w-8 animate-spin rounded-full border-4 border-zinc-200 border-t-purple-600 mb-2" />
            Fetching activities sequence...
          </div>
        ) : error ? (
          <div className="flex flex-col items-center justify-center p-12 text-center text-sm text-rose-500">
            <AlertCircle className="h-8 w-8 mb-2" />
            {error}
          </div>
        ) : logs.length === 0 ? (
          <div className="flex flex-col items-center justify-center p-12 text-center text-sm text-zinc-400 border border-dashed border-zinc-200 rounded-xl">
            <History className="h-8 w-8 text-zinc-300 mb-2" />
            <p className="font-semibold text-zinc-500">No activities recorded for this date</p>
            <p className="text-xs text-zinc-400 mt-1 max-w-xs">
              Factory operations, customer batch updates, and payment collection ledgers will automatically display here upon transaction success.
            </p>
          </div>
        ) : (
          <div className="relative border-l-2 border-zinc-100 ml-4 pl-6 space-y-6">
            {logs.map((log) => {
              return (
                <div key={log.id} className="relative group">
                  {/* Stepper Bullet icon */}
                  <span className="absolute -left-[35px] top-1.5 flex h-8 w-8 items-center justify-center rounded-full border-2 border-purple-500 bg-white text-purple-700 shadow-sm transition group-hover:scale-110">
                    <ShieldCheck className="h-4 w-4" />
                  </span>

                  {/* Card item */}
                  <div className="rounded-xl border border-zinc-100 bg-zinc-50/50 p-4 transition-all duration-300 hover:border-zinc-200 hover:bg-white hover:shadow-sm flex flex-col md:flex-row md:items-start md:justify-between gap-4">
                    <div className="space-y-2">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="inline-flex items-center rounded-full bg-zinc-100 px-2.5 py-0.5 text-[10px] font-bold uppercase tracking-wider text-zinc-700">
                          {log.action_type || "CREATE"}
                        </span>
                        <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-bold ${getRoleBadgeColor(log.user_role)}`}>
                          {log.user_role}
                        </span>
                        <div className="inline-flex items-center gap-1 text-[11px] font-semibold text-zinc-500">
                          <Clock className="h-3 w-3" />
                          {log.created_time || "Pending"}
                        </div>
                      </div>
                      <p className="text-sm font-medium leading-relaxed text-zinc-800">{log.short_statement}</p>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </section>
    </div>
  );
}
