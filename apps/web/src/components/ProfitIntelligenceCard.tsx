import { IndianRupee, TrendingUp } from "lucide-react";
import { useEffect, useState } from "react";

import { getTodayProfit, type ProfitResponse } from "../lib/api";

const statusClasses: Record<string, string> = {
  EXCELLENT: "border-emerald-200 bg-emerald-50 text-emerald-700",
  GOOD: "border-blue-200 bg-blue-50 text-blue-700",
  WARNING: "border-amber-200 bg-amber-50 text-amber-800",
  CRITICAL: "border-red-200 bg-red-50 text-red-700",
  DATA_NOT_AVAILABLE: "border-zinc-200 bg-zinc-50 text-zinc-600",
};

function money(value: number | string | undefined | null) {
  if (value == null) return "₹0";
  return typeof value === "number" ? `₹${value.toLocaleString("en-IN")}` : value;
}

function margin(value: number | null | undefined) {
  return value == null ? "Not available" : `${Number(value).toFixed(1)}%`;
}

export default function ProfitIntelligenceCard() {
  const [data, setData] = useState<ProfitResponse | null>(null);

  useEffect(() => {
    void getTodayProfit().then(setData).catch(() => setData(null));
  }, []);

  if (!data) return null;

  const status = data.profit_status || "DATA_NOT_AVAILABLE";
  const marginPct = data.profit_margin_percent;

  return (
    <section className="rounded-xl border border-zinc-200 bg-white p-4 shadow-sm" aria-label="Profit intelligence">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-center">
        <div className="flex min-w-[205px] items-center gap-3">
          <div className="grid h-12 w-12 place-items-center rounded-full bg-emerald-50 text-emerald-700">
            <TrendingUp className="h-6 w-6" />
          </div>
          <div>
            <p className="text-xs font-bold uppercase tracking-wide text-zinc-500">Profit Intelligence</p>
            <p className="text-2xl font-black text-zinc-950">{money(data.gross_profit)}</p>
          </div>
        </div>
        <div className="min-w-[145px]">
          <span className={`inline-flex rounded-full border px-3 py-1 text-xs font-bold ${statusClasses[status] || statusClasses.DATA_NOT_AVAILABLE}`}>
            {(status || "").replace(/_/g, " ")}
          </span>
          <p className="mt-2 text-xs text-zinc-600">Margin {typeof marginPct === "number" ? `${marginPct.toFixed(1)}%` : marginPct || "Not available"}</p>
        </div>
        <div className="grid flex-1 grid-cols-2 gap-2 sm:grid-cols-4">
          {[
            ["Revenue", money(data.revenue)],
            ["Total Cost", money(data.total_cost)],
            ["7 Day Margin", margin(data.seven_day_margin)],
            ["30 Day Margin", margin(data.thirty_day_margin)],
          ].map(([label, value]) => (
            <div key={label} className="rounded-md bg-zinc-50 px-3 py-2">
              <p className="text-[10px] font-semibold text-zinc-500">{label}</p>
              <p className="mt-1 flex items-center text-sm font-bold text-zinc-900">{label === "Revenue" || label === "Total Cost" ? <IndianRupee className="hidden" /> : null}{value}</p>
            </div>
          ))}
        </div>
        <div className="min-w-[165px] text-xs">
          <p className="text-zinc-500">Largest Risk</p>
          <p className="mt-1 font-bold text-zinc-900">{data.largest_profit_risk || "None"}</p>
        </div>
      </div>
    </section>
  );
}

