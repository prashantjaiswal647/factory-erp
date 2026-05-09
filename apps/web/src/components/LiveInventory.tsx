import { useEffect, useMemo, useState } from "react";

import { useDataRefresh } from "../context/DataRefreshContext";
import { api } from "../lib/api";
import { formatCurrency, formatDate, formatNumber } from "../lib/format";
import EmptyState from "./EmptyState";
import LoadingState from "./LoadingState";

type InventoryItem = {
  id: number;
  item_name: string;
  category: string;
  unit: string;
  quantity: string;
  price_per_unit: string;
};

type FinishedGoodsItem = {
  id: number;
  cup_size_ml: number;
  packaging_profile_name: string;
  boxes_available: number;
  updated_at: string;
};

type LiveInventoryReport = {
  raw_materials: InventoryItem[];
  packaging_materials: InventoryItem[];
  finished_goods: FinishedGoodsItem[];
};

type InventoryTab = "raw" | "packaging" | "finished";

const tabs: Array<{ id: InventoryTab; label: string }> = [
  { id: "raw", label: "Raw Materials" },
  { id: "packaging", label: "Packaging Materials" },
  { id: "finished", label: "Finished Goods" }
];

export default function LiveInventory() {
  const [report, setReport] = useState<LiveInventoryReport | null>(null);
  const [activeTab, setActiveTab] = useState<InventoryTab>("raw");
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const { refreshVersion } = useDataRefresh();

  useEffect(() => {
    async function loadInventory() {
      setIsLoading(true);
      setError(null);

      try {
        const response = await api.get<LiveInventoryReport>("/report/live-inventory");
        setReport(response.data);
      } catch {
        setError("Unable to load live inventory.");
      } finally {
        setIsLoading(false);
      }
    }

    void loadInventory();
  }, [refreshVersion]);

  const activeRows = useMemo(() => {
    if (!report) {
      return [];
    }
    if (activeTab === "raw") {
      return report.raw_materials;
    }
    if (activeTab === "packaging") {
      return report.packaging_materials;
    }
    return report.finished_goods;
  }, [activeTab, report]);

  if (isLoading) {
    return <LoadingState label="Loading warehouse stock..." />;
  }

  if (error) {
    return <EmptyState title="Inventory unavailable" message={error} />;
  }

  if (!report) {
    return <EmptyState title="No inventory report" message="Inventory data will appear after the API responds." />;
  }

  return (
    <div>
      <div className="border-b border-zinc-200 px-4 pt-4">
        <div className="flex flex-wrap gap-2">
          {tabs.map((tab) => (
            <button
              key={tab.id}
              className={`rounded-md px-3 py-2 text-sm font-medium transition ${
                activeTab === tab.id
                  ? "bg-brand-50 text-brand-700"
                  : "text-zinc-600 hover:bg-zinc-100 hover:text-zinc-950"
              }`}
              type="button"
              onClick={() => setActiveTab(tab.id)}
            >
              {tab.label}
            </button>
          ))}
        </div>
      </div>

      {activeRows.length === 0 ? (
        <EmptyState title="No stock records" message="This inventory section has no records yet." />
      ) : activeTab === "finished" ? (
        <FinishedGoodsTable rows={report.finished_goods} />
      ) : (
        <InventoryTable rows={activeRows as InventoryItem[]} />
      )}
    </div>
  );
}

function InventoryTable({ rows }: { rows: InventoryItem[] }) {
  return (
    <div className="overflow-x-auto">
      <table className="min-w-full divide-y divide-zinc-200">
        <thead className="bg-zinc-50">
          <tr>
            <th className="px-5 py-3 text-left text-xs font-semibold uppercase text-zinc-500">Item</th>
            <th className="px-5 py-3 text-left text-xs font-semibold uppercase text-zinc-500">Category</th>
            <th className="px-5 py-3 text-right text-xs font-semibold uppercase text-zinc-500">Quantity</th>
            <th className="px-5 py-3 text-left text-xs font-semibold uppercase text-zinc-500">Unit</th>
            <th className="px-5 py-3 text-right text-xs font-semibold uppercase text-zinc-500">Price / Unit</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-zinc-100 bg-white">
          {rows.map((row) => (
            <tr key={row.id} className="hover:bg-zinc-50">
              <td className="whitespace-nowrap px-5 py-4 text-sm font-medium text-zinc-950">{row.item_name}</td>
              <td className="whitespace-nowrap px-5 py-4 text-sm text-zinc-700">{row.category}</td>
              <td className="whitespace-nowrap px-5 py-4 text-right text-sm tabular-nums text-zinc-700">
                {formatNumber(row.quantity, 3)}
              </td>
              <td className="whitespace-nowrap px-5 py-4 text-sm text-zinc-700">{row.unit}</td>
              <td className="whitespace-nowrap px-5 py-4 text-right text-sm tabular-nums text-zinc-700">
                {formatCurrency(row.price_per_unit)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function FinishedGoodsTable({ rows }: { rows: FinishedGoodsItem[] }) {
  return (
    <div className="overflow-x-auto">
      <table className="min-w-full divide-y divide-zinc-200">
        <thead className="bg-zinc-50">
          <tr>
            <th className="px-5 py-3 text-left text-xs font-semibold uppercase text-zinc-500">Packing Profile</th>
            <th className="px-5 py-3 text-left text-xs font-semibold uppercase text-zinc-500">Cup Size</th>
            <th className="px-5 py-3 text-right text-xs font-semibold uppercase text-zinc-500">Ready Boxes</th>
            <th className="px-5 py-3 text-left text-xs font-semibold uppercase text-zinc-500">Updated</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-zinc-100 bg-white">
          {rows.map((row) => (
            <tr key={row.id} className="hover:bg-zinc-50">
              <td className="whitespace-nowrap px-5 py-4 text-sm font-medium text-zinc-950">
                {row.packaging_profile_name}
              </td>
              <td className="whitespace-nowrap px-5 py-4 text-sm text-zinc-700">{row.cup_size_ml}ml</td>
              <td className="whitespace-nowrap px-5 py-4 text-right text-sm font-semibold tabular-nums text-brand-700">
                {formatNumber(row.boxes_available)}
              </td>
              <td className="whitespace-nowrap px-5 py-4 text-sm text-zinc-500">{formatDate(row.updated_at)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
