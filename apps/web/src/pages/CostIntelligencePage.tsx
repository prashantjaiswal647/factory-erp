import { AlertTriangle, IndianRupee, RefreshCw } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { getTodayCostVariance, type CostVarianceResponse } from "../lib/api";

const MISSING = "Data not available";

function money(value: string) {
  return value === MISSING
    ? value
    : `₹${Number(value).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 4 })}`;
}

function percent(value: string) {
  return value === MISSING ? value : `${Number(value) > 0 ? "+" : ""}${Number(value).toFixed(1)}%`;
}

const badgeClasses = {
  NORMAL: "border-emerald-200 bg-emerald-50 text-emerald-700",
  WARNING: "border-amber-200 bg-amber-50 text-amber-800",
  CRITICAL: "border-red-200 bg-red-50 text-red-700",
};

export default function CostIntelligencePage() {
  const [variance, setVariance] = useState<CostVarianceResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      setVariance(await getTodayCostVariance());
    } catch {
      setError("Cost variance data could not be loaded.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const warnings = Array.from(
    new Set([
      ...(variance?.today?.missing_fields ?? []),
      ...(variance?.seven_day?.missing_fields ?? []),
      ...(variance?.thirty_day?.missing_fields ?? []),
    ]),
  );

  return (
    <div className="mx-auto max-w-6xl space-y-5">
      <header className="flex items-start justify-between border-b border-zinc-200 pb-4">
        <div>
          <div className="mb-3 flex h-10 w-10 items-center justify-center rounded-md bg-brand-600 text-white">
            <IndianRupee className="h-5 w-5" />
          </div>
          <h1 className="text-2xl font-semibold text-zinc-950">Cost Intelligence</h1>
          <p className="mt-1 text-sm text-zinc-500">Deterministic daily cost variance against weighted baselines.</p>
        </div>
        <button
          type="button"
          onClick={() => void load()}
          disabled={loading}
          className="inline-flex items-center gap-2 rounded-md border border-zinc-300 bg-white px-3 py-2 text-sm font-medium text-zinc-700 disabled:opacity-50"
        >
          <RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />
          Refresh
        </button>
      </header>

      {error ? <div className="rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-700">{error}</div> : null}
      {loading && !variance ? <p className="text-sm text-zinc-500">Calculating cost variance...</p> : null}

      {variance ? (
        <>
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
            <Metric label="Today CPC" value={money(variance.today_cpc)} />
            <Metric label="7 Day CPC" value={money(variance.seven_day_cpc)} />
            <Metric label="30 Day CPC" value={money(variance.thirty_day_cpc)} />
            <Metric label="Variance" value={percent(variance.variance_percent)} />
          </div>

          <section className="grid gap-4 rounded-lg border border-zinc-200 bg-white p-5 shadow-sm md:grid-cols-3">
            <div>
              <p className="text-xs font-semibold uppercase tracking-wide text-zinc-500">Status</p>
              <span className={`mt-2 inline-flex rounded-full border px-3 py-1 text-xs font-bold ${badgeClasses[variance.variance_level]}`}>
                {variance.variance_level}
              </span>
            </div>
            <div>
              <p className="text-xs font-semibold uppercase tracking-wide text-zinc-500">Primary Driver</p>
              <p className="mt-2 text-lg font-semibold text-zinc-950">{variance.primary_driver}</p>
            </div>
            <div>
              <p className="text-xs font-semibold uppercase tracking-wide text-zinc-500">Loaded CPC</p>
              <p className="mt-2 text-lg font-semibold text-zinc-950">{money(variance.today_loaded_cpc)}</p>
            </div>
          </section>

          <section className="rounded-lg border border-zinc-200 bg-white p-5 shadow-sm">
            <h2 className="font-semibold text-zinc-950">Cost Driver Changes vs 7 Day Average</h2>
            <CostDriverBars values={[
              ["Material", variance.material_change_percent],
              ["Labour", variance.labour_change_percent],
              ["Electricity", variance.electricity_change_percent],
              ["Overhead", variance.overhead_change_percent],
            ]} />
          </section>
        </>
      ) : null}

      {warnings.length ? (
        <div className="flex items-start gap-2 rounded-lg border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
          <div>
            <p className="font-semibold">Partial data quality</p>
            <p className="mt-1">{warnings.join(", ")}</p>
          </div>
        </div>
      ) : null}
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-zinc-200 bg-white p-4 shadow-sm">
      <p className="text-xs font-semibold uppercase tracking-wide text-zinc-500">{label}</p>
      <p className="mt-2 text-xl font-bold text-zinc-950">{value}</p>
    </div>
  );
}

function CostDriverBars({ values }: { values: Array<[string, string]> }) {
  const numericValues = values.map(([, value]) => value === MISSING ? 0 : Number(value));
  const maxMagnitude = Math.max(...numericValues.map((value) => Math.abs(value)), 1);
  return (
    <div className="mt-5 space-y-4" role="img" aria-label="Cost driver change percentages">
      {values.map(([label, value], index) => {
        const numeric = numericValues[index];
        const width = value === MISSING ? 0 : Math.max((Math.abs(numeric) / maxMagnitude) * 100, 2);
        const barColor = numeric < 0 ? "bg-emerald-500" : "bg-brand-600";
        return (
          <div key={label} className="grid grid-cols-[88px_minmax(0,1fr)_72px] items-center gap-3 text-sm">
            <span className="font-medium text-zinc-700">{label}</span>
            <div className="h-7 overflow-hidden rounded bg-zinc-100">
              <div className={`h-full rounded ${barColor}`} style={{ width: `${width}%` }} />
            </div>
            <span className="text-right font-semibold text-zinc-900">{percent(value)}</span>
          </div>
        );
      })}
    </div>
  );
}
