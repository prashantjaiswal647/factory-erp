import { useEffect, useState } from "react";

import { useDataRefresh } from "../context/DataRefreshContext";
import { api } from "../lib/api";
import { formatCurrency, formatDate, formatNumber } from "../lib/format";
import EmptyState from "./EmptyState";
import LoadingState from "./LoadingState";

type ProductionLogRow = {
  id: number;
  date: string;
  shift: string;
  cup_size_ml: number;
  packaging_profile_name: string;
  boxes_produced: number;
  estimated_good_cups: number;
  blank_waste_pcs: number;
  bottom_waste_kg: string;
  blank_wastage_percent: string;
  total_packing_cost: string;
  total_production_cost: string;
};

export default function ProductionLog() {
  const [rows, setRows] = useState<ProductionLogRow[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const { refreshVersion } = useDataRefresh();

  useEffect(() => {
    async function loadProductionLog() {
      setIsLoading(true);
      setError(null);

      try {
        const response = await api.get<ProductionLogRow[]>("/report/production-log");
        setRows(response.data);
      } catch {
        setError("Unable to load production log.");
      } finally {
        setIsLoading(false);
      }
    }

    void loadProductionLog();
  }, [refreshVersion]);

  if (isLoading) {
    return <LoadingState label="Loading production records..." />;
  }

  if (error) {
    return <EmptyState title="Production log unavailable" message={error} />;
  }

  if (rows.length === 0) {
    return <EmptyState title="No production entries" message="Production entries from AI Supervisor will appear here." />;
  }

  return (
    <div className="overflow-x-auto">
      <table className="min-w-full divide-y divide-zinc-200">
        <thead className="bg-zinc-50">
          <tr>
            <th className="px-5 py-3 text-left text-xs font-semibold uppercase text-zinc-500">Date</th>
            <th className="px-5 py-3 text-left text-xs font-semibold uppercase text-zinc-500">Shift</th>
            <th className="px-5 py-3 text-left text-xs font-semibold uppercase text-zinc-500">Cup Size</th>
            <th className="px-5 py-3 text-left text-xs font-semibold uppercase text-zinc-500">Packing</th>
            <th className="px-5 py-3 text-right text-xs font-semibold uppercase text-zinc-500">Boxes</th>
            <th className="px-5 py-3 text-right text-xs font-semibold uppercase text-zinc-500">Good Cups</th>
            <th className="px-5 py-3 text-right text-xs font-semibold uppercase text-zinc-500">Blank Waste</th>
            <th className="px-5 py-3 text-right text-xs font-semibold uppercase text-zinc-500">Bottom Waste</th>
            <th className="px-5 py-3 text-right text-xs font-semibold uppercase text-zinc-500">Waste %</th>
            <th className="px-5 py-3 text-right text-xs font-semibold uppercase text-zinc-500">Cost</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-zinc-100 bg-white">
          {rows.map((row) => (
            <tr key={row.id} className="hover:bg-zinc-50">
              <td className="whitespace-nowrap px-5 py-4 text-sm text-zinc-700">{formatDate(row.date)}</td>
              <td className="whitespace-nowrap px-5 py-4 text-sm font-medium text-zinc-950">{row.shift}</td>
              <td className="whitespace-nowrap px-5 py-4 text-sm text-zinc-700">{row.cup_size_ml}ml</td>
              <td className="whitespace-nowrap px-5 py-4 text-sm text-zinc-700">{row.packaging_profile_name}</td>
              <td className="whitespace-nowrap px-5 py-4 text-right text-sm tabular-nums text-zinc-700">
                {formatNumber(row.boxes_produced)}
              </td>
              <td className="whitespace-nowrap px-5 py-4 text-right text-sm tabular-nums text-zinc-700">
                {formatNumber(row.estimated_good_cups)}
              </td>
              <td className="whitespace-nowrap px-5 py-4 text-right text-sm tabular-nums text-zinc-700">
                {formatNumber(row.blank_waste_pcs)}
              </td>
              <td className="whitespace-nowrap px-5 py-4 text-right text-sm tabular-nums text-zinc-700">
                {formatNumber(row.bottom_waste_kg, 3)} kg
              </td>
              <td className="whitespace-nowrap px-5 py-4 text-right text-sm font-semibold tabular-nums text-amber-700">
                {formatNumber(row.blank_wastage_percent, 2)}%
              </td>
              <td className="whitespace-nowrap px-5 py-4 text-right text-sm tabular-nums text-zinc-700">
                {formatCurrency(row.total_production_cost)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
