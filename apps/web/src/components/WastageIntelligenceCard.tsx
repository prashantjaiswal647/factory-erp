import { AlertTriangle, IndianRupee } from "lucide-react";
import { useEffect, useState } from "react";

import { getTodayWastage, type WastageResponse } from "../lib/api";

const statusClasses = {
  NORMAL: "border-emerald-200 bg-emerald-50 text-emerald-700",
  WARNING: "border-amber-200 bg-amber-50 text-amber-800",
  CRITICAL: "border-red-200 bg-red-50 text-red-700",
};

function trend(value: number | null | undefined) {
  return value == null ? "Not available" : `${Number(value).toFixed(1)}%`;
}

const formatNumber = (value: number | undefined | null) => {
  if (value == null) return "0";
  return Number(value).toLocaleString("en-IN");
};

export default function WastageIntelligenceCard() {
  const [data, setData] = useState<WastageResponse | null>(null);

  useEffect(() => {
    void getTodayWastage().then(setData).catch(() => setData(null));
  }, []);

  if (!data) return null;

  const pct = data.wastage_percentage != null ? Number(data.wastage_percentage) : 0;
  const status = data.wastage_status || "NORMAL";
  const expected = data.expected_wastage_percentage != null ? Number(data.expected_wastage_percentage) : 0;
  const loss = data.estimated_loss != null ? Number(data.estimated_loss) : 0;

  return (
    <section className="rounded-xl border border-zinc-200 bg-white p-4 shadow-sm" aria-label="Wastage intelligence">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-center">
        <div className="flex min-w-[205px] items-center gap-3">
          <div className="grid h-12 w-12 place-items-center rounded-full bg-amber-50 text-amber-700">
            <AlertTriangle className="h-6 w-6" />
          </div>
          <div>
            <p className="text-xs font-bold uppercase tracking-wide text-zinc-500">Wastage Intelligence</p>
            <p className="text-3xl font-black text-zinc-950">{pct.toFixed(1)}<span className="text-base text-zinc-500">%</span></p>
          </div>
        </div>
        <div className="min-w-[135px]">
          <span className={`inline-flex rounded-full border px-3 py-1 text-xs font-bold ${statusClasses[status] || statusClasses.NORMAL}`}>
            {status}
          </span>
          <p className="mt-2 text-xs text-zinc-600">Expected {expected.toFixed(1)}%</p>
        </div>
        <div className="grid flex-1 grid-cols-2 gap-2 sm:grid-cols-4">
          <div className="rounded-md bg-zinc-50 px-3 py-2">
            <p className="text-[10px] font-semibold text-zinc-500">Estimated Loss</p>
            <p className="mt-1 flex items-center text-sm font-bold text-zinc-900"><IndianRupee className="h-3.5 w-3.5" />{formatNumber(loss)}</p>
          </div>
          <div className="rounded-md bg-zinc-50 px-3 py-2">
            <p className="text-[10px] font-semibold text-zinc-500">Primary Source</p>
            <p className="mt-1 text-sm font-bold text-zinc-900">{data.primary_wastage_source || "N/A"}</p>
          </div>
          <div className="rounded-md bg-zinc-50 px-3 py-2">
            <p className="text-[10px] font-semibold text-zinc-500">7 Day Weighted</p>
            <p className="mt-1 text-sm font-bold text-zinc-900">{trend(data.seven_day_trend)}</p>
          </div>
          <div className="rounded-md bg-zinc-50 px-3 py-2">
            <p className="text-[10px] font-semibold text-zinc-500">30 Day Weighted</p>
            <p className="mt-1 text-sm font-bold text-zinc-900">{trend(data.thirty_day_trend)}</p>
          </div>
        </div>
      </div>
    </section>
  );
}

