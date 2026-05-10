import { BellRing, IndianRupee, Search, WalletCards, X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { getOutstandingDues, recordPayment, sendOutstandingReminder } from "../lib/api";
import type { OutstandingCustomer, PaymentCreate } from "../lib/api";

const initialPayment: PaymentCreate = {
  customer_phone: "",
  amount_paid: 0,
  payment_mode: "Cash",
  date: new Date().toISOString().slice(0, 10)
};

function money(value: string | number) {
  return `Rs ${Number(value || 0).toLocaleString("en-IN", { maximumFractionDigits: 2 })}`;
}

function formatDateTime(value?: string | null) {
  if (!value) return "-";
  return new Date(value).toLocaleString("en-IN", { dateStyle: "medium", timeStyle: "short" });
}

export default function OutstandingPage() {
  const [rows, setRows] = useState<OutstandingCustomer[]>([]);
  const [grandTotal, setGrandTotal] = useState("0");
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState<OutstandingCustomer | null>(null);
  const [payment, setPayment] = useState<PaymentCreate>(initialPayment);
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [toast, setToast] = useState("");
  const [error, setError] = useState("");

  async function load() {
    setIsLoading(true);
    setError("");
    try {
      const response = await getOutstandingDues();
      setRows(response.data.customers);
      setGrandTotal(response.data.grand_total_outstanding);
    } catch {
      setError("Outstanding dues load nahi ho paaya.");
    } finally {
      setIsLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, []);

  const filteredRows = useMemo(() => {
    const term = query.trim().toLowerCase();
    if (!term) return rows;
    return rows.filter((row) =>
      [row.customer_name, row.customer_phone].some((value) => value.toLowerCase().includes(term))
    );
  }, [query, rows]);

  function openPaymentModal(row: OutstandingCustomer) {
    setSelected(row);
    setPayment({
      ...initialPayment,
      customer_phone: row.customer_phone,
      amount_paid: Number(row.current_pending_balance)
    });
  }

  async function triggerReminder(row: OutstandingCustomer) {
    setError("");
    try {
      const response = await sendOutstandingReminder(row.customer_id);
      setRows((current) =>
        current.map((item) =>
          item.customer_id === row.customer_id ? { ...item, last_reminded_at: response.data.last_reminded_at } : item
        )
      );
      setToast("WhatsApp reminder webhook triggered");
    } catch {
      setError("Reminder bhejne mein error aaya.");
    }
  }

  async function submitPayment() {
    if (!selected || payment.amount_paid <= 0) {
      setError("Valid payment amount daalein.");
      return;
    }

    setIsSaving(true);
    setError("");
    try {
      await recordPayment(payment);
      setToast("Payment saved");
      setSelected(null);
      setPayment(initialPayment);
      await load();
    } catch {
      setError("Payment save nahi ho paaya.");
    } finally {
      setIsSaving(false);
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-zinc-950">Outstanding Udhaar</h1>
          <p className="text-sm text-zinc-500">Customer ledger aur pending market dues.</p>
        </div>
        <button className="h-10 rounded-md border border-zinc-200 px-4 text-sm font-semibold text-zinc-700 hover:bg-zinc-50" type="button" onClick={load}>
          Refresh
        </button>
      </div>

      {toast ? <div className="rounded-md border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm font-medium text-emerald-700">{toast}</div> : null}
      {error ? <div className="rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm font-medium text-red-700">{error}</div> : null}

      <section className="grid gap-4 md:grid-cols-[1fr_2fr]">
        <div className="rounded-lg border border-zinc-200 bg-white p-5 shadow-sm">
          <div className="flex items-center gap-3">
            <div className="grid h-11 w-11 place-items-center rounded-md bg-emerald-50 text-emerald-700">
              <IndianRupee className="h-5 w-5" />
            </div>
            <div>
              <p className="text-sm font-medium text-zinc-500">Total Market Outstanding</p>
              <p className="text-3xl font-semibold text-zinc-950">{money(grandTotal)}</p>
            </div>
          </div>
        </div>

        <div className="rounded-lg border border-zinc-200 bg-white p-5 shadow-sm">
          <label className="text-sm font-medium text-zinc-700" htmlFor="outstanding-search">Search Customer</label>
          <div className="relative mt-2">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-zinc-400" />
            <input
              id="outstanding-search"
              className="h-11 w-full rounded-md border border-zinc-200 pl-9 pr-3 text-sm outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-100"
              placeholder="Name ya phone number"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
            />
          </div>
        </div>
      </section>

      <section className="overflow-hidden rounded-lg border border-zinc-200 bg-white shadow-sm">
        <div className="flex items-center gap-2 border-b border-zinc-200 px-5 py-4">
          <WalletCards className="h-5 w-5 text-brand-600" />
          <h2 className="text-base font-semibold text-zinc-950">Pending Customer Balances</h2>
        </div>

        {isLoading ? (
          <div className="p-6 text-sm text-zinc-500">Loading outstanding dues...</div>
        ) : filteredRows.length === 0 ? (
          <div className="p-6 text-sm text-zinc-500">Koi pending udhaar nahi hai.</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-zinc-200 text-sm">
              <thead className="bg-zinc-50 text-left text-xs font-semibold uppercase text-zinc-500">
                <tr>
                  <th className="px-5 py-3">Name</th>
                  <th className="px-5 py-3">Phone</th>
                  <th className="px-5 py-3 text-right">Total Bill</th>
                  <th className="px-5 py-3 text-right">Total Paid</th>
                  <th className="px-5 py-3 text-right">Pending</th>
                  <th className="px-5 py-3">Last Reminded</th>
                  <th className="px-5 py-3 text-right">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-zinc-100">
                {filteredRows.map((row) => (
                  <tr key={row.customer_id}>
                    <td className="px-5 py-3 font-medium text-zinc-900">{row.customer_name}</td>
                    <td className="px-5 py-3 text-zinc-600">{row.customer_phone}</td>
                    <td className="px-5 py-3 text-right text-zinc-700">{money(row.total_bill_amount)}</td>
                    <td className="px-5 py-3 text-right text-zinc-700">{money(row.total_paid)}</td>
                    <td className="px-5 py-3 text-right font-semibold text-red-700">{money(row.current_pending_balance)}</td>
                    <td className="px-5 py-3 text-zinc-600">{formatDateTime(row.last_reminded_at)}</td>
                    <td className="px-5 py-3 text-right">
                      <div className="flex justify-end gap-2">
                        <button className="rounded-md bg-brand-600 px-3 py-2 text-xs font-semibold text-white hover:bg-brand-700" type="button" onClick={() => openPaymentModal(row)}>
                          Quick Pay
                        </button>
                        <button className="inline-flex items-center gap-1 rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-xs font-semibold text-amber-800 hover:bg-amber-100" type="button" onClick={() => triggerReminder(row)}>
                          <BellRing className="h-3.5 w-3.5" />
                          Send Reminder
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {selected ? (
        <div className="fixed inset-0 z-40 grid place-items-center bg-zinc-950/40 px-4">
          <div className="w-full max-w-md rounded-lg bg-white p-5 shadow-xl">
            <div className="flex items-start justify-between gap-4">
              <div>
                <h2 className="text-lg font-semibold text-zinc-950">Record Payment</h2>
                <p className="text-sm text-zinc-500">{selected.customer_name} - {selected.customer_phone}</p>
              </div>
              <button className="grid h-9 w-9 place-items-center rounded-md border border-zinc-200 text-zinc-600" type="button" onClick={() => setSelected(null)}>
                <X className="h-4 w-4" />
              </button>
            </div>

            <div className="mt-5 grid gap-4">
              <label className="grid gap-1 text-sm font-medium text-zinc-700">
                Amount Paid
                <input className="h-10 rounded-md border border-zinc-200 px-3 text-sm outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-100" type="number" value={payment.amount_paid} onFocus={(event) => event.target.select()} onChange={(event) => setPayment((current) => ({ ...current, amount_paid: Number(event.target.value) }))} />
              </label>
              <label className="grid gap-1 text-sm font-medium text-zinc-700">
                Payment Mode
                <select className="h-10 rounded-md border border-zinc-200 px-3 text-sm outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-100" value={payment.payment_mode} onChange={(event) => setPayment((current) => ({ ...current, payment_mode: event.target.value as PaymentCreate["payment_mode"] }))}>
                  <option value="Cash">Cash</option>
                  <option value="UPI">UPI</option>
                  <option value="Bank Transfer">Bank Transfer</option>
                </select>
              </label>
              <label className="grid gap-1 text-sm font-medium text-zinc-700">
                Date
                <input className="h-10 rounded-md border border-zinc-200 px-3 text-sm outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-100" type="date" value={payment.date} onChange={(event) => setPayment((current) => ({ ...current, date: event.target.value }))} />
              </label>
            </div>

            <div className="mt-6 flex justify-end gap-3">
              <button className="h-10 rounded-md border border-zinc-200 px-4 text-sm font-semibold text-zinc-700 hover:bg-zinc-50" type="button" onClick={() => setSelected(null)}>
                Cancel
              </button>
              <button className="h-10 rounded-md bg-brand-600 px-4 text-sm font-semibold text-white hover:bg-brand-700 disabled:bg-zinc-300" type="button" disabled={isSaving} onClick={submitPayment}>
                {isSaving ? "Saving..." : "Save Payment"}
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
