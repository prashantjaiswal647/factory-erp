import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { getFactoryHealthHistory, type FactoryHealthHistoryItem, type FactoryHealthHistoryResponse } from "../lib/api";
import { factoryHealthRiskRoute } from "../lib/factoryHealthRoutes";


const trendClasses = {
  IMPROVING: "bg-emerald-100 text-emerald-700",
  STABLE: "bg-blue-100 text-blue-700",
  DECLINING: "bg-red-100 text-red-700",
};

function score(value: number | null) {
  return value == null ? "Not available" : value.toFixed(1);
}

function HealthLineChart({ items, onSelect }: { items: FactoryHealthHistoryItem[]; onSelect: (item: FactoryHealthHistoryItem) => void }) {
  const width = 700;
  const height = 150;
  const points = useMemo(() => items.map((item, index) => {
    const x = items.length === 1 ? width / 2 : (index / (items.length - 1)) * width;
    const y = height - (item.overall_score / 100) * height;
    return { item, x, y };
  }), [items]);

  if (!items.length) return <p className="py-8 text-center text-sm text-zinc-500">No health history available.</p>;

  return (
    <div className="overflow-x-auto">
      <svg className="h-44 min-w-[620px] w-full" viewBox={`-10 -10 ${width + 20} ${height + 30}`} role="img" aria-label="Factory health 30 day trend">
        {[25, 50, 75].map((line) => <line key={line} x1="0" x2={width} y1={height - line / 100 * height} y2={height - line / 100 * height} stroke="#e4e4e7" strokeDasharray="4 4" />)}
        <polyline fill="none" stroke="#4f46e5" strokeWidth="3" points={points.map(({ x, y }) => `${x},${y}`).join(" ")} />
        {points.map(({ item, x, y }) => (
          <circle key={item.date} cx={x} cy={y} r="5" fill="#4f46e5" className="cursor-pointer" onClick={() => onSelect(item)}>
            <title>{item.date}: {item.overall_score.toFixed(1)}</title>
          </circle>
        ))}
      </svg>
    </div>
  );
}

function DayPanel({ item }: { item: FactoryHealthHistoryItem }) {
  const components = [
    ["Production", item.production_score],
    ["Attendance", item.attendance_score],
    ["Collections", item.collections_score],
    ["Inventory", item.inventory_score],
    ["Cost", item.cost_score],
  ] as const;
  return (
    <div className="mt-4 rounded-lg border border-zinc-200 bg-zinc-50 p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <p className="font-bold">{item.date} · {item.overall_score.toFixed(1)}/100</p>
          <p className="text-xs text-zinc-600">{item.health_status} · Largest Risk: {item.largest_risk}</p>
        </div>
        <Link className="rounded-md bg-indigo-600 px-3 py-1.5 text-xs font-bold text-white" to={factoryHealthRiskRoute(item.largest_risk)}>Open {item.largest_risk}</Link>
      </div>
      <div className="mt-3 grid grid-cols-5 gap-2">
        {components.map(([label, value]) => <div key={label} className="rounded bg-white p-2 text-center"><p className="truncate text-[10px] text-zinc-500">{label}</p><strong className="text-sm">{Math.round(value)}</strong></div>)}
      </div>
      <div className="mt-3 flex flex-wrap gap-2">
        {components.map(([label]) => <Link key={label} className="rounded border border-zinc-300 bg-white px-2 py-1 text-xs font-semibold" to={factoryHealthRiskRoute(label)}>View {label}</Link>)}
      </div>
    </div>
  );
}

export default function FactoryHealthHistoryCard() {
  const [data, setData] = useState<FactoryHealthHistoryResponse | null>(null);
  const [selected, setSelected] = useState<FactoryHealthHistoryItem | null>(null);

  useEffect(() => {
    void getFactoryHealthHistory(30).then((result) => {
      setData(result);
      setSelected(result.items.length ? result.items[result.items.length - 1] : null);
    }).catch(() => setData(null));
  }, []);

  if (!data) return null;
  const summary = data.summary;
  return (
    <section className="rounded-xl border border-zinc-200 bg-white p-4 shadow-sm" aria-label="Factory health history">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-sm font-bold text-zinc-950">Factory Health History</h2>
          <p className="text-xs text-zinc-600">Deterministic score history from daily snapshots.</p>
        </div>
        <span className={`rounded-full px-3 py-1 text-xs font-bold ${trendClasses[summary.trend_direction]}`}>{summary.trend_direction}</span>
      </div>
      <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-5">
        {[
          ["Current", score(summary.current_score)],
          ["7 Day Avg", score(summary.seven_day_average)],
          ["30 Day Avg", score(summary.thirty_day_average)],
          ["Best Day", summary.best_day?.date || "Not available"],
          ["Worst Day", summary.worst_day?.date || "Not available"],
        ].map(([label, value]) => <div key={label} className="rounded-md bg-zinc-50 p-2"><p className="text-[10px] font-semibold text-zinc-500">{label}</p><p className="mt-1 truncate text-sm font-bold">{value}</p></div>)}
      </div>
      <HealthLineChart items={data.items} onSelect={setSelected} />
      {selected ? <DayPanel item={selected} /> : null}
    </section>
  );
}
