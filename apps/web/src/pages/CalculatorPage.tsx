import { Bot, Calculator, IndianRupee, RefreshCw } from "lucide-react";
import type { FormEvent } from "react";
import { useState } from "react";

import { calculateIdealCost, compareIdealWithActual, getActualMonthlyData } from "../lib/api";
import type { ActualMonthlyData, AiCompareResponse, IdealCostRequest, IdealCostResponse } from "../lib/api";

const initialForm: IdealCostRequest = {
  blank_size_ml: 210,
  pieces_per_box: 1000,
  yield_pieces_per_kg_blank: 400,
  blank_price_per_kg: 95,
  bottom_price_per_kg: 110,
  bottom_yield_pieces_per_kg: 2200,
  direct_bottom_cost_per_cup: null,
  daily_labor_cost: 1200,
  expected_daily_production_pieces: 30000,
  packaging_box_price: 22,
  packaging_cost_per_piece: null,
  plastic_price_per_box: 8,
  plastic_price_per_piece: null,
  electricity_flat_cost_per_box: 5,
  electricity_cost_per_piece: null,
  desired_profit_per_box: 50
};

export default function CalculatorPage() {
  const [form, setForm] = useState<IdealCostRequest>(initialForm);
  const [ideal, setIdeal] = useState<IdealCostResponse | null>(null);
  const [actual, setActual] = useState<ActualMonthlyData | null>(null);
  const [aiResult, setAiResult] = useState<AiCompareResponse | null>(null);
  const [bottomMode, setBottomMode] = useState<"yield" | "direct">("yield");
  const [packagingMode, setPackagingMode] = useState<"box" | "piece">("box");
  const [plasticMode, setPlasticMode] = useState<"box" | "piece">("box");
  const [electricityMode, setElectricityMode] = useState<"box" | "piece">("box");
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState("");

  async function submitCalculator(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setIsLoading(true);
    setError("");
    setAiResult(null);

    try {
      const payload: IdealCostRequest =
        bottomMode === "direct"
          ? { ...form, bottom_price_per_kg: null, bottom_yield_pieces_per_kg: null }
          : { ...form, direct_bottom_cost_per_cup: null };
      if (packagingMode === "box") {
        payload.packaging_cost_per_piece = null;
      } else {
        payload.packaging_box_price = null;
      }
      if (plasticMode === "box") {
        payload.plastic_price_per_piece = null;
      } else {
        payload.plastic_price_per_box = null;
      }
      if (electricityMode === "box") {
        payload.electricity_cost_per_piece = null;
      } else {
        payload.electricity_flat_cost_per_box = null;
      }
      const [idealRes, actualRes] = await Promise.all([calculateIdealCost(payload), getActualMonthlyData()]);
      setIdeal(idealRes.data);
      setActual(actualRes.data);
      const aiRes = await compareIdealWithActual({
        ideal_calculation_results: idealRes.data,
        actual_monthly_data: actualRes.data
      });
      setAiResult(aiRes.data);
    } catch {
      setError("Calculator failed. Check backend logs and required inputs.");
    } finally {
      setIsLoading(false);
    }
  }

  return (
    <div className="mx-auto max-w-7xl space-y-6">
      <header className="border-b border-zinc-200 pb-5">
        <div className="mb-3 flex h-11 w-11 items-center justify-center rounded-md bg-brand-600 text-white">
          <Calculator className="h-5 w-5" />
        </div>
        <h1 className="text-2xl font-semibold text-zinc-950">Ideal vs Actual Cost Calculator</h1>
        <p className="mt-1 text-sm text-zinc-500">Deterministic cost math with AI financial comparison.</p>
      </header>

      <form onSubmit={submitCalculator} className="rounded-lg border border-zinc-200 bg-white p-5 shadow-sm">
        <div className="grid gap-4 md:grid-cols-3 xl:grid-cols-4">
          <NumberField label="Blank Size (ml)" value={form.blank_size_ml} onChange={(blank_size_ml) => setForm({ ...form, blank_size_ml })} />
          <NumberField label="Pieces per Box" value={form.pieces_per_box} onChange={(pieces_per_box) => setForm({ ...form, pieces_per_box })} />
          <NumberField label="Blank Yield / KG" value={form.yield_pieces_per_kg_blank} onChange={(yield_pieces_per_kg_blank) => setForm({ ...form, yield_pieces_per_kg_blank })} />
          <NumberField label="Blank Price / KG (₹)" value={form.blank_price_per_kg} onChange={(blank_price_per_kg) => setForm({ ...form, blank_price_per_kg })} />
          <NumberField label="Daily Labor Cost (₹)" value={form.daily_labor_cost} onChange={(daily_labor_cost) => setForm({ ...form, daily_labor_cost })} />
          <NumberField label="Expected Daily Pieces" value={form.expected_daily_production_pieces} onChange={(expected_daily_production_pieces) => setForm({ ...form, expected_daily_production_pieces })} />
          <NumberField label="Desired Profit / Box (₹)" value={form.desired_profit_per_box} onChange={(desired_profit_per_box) => setForm({ ...form, desired_profit_per_box })} />
        </div>

        <div className="mt-5 grid gap-4 xl:grid-cols-4">
          <CostModeCard
            title="Bottom Cost"
            leftLabel="By KG Yield"
            rightLabel="Direct per Cup"
            mode={bottomMode}
            leftValue="yield"
            rightValue="direct"
            onModeChange={setBottomMode}
          >
            {bottomMode === "yield" ? (
              <>
                <OptionalNumberField label="Bottom Price / KG (₹)" value={form.bottom_price_per_kg ?? null} onChange={(bottom_price_per_kg) => setForm({ ...form, bottom_price_per_kg })} />
                <OptionalNumberField label="Bottom Yield / KG" value={form.bottom_yield_pieces_per_kg ?? null} onChange={(bottom_yield_pieces_per_kg) => setForm({ ...form, bottom_yield_pieces_per_kg })} />
              </>
            ) : (
              <OptionalNumberField label="Direct Bottom Cost per Cup (₹)" value={form.direct_bottom_cost_per_cup ?? null} onChange={(direct_bottom_cost_per_cup) => setForm({ ...form, direct_bottom_cost_per_cup })} />
            )}
          </CostModeCard>

          <CostModeCard
            title="Box Packaging Cost"
            leftLabel="Direct per Box"
            rightLabel="Cost per Piece"
            mode={packagingMode}
            leftValue="box"
            rightValue="piece"
            onModeChange={setPackagingMode}
          >
            {packagingMode === "box" ? (
              <OptionalNumberField label="Packaging Box Price (₹)" value={form.packaging_box_price ?? null} onChange={(packaging_box_price) => setForm({ ...form, packaging_box_price })} />
            ) : (
              <OptionalNumberField label="Packaging Cost per Piece (₹)" value={form.packaging_cost_per_piece ?? null} onChange={(packaging_cost_per_piece) => setForm({ ...form, packaging_cost_per_piece })} />
            )}
          </CostModeCard>

          <CostModeCard
            title="Plastic Cost"
            leftLabel="Direct per Box"
            rightLabel="Cost per Piece"
            mode={plasticMode}
            leftValue="box"
            rightValue="piece"
            onModeChange={setPlasticMode}
          >
            {plasticMode === "box" ? (
              <OptionalNumberField label="Plastic Price / Box (₹)" value={form.plastic_price_per_box ?? null} onChange={(plastic_price_per_box) => setForm({ ...form, plastic_price_per_box })} />
            ) : (
              <OptionalNumberField label="Plastic Price per Piece (₹)" value={form.plastic_price_per_piece ?? null} onChange={(plastic_price_per_piece) => setForm({ ...form, plastic_price_per_piece })} />
            )}
          </CostModeCard>

          <CostModeCard
            title="Electricity Cost"
            leftLabel="Flat per Box"
            rightLabel="Cost per Piece"
            mode={electricityMode}
            leftValue="box"
            rightValue="piece"
            onModeChange={setElectricityMode}
          >
            {electricityMode === "box" ? (
              <OptionalNumberField label="Electricity / Box (₹)" value={form.electricity_flat_cost_per_box ?? null} onChange={(electricity_flat_cost_per_box) => setForm({ ...form, electricity_flat_cost_per_box })} />
            ) : (
              <OptionalNumberField label="Electricity per Piece (₹)" value={form.electricity_cost_per_piece ?? null} onChange={(electricity_cost_per_piece) => setForm({ ...form, electricity_cost_per_piece })} />
            )}
          </CostModeCard>
        </div>

        <button className="mt-5 inline-flex h-10 items-center gap-2 rounded-md bg-brand-600 px-4 text-sm font-semibold text-white hover:bg-brand-700 disabled:bg-zinc-300" type="submit" disabled={isLoading}>
          {isLoading ? <RefreshCw className="h-4 w-4 animate-spin" /> : <IndianRupee className="h-4 w-4" />}
          {isLoading ? "Calculating..." : "Calculate Ideal vs Actual"}
        </button>
      </form>

      {error ? <div className="rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{error}</div> : null}

      <section className="grid gap-6 xl:grid-cols-2">
        <ResultTable title="Ideal Projections" rows={idealRows(ideal)} emptyLabel="Run the calculator to see ideal cost projection." />
        <ResultTable title="Actual Monthly Reality" rows={actualRows(actual)} emptyLabel="Run the calculator to fetch actual monthly production data." />
      </section>

      <section className="rounded-lg border border-amber-200 bg-amber-50 p-5 shadow-sm">
        <div className="flex items-center gap-2">
          <Bot className="h-5 w-5 text-amber-700" />
          <h2 className="text-base font-semibold text-amber-950">AI Financial Analyst Insight</h2>
        </div>
        <p className="mt-3 text-sm leading-6 text-amber-900">
          {aiResult?.ai_insights || "AI comparison will appear here after ideal and actual values are calculated."}
        </p>
      </section>

      {aiResult ? (
        <ResultTable
          title="AI Comparison Table"
          rows={aiResult.comparison_table_data.map((row) => ({
            metric: row.metric,
            value: row.ideal_value,
            helper: `Actual: ${row.actual_value} | ${row.difference}`
          }))}
          emptyLabel=""
        />
      ) : null}
    </div>
  );
}

function NumberField({ label, value, onChange }: { label: string; value: number; onChange: (value: number) => void }) {
  return (
    <label className="space-y-1 text-sm">
      <span className="font-medium text-zinc-700">{label}</span>
      <input
        className="h-10 w-full rounded-md border border-zinc-200 px-3 outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-100"
        min="0"
        step="any"
        type="number"
        value={value}
        onFocus={(event) => event.target.select()}
        onChange={(event) => onChange(Number(event.target.value))}
      />
    </label>
  );
}

function OptionalNumberField({ label, value, onChange }: { label: string; value: number | null; onChange: (value: number | null) => void }) {
  return (
    <label className="space-y-1 text-sm">
      <span className="font-medium text-zinc-700">{label}</span>
      <input
        className="h-10 w-full rounded-md border border-zinc-200 px-3 outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-100"
        min="0"
        step="any"
        type="number"
        value={value ?? ""}
        onFocus={(event) => event.target.select()}
        onChange={(event) => onChange(event.target.value === "" ? null : Number(event.target.value))}
      />
    </label>
  );
}

function CostModeCard<T extends string>({
  title,
  leftLabel,
  rightLabel,
  mode,
  leftValue,
  rightValue,
  onModeChange,
  children
}: {
  title: string;
  leftLabel: string;
  rightLabel: string;
  mode: T;
  leftValue: T;
  rightValue: T;
  onModeChange: (mode: T) => void;
  children: React.ReactNode;
}) {
  return (
    <section className="rounded-lg border border-zinc-200 bg-zinc-50 p-4">
      <h2 className="text-sm font-semibold text-zinc-950">{title}</h2>
      <div className="mt-3 flex flex-wrap items-center gap-2">
        <button className={`h-9 rounded-md px-3 text-sm font-semibold ${mode === leftValue ? "bg-brand-600 text-white" : "bg-white text-zinc-700"}`} type="button" onClick={() => onModeChange(leftValue)}>
          {leftLabel}
        </button>
        <button className={`h-9 rounded-md px-3 text-sm font-semibold ${mode === rightValue ? "bg-brand-600 text-white" : "bg-white text-zinc-700"}`} type="button" onClick={() => onModeChange(rightValue)}>
          {rightLabel}
        </button>
      </div>
      <div className="mt-4 grid gap-4">{children}</div>
    </section>
  );
}

function ResultTable({ title, rows, emptyLabel }: { title: string; rows: Array<{ metric: string; value: string; helper?: string }>; emptyLabel: string }) {
  return (
    <div className="rounded-lg border border-zinc-200 bg-white p-5 shadow-sm">
      <h2 className="text-base font-semibold text-zinc-950">{title}</h2>
      {rows.length === 0 ? (
        <p className="mt-4 rounded-md border border-dashed border-zinc-300 p-6 text-center text-sm text-zinc-500">{emptyLabel}</p>
      ) : (
        <div className="mt-4 overflow-x-auto">
          <table className="min-w-full divide-y divide-zinc-200">
            <tbody className="divide-y divide-zinc-100">
              {rows.map((row) => (
                <tr key={row.metric}>
                  <td className="px-3 py-3 text-sm font-medium text-zinc-700">{row.metric}</td>
                  <td className="px-3 py-3 text-right text-sm font-semibold text-zinc-950">{row.value}</td>
                  {row.helper ? <td className="px-3 py-3 text-sm text-zinc-500">{row.helper}</td> : null}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function idealRows(ideal: IdealCostResponse | null) {
  if (!ideal) return [];
  return [
    { metric: "Blank cost / piece", value: `₹${ideal.per_piece_blank_cost}` },
    { metric: "Bottom cost / piece", value: `₹${ideal.per_piece_bottom_cost}` },
    { metric: "Labor cost / piece", value: `₹${ideal.labor_cost_per_piece}` },
    { metric: "Raw cost / box", value: `₹${ideal.total_raw_cost_per_box}` },
    { metric: "Final cost / box", value: `₹${ideal.final_cost_per_box}` },
    { metric: "Suggested selling price", value: `₹${ideal.suggested_selling_price}` },
    { metric: "Profit margin", value: `${ideal.profit_margin_percent}%` }
  ];
}

function actualRows(actual: ActualMonthlyData | null) {
  if (!actual) return [];
  return [
    { metric: "Month start", value: actual.month_start },
    { metric: "Production entries", value: String(actual.production_entries) },
    { metric: "Actual boxes made", value: String(actual.actual_boxes_made) },
    { metric: "Estimated pieces made", value: String(actual.estimated_pieces_made) },
    { metric: "Blank used", value: `${actual.blank_used_kg} kg` },
    { metric: "Bottom used", value: `${actual.bottom_used_kg} kg` },
    { metric: "Blank kg / box", value: `${actual.actual_blank_kg_per_box}` },
    { metric: "Bottom kg / box", value: `${actual.actual_bottom_kg_per_box}` },
    { metric: "Final stock boxes", value: String(actual.final_stock_boxes) }
  ];
}
