import { Check, Plus, ReceiptText, Search, Trash2 } from "lucide-react";
import { RefObject, useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";

import { useDataRefresh } from "../context/DataRefreshContext";
import { useAuth } from "../context/AuthContext";
import { createDailySale, createPendingSaleOrder, getInventory, searchCustomers } from "../lib/api";
import type { CustomerSearchResult, DailySaleCreate, LiveStockRow } from "../lib/api";

type SaleItem = DailySaleCreate["items"][number];

const emptyItem: SaleItem = {
  product_id: null,
  product_size_ml: 0,
  variety: "Plain White",
  packaging_size: "",
  packaging_size_name: "",
  boxes_sold: 0,
  loose_packets_sold: 0,
  rate_per_box: 0,
  rate_per_packet: 0,
  packets_per_box: 0
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

export default function SalesEntryPage() {
  const [toast, setToast] = useState("");
  const [lastInvoiceId, setLastInvoiceId] = useState<number | null>(null);
  const [isSaving, setIsSaving] = useState(false);
  const [customerQuery, setCustomerQuery] = useState("");
  const [customerResults, setCustomerResults] = useState<CustomerSearchResult[]>([]);
  const [selectedCustomer, setSelectedCustomer] = useState<CustomerSearchResult | null>(null);
  const [inventoryRows, setInventoryRows] = useState<LiveStockRow[]>([]);
  const { triggerDataRefresh } = useDataRefresh();
  const { user } = useAuth();
  const customerSearchRef = useRef<HTMLInputElement>(null);
  const [form, setForm] = useState<DailySaleCreate>({
    date: new Date().toISOString().slice(0, 10),
    customer_id: 0,
    amount_paid: 0,
    legal_invoice_type: "bill_of_supply",
    legal_invoice_number: "",
    rough_bill_enabled: true,
    rough_bill_number: "",
    items: [{ ...emptyItem }]
  });

  useEffect(() => {
    void getInventory()
      .then((response) => {
        const variations = response.data.filter((row) => row.stock_type === "Final Product" && row.product_id);
        setInventoryRows(variations);
        if (variations[0]) {
          setForm((current) => ({ ...current, items: [itemFromVariation(variations[0], current.items[0])] }));
        }
      })
      .catch((error) => setToast(apiErrorMessage(error)));
  }, []);

  useEffect(() => {
    const handle = window.setTimeout(async () => {
      try {
        const response = await searchCustomers(customerQuery);
        setCustomerResults(response.data);
      } catch (error) {
        setCustomerResults([]);
        setToast(apiErrorMessage(error));
      }
    }, 200);
    return () => window.clearTimeout(handle);
  }, [customerQuery]);

  const billTotal = useMemo(() => {
    return form.items.reduce((total, item) => total + item.boxes_sold * item.rate_per_box, 0);
  }, [form.items]);
  const hasInsufficientStock = useMemo(() => {
    return form.items.some((item) => {
      const stock = inventoryRows.find((row) => row.product_id === item.product_id);
      const available = Number(stock?.current_quantity ?? stock?.quantity ?? 0);
      return Number(item.boxes_sold || 0) > available;
    });
  }, [form.items, inventoryRows]);

  async function submit() {
    if (!selectedCustomer) return;
    const billableItems = form.items.filter((item) => Number(item.boxes_sold || 0) > 0 || Number(item.loose_packets_sold || 0) > 0);
    if (hasInsufficientStock) {
      setToast("Insufficient Stock");
      return;
    }
    if (billableItems.length === 0) {
      setToast("Enter boxes quantity for at least one product.");
      return;
    }
    if (billableItems.some((item) => !item.product_id || !item.product_size_ml || !item.packaging_size_name.trim())) {
      setToast("Please select a valid product variation before saving.");
      return;
    }
    setIsSaving(true);
    try {
      const payload: DailySaleCreate = {
        ...form,
        customer_id: Number(selectedCustomer.id),
        amount_paid: Number(form.amount_paid || 0),
        legal_invoice_type: form.legal_invoice_type,
        legal_invoice_number: form.legal_invoice_number?.trim() || null,
        rough_bill_enabled: Boolean(form.rough_bill_enabled),
        rough_bill_number: form.rough_bill_number?.trim() || null,
        items: billableItems.map((item) => normalizeItem({
          ...item,
          product_size_ml: Number(item.product_size_ml || 0),
          product_id: item.product_id || null,
          boxes_sold: Number(item.boxes_sold || 0),
          loose_packets_sold: 0,
          rate_per_packet: Number(item.rate_per_packet || 0),
          packets_per_box: Number(item.packets_per_box || 0),
          packaging_size: (item.packaging_size || item.packaging_size_name).trim(),
          packaging_size_name: item.packaging_size_name.trim(),
          variety: item.variety.trim() || "Plain White"
        }))
      };
      if (user?.role === "Owner") {
        const response = await createDailySale(payload);
        setLastInvoiceId(response.data.invoice_document_id || null);
        setToast("Invoice saved. PDF can be downloaded from Invoices.");
      } else {
        await createPendingSaleOrder(payload);
        setLastInvoiceId(null);
        setToast("Order sent to Owner for approval.");
      }
      triggerDataRefresh();
      setSelectedCustomer(null);
      setCustomerQuery("");
      setCustomerResults([]);
      setForm({
        date: new Date().toISOString().slice(0, 10),
        customer_id: 0,
        amount_paid: 0,
        legal_invoice_type: form.legal_invoice_type,
        legal_invoice_number: "",
        rough_bill_enabled: form.rough_bill_enabled,
        rough_bill_number: "",
        items: inventoryRows[0] ? [itemFromVariation(inventoryRows[0], emptyItem)] : [{ ...emptyItem }]
      });
      window.setTimeout(() => customerSearchRef.current?.focus(), 0);
    } catch (error) {
      setToast(apiErrorMessage(error));
    } finally {
      setIsSaving(false);
    }
  }

  function selectCustomer(customer: CustomerSearchResult) {
    setSelectedCustomer(customer);
    setCustomerQuery(`${customer.name} - ${customer.place} (${customer.phone_number})`);
    setForm({ ...form, customer_id: customer.id });
    setCustomerResults([]);
  }

  return (
    <div className="mx-auto max-w-6xl space-y-5">
      {toast ? <Toast message={toast} onClose={() => setToast("")} /> : null}
      {lastInvoiceId ? (
        <div className="rounded-md border border-green-200 bg-green-50 px-4 py-3 text-sm font-semibold text-green-800">
          Invoice saved. <Link className="underline" to="/invoices">Open Invoices to download PDF</Link>.
        </div>
      ) : null}
      <header>
        <h1 className="text-2xl font-semibold text-zinc-950">Sales Entry</h1>
        <p className="mt-1 text-sm text-zinc-500">Search customer, select stock by size and variety, and generate invoice.</p>
      </header>

      <section className="rounded-lg border border-zinc-200 bg-white p-5 shadow-sm">
        <div className="mb-5 flex items-center gap-3">
          <span className="grid h-10 w-10 place-items-center rounded-md bg-brand-50 text-brand-700">
            <ReceiptText className="h-5 w-5" />
          </span>
          <h2 className="text-lg font-semibold text-zinc-950">Bill Details</h2>
        </div>

        <div className="grid gap-4 md:grid-cols-[1.4fr_0.7fr_0.7fr]">
          <CustomerCombobox inputRef={customerSearchRef} query={customerQuery} results={customerResults} onQueryChange={setCustomerQuery} onSelect={selectCustomer} />
          <Field label="Date" type="date" value={form.date} onChange={(date) => setForm({ ...form, date })} />
          <NumberField label="Amount paid" value={form.amount_paid} onChange={(amount_paid) => setForm({ ...form, amount_paid })} />
        </div>

        <div className="mt-5 grid gap-4 rounded-lg border border-zinc-200 bg-zinc-50 p-4 md:grid-cols-4">
          <InvoiceModeField value={form.legal_invoice_type} onChange={(legal_invoice_type) => setForm({ ...form, legal_invoice_type })} />
          <Field label="Legal invoice number" value={form.legal_invoice_number || ""} onChange={(legal_invoice_number) => setForm({ ...form, legal_invoice_number })} />
          <Field label="Rough bill number" value={form.rough_bill_number || ""} onChange={(rough_bill_number) => setForm({ ...form, rough_bill_number })} />
          <label className="flex items-end gap-3 rounded-md border border-zinc-200 bg-white px-3 py-2 text-sm font-semibold text-zinc-700">
            <input className="h-4 w-4 accent-brand-600" type="checkbox" checked={form.rough_bill_enabled} onChange={(event) => setForm({ ...form, rough_bill_enabled: event.target.checked })} />
            Generate parallel rough bill
          </label>
        </div>

        <div className="mt-5 space-y-3">
          {form.items.map((item, index) => (
            <div key={index} className="grid gap-3 rounded-md border border-zinc-200 p-3 md:grid-cols-[1.5fr_0.75fr_0.75fr_0.75fr_0.65fr_0.75fr_auto]">
              <VariationField value={item.product_id || 0} rows={inventoryRows} onChange={(value) => {
                const selected = inventoryRows.find((row) => row.product_id === value);
                if (selected) patchItem(index, itemFromVariation(selected, item));
              }} />
              <NumberField label="Rate/packet" value={item.rate_per_packet} onChange={(rate_per_packet) => patchItem(index, { rate_per_packet })} />
              <NumberField label="Packets/box" value={item.packets_per_box} onChange={(packets_per_box) => patchItem(index, { packets_per_box })} />
              <NumberField label="Rate/box" value={item.rate_per_box} onChange={() => undefined} readOnly />
              <NumberField label="Boxes" value={item.boxes_sold} onChange={(boxes_sold) => patchItem(index, { boxes_sold })} />
              <StockIndicator item={item} rows={inventoryRows} />
              <button className="mt-auto grid h-10 w-10 place-items-center rounded-md text-zinc-400 hover:bg-red-50 hover:text-red-600" type="button" onClick={() => removeItem(index)}>
                <Trash2 className="h-4 w-4" />
              </button>
            </div>
          ))}
        </div>

        <InvoicePreview customer={selectedCustomer} form={form} billTotal={billTotal} />

        <div className="mt-5 flex flex-wrap gap-2">
          <button className="inline-flex h-10 items-center gap-2 rounded-md border border-zinc-200 bg-white px-4 text-sm font-semibold text-zinc-700" type="button" onClick={() => setForm({ ...form, items: [...form.items, inventoryRows[0] ? itemFromVariation(inventoryRows[0], emptyItem) : { ...emptyItem }] })}>
            <Plus className="h-4 w-4" />
            Add Product
          </button>
          <button className="inline-flex h-10 items-center gap-2 rounded-md bg-brand-600 px-4 text-sm font-semibold text-white hover:bg-brand-700 disabled:bg-zinc-300" disabled={isSaving || !selectedCustomer || hasInsufficientStock} type="button" onClick={submit}>
            <Check className="h-4 w-4" />
            {isSaving ? "Saving..." : "Save Sale"}
          </button>
        </div>
      </section>
    </div>
  );

  function patchItem(index: number, patch: Partial<SaleItem>) {
    setForm({ ...form, items: form.items.map((item, itemIndex) => (itemIndex === index ? normalizeItem({ ...item, ...patch }) : item)) });
  }

  function removeItem(index: number) {
    if (form.items.length === 1) return;
    setForm({ ...form, items: form.items.filter((_, itemIndex) => itemIndex !== index) });
  }
}

function itemFromVariation(stock: LiveStockRow, current: SaleItem): SaleItem {
  return normalizeItem({
    ...current,
    product_id: stock.product_id || null,
    product_size_ml: stock.product_size_ml || 0,
    variety: stock.variety || "Plain White",
    packaging_size: stock.packaging_size || stock.packaging_size_name || "",
    packaging_size_name: stock.packaging_size_name || stock.packaging_size || "",
    packets_per_box: stock.packets_per_box || stock.packets_per_box_limit || current.packets_per_box || 0
  });
}

function normalizeItem(item: SaleItem): SaleItem {
  const packetsPerBox = Number(item.packets_per_box || 0);
  const ratePerPacket = Number(item.rate_per_packet || 0);
  return {
    ...item,
    loose_packets_sold: 0,
    packets_per_box: packetsPerBox,
    rate_per_packet: ratePerPacket,
    rate_per_box: Number((ratePerPacket * packetsPerBox).toFixed(2))
  };
}

function itemTotal(item: SaleItem) {
  return Number(item.boxes_sold || 0) * Number(item.rate_per_box || 0);
}

function VariationField({ value, rows, onChange }: { value: number; rows: LiveStockRow[]; onChange: (value: number) => void }) {
  return (
    <label className="block text-sm">
      <span className="font-medium text-zinc-700">Product Variation</span>
      <select className="mt-1 h-10 w-full rounded-md border border-zinc-200 px-3 outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-100" value={value} onChange={(event) => onChange(Number(event.target.value))}>
        <option value={0}>Select variation</option>
        {rows.map((row) => (
          <option key={String(row.id)} value={row.product_id || 0}>
            {(row.variety || "Product")} - {row.packaging_size || row.packaging_size_name || "Standard"} [{row.pieces_per_packet || 0} Pcs/Pkt] - Stock {row.current_quantity ?? row.quantity}
          </option>
        ))}
      </select>
    </label>
  );
}

function StockIndicator({ item, rows }: { item: SaleItem; rows: LiveStockRow[] }) {
  const stock = rows.find((row) => row.product_id === item.product_id);
  const available = Number(stock?.current_quantity ?? stock?.quantity ?? 0);
  const insufficient = Number(item.boxes_sold || 0) > available;
  return (
    <div className="block text-sm">
      <span className="font-medium text-zinc-700">Stock</span>
      <div className={`mt-1 flex h-10 items-center rounded-md border px-3 font-semibold ${insufficient ? "border-red-200 bg-red-50 text-red-700" : "border-zinc-200 bg-zinc-50 text-zinc-900"}`}>
        {insufficient ? "Insufficient Stock" : `${available} boxes`}
      </div>
    </div>
  );
}

function CustomerCombobox({ inputRef, query, results, onQueryChange, onSelect }: { inputRef: RefObject<HTMLInputElement>; query: string; results: CustomerSearchResult[]; onQueryChange: (value: string) => void; onSelect: (customer: CustomerSearchResult) => void }) {
  return (
    <div className="relative text-sm">
      <span className="font-medium text-zinc-700">Customer</span>
      <Search className="pointer-events-none absolute left-3 top-9 h-4 w-4 text-zinc-400" />
      <input ref={inputRef} className="mt-1 h-10 w-full rounded-md border border-zinc-200 pl-9 pr-3 outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-100" value={query} onChange={(event) => onQueryChange(event.target.value)} placeholder="Search name or phone" />
      {results.length > 0 ? (
        <div className="absolute z-20 mt-1 max-h-64 w-full overflow-auto rounded-md border border-zinc-200 bg-white shadow-lg">
          {results.map((customer) => (
            <button key={customer.id} className="block w-full px-3 py-2 text-left text-sm hover:bg-brand-50" type="button" onClick={() => onSelect(customer)}>
              {customer.name} - {customer.place} ({customer.phone_number})
            </button>
          ))}
        </div>
      ) : null}
    </div>
  );
}

function InvoicePreview({ customer, form, billTotal }: { customer: CustomerSearchResult | null; form: DailySaleCreate; billTotal: number }) {
  return (
    <div className="mt-5 rounded-lg border border-zinc-200 bg-white p-5">
      <div className="flex items-start justify-between gap-4 border-b border-zinc-200 pb-4">
        <div>
          <p className="text-xs font-semibold uppercase text-zinc-500">Bill To</p>
          <p className="mt-2 text-lg font-semibold text-zinc-950">{customer?.name || "Select customer"}</p>
          <p className="text-sm text-zinc-600">{customer?.place || "Place / address"}</p>
          <p className="text-sm text-zinc-600">{customer?.phone_number || ""}</p>
        </div>
        <div className="text-right text-sm text-zinc-600">
          <p>Date: {form.date}</p>
          <p className="mt-2 text-lg font-semibold text-zinc-950">Rs {billTotal.toFixed(2)}</p>
        </div>
      </div>
    </div>
  );
}

function Field({ label, value, type = "text", onChange }: { label: string; value: string; type?: string; onChange: (value: string) => void }) {
  return (
    <label className="block text-sm">
      <span className="font-medium text-zinc-700">{label}</span>
      <input className="mt-1 h-10 w-full rounded-md border border-zinc-200 px-3 outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-100" type={type} value={value} onChange={(event) => onChange(event.target.value)} />
    </label>
  );
}

function InvoiceModeField({ value, onChange }: { value: DailySaleCreate["legal_invoice_type"]; onChange: (value: DailySaleCreate["legal_invoice_type"]) => void }) {
  return (
    <div className="block text-sm">
      <span className="font-medium text-zinc-700">Legal Invoice Mode</span>
      <div className="mt-1 flex h-10 w-full rounded-lg bg-zinc-200/70 p-1 transition-all duration-200">
        <button
          type="button"
          onClick={() => onChange("bill_of_supply")}
          className={`flex-1 rounded-md text-xs font-bold transition-all duration-300 ${
            value === "bill_of_supply"
              ? "bg-white text-brand-700 shadow-[0_2px_8px_rgba(0,0,0,0.08)] scale-[1.02]"
              : "text-zinc-600 hover:text-zinc-950 hover:bg-white/30"
          }`}
        >
          Bill of Supply
        </button>
        <button
          type="button"
          onClick={() => onChange("tax_invoice")}
          className={`flex-1 rounded-md text-xs font-bold transition-all duration-300 ${
            value === "tax_invoice"
              ? "bg-white text-brand-700 shadow-[0_2px_8px_rgba(0,0,0,0.08)] scale-[1.02]"
              : "text-zinc-600 hover:text-zinc-950 hover:bg-white/30"
          }`}
        >
          Tax Invoice
        </button>
      </div>
    </div>
  );
}

function NumberField({ label, value, onChange, readOnly = false }: { label: string; value: number; onChange: (value: number) => void; readOnly?: boolean }) {
  return (
    <label className="block text-sm">
      <span className="font-medium text-zinc-700">{label}</span>
      <input className="mt-1 h-10 w-full rounded-md border border-zinc-200 px-3 outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-100 disabled:bg-zinc-50 disabled:text-zinc-600" disabled={readOnly} placeholder="0" type="number" value={value === 0 ? "" : value} onChange={(event) => onChange(event.target.value === "" ? 0 : Number(event.target.value))} />
    </label>
  );
}

function ReadOnlyValue({ label, value }: { label: string; value: string }) {
  return (
    <div className="block text-sm">
      <span className="font-medium text-zinc-700">{label}</span>
      <div className="mt-1 flex h-10 items-center rounded-md border border-zinc-200 bg-zinc-50 px-3 font-semibold text-zinc-900">{value}</div>
    </div>
  );
}

function Toast({ message, onClose }: { message: string; onClose: () => void }) {
  return (
    <button className="fixed right-5 top-20 z-50 rounded-md bg-[#16A34A] px-4 py-3 text-sm font-semibold text-white shadow-lg" type="button" onClick={onClose}>
      {message}
    </button>
  );
}
