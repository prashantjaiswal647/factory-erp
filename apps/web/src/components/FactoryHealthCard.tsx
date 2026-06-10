import { Activity, TrendingDown, TrendingUp } from "lucide-react";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { getTodayFactoryHealth, type FactoryHealthResponse } from "../lib/api";
import { factoryHealthRiskRoute } from "../lib/factoryHealthRoutes";


const statusClasses = {
  CRITICAL: "border-red-200 bg-red-50 text-red-700",
  WARNING: "border-amber-200 bg-amber-50 text-amber-800",
  GOOD: "border-blue-200 bg-blue-50 text-blue-700",
  EXCELLENT: "border-emerald-200 bg-emerald-50 text-emerald-700",
};

export default function FactoryHealthCard() {
  const [health, setHealth] = useState<FactoryHealthResponse | null>(null);

  useEffect(() => {
    void getTodayFactoryHealth().then(setHealth).catch(() => setHealth(null));
  }, []);

  if (!health) return null;
  const trend = health.trend;
  const TrendIcon = trend != null && trend < 0 ? TrendingDown : TrendingUp;
  const components = [
    ["Production", health.production_score ?? 0],
    ["Attendance", health.attendance_score ?? 0],
    ["Collections", health.collections_score ?? 0],
    ["Inventory", health.inventory_score ?? 0],
    ["Cost", health.cost_score ?? 0],
  ] as const;

  const status = health.health_status || "GOOD";

  return (
    <section className="rounded-xl border border-zinc-200 bg-white p-4 shadow-sm" aria-label="Factory health score" data-test-id="factory-health-card">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-center">
        <div className="flex min-w-[190px] items-center gap-3">
          <div className="grid h-12 w-12 place-items-center rounded-full bg-brand-50 text-brand-700">
            <Activity className="h-6 w-6" />
          </div>
          <div>
            <p className="text-xs font-bold uppercase tracking-wide text-zinc-500">Factory Health</p>
            <p className="text-3xl font-black text-zinc-950" data-test-id="health-score">{Math.round(health.overall_score ?? 0)}<span className="text-base text-zinc-500">/100</span></p>
          </div>
        </div>
        <div className="min-w-[150px]">
          <span className={`inline-flex rounded-full border px-3 py-1 text-xs font-bold ${statusClasses[status] || statusClasses.GOOD}`}>
            {status}
          </span>
          <p className="mt-2 flex items-center gap-1 text-xs text-zinc-600">
            {trend == null ? "First snapshot" : <><TrendIcon className="h-3.5 w-3.5" />{trend > 0 ? "+" : ""}{Number(trend).toFixed(1)} vs previous</>}
          </p>
        </div>
        <div className="grid flex-1 grid-cols-5 gap-2">
          {components.map(([label, score]) => (
            <div key={label} className="min-w-0 rounded-md bg-zinc-50 px-2 py-2 text-center">
              <p className="truncate text-[10px] font-semibold text-zinc-500">{label}</p>
              <p className="mt-1 text-sm font-bold text-zinc-900">{Math.round(score)}</p>
            </div>
          ))}
        </div>
        <div className="min-w-[180px] text-xs">
          <p><span className="text-zinc-500">Strength:</span> <strong>{health.largest_strength || "N/A"}</strong></p>
          <p className="mt-1"><span className="text-zinc-500">Risk:</span> <Link className="font-bold text-indigo-700 underline" to={factoryHealthRiskRoute(health.largest_risk || "Production")}>{health.largest_risk || "None"}</Link></p>
        </div>
      </div>
    </section>
  );
}

