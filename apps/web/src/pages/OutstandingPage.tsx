import { BellRing, ChevronDown, IndianRupee, Search, Trash2, WalletCards, X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { clearOutstandingBill, getOutstandingDues, recordPayment, sendOutstandingReminder } from "../lib/api";
import { useDataRefresh } from "../context/DataRefreshContext";
import { useAuth } from "../context/AuthContext";
import type { OutstandingBill, OutstandingCustomer, PaymentCreate } from "../lib/api";

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

function Summary({ label, value, strong = false }: { label: string; value: string; strong?: boolean }) {
  return (
    <span className="text-sm md:text-right">
      <span className="block text-xs font-medium uppercase text-zinc-400">{label}</span>
      <span className={strong ? "font-semibold text-red-700" : "font-medium text-zinc-700"}>{value}</span>
    </span>
  );
}

export default function OutstandingPage() {
  const [rows, setRows] = useState<OutstandingCustomer[]>([]);
  const [grandTotal, setGrandTotal] = useState("0");
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState<OutstandingCustomer | null>(null);
  const [selectedBill, setSelectedBill] = useState<OutstandingBill | null>(null);
  const [expandedCustomerId, setExpandedCustomerId] = useState<number | null>(null);
  const [payment, setPayment] = useState<PaymentCreate>(initialPayment);
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [toast, setToast] = useState("");
  const [error, setError] = useState("");
  const [deleteModalData, setDeleteModalData] = useState<{ row: OutstandingCustomer; bill: OutstandingBill } | null>(null);
  const [expandedBillHistoryId, setExpandedBillHistoryId] = useState<number | null>(null);
  const { refreshVersion, triggerDataRefresh } = useDataRefresh();
  const { user } = useAuth();
  const canDeleteOutstanding = user?.role === "Owner";

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
  }, [refreshVersion]);

  const filteredRows = useMemo(() => {
    const term = query.trim().toLowerCase();
    if (!term) return rows;
    return rows.filter((row) =>
      [row.customer_name, row.customer_phone].some((value) => value.toLowerCase().includes(term))
    );
  }, [query, rows]);

  function openPaymentModal(row: OutstandingCustomer, bill?: OutstandingBill) {
    setSelected(row);
    setSelectedBill(bill || null);
    setPayment({
      ...initialPayment,
      customer_phone: row.customer_phone,
      sale_id: bill?.order_id ?? undefined,
      amount_paid: Number(bill?.remaining_balance ?? row.current_pending_balance)
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
      setSelectedBill(null);
      setPayment(initialPayment);
      triggerDataRefresh();
      await load();
    } catch {
      setError("Payment save nahi ho paaya.");
    } finally {
      setIsSaving(false);
    }
  }

  function initiateDeleteBill(row: OutstandingCustomer, bill: OutstandingBill) {
    if (!canDeleteOutstanding) {
      setError("Access Denied: Only the Factory Owner is authorized to delete entries.");
      return;
    }
    setDeleteModalData({ row, bill });
  }

  async function handleConfirmDelete(reason: "mistake" | "paid") {
    if (!deleteModalData) return;
    const { row, bill } = deleteModalData;
    setIsSaving(true);
    setError("");
    try {
      const response = await clearOutstandingBill(bill.bill_id ?? bill.order_id ?? 0, reason);
      if (response.status === 200 || response.data?.status === "success") {
        setRows((currentRows) =>
          currentRows
            .map((cust) => {
              if (cust.customer_id === row.customer_id) {
                const updatedBills = (cust.bills || []).filter(
                  (b) => (b.bill_id ?? b.order_id) !== (bill.bill_id ?? bill.order_id)
                );
                
                // Recalculate totals for this customer row
                const billSum = updatedBills.reduce((acc, curr) => acc + Number(curr.bill_amount || 0), 0);
                const paidSum = updatedBills.reduce((acc, curr) => acc + Number(curr.amount_paid || 0), 0);
                const pendingSum = updatedBills.reduce((acc, curr) => acc + Number(curr.remaining_balance || 0), 0);
                
                return {
                  ...cust,
                  bills: updatedBills,
                  total_bill_amount: String(billSum),
                  total_paid: String(paidSum),
                  current_pending_balance: String(pendingSum),
                };
              }
              return cust;
            })
            .filter((cust) => (cust.bills || []).length > 0)
        );
      }
      setToast(`Outstanding bill manually cleared (${reason === "mistake" ? "Stock reversed" : "Stock kept deducted"})`);
      setDeleteModalData(null);
      triggerDataRefresh();
      await load();
      if (expandedCustomerId === row.customer_id && row.bills?.length === 1) {
        setExpandedCustomerId(null);
      }
    } catch {
      setError("Outstanding bill clear nahi ho paaya.");
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
            <div className="divide-y divide-zinc-100">
              {filteredRows.map((row) => {
                const isExpanded = expandedCustomerId === row.customer_id;
                return (
                  <div key={row.customer_id}>
                    <button className="grid w-full gap-3 px-5 py-4 text-left hover:bg-zinc-50 md:grid-cols-[1fr_140px_140px_140px_auto]" type="button" onClick={() => setExpandedCustomerId(isExpanded ? null : row.customer_id)}>
                      <div>
                        <p className="font-semibold text-zinc-950">{row.customer_name}</p>
                        <p className="text-sm text-zinc-500">{row.customer_phone} · {row.place || "-"}</p>
                      </div>
                      <Summary label="Total Bill" value={money(row.total_bill_amount)} />
                      <Summary label="Total Paid" value={money(row.total_paid)} />
                      <Summary label="Pending" value={money(row.current_pending_balance)} strong />
                      <span className="flex items-center justify-end gap-2 text-sm font-semibold text-brand-700">
                        {(row.bills || []).length} bills
                        <ChevronDown className={`h-4 w-4 transition ${isExpanded ? "rotate-180" : ""}`} />
                      </span>
                    </button>

                    {isExpanded ? (
                      <div className="bg-zinc-50 px-5 pb-5">
                        <div className="overflow-hidden rounded-md border border-zinc-200 bg-white">
                          <table className="min-w-full divide-y divide-zinc-200 text-sm">
                            <thead className="bg-zinc-50 text-left text-xs font-semibold uppercase text-zinc-500">
                              <tr>
                                <th className="px-4 py-3">Order ID</th>
                                <th className="px-4 py-3">Date</th>
                                <th className="px-4 py-3 text-right">Bill Amount</th>
                                <th className="px-4 py-3 text-right">Remaining</th>
                                <th className="px-4 py-3 text-right">Action</th>
                              </tr>
                            </thead>
                            <tbody className="divide-y divide-zinc-100">
                              {(row.bills || []).map((bill) => {
                                const isHistoryExpanded = expandedBillHistoryId === (bill.bill_id ?? bill.order_id);
                                return (
                                  <div key={bill.bill_id ?? bill.order_id} style={{ display: "contents" }}>
                                    <tr className={isHistoryExpanded ? "bg-zinc-50/30" : ""}>
                                      <td className="px-4 py-3 font-medium text-zinc-950">#{bill.order_id ?? bill.bill_id}</td>
                                      <td className="px-4 py-3 text-zinc-600">{formatDateTime(bill.order_date)}</td>
                                      <td className="px-4 py-3 text-right text-zinc-700">{money(bill.bill_amount)}</td>
                                      <td className="px-4 py-3 text-right font-semibold text-red-700">{money(bill.remaining_balance)}</td>
                                      <td className="px-4 py-3 text-right">
                                        <div className="flex justify-end gap-2">
                                          <button
                                            className={`rounded-md border px-3 py-2 text-xs font-semibold transition ${
                                              isHistoryExpanded
                                                ? "border-zinc-300 bg-zinc-100 text-zinc-800"
                                                : "border-zinc-200 bg-white text-zinc-700 hover:bg-zinc-50"
                                            }`}
                                            type="button"
                                            onClick={() => setExpandedBillHistoryId(isHistoryExpanded ? null : (bill.bill_id ?? bill.order_id ?? null))}
                                          >
                                            {isHistoryExpanded ? "Hide History" : "History"}
                                          </button>
                                          <button className="rounded-md bg-brand-600 px-3 py-2 text-xs font-semibold text-white hover:bg-brand-700" type="button" onClick={() => openPaymentModal(row, bill)}>
                                            Pay Bill
                                          </button>
                                          {canDeleteOutstanding ? (
                                            <button className="grid h-8 w-8 place-items-center rounded-md text-red-600 hover:bg-red-50" type="button" title="Clear outstanding bill" onClick={() => initiateDeleteBill(row, bill)}>
                                              <Trash2 className="h-4 w-4" />
                                            </button>
                                          ) : null}
                                        </div>
                                      </td>
                                    </tr>

                                    {isHistoryExpanded ? (
                                      <tr className="bg-zinc-50/50">
                                        <td colSpan={5} className="px-4 py-3">
                                          <div className="rounded-lg border border-zinc-200 bg-white p-4 shadow-sm">
                                            <p className="text-xs font-bold uppercase tracking-wider text-zinc-400 mb-2">Payment History Log</p>
                                            {(!bill.payments || bill.payments.length === 0) ? (
                                              <p className="text-xs text-zinc-500 py-1">No payment transactions recorded for this bill.</p>
                                            ) : (
                                              <div className="overflow-x-auto">
                                                <table className="min-w-full divide-y divide-zinc-200 text-xs">
                                                  <thead className="bg-zinc-50 text-left font-semibold uppercase text-zinc-500">
                                                    <tr>
                                                      <th className="px-3 py-2">Date of Payment</th>
                                                      <th className="px-3 py-2 text-right">Amount Paid</th>
                                                      <th className="px-3 py-2">Received By (Staff Role/Name)</th>
                                                    </tr>
                                                  </thead>
                                                  <tbody className="divide-y divide-zinc-100">
                                                    {bill.payments.map((p) => (
                                                      <tr key={p.id}>
                                                        <td className="px-3 py-2 text-zinc-600">{formatDateTime(p.payment_date)}</td>
                                                        <td className="px-3 py-2 text-right font-semibold text-emerald-700">{money(p.amount_allocated)}</td>
                                                        <td className="px-3 py-2 text-zinc-700">
                                                          <span className="inline-flex items-center gap-1 rounded bg-brand-50 px-2 py-0.5 font-medium text-brand-700 text-[10px]">
                                                            {p.received_by_role || "System"}
                                                          </span>{" "}
                                                          {p.received_by_name || "Unknown"}
                                                        </td>
                                                      </tr>
                                                    ))}
                                                  </tbody>
                                                </table>
                                              </div>
                                            )}
                                          </div>
                                        </td>
                                      </tr>
                                    ) : null}
                                  </div>
                                );
                              })}
                            </tbody>
                          </table>
                        </div>
                        <div className="mt-3 flex justify-end gap-2">
                          <button className="inline-flex items-center gap-1 rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-xs font-semibold text-amber-800 hover:bg-amber-100" type="button" onClick={() => triggerReminder(row)}>
                            <BellRing className="h-3.5 w-3.5" />
                            Send Reminder
                          </button>
                        </div>
                      </div>
                    ) : null}
                  </div>
                );
              })}
            </div>
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
                {selectedBill ? <p className="mt-1 text-xs font-medium text-brand-700">Bill #{selectedBill.order_id ?? selectedBill.bill_id}</p> : null}
              </div>
              <button className="grid h-9 w-9 place-items-center rounded-md border border-zinc-200 text-zinc-600" type="button" onClick={() => setSelected(null)}>
                <X className="h-4 w-4" />
              </button>
            </div>

            <div className="mt-5 grid gap-4">
              <label className="grid gap-1 text-sm font-medium text-zinc-700">
                Amount Paid
                <input className="h-10 rounded-md border border-zinc-200 px-3 text-sm outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-100" type="number" value={payment.amount_paid === 0 ? "" : payment.amount_paid} onChange={(event) => setPayment((current) => ({ ...current, amount_paid: event.target.value === "" ? 0 : Number(event.target.value) }))} />
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

      {deleteModalData ? (
        <div className="fixed inset-0 z-40 grid place-items-center bg-zinc-950/60 backdrop-blur-sm px-4">
          <div className="w-full max-w-lg rounded-xl bg-white p-6 shadow-2xl border border-zinc-100">
            <div className="flex items-start justify-between gap-4">
              <div>
                <h2 className="text-xl font-bold text-zinc-950 flex items-center gap-2">
                  <Trash2 className="h-5 w-5 text-red-600 animate-pulse" />
                  Delete Outstanding Bill
                </h2>
                <p className="mt-1 text-sm text-zinc-500">
                  Customer: <span className="font-semibold text-zinc-800">{deleteModalData.row.customer_name}</span> · Bill ID: <span className="font-semibold text-zinc-800">#{deleteModalData.bill.bill_id ?? deleteModalData.bill.order_id}</span>
                </p>
              </div>
              <button className="grid h-8 w-8 place-items-center rounded-md border border-zinc-200 text-zinc-400 hover:text-zinc-600 hover:bg-zinc-50 transition" type="button" onClick={() => setDeleteModalData(null)}>
                <X className="h-4 w-4" />
              </button>
            </div>

            <div className="mt-6">
              <p className="text-sm font-medium text-zinc-700">Why are you deleting this bill?</p>
              <p className="text-xs text-zinc-400 mt-1">Please select the reason for deletion to correctly update your inventory stock.</p>
              
              <div className="mt-4 grid gap-3">
                <button
                  type="button"
                  className="flex flex-col text-left w-full p-4 rounded-lg border border-amber-200 bg-amber-50/50 hover:bg-amber-50 hover:border-amber-300 transition-all shadow-sm"
                  onClick={() => handleConfirmDelete("mistake")}
                  disabled={isSaving}
                >
                  <span className="font-semibold text-amber-900 text-sm flex items-center gap-1.5">
                    Generated by mistake (Reverse Stock)
                  </span>
                  <span className="text-xs text-amber-700 mt-1">
                    Select this if the bill was created in error. The system will automatically restore the ordered item quantities back into your finished goods stock.
                  </span>
                </button>

                <button
                  type="button"
                  className="flex flex-col text-left w-full p-4 rounded-lg border border-zinc-200 bg-zinc-50/50 hover:bg-zinc-50 hover:border-zinc-300 transition-all shadow-sm"
                  onClick={() => handleConfirmDelete("paid")}
                  disabled={isSaving}
                >
                  <span className="font-semibold text-zinc-900 text-sm">
                    Customer Paid the Bill (Keep Stock Deducted)
                  </span>
                  <span className="text-xs text-zinc-600 mt-1">
                    Select this if the customer has settled this bill. Stock is already delivered and will not be altered. The bill is closed and archived.
                  </span>
                </button>
              </div>
            </div>

            <div className="mt-6 flex justify-end gap-3 border-t border-zinc-100 pt-4">
              <button
                className="h-10 rounded-md border border-zinc-200 px-4 text-sm font-semibold text-zinc-600 hover:bg-zinc-50 transition"
                type="button"
                onClick={() => setDeleteModalData(null)}
                disabled={isSaving}
              >
                Cancel
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
