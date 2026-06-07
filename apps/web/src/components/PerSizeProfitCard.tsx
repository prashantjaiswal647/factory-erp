import { useEffect, useState } from "react";

import { getPerSizeProfit, type PerSizeProfitResponse } from "../lib/api";

const statusClasses: Record<string, string> = {
  EXCELLENT: "bg-emerald-50 text-emerald-700",
  GOOD: "bg-blue-50 text-blue-700",
  WARNING: "bg-amber-50 text-amber-800",
  CRITICAL: "bg-red-50 text-red-700",
  DATA_NOT_AVAILABLE: "bg-zinc-100 text-zinc-600",
};

const safeArray = <T,>(arr: T[] | undefined | null): T[] => Array.isArray(arr) ? arr : [];

const money = (paise: number | string | undefined | null) => {
  if (paise == null) return "₹0";
  return typeof paise === "number" ? `₹${(paise / 100).toLocaleString("en-IN")}` : paise;
};

const formatNumber = (value: number | undefined | null) => {
  if (value == null) return "0";
  return Number(value).toLocaleString("en-IN");
};

export default function PerSizeProfitCard() {
  const [data, setData] = useState<PerSizeProfitResponse | null>(null);

  useEffect(() => {
    void getPerSizeProfit().then(setData).catch(() => setData(null));
  }, []);

  if (!data) return null;

  const sizes = safeArray(data.sizes);

  return (
    <section className="rounded-xl border border-zinc-200 bg-white p-4 shadow-sm" aria-label="Per-size profit">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="text-xs font-bold uppercase tracking-wide text-zinc-500">Per-Size Profit</p>
          <p className="mt-1 text-sm font-semibold text-zinc-900">
            Best: {data.best_size ? `${data.best_size.size_ml} ml` : "Data not available"}
          </p>
        </div>
        <p className="text-sm font-semibold text-zinc-700">
          Risk: {data.worst_size ? `${data.worst_size.size_ml} ml` : "Data not available"}
        </p>
      </div>
      {sizes.length === 0 ? (
        <p className="rounded-lg bg-zinc-50 px-3 py-4 text-sm text-zinc-600">Per-size profit: Data not available</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[820px] text-left text-xs">
            <thead className="border-b border-zinc-200 text-zinc-500">
              <tr>
                {["Size", "Sold", "Produced", "Revenue", "Cost", "Profit", "Margin", "Status"].map((label) => (
                  <th key={label} className="px-2 py-2 font-semibold">{label}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {sizes.map((item) => {
                const unitsSold = item.units_sold || 0;
                const unitsProduced = item.units_produced || 0;
                const status = item.status || "DATA_NOT_AVAILABLE";
                return (
                  <tr
                    key={item.size_ml}
                    className={`border-b border-zinc-100 last:border-0 ${
                      unitsSold > 0 && unitsProduced > 0 && unitsSold !== unitsProduced
                        ? "bg-amber-50/60"
                        : ""
                    }`}
                  >
                    <td className="px-2 py-2 font-bold text-zinc-900">{item.size_ml} ml</td>
                    <td className="px-2 py-2">{formatNumber(unitsSold)}</td>
                    <td className="px-2 py-2">
                      <span>{formatNumber(unitsProduced)}</span>
                      {unitsSold > 0 && unitsProduced > 0 && unitsSold !== unitsProduced ? (
                        <span className="ml-2 rounded bg-amber-100 px-1.5 py-0.5 text-[10px] font-bold text-amber-800">
                          {unitsProduced > unitsSold ? "Produced > Sold" : "Sold > Produced"}
                        </span>
                      ) : null}
                    </td>
                    <td className="px-2 py-2">{money(item.revenue_paise)}</td>
                    <td className="px-2 py-2">{money(item.cost_paise)}</td>
                    <td className="px-2 py-2">{money(item.gross_profit_paise)}</td>
                    <td className="px-2 py-2">
                      {typeof item.margin_percent === "number" ? `${item.margin_percent.toFixed(1)}%` : item.margin_percent || "0%"}
                    </td>
                    <td className="px-2 py-2">
                      <span className={`rounded-full px-2 py-1 font-bold ${statusClasses[status] || statusClasses.DATA_NOT_AVAILABLE}`}>
                        {(status || "").replace(/_/g, " ")}
                      </span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

