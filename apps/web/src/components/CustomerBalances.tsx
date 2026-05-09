import { useEffect, useState } from "react";

import { useDataRefresh } from "../context/DataRefreshContext";
import { api } from "../lib/api";
import { asNumber, formatCurrency } from "../lib/format";
import EmptyState from "./EmptyState";
import LoadingState from "./LoadingState";

type CustomerBalance = {
  customer_name: string;
  total_billed: string;
  pending_amount: string;
};

export default function CustomerBalances() {
  const [rows, setRows] = useState<CustomerBalance[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const { refreshVersion } = useDataRefresh();

  useEffect(() => {
    async function loadCustomerBalances() {
      setIsLoading(true);
      setError(null);

      try {
        const response = await api.get<CustomerBalance[]>("/report/customer-balance");
        setRows(response.data);
      } catch {
        setError("Unable to load customer balances.");
      } finally {
        setIsLoading(false);
      }
    }

    void loadCustomerBalances();
  }, [refreshVersion]);

  if (isLoading) {
    return <LoadingState label="Loading customer balances..." />;
  }

  if (error) {
    return <EmptyState title="Customer balances unavailable" message={error} />;
  }

  if (rows.length === 0) {
    return <EmptyState title="No customer balances" message="Sales invoices will appear here once entries are posted." />;
  }

  return (
    <div className="overflow-x-auto">
      <table className="min-w-full divide-y divide-zinc-200">
        <thead className="bg-zinc-50">
          <tr>
            <th className="px-5 py-3 text-left text-xs font-semibold uppercase text-zinc-500">Customer Name</th>
            <th className="px-5 py-3 text-right text-xs font-semibold uppercase text-zinc-500">Total Billed</th>
            <th className="px-5 py-3 text-right text-xs font-semibold uppercase text-zinc-500">Pending Amount</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-zinc-100 bg-white">
          {rows.map((row) => {
            const pending = asNumber(row.pending_amount);
            return (
              <tr key={row.customer_name} className="hover:bg-zinc-50">
                <td className="whitespace-nowrap px-5 py-4 text-sm font-medium text-zinc-950">{row.customer_name}</td>
                <td className="whitespace-nowrap px-5 py-4 text-right text-sm tabular-nums text-zinc-700">
                  {formatCurrency(row.total_billed)}
                </td>
                <td
                  className={`whitespace-nowrap px-5 py-4 text-right text-sm font-semibold tabular-nums ${
                    pending > 0 ? "text-red-600" : "text-emerald-600"
                  }`}
                >
                  {formatCurrency(row.pending_amount)}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
