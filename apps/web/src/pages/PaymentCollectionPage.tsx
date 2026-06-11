import { CreditCard, IndianRupee, Search, WalletCards } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { useDataRefresh } from "../context/DataRefreshContext";
import { addPayment, getPaymentDues, searchCustomers } from "../lib/api";
import type { CustomerSearchResult, OutstandingCustomer, PaymentCreate } from "../lib/api";

const today = new Date().toISOString().slice(0, 10);

const initialPayment: PaymentCreate = {
  customer_phone: "",
  amount_paid: 0,
  payment_mode: "Cash",
  date: today,
  save_extra_as_advance: true
};

function apiErrorMessage(error: unknown) {
  const detail = (error as { response?: { data?: { detail?: unknown } } }).response?.data?.detail;
  if (Array.isArray(detail)) {
    return detail.map((item) => {
      if (typeof item === "string") return item;
      const location = Array.isArray((item as { loc?: unknown }).loc) ? (item as { loc: unknown[] }).loc.join(".") : "";
      const message = (item as { msg?: unknown }).msg;
      return [location, message].filter(Boolean).join(": ") || JSON.stringify(item);
    }).join("; ");
  }
  if (typeof detail === "string") return detail;
  if (detail) return JSON.stringify(detail);
  return "An error occurred";
}

function money(value: string | number) {
  return `₹${Number(value || 0).toLocaleString("en-IN", { maximumFractionDigits: 2 })}`;
}

export default function PaymentCollectionPage() {
  const [customerQuery, setCustomerQuery] = useState("");
  const [customerResults, setCustomerResults] = useState<CustomerSearchResult[]>([]);
  const [selectedCustomer, setSelectedCustomer] = useState<CustomerSearchResult | null>(null);
  const [dues, setDues] = useState<OutstandingCustomer[]>([]);
  const [grandTotal, setGrandTotal] = useState("0");
  const [payment, setPayment] = useState<PaymentCreate>(initialPayment);
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [toast, setToast] = useState("");
  const [error, setError] = useState("");
  const { refreshVersion, triggerDataRefresh } = useDataRefresh();

  async function loadDues() {
    setIsLoading(true);
    setError("");
    try {
      const response = await getPaymentDues();
      setDues(response.data.customers);
      setGrandTotal(response.data.grand_total_outstanding);
    } catch {
      setError("Market outstanding load nahi ho paaya.");
    } finally {
      setIsLoading(false);
    }
  }

  useEffect(() => {
    void loadDues();
  }, [refreshVersion]);

  useEffect(() => {
    const query = customerQuery.trim();
    if (query.length < 2 || selectedCustomer) {
      setCustomerResults([]);
      return;
    }

    const timer = window.setTimeout(async () => {
      try {
        const response = await searchCustomers(query);
        setCustomerResults(response.data);
      } catch {
        setCustomerResults([]);
      }
    }, 250);

    return () => window.clearTimeout(timer);
  }, [customerQuery, selectedCustomer]);

  const selectedDue = useMemo(() => {
    if (!selectedCustomer) return null;
    return dues.find((row) => row.customer_phone === selectedCustomer.phone_number) || null;
  }, [dues, selectedCustomer]);

  const remainingBalance = selectedDue?.current_pending_balance || "0";

  function selectCustomer(customer: CustomerSearchResult) {
    setSelectedCustomer(customer);
    setCustomerQuery(`${customer.name} - ${customer.place} (${customer.phone_number})`);
    setCustomerResults([]);
    setPayment((current) => ({
      ...current,
      customer_phone: customer.phone_number,
      save_extra_as_advance: true
    }));
  }

  function clearCustomer() {
    setSelectedCustomer(null);
    setCustomerQuery("");
    setPayment(initialPayment);
  }

  async function savePayment() {
    if (!selectedCustomer) {
      setError("Pehle customer select karein.");
      return;
    }
    if (payment.amount_paid <= 0) {
      setError("Amount received valid hona chahiye.");
      return;
    }

    setIsSaving(true);
    setError("");
    try {
      const payload: PaymentCreate = {
        customer_phone: String(selectedCustomer.phone_number || payment.customer_phone || "").trim(),
        amount_paid: Number(payment.amount_paid || 0),
        payment_mode: payment.payment_mode,
        date: payment.date || undefined,
        sale_id: payment.sale_id ? Number(payment.sale_id) : undefined,
        save_extra_as_advance: payment.save_extra_as_advance !== false
      };
      const response = await addPayment(payload);
      setToast(`Payment saved. Remaining balance: ${money(response.data.total_remaining_balance)}`);
      setPayment({ ...initialPayment, customer_phone: selectedCustomer.phone_number });
      triggerDataRefresh();
      await loadDues();
    } catch (error) {
      setError(apiErrorMessage(error));
    } finally {
      setIsSaving(false);
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-zinc-950">Payment Collection</h1>
        <p className="text-sm text-zinc-500">Customer payment entry aur live market outstanding.</p>
      </div>

      {toast ? <div className="rounded-md border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm font-medium text-emerald-700">{toast}</div> : null}
      {error ? <div className="rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm font-medium text-red-700">{error}</div> : null}

      <section className="grid gap-5 xl:grid-cols-[1fr_360px]">
        <div className="rounded-lg border border-zinc-200 bg-white p-5 shadow-sm">
          <div className="mb-5 flex items-center gap-2">
            <CreditCard className="h-5 w-5 text-brand-600" />
            <h2 className="text-base font-semibold text-zinc-950">Record Payment</h2>
          </div>

          <div className="grid gap-4 md:grid-cols-2">
            <div className="relative md:col-span-2">
              <label className="text-sm font-medium text-zinc-700" htmlFor="customer-search">Customer Search</label>
              <div className="relative mt-1">
                <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-zinc-400" />
                <input
                  id="customer-search"
                  className="h-11 w-full rounded-md border border-zinc-200 pl-9 pr-24 text-sm outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-100"
                  placeholder="Name ya phone number search karein"
                  value={customerQuery}
                  onChange={(event) => {
                    setSelectedCustomer(null);
                    setCustomerQuery(event.target.value);
                  }}
                />
                {selectedCustomer ? (
                  <button className="absolute right-2 top-1/2 -translate-y-1/2 rounded-md px-2 py-1 text-xs font-semibold text-zinc-500 hover:bg-zinc-100" type="button" onClick={clearCustomer}>
                    Clear
                  </button>
                ) : null}
              </div>
              {customerResults.length > 0 ? (
                <div className="absolute z-20 mt-2 max-h-64 w-full overflow-auto rounded-md border border-zinc-200 bg-white shadow-lg">
                  {customerResults.map((customer) => (
                    <button key={customer.id} className="block w-full px-4 py-3 text-left text-sm hover:bg-zinc-50" type="button" onClick={() => selectCustomer(customer)}>
                      <span className="font-medium text-zinc-900">{customer.name}</span>
                      <span className="text-zinc-500"> - {customer.place} ({customer.phone_number})</span>
                    </button>
                  ))}
                </div>
              ) : null}
            </div>

            <label className="grid gap-1 text-sm font-medium text-zinc-700">
              Date
              <input className="h-11 rounded-md border border-zinc-200 px-3 text-sm outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-100" type="date" value={payment.date} onChange={(event) => setPayment((current) => ({ ...current, date: event.target.value }))} />
            </label>

            <label className="grid gap-1 text-sm font-medium text-zinc-700">
              Payment Mode
              <select className="h-11 rounded-md border border-zinc-200 px-3 text-sm outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-100" value={payment.payment_mode} onChange={(event) => setPayment((current) => ({ ...current, payment_mode: event.target.value as PaymentCreate["payment_mode"] }))}>
                <option value="Cash">Cash</option>
                <option value="UPI">UPI</option>
                <option value="Bank Transfer">Bank Transfer</option>
              </select>
            </label>

            <label className="grid gap-1 text-sm font-medium text-zinc-700 md:col-span-2">
              Amount Received
              <input
                autoFocus
                inputMode="decimal"
                className="h-12 rounded-md border border-zinc-200 px-3 text-base font-semibold outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-100"
                data-test-id="payment-amount-input"
                type="number"
                value={payment.amount_paid}
                onFocus={(event) => event.target.select()}
                onChange={(event) => setPayment((current) => ({ ...current, amount_paid: event.target.value === "" ? 0 : Number(event.target.value) }))}
              />
            </label>

            {(() => {
              if (!selectedCustomer) return null;
              const outstandingLimit = Number(remainingBalance);
              const isOverpaying = payment.amount_paid > outstandingLimit;
              const overpaidAmount = payment.amount_paid - outstandingLimit;
              if (isOverpaying) {
                return (
                  <div className="p-3 rounded-md bg-emerald-50 border border-emerald-200 text-xs text-emerald-800 space-y-1 md:col-span-2">
                    <p className="font-semibold">
                      ₹{outstandingLimit.toFixed(2)} outstanding clear होगा और ₹{overpaidAmount.toFixed(2)} advance के रूप में save होगा.
                    </p>
                    <label className="flex items-center gap-1.5 font-medium text-emerald-700 cursor-pointer">
                      <input
                        type="checkbox"
                        checked={payment.save_extra_as_advance ?? true}
                        onChange={(e) => setPayment((current) => ({ ...current, save_extra_as_advance: e.target.checked }))}
                        className="rounded text-emerald-600 focus:ring-emerald-500"
                      />
                      <span>Extra amount will be saved as advance for next order.</span>
                    </label>
                  </div>
                );
              }
              return null;
            })()}
          </div>

          <div className="mt-5 flex justify-end">
            <button className="h-11 rounded-md bg-brand-600 px-5 text-sm font-semibold text-white hover:bg-brand-700 disabled:bg-zinc-300" data-test-id="record-payment-button" type="button" disabled={isSaving || !selectedCustomer} onClick={savePayment}>
              {isSaving ? "Saving..." : "Save Payment"}
            </button>
          </div>
        </div>

        <div className="rounded-lg border border-amber-200 bg-amber-50 p-5 shadow-sm h-fit">
          <div className="flex items-center gap-3">
            <div className="grid h-11 w-11 place-items-center rounded-md bg-white text-amber-700">
              <IndianRupee className="h-5 w-5" />
            </div>
            <div>
              <p className="text-sm font-semibold text-amber-800">Current Remaining Balance</p>
              <p className="text-3xl font-semibold text-amber-950">{money(remainingBalance)}</p>
            </div>
          </div>
          {selectedCustomer ? (
            <div className="mt-4 rounded-md bg-white/80 p-3 text-sm text-amber-950 space-y-1">
              <p className="font-semibold">{selectedCustomer.name}</p>
              <p>{selectedCustomer.place} ({selectedCustomer.phone_number})</p>
              {Number(selectedCustomer.advance_balance || 0) > 0 && (
                <p className="text-xs font-bold text-emerald-700 mt-1">
                  Advance available: ₹{Number(selectedCustomer.advance_balance).toFixed(2)}
                </p>
              )}
            </div>
          ) : (
            <p className="mt-4 text-sm text-amber-800">Balance dekhne ke liye customer select karein.</p>
          )}
        </div>
      </section>

      <section className="overflow-hidden rounded-lg border border-zinc-200 bg-white shadow-sm">
        <div className="flex flex-col gap-2 border-b border-zinc-200 px-5 py-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-center gap-2">
            <WalletCards className="h-5 w-5 text-brand-600" />
            <h2 className="text-base font-semibold text-zinc-950">Market Outstanding Summary</h2>
          </div>
          <p className="text-sm font-semibold text-zinc-700">Grand Total: {money(grandTotal)}</p>
        </div>

        {isLoading ? (
          <div className="p-6 text-sm text-zinc-500">Loading dues...</div>
        ) : dues.length === 0 ? (
          <div className="p-6 text-sm text-zinc-500">Abhi koi net balance pending nahi hai.</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-zinc-200 text-sm">
              <thead className="bg-zinc-50 text-left text-xs font-semibold uppercase text-zinc-500">
                <tr>
                  <th className="px-5 py-3">Customer Name</th>
                  <th className="px-5 py-3">Phone</th>
                  <th className="px-5 py-3">Place</th>
                  <th className="px-5 py-3 text-right">Total Bill Amount</th>
                  <th className="px-5 py-3 text-right">Total Paid</th>
                  <th className="px-5 py-3 text-right">Net Balance Remaining</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-zinc-100">
                {dues.map((row) => (
                  <tr key={row.customer_id}>
                    <td className="px-5 py-3 font-medium text-zinc-900">{row.customer_name}</td>
                    <td className="px-5 py-3 text-zinc-600">{row.customer_phone}</td>
                    <td className="px-5 py-3 text-zinc-600">{row.place || "-"}</td>
                    <td className="px-5 py-3 text-right text-zinc-700">{money(row.total_bill_amount)}</td>
                    <td className="px-5 py-3 text-right text-zinc-700">{money(row.total_paid)}</td>
                    <td className="px-5 py-3 text-right font-semibold text-red-700">{money(row.current_pending_balance)}</td>
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
