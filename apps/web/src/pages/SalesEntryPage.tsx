import { Check, Plus, ReceiptText, Search, Trash2 } from "lucide-react";
import { RefObject, useEffect, useMemo, useRef, useState } from "react";

import { createDailySale, getFinalStockOptions, searchCustomers } from "../lib/api";
import type { CustomerSearchResult, DailySaleCreate, FinalStockOption } from "../lib/api";

type SaleItem = DailySaleCreate["items"][number];

const varietyOptions = ["Plain White", "Multicolor", "Custom Print"];

const emptyItem: SaleItem = {
  product_size_ml: 0,
  variety: "Plain White",
  packaging_size_name: "",
  boxes_sold: 0,
  loose_packets_sold: 0,
  rate_per_box: 0,
  rate_per_packet: 0
};

export default function SalesEntryPage() {
  const [toast, setToast] = useState("");
  const [isSaving, setIsSaving] = useState(false);
  const [customerQuery, setCustomerQuery] = useState("");
  const [customerResults, setCustomerResults] = useState<CustomerSearchResult[]>([]);
  const [selectedCustomer, setSelectedCustomer] = useState<CustomerSearchResult | null>(null);
  const [finalStocks, setFinalStocks] = useState<FinalStockOption[]>([]);
  const customerSearchRef = useRef<HTMLInputElement>(null);
  const [form, setForm] = useState<DailySaleCreate>({
    date: new Date().toISOString().slice(0, 10),
    customer_id: 0,
    amount_paid: 0,
    items: [{ ...emptyItem }]
  });

  useEffect(() => {
    void getFinalStockOptions().then((response) => {
      setFinalStocks(response.data);
      if (response.data[0]) {
        setForm((current) => ({ ...current, items: [itemFromStock(response.data[0], current.items[0])] }));
      }
    });
  }, []);

  useEffect(() => {
    const handle = window.setTimeout(async () => {
      const response = await searchCustomers(customerQuery);
      setCustomerResults(response.data);
    }, 200);
    return () => window.clearTimeout(handle);
  }, [customerQuery]);

  const billTotal = useMemo(() => {
    return form.items.reduce((total, item) => total + item.boxes_sold * item.rate_per_box + item.loose_packets_sold * item.rate_per_packet, 0);
  }, [form.items]);

  async function submit() {
    if (!selectedCustomer) return;
    setIsSaving(true);
    try {
      await createDailySale(form);
      setToast("Bill Generated & WhatsApp Message Sent!");
      setSelectedCustomer(null);
      setCustomerQuery("");
      setCustomerResults([]);
      setForm({
        date: new Date().toISOString().slice(0, 10),
        customer_id: 0,
        amount_paid: 0,
        items: finalStocks[0] ? [itemFromStock(finalStocks[0], emptyItem)] : [{ ...emptyItem }]
      });
      window.setTimeout(() => customerSearchRef.current?.focus(), 0);
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

        <div className="mt-5 space-y-3">
          {form.items.map((item, index) => (
            <div key={index} className="grid gap-3 rounded-md border border-zinc-200 p-3 md:grid-cols-[0.9fr_0.9fr_0.7fr_0.7fr_0.8fr_0.8fr_auto]">
              <StockSelect value={stockValue(item)} stocks={finalStocks} onChange={(stock) => patchItem(index, itemFromStock(stock, item))} />
              <SelectField label="Variety" value={item.variety} options={varietyOptions} onChange={(variety) => patchItem(index, syncStockForVariety({ ...item, variety }, finalStocks))} />
              <NumberField label="Boxes" value={item.boxes_sold} onChange={(value) => patchItem(index, { boxes_sold: value })} />
              <NumberField label="Loose Packets" value={item.loose_packets_sold} onChange={(value) => patchItem(index, { loose_packets_sold: value })} />
              <NumberField label="Rate/packet" value={item.rate_per_packet} onChange={(value) => patchItem(index, ratesFromPacket(item, value, finalStocks))} />
              <NumberField label="Rate/box" value={item.rate_per_box} onChange={(value) => patchItem(index, ratesFromBox(item, value, finalStocks))} />
              <button className="mt-auto grid h-10 w-10 place-items-center rounded-md text-zinc-400 hover:bg-red-50 hover:text-red-600" type="button" onClick={() => removeItem(index)}>
                <Trash2 className="h-4 w-4" />
              </button>
            </div>
          ))}
        </div>

        <InvoicePreview customer={selectedCustomer} form={form} billTotal={billTotal} />

        <div className="mt-5 flex flex-wrap gap-2">
          <button className="inline-flex h-10 items-center gap-2 rounded-md border border-zinc-200 bg-white px-4 text-sm font-semibold text-zinc-700" type="button" onClick={() => setForm({ ...form, items: [...form.items, finalStocks[0] ? itemFromStock(finalStocks[0], emptyItem) : { ...emptyItem }] })}>
            <Plus className="h-4 w-4" />
            Add Product
          </button>
          <button className="inline-flex h-10 items-center gap-2 rounded-md bg-brand-600 px-4 text-sm font-semibold text-white hover:bg-brand-700 disabled:bg-zinc-300" disabled={isSaving || !selectedCustomer} type="button" onClick={submit}>
            <Check className="h-4 w-4" />
            {isSaving ? "Saving..." : "Save Sale"}
          </button>
        </div>
      </section>
    </div>
  );

  function patchItem(index: number, patch: Partial<SaleItem>) {
    setForm({ ...form, items: form.items.map((item, itemIndex) => (itemIndex === index ? { ...item, ...patch } : item)) });
  }

  function removeItem(index: number) {
    if (form.items.length === 1) return;
    setForm({ ...form, items: form.items.filter((_, itemIndex) => itemIndex !== index) });
  }
}

function itemFromStock(stock: FinalStockOption, current: SaleItem): SaleItem {
  return {
    ...current,
    product_size_ml: stock.product_size_ml,
    variety: stock.variety,
    packaging_size_name: stock.packaging_size_name
  };
}

function stockValue(item: SaleItem) {
  return `${item.product_size_ml}|${item.variety}|${item.packaging_size_name}`;
}

function findStock(item: SaleItem, stocks: FinalStockOption[]) {
  return stocks.find((stock) => stock.product_size_ml === item.product_size_ml && stock.variety === item.variety && stock.packaging_size_name === item.packaging_size_name);
}

function syncStockForVariety(item: SaleItem, stocks: FinalStockOption[]) {
  const match = stocks.find((stock) => stock.product_size_ml === item.product_size_ml && stock.variety === item.variety) || stocks.find((stock) => stock.variety === item.variety);
  return match ? itemFromStock(match, item) : item;
}

function ratesFromPacket(item: SaleItem, rate_per_packet: number, stocks: FinalStockOption[]) {
  const packets = findStock(item, stocks)?.packets_per_box_limit || 1;
  return { rate_per_packet, rate_per_box: Number((rate_per_packet * packets).toFixed(2)) };
}

function ratesFromBox(item: SaleItem, rate_per_box: number, stocks: FinalStockOption[]) {
  const packets = findStock(item, stocks)?.packets_per_box_limit || 1;
  return { rate_per_box, rate_per_packet: Number((rate_per_box / packets).toFixed(2)) };
}

function StockSelect({ value, stocks, onChange }: { value: string; stocks: FinalStockOption[]; onChange: (stock: FinalStockOption) => void }) {
  return (
    <label className="block text-sm">
      <span className="font-medium text-zinc-700">Packaging Size (ml)</span>
      <select className="mt-1 h-10 w-full rounded-md border border-zinc-200 px-3 outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-100" value={value} onChange={(event) => {
        const stock = stocks.find((item) => `${item.product_size_ml}|${item.variety}|${item.packaging_size_name}` === event.target.value);
        if (stock) onChange(stock);
      }}>
        {stocks.map((stock) => (
          <option key={`${stock.id}-${stock.variety}`} value={`${stock.product_size_ml}|${stock.variety}|${stock.packaging_size_name}`}>
            {stock.product_size_ml} ml
          </option>
        ))}
      </select>
    </label>
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

function SelectField({ label, value, options, onChange }: { label: string; value: string; options: string[]; onChange: (value: string) => void }) {
  return (
    <label className="block text-sm">
      <span className="font-medium text-zinc-700">{label}</span>
      <select className="mt-1 h-10 w-full rounded-md border border-zinc-200 px-3 outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-100" value={value} onChange={(event) => onChange(event.target.value)}>
        {options.map((option) => <option key={option}>{option}</option>)}
      </select>
    </label>
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

function NumberField({ label, value, onChange }: { label: string; value: number; onChange: (value: number) => void }) {
  return (
    <label className="block text-sm">
      <span className="font-medium text-zinc-700">{label}</span>
      <input className="mt-1 h-10 w-full rounded-md border border-zinc-200 px-3 outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-100" type="number" value={value} onFocus={(event) => event.target.select()} onChange={(event) => onChange(Number(event.target.value))} />
    </label>
  );
}

function Toast({ message, onClose }: { message: string; onClose: () => void }) {
  return (
    <button className="fixed right-5 top-20 z-50 rounded-md bg-emerald-600 px-4 py-3 text-sm font-semibold text-white shadow-lg" type="button" onClick={onClose}>
      {message}
    </button>
  );
}
