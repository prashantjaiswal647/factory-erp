import { Calculator, IndianRupee, Percent, TrendingUp } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import type { FormEvent } from "react";
import { useState } from "react";

import { calculateProfit } from "../lib/api";
import type { ProfitResult } from "../lib/api";
import { asNumber, formatCurrency, formatNumber } from "../lib/format";

export default function CalculatorPage() {
  const [productNameMl, setProductNameMl] = useState(210);
  const [sellingPricePerBox, setSellingPricePerBox] = useState(0);
  const [result, setResult] = useState<ProfitResult | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submitCalculator(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setIsLoading(true);
    setError(null);

    try {
      const response = await calculateProfit({
        product_name_ml: productNameMl,
        selling_price_per_box: sellingPricePerBox
      });
      setResult(response.data);
    } catch {
      setError("Profit calculation failed. Check packaging profile, yield, and costing master setup.");
    } finally {
      setIsLoading(false);
    }
  }

  return (
    <div className="mx-auto max-w-5xl space-y-6">
      <div className="border-b border-zinc-200 pb-5">
        <div className="mb-3 flex h-11 w-11 items-center justify-center rounded-md bg-brand-600 text-white">
          <Calculator className="h-5 w-5" />
        </div>
        <h1 className="text-2xl font-semibold text-zinc-950">Profitability Calculator</h1>
        <p className="mt-1 text-sm text-zinc-500">Calculate paper cup box cost, margin, and per-glass profit.</p>
      </div>

      <form onSubmit={submitCalculator} className="grid gap-4 rounded-md border border-zinc-200 bg-white p-5 shadow-sm md:grid-cols-[1fr_1fr_auto] md:items-end">
        <label className="space-y-1 text-sm">
          <span className="font-medium text-zinc-700">Product Size</span>
          <select
            className="h-10 w-full rounded-md border border-zinc-200 px-3 outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-100"
            value={productNameMl}
            onChange={(event) => setProductNameMl(Number(event.target.value))}
          >
            {[65, 90, 100, 150, 200, 210, 250, 300, 350, 500].map((size) => (
              <option key={size} value={size}>{size}ml</option>
            ))}
          </select>
        </label>

        <label className="space-y-1 text-sm">
          <span className="font-medium text-zinc-700">Selling Price Per Box</span>
          <input
            className="h-10 w-full rounded-md border border-zinc-200 px-3 outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-100"
            min="0"
            type="number"
            value={sellingPricePerBox}
            onChange={(event) => setSellingPricePerBox(Number(event.target.value))}
          />
        </label>

        <button
          type="submit"
          disabled={isLoading}
          className="inline-flex h-10 items-center justify-center gap-2 rounded-md bg-brand-600 px-4 text-sm font-medium text-white hover:bg-brand-700 disabled:cursor-not-allowed disabled:opacity-60"
        >
          <Calculator className="h-4 w-4" />
          {isLoading ? "Calculating..." : "Calculate"}
        </button>
      </form>

      {error ? <p className="rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{error}</p> : null}

      {result ? (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          <MetricCard icon={IndianRupee} label="Total Cost" value={formatCurrency(asNumber(result.cost_per_box))} helper={`${result.cups_per_box} cups per box`} />
          <MetricCard icon={Percent} label="Profit Margin" value={`${formatNumber(asNumber(result.profit_margin_percent))}%`} helper="Against selling price" />
          <MetricCard icon={TrendingUp} label="Profit per Box" value={formatCurrency(asNumber(result.profit_per_box))} helper={`Selling at ${formatCurrency(sellingPricePerBox)}`} />
          <MetricCard icon={IndianRupee} label="Profit per Glass" value={formatCurrency(asNumber(result.profit_per_piece))} helper={`Cost ${formatCurrency(asNumber(result.cost_per_piece))}`} />
        </div>
      ) : (
        <div className="rounded-md border border-dashed border-zinc-300 bg-white p-8 text-center text-sm text-zinc-500">
          Enter a product and selling price to see profitability.
        </div>
      )}
    </div>
  );
}

function MetricCard({
  icon: Icon,
  label,
  value,
  helper
}: {
  icon: LucideIcon;
  label: string;
  value: string;
  helper: string;
}) {
  return (
    <div className="rounded-md border border-zinc-200 bg-white p-5 shadow-sm">
      <div className="mb-4 flex h-10 w-10 items-center justify-center rounded-md bg-brand-50 text-brand-700">
        <Icon className="h-5 w-5" />
      </div>
      <p className="text-sm font-medium text-zinc-500">{label}</p>
      <p className="mt-2 text-2xl font-semibold text-zinc-950">{value}</p>
      <p className="mt-1 text-xs text-zinc-500">{helper}</p>
    </div>
  );
}
