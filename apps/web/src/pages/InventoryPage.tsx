import { Boxes, RefreshCw } from "lucide-react";
import { useEffect, useState } from "react";

import { getInventory } from "../lib/api";
import type { LiveStockRow } from "../lib/api";

export default function InventoryPage() {
  const [rows, setRows] = useState<LiveStockRow[]>([]);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    void load();
  }, []);

  async function load() {
    setIsLoading(true);
    const response = await getInventory();
    setRows(response.data);
    setIsLoading(false);
  }

  return (
    <div className="space-y-5">
      <header className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-zinc-950">Live Inventory</h1>
          <p className="mt-1 text-sm text-zinc-500">Blank, bottom, box, and finished product stock.</p>
        </div>
        <button className="inline-flex h-10 items-center gap-2 rounded-md border border-zinc-200 bg-white px-4 text-sm font-semibold text-zinc-700" type="button" onClick={load}>
          <RefreshCw className="h-4 w-4" />
          Refresh
        </button>
      </header>

      <section className="overflow-hidden rounded-lg border border-zinc-200 bg-white shadow-sm">
        {isLoading ? (
          <div className="p-8 text-sm text-zinc-500">Loading inventory...</div>
        ) : rows.length === 0 ? (
          <div className="flex items-center gap-3 p-8 text-sm text-zinc-500">
            <Boxes className="h-5 w-5" />
            No stock rows found.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-zinc-200">
              <thead className="bg-zinc-50">
                <tr>
                  <th className="px-5 py-3 text-left text-xs font-semibold uppercase text-zinc-500">Type</th>
                  <th className="px-5 py-3 text-left text-xs font-semibold uppercase text-zinc-500">Item</th>
                  <th className="px-5 py-3 text-right text-xs font-semibold uppercase text-zinc-500">Quantity</th>
                  <th className="px-5 py-3 text-left text-xs font-semibold uppercase text-zinc-500">Unit</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-zinc-100">
                {rows.map((row) => (
                  <tr key={`${row.stock_type}-${row.id}`} className="hover:bg-zinc-50">
                    <td className="whitespace-nowrap px-5 py-4 text-sm font-medium text-zinc-950">{row.stock_type}</td>
                    <td className="whitespace-nowrap px-5 py-4 text-sm text-zinc-700">{row.item_name}</td>
                    <td className={`whitespace-nowrap px-5 py-4 text-right text-sm font-semibold tabular-nums ${row.quantity < 0 ? "text-red-600" : "text-zinc-700"}`}>
                      {row.quantity}
                    </td>
                    <td className="whitespace-nowrap px-5 py-4 text-sm text-zinc-500">{row.unit}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}
