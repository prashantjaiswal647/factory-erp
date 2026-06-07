import { Check, ChevronDown, FileText, Plus, Receipt, ReceiptText, Search, Trash2 } from "lucide-react";
import { RefObject, useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";

import { useDataRefresh } from "../context/DataRefreshContext";
import { useAuth } from "../context/AuthContext";
import { createDailySale, createPendingSaleOrder, downloadInvoicePdf, generateInvoiceFromSale, getInventory, getNextInvoiceNumber, searchCustomers, getFactoryProfile } from "../lib/api";
import type { CustomerSearchResult, DailySaleCreate, LiveStockRow } from "../lib/api";

// ─── Types ──────────────────────────────────────────────────────────────────

type SaleItem = DailySaleCreate["items"][number];

const TAX_RATES = [0, 5, 12, 18, 28] as const;

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
  packets_per_box: 0,
  description: "",
  hsn_code: "",
  tax_rate: 18,
};

// ─── Helpers ─────────────────────────────────────────────────────────────────

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

function itemFromVariation(stock: LiveStockRow, current: SaleItem): SaleItem {
  return normalizeItem({
    ...current,
    product_id: stock.product_id || null,
    product_size_ml: stock.product_size_ml || 0,
    variety: stock.variety || "Plain White",
    packaging_size: stock.packaging_size || stock.packaging_size_name || "",
    packaging_size_name: stock.packaging_size_name || stock.packaging_size || "",
    packets_per_box: stock.packets_per_box || stock.packets_per_box_limit || current.packets_per_box || 0,
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
    rate_per_box: Number((ratePerPacket * packetsPerBox).toFixed(2)),
  };
}

function itemTaxableValue(item: SaleItem) {
  return Number(item.boxes_sold || 0) * Number(item.rate_per_box || 0);
}

function stateCode(value?: string | null) {
  const cleaned = (value || "").trim();
  return cleaned.length >= 2 ? cleaned.slice(0, 2).toUpperCase() : "";
}

function inferIntraStateSupply(buyerGstin?: string | null, placeOfSupply?: string | null) {
  const buyerCode = stateCode(buyerGstin);
  const supplyCode = stateCode(placeOfSupply);
  if (buyerCode && supplyCode && /^\d{2}$/.test(supplyCode)) {
    return buyerCode === supplyCode;
  }
  return true;
}

function numberToWords(num: number): string {
  if (num === 0) return "Rupees Zero Only";
  const a = [
    "", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine", "Ten",
    "Eleven", "Twelve", "Thirteen", "Fourteen", "Fifteen", "Sixteen", "Seventeen", "Eighteen", "Nineteen"
  ];
  const b = ["", "", "Twenty", "Thirty", "Forty", "Fifty", "Sixty", "Seventy", "Eighty", "Ninety"];

  function g(n: number): string {
    if (n < 20) return a[n];
    const digit = n % 10;
    return b[Math.floor(n / 10)] + (digit ? "-" + a[digit] : "");
  }

  function h(n: number): string {
    if (n === 0) return "";
    let str = "";
    if (n >= 100) {
      str += a[Math.floor(n / 100)] + " Hundred ";
      n %= 100;
    }
    if (n > 0) {
      if (str !== "") str += "and ";
      str += g(n) + " ";
    }
    return str;
  }

  let result = "";
  let temp = num;

  if (temp >= 10000000) {
    result += h(Math.floor(temp / 10000000)) + "Crore ";
    temp %= 10000000;
  }
  if (temp >= 100000) {
    result += h(Math.floor(temp / 100000)) + "Lakh ";
    temp %= 100000;
  }
  if (temp >= 1000) {
    result += h(Math.floor(temp / 1000)) + "Thousand ";
    temp %= 1000;
  }
  if (temp > 0) {
    result += h(temp);
  }

  return "Rupees " + result.trim() + " Only";
}

// ─── Main Component ──────────────────────────────────────────────────────────

export default function SalesEntryPage() {
  const [toast, setToast] = useState("");
  const [lastInvoiceId, setLastInvoiceId] = useState<number | null>(null);
  const [lastSaleId, setLastSaleId] = useState<number | null>(null);
  const [isGeneratingPdf, setIsGeneratingPdf] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [customerQuery, setCustomerQuery] = useState("");
  const [customerResults, setCustomerResults] = useState<CustomerSearchResult[]>([]);
  const [selectedCustomer, setSelectedCustomer] = useState<CustomerSearchResult | null>(null);
  const [inventoryRows, setInventoryRows] = useState<LiveStockRow[]>([]);
  const { triggerDataRefresh } = useDataRefresh();
  const { user } = useAuth();
  const customerSearchRef = useRef<HTMLInputElement>(null);
  const customerDropdownRef = useRef<HTMLDivElement>(null);
  const [isCustomerDropdownOpen, setIsCustomerDropdownOpen] = useState(false);

  // Bill of Supply Simple State Variables
  const [profile, setProfile] = useState<any>(null);
  const [simpleDesc, setSimpleDesc] = useState("");
  const [simpleHsn, setSimpleHsn] = useState("");
  const [simpleQty, setSimpleQty] = useState(0);
  const [simpleRate, setSimpleRate] = useState(0);

  useEffect(() => {
    void getFactoryProfile()
      .then((res) => setProfile(res.data))
      .catch(console.error);
  }, []);

  const [form, setForm] = useState<DailySaleCreate>({
    date: new Date().toISOString().slice(0, 10),
    customer_id: 0,
    amount_paid: 0,
    legal_invoice_type: "bill_of_supply",
    legal_invoice_number: "",
    rough_bill_enabled: true,
    rough_bill_number: "",
    buyer_gstin: "",
    transport_mode: "",
    vehicle_number: "",
    place_of_supply: "",
    items: [{ ...emptyItem }],
  });

  const isTaxInvoice = form.legal_invoice_type === "tax_invoice";
  const isSimpleInvoice = form.legal_invoice_type === "BILL_OF_SUPPLY_SIMPLE" || form.legal_invoice_type === "bill_of_supply_simple";

  async function refreshNextInvoiceNumber(overwrite = false) {
    try {
      const response = await getNextInvoiceNumber(form.legal_invoice_type);
      const invoiceNumber = response.data.invoice_number || "";
      setForm((current) => ({
        ...current,
        legal_invoice_number: overwrite || !current.legal_invoice_number ? invoiceNumber : current.legal_invoice_number,
      }));
      return invoiceNumber;
    } catch (error) {
      setToast(apiErrorMessage(error));
      return "";
    }
  }

  // Compute the invoice number to show in the Simple tab's readonly field
  // by reading directly from the profile counter for the active invoice type.
  const simpleTabInvoiceNumber: string = (() => {
    if (!profile) return form.legal_invoice_number || "Auto";
    const prefix = profile.invoice_prefix || "INV-";
    if (form.legal_invoice_type === "tax_invoice") {
      return `${prefix}${profile.tax_invoice_start_seq ?? profile.next_tax_invoice_number ?? 1}`;
    }
    if (form.legal_invoice_type === "BILL_OF_SUPPLY_SIMPLE" || form.legal_invoice_type === "bill_of_supply_simple") {
      return `${prefix}${profile.bill_of_supply_simple_start_seq ?? profile.next_bill_of_supply_simple_number ?? 1}`;
    }
    return `${prefix}${profile.bill_of_supply_start_seq ?? profile.next_bill_of_supply_number ?? 1}`;
  })();

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
    void refreshNextInvoiceNumber(true);
  }, [form.legal_invoice_type]);

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

  useEffect(() => {
    function closeCustomerDropdown(event: MouseEvent) {
      if (!customerDropdownRef.current?.contains(event.target as Node)) {
        setIsCustomerDropdownOpen(false);
      }
    }
    document.addEventListener("mousedown", closeCustomerDropdown);
    return () => document.removeEventListener("mousedown", closeCustomerDropdown);
  }, []);

  // ─── Tax Calculations ───────────────────────────────────────────────────────
  const taxCalc = useMemo(() => {
    const subtotal = form.items.reduce((sum, item) => sum + itemTaxableValue(item), 0);

    if (!isTaxInvoice) {
      return { subtotal, cgst: 0, sgst: 0, igst: 0, grandTotal: subtotal };
    }

    const isIntraState = inferIntraStateSupply(form.buyer_gstin, form.place_of_supply);

    // Accumulate tax per item (items can have different tax rates)
    let totalCgst = 0;
    let totalSgst = 0;
    let totalIgst = 0;

    for (const item of form.items) {
      const taxable = itemTaxableValue(item);
      const rate = Number(item.tax_rate ?? 18);
      if (isIntraState) {
        totalCgst += (taxable * rate) / 200; // half for CGST
        totalSgst += (taxable * rate) / 200; // half for SGST
      } else {
        totalIgst += (taxable * rate) / 100;
      }
    }

    const grandTotal = Math.round(subtotal + totalCgst + totalSgst + totalIgst);
    return {
      subtotal,
      cgst: Number(totalCgst.toFixed(2)),
      sgst: Number(totalSgst.toFixed(2)),
      igst: Number(totalIgst.toFixed(2)),
      grandTotal,
    };
  }, [form.items, form.buyer_gstin, form.place_of_supply, isTaxInvoice]);

  const hasInsufficientStock = useMemo(() => {
    return form.items.some((item) => {
      if (!item.product_id) return false;
      const stock = inventoryRows.find((row) => row.product_id === item.product_id);
      const available = Number(stock?.current_quantity ?? stock?.quantity ?? 0);
      return Number(item.boxes_sold || 0) > available;
    });
  }, [form.items, inventoryRows]);

  async function submitSimple() {
    if (!selectedCustomer) { setToast("Please select a customer."); return; }
    if (simpleQty <= 0 || simpleRate <= 0) { setToast("Quantity and Rate must be greater than zero."); return; }
    if (!simpleDesc.trim()) { setToast("Description is required."); return; }
    setIsSaving(true);
    try {
      const payload: DailySaleCreate = {
        date: form.date,
        customer_id: Number(selectedCustomer.id),
        amount_paid: Number(form.amount_paid || 0),
        legal_invoice_type: "BILL_OF_SUPPLY_SIMPLE",
        legal_invoice_number: form.legal_invoice_number?.trim() || null,
        rough_bill_enabled: false,
        rough_bill_number: null,
        items: [{
          product_id: null,
          product_size_ml: 210,
          variety: "Standard/White",
          packaging_size: "Standard Box",
          packaging_size_name: "Standard Box",
          boxes_sold: simpleQty,
          loose_packets_sold: 0,
          rate_per_box: simpleRate,
          rate_per_packet: 0,
          packets_per_box: 1,
          description: simpleDesc,
          hsn_code: simpleHsn || null,
          tax_rate: 0,
        }],
      };
      
      if (user?.role === "Owner") {
        const response = await createDailySale(payload);
        setLastInvoiceId(response.data.invoice_document_id || null);
        setLastSaleId(response.data.sale_ids[0] || null);
        setToast("Invoice saved. PDF can be downloaded from Invoices.");
      } else {
        await createPendingSaleOrder(payload);
        setToast("Order sent to Owner for approval.");
      }
      triggerDataRefresh();
      const nextInvoiceNumber = await refreshNextInvoiceNumber(true);
      setSelectedCustomer(null);
      setCustomerQuery("");
      setCustomerResults([]);
      setIsCustomerDropdownOpen(false);
      setSimpleDesc("");
      setSimpleHsn("");
      setSimpleQty(0);
      setSimpleRate(0);
      setForm({
        ...form,
        amount_paid: 0,
        legal_invoice_number: nextInvoiceNumber,
      });
      window.setTimeout(() => customerSearchRef.current?.focus(), 0);
    } catch (error) {
      setToast(apiErrorMessage(error));
    } finally {
      setIsSaving(false);
    }
  }

  async function submit() {
    if (isSimpleInvoice) {
      await submitSimple();
      return;
    }
    if (!selectedCustomer) return;
    const billableItems = form.items.filter((item) => Number(item.boxes_sold || 0) > 0 || Number(item.loose_packets_sold || 0) > 0);
    if (hasInsufficientStock) { setToast("Insufficient Stock"); return; }
    if (billableItems.length === 0) { setToast("Enter boxes quantity for at least one product."); return; }
    if (billableItems.some((item) => !item.product_size_ml || !item.packaging_size_name.trim() || !item.variety.trim())) {
      setToast("Please enter product size, variation, and packaging before saving.");
      return;
    }
    setIsSaving(true);
    try {
      const payload: DailySaleCreate = {
        ...form,
        customer_id: Number(selectedCustomer.id),
        amount_paid: Number(form.amount_paid || 0),
        legal_invoice_number: form.legal_invoice_number?.trim() || null,
        rough_bill_enabled: Boolean(form.rough_bill_enabled),
        rough_bill_number: null,
        buyer_gstin: isTaxInvoice ? (form.buyer_gstin?.trim() || null) : null,
        transport_mode: isTaxInvoice ? (form.transport_mode?.trim() || null) : null,
        vehicle_number: isTaxInvoice ? (form.vehicle_number?.trim() || null) : null,
        place_of_supply: isTaxInvoice ? (form.place_of_supply?.trim() || null) : null,
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
          variety: item.variety.trim() || "Plain White",
          description: item.description?.trim() || null,
          hsn_code: isTaxInvoice ? (item.hsn_code?.trim() || null) : null,
          tax_rate: isTaxInvoice ? Number(item.tax_rate ?? 18) : null,
        })),
      };

      if (user?.role === "Owner") {
        const response = await createDailySale(payload);
        setLastInvoiceId(response.data.invoice_document_id || null);
        setLastSaleId(response.data.sale_ids[0] || null);
        setToast("Invoice saved. PDF can be downloaded from Invoices.");
      } else {
        await createPendingSaleOrder(payload);
        setLastInvoiceId(null);
        setToast("Order sent to Owner for approval.");
      }
      triggerDataRefresh();
      const nextInvoiceNumber = await refreshNextInvoiceNumber(true);
      setSelectedCustomer(null);
      setCustomerQuery("");
      setCustomerResults([]);
      setIsCustomerDropdownOpen(false);
      setForm({
        date: new Date().toISOString().slice(0, 10),
        customer_id: 0,
        amount_paid: 0,
        legal_invoice_type: form.legal_invoice_type,
        legal_invoice_number: nextInvoiceNumber,
        rough_bill_enabled: false,
        rough_bill_number: "",
        buyer_gstin: "",
        transport_mode: "",
        vehicle_number: "",
        place_of_supply: "",
        items: inventoryRows[0] ? [itemFromVariation(inventoryRows[0], emptyItem)] : [{ ...emptyItem }],
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
    setForm({
      ...form,
      customer_id: customer.id,
      buyer_gstin: form.buyer_gstin || customer.gst_number || "",
      place_of_supply: form.place_of_supply || customer.place || "",
    });
    setCustomerResults([]);
    setIsCustomerDropdownOpen(false);
  }

  async function generateAndDownloadInvoice() {
    if (!lastSaleId) return;
    setIsGeneratingPdf(true);
    try {
      const generated = await generateInvoiceFromSale(lastSaleId, {
        invoice_type: isTaxInvoice ? "tax_invoice" : "bill_of_supply",
        tax_rate: isTaxInvoice ? 18 : 0,
        payment_method: "Cash",
      });
      setLastInvoiceId(generated.data.invoice_id);
      const response = await downloadInvoicePdf(generated.data.invoice_id);
      const url = URL.createObjectURL(response.data);
      const link = document.createElement("a");
      link.href = url;
      link.download = `${generated.data.invoice_number.replace(/[\\/]/g, "_")}.pdf`;
      link.click();
      URL.revokeObjectURL(url);
      setToast("Invoice PDF generated and downloaded.");
    } catch (error) {
      setToast(apiErrorMessage(error));
    } finally {
      setIsGeneratingPdf(false);
    }
  }

  function patchItem(index: number, patch: Partial<SaleItem>) {
    setForm({ ...form, items: form.items.map((item, itemIndex) => (itemIndex === index ? normalizeItem({ ...item, ...patch }) : item)) });
  }

  function removeItem(index: number) {
    if (form.items.length === 1) return;
    setForm({ ...form, items: form.items.filter((_, itemIndex) => itemIndex !== index) });
  }

  const isIntraState = useMemo(() => {
    return inferIntraStateSupply(form.buyer_gstin, form.place_of_supply);
  }, [form.buyer_gstin, form.place_of_supply]);

  return (
    <div className="mx-auto max-w-6xl space-y-5">
      {toast ? <Toast message={toast} onClose={() => setToast("")} /> : null}
      {lastInvoiceId ? (
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-md border border-green-200 bg-green-50 px-4 py-3 text-sm font-semibold text-green-800">
          <span>Sale saved. <Link className="underline" to="/invoices">View all invoices</Link>.</span>
          <button
            className="inline-flex items-center gap-2 rounded-md bg-green-700 px-3 py-2 text-sm font-bold text-white disabled:opacity-60"
            type="button"
            disabled={!lastSaleId || isGeneratingPdf}
            onClick={() => void generateAndDownloadInvoice()}
          >
            <FileText className="h-4 w-4" />
            {isGeneratingPdf ? "Generating PDF..." : "Generate Invoice PDF"}
          </button>
        </div>
      ) : null}

      <header>
        <h1 className="text-2xl font-semibold text-zinc-950">Sales Entry</h1>
        <p className="mt-1 text-sm text-zinc-500">Search customer, select stock by size and variety, and generate invoice.</p>
      </header>

      {/* ── Invoice Type Toggle Tabs ────────────────────────────────────────── */}
      <div className="flex gap-0 rounded-xl border border-zinc-200 bg-zinc-50 p-1 shadow-sm w-fit flex-wrap">
        <button
          type="button"
          onClick={() => setForm({ ...form, legal_invoice_type: "bill_of_supply" })}
          className={`inline-flex items-center gap-2 rounded-lg px-5 py-2.5 text-sm font-semibold transition-all duration-200 ${
            !isTaxInvoice && !isSimpleInvoice
              ? "bg-white text-brand-700 shadow-[0_2px_8px_rgba(0,0,0,0.10)] ring-1 ring-zinc-200"
              : "text-zinc-500 hover:text-zinc-800"
          }`}
        >
          <Receipt className="h-4 w-4" />
          Bill of Supply
        </button>
        <button
          type="button"
          onClick={() => setForm({ ...form, legal_invoice_type: "tax_invoice" })}
          className={`inline-flex items-center gap-2 rounded-lg px-5 py-2.5 text-sm font-semibold transition-all duration-200 ${
            isTaxInvoice
              ? "bg-white text-brand-700 shadow-[0_2px_8px_rgba(0,0,0,0.10)] ring-1 ring-zinc-200"
              : "text-zinc-500 hover:text-zinc-800"
          }`}
        >
          <FileText className="h-4 w-4" />
          Tax Invoice (GST)
        </button>
        <button
          type="button"
          onClick={() => setForm({ ...form, legal_invoice_type: "BILL_OF_SUPPLY_SIMPLE" })}
          className={`inline-flex items-center gap-2 rounded-lg px-5 py-2.5 text-sm font-semibold transition-all duration-200 ${
            isSimpleInvoice
              ? "bg-white text-brand-700 shadow-[0_2px_8px_rgba(0,0,0,0.10)] ring-1 ring-zinc-200"
              : "text-zinc-500 hover:text-zinc-800"
          }`}
        >
          <ReceiptText className="h-4 w-4" />
          Bill of Supply Simple
        </button>
      </div>

      <section className="rounded-lg border border-zinc-200 bg-white p-5 shadow-sm">
        <div className="mb-5 flex items-center gap-3">
          <span className="grid h-10 w-10 place-items-center rounded-md bg-brand-50 text-brand-700">
            <ReceiptText className="h-5 w-5" />
          </span>
          <div>
            <h2 className="text-lg font-semibold text-zinc-950">
              {isTaxInvoice ? "Tax Invoice (B2B GST)" : isSimpleInvoice ? "Bill of Supply Simple" : "Bill of Supply"}
            </h2>
            <p className="text-xs text-zinc-400 mt-0.5">
              {isTaxInvoice
                ? "GST registered — CGST/SGST or IGST calculated automatically"
                : isSimpleInvoice
                ? "Manual entry — free-form goods description, no inventory lookup"
                : "Composition scheme / unregistered — no GST breakdown"}
            </p>
          </div>
        </div>

        {/* ── Core Fields ─────────────────────────────────────────────────── */}
        <div className="grid gap-4 md:grid-cols-[1.4fr_0.7fr_0.7fr]">
          <CustomerCombobox
            containerRef={customerDropdownRef}
            inputRef={customerSearchRef}
            isOpen={isCustomerDropdownOpen}
            query={customerQuery}
            results={customerResults}
            onQueryChange={(value) => {
              setCustomerQuery(value);
              setIsCustomerDropdownOpen(true);
            }}
            onSelect={selectCustomer}
            onToggle={() => setIsCustomerDropdownOpen((open) => !open)}
          />
          <Field label="Date" type="date" value={form.date} onChange={(date) => setForm({ ...form, date })} />
          <NumberField label="Amount paid" value={form.amount_paid} onChange={(amount_paid) => setForm({ ...form, amount_paid })} />
        </div>

        <div className="mt-4 grid gap-4 rounded-lg border border-zinc-200 bg-zinc-50 p-4 md:grid-cols-1">
          <Field label="Legal invoice number" value={form.legal_invoice_number || ""} onChange={(legal_invoice_number) => setForm({ ...form, legal_invoice_number })} />
        </div>

        {/* ── Tax Invoice B2B Fields (only visible in Tax Invoice mode) ───── */}
        {isTaxInvoice && (
          <div className="mt-4 rounded-xl border border-brand-200 bg-brand-50/40 p-4">
            <p className="mb-3 text-xs font-bold uppercase tracking-widest text-brand-700">GST & Transport Details <span className="font-normal text-zinc-400 normal-case tracking-normal">(all optional)</span></p>
            <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-4">
              <Field
                label="Buyer GSTIN (Optional)"
                value={form.buyer_gstin || ""}
                onChange={(buyer_gstin) => setForm({ ...form, buyer_gstin })}
                placeholder="e.g. 27AABCU9603R1ZX"
              />
              <Field
                label="Place of Supply (Optional)"
                value={form.place_of_supply || ""}
                onChange={(place_of_supply) => setForm({ ...form, place_of_supply })}
                placeholder="e.g. 27 or Maharashtra"
              />
              <Field
                label="Transport Mode (Optional)"
                value={form.transport_mode || ""}
                onChange={(transport_mode) => setForm({ ...form, transport_mode })}
                placeholder="Road / Rail / Air"
              />
              <Field
                label="Vehicle Number (Optional)"
                value={form.vehicle_number || ""}
                onChange={(vehicle_number) => setForm({ ...form, vehicle_number })}
                placeholder="e.g. MH12AB1234"
              />
            </div>
            {(form.buyer_gstin?.trim() || form.place_of_supply?.trim()) && (
              <div className="mt-2 inline-flex items-center gap-2 rounded-full bg-white px-3 py-1 text-xs font-semibold shadow-sm border border-zinc-200">
                <span className={`h-2 w-2 rounded-full ${isIntraState ? "bg-green-500" : "bg-amber-500"}`} />
                {isIntraState ? "Intra-State: CGST + SGST will be applied" : "Inter-State: IGST will be applied"}
              </div>
            )}
          </div>
        )}

        {/* ── Items Table (standard tabs only) ─────────────────────────────── */}
        {!isSimpleInvoice && (
          <div className="mt-5 space-y-3">
            {form.items.map((item, index) => (
              <div
                key={index}
                className={`rounded-md border border-zinc-200 p-3 ${isTaxInvoice ? "grid gap-3 md:grid-cols-[1.4fr_1fr_0.55fr_0.55fr_0.55fr_0.55fr_0.5fr_0.65fr_auto]" : "grid gap-3 md:grid-cols-[1.5fr_0.75fr_0.75fr_0.75fr_0.65fr_0.75fr_auto]"}`}
              >
                <VariationField
                  item={item}
                  rows={inventoryRows}
                  onCustomChange={(value) => patchItem(index, {
                    product_id: null,
                    variety: value || "Plain White",
                    packaging_size: value,
                    packaging_size_name: value,
                  })}
                  onSelect={(stock) => patchItem(index, itemFromVariation(stock, item))}
                />
                {isTaxInvoice && (
                  <Field
                    label="Product Description"
                    value={item.description || ""}
                    onChange={(description) => patchItem(index, { description })}
                    placeholder="Optional item description"
                  />
                )}
                {isTaxInvoice && (
                  <label className="block text-sm">
                    <span className="font-medium text-zinc-700">HSN Code</span>
                    <input
                      className="mt-1 h-10 w-full rounded-md border border-zinc-200 px-3 text-sm outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-100"
                      placeholder="Optional"
                      type="text"
                      value={item.hsn_code || ""}
                      onChange={(e) => patchItem(index, { hsn_code: e.target.value })}
                    />
                  </label>
                )}
                <NumberField label="Rate/packet" value={item.rate_per_packet} onChange={(rate_per_packet) => patchItem(index, { rate_per_packet })} />
                <NumberField label="Packets/box" value={item.packets_per_box} onChange={(packets_per_box) => patchItem(index, { packets_per_box })} />
                <NumberField label="Rate/box" value={item.rate_per_box} onChange={() => undefined} readOnly />
                <NumberField label="Boxes" value={item.boxes_sold} onChange={(boxes_sold) => patchItem(index, { boxes_sold })} />
                {isTaxInvoice && (
                  <label className="block text-sm">
                    <span className="font-medium text-zinc-700">Tax %</span>
                    <select
                      className="mt-1 h-10 w-full rounded-md border border-zinc-200 px-2 text-sm outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-100"
                      value={item.tax_rate ?? 18}
                      onChange={(e) => patchItem(index, { tax_rate: Number(e.target.value) })}
                    >
                      {TAX_RATES.map((rate) => (
                        <option key={rate} value={rate}>{rate}%</option>
                      ))}
                    </select>
                  </label>
                )}
                <StockIndicator item={item} rows={inventoryRows} />
                <button className="mt-auto grid h-10 w-10 place-items-center rounded-md text-zinc-400 hover:bg-red-50 hover:text-red-600" type="button" onClick={() => removeItem(index)}>
                  <Trash2 className="h-4 w-4" />
                </button>
              </div>
            ))}
          </div>
        )}

        {/* ── Tax Breakdown Card (Tax Invoice only) ────────────────────────── */}
        {isTaxInvoice && (
          <div className="mt-5 rounded-xl border border-brand-200 bg-white shadow-sm overflow-hidden">
            <div className="bg-brand-600 px-4 py-2">
              <p className="text-xs font-bold uppercase tracking-widest text-white">Live Tax Calculation</p>
            </div>
            <div className="divide-y divide-zinc-100">
              <TaxRow label="Subtotal (Before Tax)" value={taxCalc.subtotal} />
              {isIntraState ? (
                <>
                  <TaxRow label={`CGST (${form.items[0]?.tax_rate ?? 18}% ÷ 2)`} value={taxCalc.cgst} accent />
                  <TaxRow label={`SGST (${form.items[0]?.tax_rate ?? 18}% ÷ 2)`} value={taxCalc.sgst} accent />
                </>
              ) : (
                <TaxRow label={`IGST (${form.items[0]?.tax_rate ?? 18}%)`} value={taxCalc.igst} accent />
              )}
              <div className="flex items-center justify-between px-4 py-3 bg-brand-50">
                <span className="text-sm font-bold text-brand-900">Grand Total (Rounded)</span>
                <span className="text-xl font-extrabold text-brand-700">₹{taxCalc.grandTotal.toLocaleString("en-IN")}</span>
              </div>
            </div>
          </div>
        )}

        {/* ── Bill of Supply Preview (standard bill_of_supply only) ────────── */}
        {!isTaxInvoice && !isSimpleInvoice && (
          <InvoicePreview customer={selectedCustomer} form={form} billTotal={taxCalc.subtotal} />
        )}

        {/* ── Bill of Supply Simple — Manual Entry Form ────────────────────── */}
        {isSimpleInvoice && (
          <div className="mt-5 space-y-5">
            {/* Read-only profile fields */}
            <div className="rounded-xl border border-zinc-200 bg-zinc-50 p-4">
              <p className="mb-3 text-xs font-bold uppercase tracking-widest text-zinc-500">Factory Details (Auto-Filled)</p>
              <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-3">
                <ReadonlyField label="Factory Name" value={profile?.factory_name || "Loading..."} />
                <ReadonlyField label="GST Number" value={profile?.gst_number || "—"} />
                <ReadonlyField label="Address" value={profile?.address || "—"} />
                <ReadonlyField label="Mobile Number" value={profile?.mobile_number || "—"} />
                <ReadonlyField label="Invoice Number" value={simpleTabInvoiceNumber} />
              </div>
            </div>

            {/* Manual entry fields */}
            <div className="rounded-xl border border-zinc-200 bg-white p-4">
              <p className="mb-3 text-xs font-bold uppercase tracking-widest text-zinc-500">Goods Details (Manual Entry)</p>
              <div className="grid gap-4 md:grid-cols-2">
                <label className="col-span-full block text-sm">
                  <span className="font-medium text-zinc-700">Description of Goods <span className="text-red-500">*</span></span>
                  <textarea
                    className="mt-1 w-full rounded-md border border-zinc-200 px-3 py-2 text-sm outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-100 resize-none"
                    rows={2}
                    placeholder="Enter description of goods supplied..."
                    value={simpleDesc}
                    onChange={(e) => setSimpleDesc(e.target.value)}
                  />
                </label>
                <label className="block text-sm">
                  <span className="font-medium text-zinc-700">HSN Code</span>
                  <input
                    className="mt-1 h-10 w-full rounded-md border border-zinc-200 px-3 text-sm outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-100"
                    type="text"
                    placeholder="e.g. 3923"
                    value={simpleHsn}
                    onChange={(e) => setSimpleHsn(e.target.value)}
                  />
                </label>
                <div className="grid grid-cols-2 gap-3">
                  <label className="block text-sm">
                    <span className="font-medium text-zinc-700">Quantity <span className="text-red-500">*</span></span>
                    <input
                      className="mt-1 h-10 w-full rounded-md border border-zinc-200 px-3 text-sm outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-100"
                      type="number"
                      min="0"
                      placeholder="0"
                      value={simpleQty === 0 ? "" : simpleQty}
                      onChange={(e) => setSimpleQty(e.target.value === "" ? 0 : Number(e.target.value))}
                    />
                  </label>
                  <label className="block text-sm">
                    <span className="font-medium text-zinc-700">Rate (₹) <span className="text-red-500">*</span></span>
                    <input
                      className="mt-1 h-10 w-full rounded-md border border-zinc-200 px-3 text-sm outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-100"
                      type="number"
                      min="0"
                      placeholder="0.00"
                      value={simpleRate === 0 ? "" : simpleRate}
                      onChange={(e) => setSimpleRate(e.target.value === "" ? 0 : Number(e.target.value))}
                    />
                  </label>
                </div>
              </div>
            </div>

            {/* Live total calculation */}
            <div className="rounded-xl border border-brand-200 bg-white shadow-sm overflow-hidden">
              <div className="bg-brand-600 px-4 py-2">
                <p className="text-xs font-bold uppercase tracking-widest text-white">Total Taxable Amount</p>
              </div>
              <div className="px-4 py-4 space-y-1">
                <div className="flex items-center justify-between">
                  <span className="text-sm text-zinc-600">
                    {simpleQty} × ₹{simpleRate} =
                  </span>
                  <span className="text-2xl font-extrabold text-brand-700">
                    ₹{(simpleQty * simpleRate).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                  </span>
                </div>
                {(simpleQty > 0 && simpleRate > 0) && (
                  <p className="text-xs font-semibold text-zinc-500 italic">
                    {numberToWords(Math.round(simpleQty * simpleRate))}
                  </p>
                )}
              </div>
            </div>
          </div>
        )}

        {/* ── Footer Buttons ───────────────────────────────────────────────── */}
        <div className="mt-5 flex flex-wrap gap-2">
          {!isSimpleInvoice && (
            <button
              className="inline-flex h-10 items-center gap-2 rounded-md border border-zinc-200 bg-white px-4 text-sm font-semibold text-zinc-700"
              type="button"
              onClick={() => setForm({ ...form, items: [...form.items, inventoryRows[0] ? itemFromVariation(inventoryRows[0], { ...emptyItem }) : { ...emptyItem }] })}
            >
              <Plus className="h-4 w-4" />
              Add Product
            </button>
          )}
          <button
            className="inline-flex h-10 items-center gap-2 rounded-md bg-brand-600 px-4 text-sm font-semibold text-white hover:bg-brand-700 disabled:bg-zinc-300"
            disabled={isSaving || !selectedCustomer || (!isSimpleInvoice && hasInsufficientStock)}
            type="button"
            onClick={submit}
          >
            <Check className="h-4 w-4" />
            {isSaving ? "Saving..." : "Save Sale"}
          </button>
        </div>
      </section>
    </div>
  );
}

// ─── Sub-Components ──────────────────────────────────────────────────────────

function TaxRow({ label, value, accent = false }: { label: string; value: number; accent?: boolean }) {
  return (
    <div className={`flex items-center justify-between px-4 py-2.5 ${accent ? "bg-brand-50/50" : ""}`}>
      <span className={`text-sm ${accent ? "font-semibold text-brand-700" : "text-zinc-600"}`}>{label}</span>
      <span className={`text-sm font-bold tabular-nums ${accent ? "text-brand-700" : "text-zinc-900"}`}>
        ₹{value.toFixed(2)}
      </span>
    </div>
  );
}

function variationLabel(row: LiveStockRow) {
  return `${row.variety || "Product"} - ${row.packaging_size || row.packaging_size_name || "Standard"} [${row.pieces_per_packet || 0} Pcs/Pkt]`;
}

function VariationField({
  item,
  rows,
  onCustomChange,
  onSelect,
}: {
  item: SaleItem;
  rows: LiveStockRow[];
  onCustomChange: (value: string) => void;
  onSelect: (row: LiveStockRow) => void;
}) {
  const [isOpen, setOpen] = useState(false);
  const query = item.product_id
    ? variationLabel(rows.find((row) => row.product_id === item.product_id) || ({} as LiveStockRow))
    : item.packaging_size_name || item.variety || "";
  const normalizedQuery = query.trim().toLowerCase();
  const suggestions = rows
    .filter((row) => variationLabel(row).toLowerCase().includes(normalizedQuery))
    .slice(0, 8);

  return (
    <label className="relative block text-sm">
      <span className="font-medium text-zinc-700">Product Variation</span>
      <input
        className="mt-1 h-10 w-full rounded-md border border-zinc-200 px-3 outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-100"
        value={query}
        onBlur={() => window.setTimeout(() => setOpen(false), 120)}
        onChange={(event) => {
          onCustomChange(event.target.value);
          setOpen(true);
        }}
        onFocus={() => setOpen(true)}
        placeholder="Type or select variation"
      />
      {isOpen && suggestions.length > 0 ? (
        <div className="absolute z-30 mt-1 max-h-64 w-full overflow-auto rounded-md border border-zinc-200 bg-white shadow-lg">
          {suggestions.map((row) => (
            <button
              key={String(row.id)}
              className="block w-full px-3 py-2 text-left text-sm hover:bg-brand-50"
              type="button"
              onMouseDown={(event) => event.preventDefault()}
              onClick={() => {
                onSelect(row);
                setOpen(false);
              }}
            >
              <span className="font-semibold text-zinc-900">{variationLabel(row)}</span>
              <span className="block text-xs text-zinc-500">Stock {row.current_quantity ?? row.quantity} boxes</span>
            </button>
          ))}
        </div>
      ) : null}
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
        {insufficient ? "Insufficient" : `${available} boxes`}
      </div>
    </div>
  );
}

function CustomerCombobox({
  containerRef,
  inputRef,
  isOpen,
  query,
  results,
  onQueryChange,
  onSelect,
  onToggle,
}: {
  containerRef: RefObject<HTMLDivElement>;
  inputRef: RefObject<HTMLInputElement>;
  isOpen: boolean;
  query: string;
  results: CustomerSearchResult[];
  onQueryChange: (value: string) => void;
  onSelect: (customer: CustomerSearchResult) => void;
  onToggle: () => void;
}) {
  return (
    <div ref={containerRef} className="relative text-sm">
      <span className="font-medium text-zinc-700">Customer</span>
      <Search className="pointer-events-none absolute left-3 top-9 h-4 w-4 text-zinc-400" />
      <input
        ref={inputRef}
        className="mt-1 h-10 w-full rounded-md border border-zinc-200 pl-9 pr-10 outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-100"
        value={query}
        onChange={(event) => onQueryChange(event.target.value)}
        onClick={onToggle}
        placeholder="Search name or phone"
      />
      <button
        aria-label={isOpen ? "Collapse customer list" : "Expand customer list"}
        className="absolute right-2 top-8 grid h-7 w-7 place-items-center rounded-md text-zinc-500 hover:bg-zinc-100 hover:text-zinc-900"
        type="button"
        onClick={onToggle}
      >
        <ChevronDown className={`h-4 w-4 transition ${isOpen ? "rotate-180" : ""}`} />
      </button>
      {isOpen && results.length > 0 ? (
        <div className="absolute z-20 mt-1 max-h-64 w-full overflow-auto rounded-md border border-zinc-200 bg-white shadow-lg">
          {results.map((customer) => (
            <button key={customer.id} className="block w-full px-3 py-2 text-left text-sm hover:bg-brand-50" type="button" onMouseDown={(event) => event.preventDefault()} onClick={() => onSelect(customer)}>
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

function Field({ label, value, type = "text", onChange, placeholder }: { label: string; value: string; type?: string; onChange: (value: string) => void; placeholder?: string }) {
  return (
    <label className="block text-sm">
      <span className="font-medium text-zinc-700">{label}</span>
      <input className="mt-1 h-10 w-full rounded-md border border-zinc-200 px-3 outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-100" type={type} value={value} onChange={(event) => onChange(event.target.value)} placeholder={placeholder} />
    </label>
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

function ReadonlyField({ label, value }: { label: string; value: string }) {
  return (
    <div className="block text-sm">
      <span className="font-medium text-zinc-700">{label}</span>
      <div className="mt-1 flex h-10 items-center rounded-md border border-zinc-200 bg-zinc-100 px-3 text-sm text-zinc-600 select-all cursor-default truncate">
        {value}
      </div>
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
