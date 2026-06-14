import axios from "axios";
import { useEffect, useState } from "react";

import {
  confirmGoLiveReset,
  getDashboardCustomers,
  previewGoLiveReset,
  type DashboardCustomer,
  type GoLiveResetPreview,
  type GoLiveResetScope,
} from "../lib/api";


export default function GoLiveResetPage() {
  const [scope, setScope] = useState<GoLiveResetScope>("sales");
  const [inventoryMode, setInventoryMode] = useState<"keep_current" | "restore_baseline">("keep_current");
  const [reason, setReason] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [taxStart, setTaxStart] = useState(1);
  const [supplyStart, setSupplyStart] = useState(1);
  const [simpleStart, setSimpleStart] = useState(1);
  const [preview, setPreview] = useState<GoLiveResetPreview | null>(null);
  const [customers, setCustomers] = useState<DashboardCustomer[]>([]);
  const [openingAmounts, setOpeningAmounts] = useState<Record<number, number>>({});
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    void getDashboardCustomers().then((response) => setCustomers(response.data)).catch(() => setCustomers([]));
  }, []);

  async function loadPreview() {
    setBusy(true);
    setMessage("");
    try {
      const response = await previewGoLiveReset(scope);
      setPreview(response.data);
    } catch (caught) {
      setMessage(axios.isAxiosError(caught) ? String(caught.response?.data?.detail || caught.message) : "Preview failed.");
    } finally {
      setBusy(false);
    }
  }

  async function confirmReset() {
    if (!preview || confirmation !== "RESET LIVE START" || reason.trim().length < 5) return;
    if (!window.confirm("This permanently removes selected test transactions. Continue?")) return;
    setBusy(true);
    setMessage("");
    try {
      await confirmGoLiveReset({
        scope,
        confirmation,
        reason: reason.trim(),
        inventory_mode: inventoryMode,
        invoice_starts: {
          tax_invoice: taxStart,
          bill_of_supply: supplyStart,
          simple_bill: simpleStart,
        },
        opening_outstanding: customers
          .map((customer) => ({ customer_id: customer.id, amount: openingAmounts[customer.id] || 0 }))
          .filter((item) => item.amount > 0),
      });
      setMessage("Go-live reset completed. A database backup and audit record were created.");
      setPreview(null);
      setConfirmation("");
    } catch (caught) {
      setMessage(axios.isAxiosError(caught) ? String(caught.response?.data?.detail || caught.message) : "Reset failed.");
    } finally {
      setBusy(false);
    }
  }

  const counts = preview ? [
    ["Invoices", preview.invoices],
    ["Payments", preview.payments],
    ["Outstanding bills", preview.outstanding_bills],
    ["Payment allocations", preview.payment_allocations],
    ["Production entries", preview.production_entries],
    ["Wastage entries", preview.wastage_entries],
    ["Affected stock records", preview.affected_stock_records],
    ["Customers kept", preview.customers_kept],
  ] : [];

  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <section className="rounded-xl border border-red-300 bg-red-50 p-5">
        <h1 className="text-2xl font-black text-red-900">Go-Live Reset</h1>
        <p className="mt-2 font-semibold text-red-800">
          This will permanently remove test transaction data. Use only before real go-live.
        </p>
      </section>

      <section className="space-y-5 rounded-xl border border-zinc-200 bg-white p-5 shadow-sm">
        <label className="block">
          <span className="text-sm font-bold">What to reset</span>
          <select className="mt-1 w-full rounded border p-2" value={scope} onChange={(event) => {
            setScope(event.target.value as GoLiveResetScope);
            setPreview(null);
          }}>
            <option value="sales">Sales / Invoices / Payments only</option>
            <option value="production">Production / Wastage only</option>
            <option value="all">All transaction data</option>
          </select>
        </label>

        <label className="block">
          <span className="text-sm font-bold">Inventory handling</span>
          <select className="mt-1 w-full rounded border p-2" value={inventoryMode} onChange={(event) => setInventoryMode(event.target.value as typeof inventoryMode)}>
            <option value="keep_current">Keep current inventory as-is</option>
            <option value="restore_baseline">Reverse selected test transactions to restore starting stock</option>
          </select>
        </label>

        {scope !== "production" && (
          <div>
            <p className="text-sm font-bold">Invoice starting numbers</p>
            <div className="mt-2 grid gap-3 md:grid-cols-3">
              <NumberField label="Tax Invoice" value={taxStart} onChange={setTaxStart} />
              <NumberField label="Bill of Supply" value={supplyStart} onChange={setSupplyStart} />
              <NumberField label="Simple Bill" value={simpleStart} onChange={setSimpleStart} />
            </div>
            <p className="mt-4 text-sm font-bold">Actual opening outstanding</p>
            <p className="text-xs text-zinc-500">Leave zero for customers with no verified opening balance.</p>
            <div className="mt-2 max-h-64 space-y-2 overflow-y-auto rounded border bg-zinc-50 p-3">
              {customers.map((customer) => (
                <label key={customer.id} className="grid grid-cols-[1fr_140px] items-center gap-3 text-sm">
                  <span>{customer.name}</span>
                  <input
                    type="number"
                    min={0}
                    step="0.01"
                    className="rounded border p-2"
                    value={openingAmounts[customer.id] || 0}
                    onChange={(event) => setOpeningAmounts({
                      ...openingAmounts,
                      [customer.id]: Math.max(0, Number(event.target.value) || 0),
                    })}
                  />
                </label>
              ))}
            </div>
          </div>
        )}

        <button className="rounded bg-zinc-800 px-4 py-2 font-bold text-white disabled:opacity-50" disabled={busy} onClick={loadPreview}>
          Preview Reset
        </button>
      </section>

      {preview && (
        <section className="space-y-5 rounded-xl border border-amber-300 bg-amber-50 p-5">
          <h2 className="text-lg font-black">Reset Preview</h2>
          <div className="grid gap-2 sm:grid-cols-2">
            {counts.map(([label, value]) => (
              <div key={String(label)} className="flex justify-between rounded border border-amber-200 bg-white px-3 py-2">
                <span>{label}</span><strong>{value}</strong>
              </div>
            ))}
          </div>
          <label className="block">
            <span className="text-sm font-bold">Mandatory reason</span>
            <textarea className="mt-1 w-full rounded border p-2" value={reason} onChange={(event) => setReason(event.target.value)} />
          </label>
          <label className="block">
            <span className="text-sm font-bold">Type RESET LIVE START</span>
            <input className="mt-1 w-full rounded border p-2" value={confirmation} onChange={(event) => setConfirmation(event.target.value)} />
          </label>
          <button
            className="rounded bg-red-700 px-4 py-2 font-black text-white disabled:opacity-50"
            disabled={busy || confirmation !== "RESET LIVE START" || reason.trim().length < 5}
            onClick={confirmReset}
          >
            Create Backup and Reset
          </button>
        </section>
      )}

      {message && <p className="rounded border border-zinc-200 bg-white p-3 font-semibold">{message}</p>}
    </div>
  );
}

function NumberField({ label, value, onChange }: { label: string; value: number; onChange: (value: number) => void }) {
  return (
    <label className="text-sm">
      <span>{label}</span>
      <input type="number" min={1} className="mt-1 w-full rounded border p-2" value={value} onChange={(event) => onChange(Math.max(1, Number(event.target.value) || 1))} />
    </label>
  );
}
