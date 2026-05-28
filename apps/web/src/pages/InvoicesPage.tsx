import { Download, FileText, RefreshCw, Plus, Trash2, Calendar, FileSpreadsheet, Check, UserRound, Eye, Info, X } from "lucide-react";
import { useEffect, useState } from "react";

import { downloadInvoicePdf, getInvoiceDocuments, getDashboardCustomers, getAccountantSummary, api } from "../lib/api";
import type { InvoiceDashboardResponse, InvoiceDocumentSummary, DashboardCustomer } from "../lib/api";

function money(value: string | number) {
  return `Rs ${Number(value || 0).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function dateLabel(value: string) {
  if (!value) return "-";
  return new Date(value).toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "numeric" });
}

function apiErrorMessage(error: unknown) {
  const detail = (error as { response?: { data?: { detail?: unknown } } }).response?.data?.detail;
  return typeof detail === "string" ? detail : "Invoice request failed";
}

function numberToWords(num: number): string {
  if (num === 0) return "Zero Rupees Only";
  const a = [
    "", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine", "Ten",
    "Eleven", "Twelve", "Thirteen", "Fourteen", "Fifteen", "Sixteen", "Seventeen", "Eighteen", "Nineteen"
  ];
  const b = ["", "", "Twenty", "Thirty", "Forty", "Fifty", "Sixty", "Seventy", "Eighty", "Ninety"];
  
  function g(n: number): string {
    if (n < 20) return a[n];
    const digit = n % 10;
    return b[Math.floor(n / 10)] + (digit ? " " + a[digit] : "");
  }
  
  function h(n: number): string {
    if (n < 100) return g(n);
    return a[Math.floor(n / 100)] + " Hundred" + (n % 100 ? " and " + g(n % 100) : "");
  }
  
  function convert(n: number): string {
    if (n === 0) return "";
    let str = "";
    if (n >= 10000000) {
      str += convert(Math.floor(n / 10000000)) + " Crore ";
      n %= 10000000;
    }
    if (n >= 100000) {
      str += convert(Math.floor(n / 100000)) + " Lakh ";
      n %= 100000;
    }
    if (n >= 1000) {
      str += h(Math.floor(n / 1000)) + " Thousand ";
      n %= 1000;
    }
    if (n > 0) {
      str += h(n);
    }
    return str.trim();
  }
  
  const parts = num.toFixed(2).split(".");
  const rupees = parseInt(parts[0], 10);
  const paise = parseInt(parts[1], 10);
  
  let word = convert(rupees) + " Rupees";
  if (paise > 0) {
    word += " and " + g(paise) + " Paise";
  }
  return word + " Only";
}

export default function InvoicesPage() {
  const [data, setData] = useState<InvoiceDashboardResponse | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [downloadingId, setDownloadingId] = useState<number | null>(null);
  const [viewingId, setViewingId] = useState<number | null>(null);
  const [selectedInvoiceDetails, setSelectedInvoiceDetails] = useState<InvoiceDocumentSummary | null>(null);
  const [message, setMessage] = useState("");
  
  // Custom Invoice Form state
  const [showCreateInvoice, setShowCreateInvoice] = useState(false);
  const [invoiceType, setInvoiceType] = useState<"tax_invoice" | "bill_of_supply">("bill_of_supply");
  const [invoiceDate, setInvoiceDate] = useState(new Date().toISOString().split("T")[0]);
  const [customerId, setCustomerId] = useState<number>(0);
  const [productSerial, setProductSerial] = useState("");
  const [descriptionOfGoods, setDescriptionOfGoods] = useState("");
  const [hsnCode, setHSNCode] = useState("4823");
  const [quantity, setQuantity] = useState(0);
  const [rate, setRate] = useState(0);
  const [amountPaid, setAmountPaid] = useState(0);
  const [isSaving, setIsSaving] = useState(false);

  // Lists
  const [customers, setCustomers] = useState<DashboardCustomer[]>([]);
  const [goodsSuggestions] = useState([
    "65ml Standard Cup",
    "100ml Standard Cup",
    "150ml Standard Cup",
    "210ml Standard Cup",
    "250ml Standard Cup",
    "Printed Paper Cups",
    "Brown Kraft Cups",
    "Double Wall Cups"
  ]);
  const [showSuggestions, setShowSuggestions] = useState(false);

  // Accountant Report state
  const [accountantMonth, setAccountantMonth] = useState(new Date().getMonth() + 1);
  const [accountantYear, setAccountantYear] = useState(new Date().getFullYear());
  const [isDownloadingSummary, setIsDownloadingSummary] = useState(false);

  async function loadInvoices() {
    setIsLoading(true);
    try {
      const response = await getInvoiceDocuments();
      setData(response.data);
      setMessage("");
    } catch (error) {
      setMessage(apiErrorMessage(error));
    } finally {
      setIsLoading(false);
    }
  }

  async function loadCustomers() {
    try {
      const res = await getDashboardCustomers();
      setCustomers(res.data || []);
      if (res.data && res.data.length > 0) {
        setCustomerId(res.data[0].id);
      }
    } catch (err) {
      console.error("Failed to load customers:", err);
    }
  }

  useEffect(() => {
    void loadInvoices();
    void loadCustomers();
  }, []);

  async function download(invoice: InvoiceDocumentSummary) {
    setDownloadingId(invoice.id);
    try {
      const response = await downloadInvoicePdf(invoice.id);
      const blob = new Blob([response.data], { type: "application/pdf" });
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `${invoice.invoice_number}_invoice.pdf`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);
      setMessage("PDF download started.");
      void loadInvoices();
    } catch (error) {
      setMessage(apiErrorMessage(error));
    } finally {
      setDownloadingId(null);
    }
  }

  async function preview(invoice: InvoiceDocumentSummary) {
    setViewingId(invoice.id);
    try {
      const response = await downloadInvoicePdf(invoice.id, true);
      const blob = new Blob([response.data], { type: "application/pdf" });
      const url = window.URL.createObjectURL(blob);
      window.open(url, '_blank');
      setMessage("Invoice PDF opened in a new tab.");
      void loadInvoices();
    } catch (error) {
      setMessage(apiErrorMessage(error));
    } finally {
      setViewingId(null);
    }
  }

  async function downloadAccountantSummaryReport() {
    setIsDownloadingSummary(true);
    try {
      const response = await getAccountantSummary(accountantMonth, accountantYear, true);
      const blob = new Blob([response.data], { type: "application/pdf" });
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `accountant_summary_${accountantMonth}_${accountantYear}.pdf`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);
      setMessage("Accountant summary download completed.");
    } catch (error) {
      setMessage(apiErrorMessage(error));
    } finally {
      setIsDownloadingSummary(false);
    }
  }

  async function handleCreateInvoice() {
    if (!customerId) {
      setMessage("Please select a customer.");
      return;
    }
    if (!descriptionOfGoods.trim()) {
      setMessage("Please enter or select a Description of Goods.");
      return;
    }
    if (quantity <= 0 || rate <= 0) {
      setMessage("Quantity and Rate must be greater than zero.");
      return;
    }

    setIsSaving(true);
    try {
      const selectedCustomer = customers.find(c => c.id === customerId);
      
      const payload = {
        date: invoiceDate,
        customer_id: customerId,
        amount_paid: amountPaid,
        legal_invoice_type: invoiceType,
        legal_invoice_number: "", // Backend will automatically auto-increment!
        rough_bill_enabled: false,
        items: [
          {
            product_size_ml: parseInt(descriptionOfGoods) || 210, // Try parsing size or default to 210
            variety: descriptionOfGoods.includes("Standard") ? "Standard/White" : "Printed",
            packaging_size_name: "Boxes",
            boxes_sold: quantity,
            loose_packets_sold: 0,
            rate_per_box: rate,
            hsn_code: hsnCode,
            description: descriptionOfGoods
          }
        ]
      };

      // Hit sales invoice post endpoint directly
      await api.post("/api/sales/invoice", payload);
      
      // Reset form
      setDescriptionOfGoods("");
      setQuantity(0);
      setRate(0);
      setAmountPaid(0);
      setShowCreateInvoice(false);
      setMessage("Invoice created successfully!");
      
      void loadInvoices();
    } catch (error) {
      setMessage(apiErrorMessage(error));
    } finally {
      setIsSaving(false);
    }
  }

  const invoices = data?.invoices || [];
  const totalTaxable = quantity * rate;
  const taxableInWords = numberToWords(totalTaxable);

  return (
    <div className="mx-auto max-w-7xl space-y-5">
      <header className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-zinc-950">Invoices</h1>
          <p className="mt-1 text-sm text-zinc-500">Factory invoice records. Automatically track sequences and export monthly registers for accountants.</p>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <button 
            className="inline-flex h-10 items-center gap-2 rounded-md bg-brand-600 px-4 text-sm font-semibold text-white hover:bg-brand-700 shadow-sm"
            type="button" 
            onClick={() => setShowCreateInvoice(!showCreateInvoice)}
          >
            <Plus className="h-4 w-4" />
            {showCreateInvoice ? "Close Form" : "Create Invoice"}
          </button>
          <button className="inline-flex h-10 items-center gap-2 rounded-md border border-zinc-200 bg-white px-4 text-sm font-semibold text-zinc-700 hover:bg-zinc-50" type="button" onClick={loadInvoices}>
            <RefreshCw className="h-4 w-4" />
            Refresh
          </button>
        </div>
      </header>

      {message ? <div className="rounded-md border border-zinc-200 bg-brand-50 px-4 py-3 text-sm font-semibold text-brand-900">{message}</div> : null}

      {/* Dynamic Invoice Creation Form */}
      {showCreateInvoice && (
        <section className="rounded-xl border border-zinc-200 bg-white p-6 shadow-md transition-all space-y-5">
          <div className="flex items-center justify-between border-b border-zinc-100 pb-3">
            <h2 className="text-lg font-bold text-zinc-950 flex items-center gap-2">
              <Plus className="h-5 w-5 text-brand-600" />
              Invoice Drafting Console
            </h2>
            
            {/* Tax Invoice vs Bill of Supply switcher tabs */}
            <div className="flex rounded-lg bg-zinc-100 p-1">
              <button
                type="button"
                className={`py-1.5 px-3 text-xs font-semibold rounded-md transition-all ${
                  invoiceType === "bill_of_supply"
                    ? "bg-white text-zinc-900 shadow-sm"
                    : "text-zinc-600 hover:text-zinc-900"
                }`}
                onClick={() => {
                  setInvoiceType("bill_of_supply");
                  setHSNCode("4823");
                }}
              >
                Bill of Supply
              </button>
              <button
                type="button"
                className={`py-1.5 px-3 text-xs font-semibold rounded-md transition-all ${
                  invoiceType === "tax_invoice"
                    ? "bg-white text-zinc-900 shadow-sm"
                    : "text-zinc-600 hover:text-zinc-900"
                }`}
                onClick={() => {
                  setInvoiceType("tax_invoice");
                  setHSNCode("4823");
                }}
              >
                Tax Invoice
              </button>
            </div>
          </div>

          <div className="grid gap-4 md:grid-cols-3">
            <div>
              <label className="block text-xs font-semibold text-zinc-600 mb-1">Invoice Date</label>
              <input 
                type="date" 
                value={invoiceDate} 
                onChange={(e) => setInvoiceDate(e.target.value)} 
                className="h-10 w-full rounded-md border border-zinc-200 px-3 outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-100 text-sm font-medium"
              />
            </div>
            
            <div>
              <label className="block text-xs font-semibold text-zinc-600 mb-1">Select Customer</label>
              <select 
                value={customerId} 
                onChange={(e) => setCustomerId(Number(e.target.value))} 
                className="h-10 w-full rounded-md border border-zinc-200 px-3 outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-100 text-sm font-medium bg-white"
              >
                {customers.map(c => (
                  <option key={c.id} value={c.id}>{c.name} ({c.phone || "No Phone"})</option>
                ))}
              </select>
            </div>

            <div>
              <label className="block text-xs font-semibold text-zinc-600 mb-1">Product Serial Number (Optional)</label>
              <input 
                type="text" 
                placeholder="e.g. S-2026A"
                value={productSerial} 
                onChange={(e) => setProductSerial(e.target.value)} 
                className="h-10 w-full rounded-md border border-zinc-200 px-3 outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-100 text-sm font-medium"
              />
            </div>
          </div>

          <div className="grid gap-4 md:grid-cols-4">
            {/* Description with autocomplete suggestions dropdown */}
            <div className="relative md:col-span-2">
              <label className="block text-xs font-semibold text-zinc-600 mb-1">Description of Goods</label>
              <input 
                type="text" 
                placeholder="Type or select product..." 
                value={descriptionOfGoods}
                onChange={(e) => {
                  setDescriptionOfGoods(e.target.value);
                  setShowSuggestions(true);
                }}
                onFocus={() => setShowSuggestions(true)}
                className="h-10 w-full rounded-md border border-zinc-200 px-3 outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-100 text-sm font-medium"
              />
              {showSuggestions && (
                <div className="absolute left-0 right-0 z-20 mt-1 max-h-48 overflow-y-auto rounded-md border border-zinc-200 bg-white shadow-lg text-xs font-medium divide-y divide-zinc-50">
                  {goodsSuggestions
                    .filter(s => s.toLowerCase().includes(descriptionOfGoods.toLowerCase()))
                    .map(s => (
                      <button 
                        key={s} 
                        type="button"
                        className="w-full px-3 py-2 text-left hover:bg-brand-50 text-zinc-700 transition"
                        onClick={() => {
                          setDescriptionOfGoods(s);
                          setShowSuggestions(false);
                        }}
                      >
                        {s}
                      </button>
                    ))
                  }
                  <button 
                    type="button" 
                    className="w-full px-3 py-1.5 text-center text-[10px] text-zinc-400 hover:text-zinc-600 bg-zinc-50"
                    onClick={() => setShowSuggestions(false)}
                  >
                    Close suggestions
                  </button>
                </div>
              )}
            </div>

            <div>
              <label className="block text-xs font-semibold text-zinc-600 mb-1">HSN Code</label>
              <input 
                type="text" 
                value={hsnCode} 
                onChange={(e) => setHSNCode(e.target.value)} 
                className="h-10 w-full rounded-md border border-zinc-200 px-3 outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-100 text-sm font-medium"
              />
            </div>

            <div>
              <label className="block text-xs font-semibold text-zinc-600 mb-1">Quantity (Boxes)</label>
              <input 
                type="number" 
                placeholder="0"
                value={quantity || ""} 
                onChange={(e) => setQuantity(Number(e.target.value))} 
                className="h-10 w-full rounded-md border border-zinc-200 px-3 outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-100 text-sm font-medium"
              />
            </div>
          </div>

          <div className="grid gap-4 md:grid-cols-3 bg-zinc-50 p-4 rounded-lg border border-zinc-150">
            <div>
              <label className="block text-xs font-semibold text-zinc-600 mb-1">Rate per Box</label>
              <input 
                type="number" 
                placeholder="0.00"
                value={rate || ""} 
                onChange={(e) => setRate(Number(e.target.value))} 
                className="h-10 w-full rounded-md border border-zinc-200 px-3 outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-100 text-sm font-medium bg-white"
              />
            </div>

            <div>
              <label className="block text-xs font-semibold text-zinc-600 mb-1">Advance Amount Paid</label>
              <input 
                type="number" 
                placeholder="0.00"
                value={amountPaid || ""} 
                onChange={(e) => setAmountPaid(Number(e.target.value))} 
                className="h-10 w-full rounded-md border border-zinc-200 px-3 outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-100 text-sm font-medium bg-white"
              />
            </div>

            <div className="flex flex-col justify-center">
              <span className="text-xs font-semibold text-zinc-500">Total Taxable Amount</span>
              <span className="text-lg font-bold text-brand-700 mt-1">{money(totalTaxable)}</span>
            </div>
          </div>

          {totalTaxable > 0 && (
            <div className="p-3 bg-brand-50/50 rounded border border-brand-100 text-xs">
              <span className="font-semibold text-zinc-600 uppercase tracking-wider text-[10px]">Total in Words:</span>
              <p className="font-semibold text-brand-900 mt-0.5">{taxableInWords}</p>
            </div>
          )}

          <div className="flex items-center gap-3">
            <button 
              className="inline-flex h-10 items-center gap-2 rounded-md bg-brand-600 px-4 text-sm font-semibold text-white hover:bg-brand-700 disabled:bg-zinc-300"
              type="button" 
              disabled={isSaving}
              onClick={handleCreateInvoice}
            >
              <Check className="h-4 w-4" />
              {isSaving ? "Saving Invoice" : "Generate GST Invoice"}
            </button>
            <button 
              className="inline-flex h-10 items-center gap-2 rounded-md border border-zinc-200 bg-white px-4 text-sm font-semibold text-zinc-700 hover:bg-zinc-50"
              type="button" 
              onClick={() => setShowCreateInvoice(false)}
            >
              Cancel
            </button>
          </div>
        </section>
      )}

      {/* Main stats layout */}
      <section className="grid gap-3 md:grid-cols-4">
        <Metric label="Invoices" value={String(data?.total_invoices ?? 0)} />
        <Metric label="Billed" value={money(data?.total_billed || 0)} />
        <Metric label="Paid" value={money(data?.total_paid || 0)} />
        <Metric label="Due" value={money(data?.total_due || 0)} />
      </section>

      {/* Invoices Ledger with Accountant summary PDF widget */}
      <section className="grid gap-5 lg:grid-cols-4">
        {/* Invoices List Ledger */}
        <div className="overflow-hidden rounded-lg border border-zinc-200 bg-white shadow-sm lg:col-span-3">
          <div className="flex items-center gap-3 border-b border-zinc-200 px-5 py-4">
            <span className="grid h-9 w-9 place-items-center rounded-md bg-brand-50 text-brand-700">
              <FileText className="h-5 w-5" />
            </span>
            <h2 className="text-lg font-semibold text-zinc-950">Invoice Ledger</h2>
          </div>

          {isLoading ? (
            <div className="p-6 text-sm text-zinc-500">Loading invoices...</div>
          ) : invoices.length === 0 ? (
            <div className="p-6 text-sm text-zinc-500">No invoices generated yet.</div>
          ) : (
            <div className="overflow-x-auto">
              <table className="min-w-full divide-y divide-zinc-200 text-sm">
                <thead className="bg-zinc-50 text-left text-xs font-semibold uppercase text-zinc-500">
                  <tr>
                    <th className="px-4 py-3">Invoice</th>
                    <th className="px-4 py-3">Date</th>
                    <th className="px-4 py-3">Customer</th>
                    <th className="px-4 py-3 text-right">Bill</th>
                    <th className="px-4 py-3 text-right">Paid</th>
                    <th className="px-4 py-3 text-right">Due</th>
                    <th className="px-4 py-3 text-right">PDF</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-zinc-100">
                  {invoices.map((invoice) => (
                    <tr key={invoice.id} className="hover:bg-zinc-50">
                      <td className="px-4 py-3 font-semibold text-zinc-950">#{invoice.invoice_number}</td>
                      <td className="px-4 py-3 text-zinc-600">{dateLabel(invoice.invoice_date)}</td>
                      <td className="px-4 py-3">
                        <div className="font-medium text-zinc-900">{invoice.customer_name}</div>
                        <div className="text-xs text-zinc-500">{invoice.customer_phone || "-"}</div>
                      </td>
                      <td className="px-4 py-3 text-right font-medium">{money(invoice.bill_total)}</td>
                      <td className="px-4 py-3 text-right">{money(invoice.amount_paid)}</td>
                      <td className="px-4 py-3 text-right">{money(invoice.customer_total_due)}</td>
                      <td className="px-4 py-3 text-right">
                        <div className="flex items-center justify-end gap-2">
                          <button 
                            className="inline-flex h-9 items-center gap-2 rounded-md bg-zinc-100 px-3 text-xs font-semibold text-zinc-700 hover:bg-zinc-200 shadow-sm transition" 
                            type="button" 
                            onClick={() => setSelectedInvoiceDetails(invoice)}
                          >
                            <Info className="h-4 w-4 text-zinc-500" />
                            Details
                          </button>
                          <button 
                            className="inline-flex h-9 items-center gap-2 rounded-md bg-zinc-100 px-3 text-xs font-semibold text-zinc-700 hover:bg-zinc-200 disabled:bg-zinc-150 shadow-sm transition" 
                            type="button" 
                            disabled={viewingId === invoice.id} 
                            onClick={() => preview(invoice)}
                          >
                            <Eye className="h-4 w-4 text-zinc-500" />
                            {viewingId === invoice.id ? "Opening" : "View"}
                          </button>
                          <button 
                            className="inline-flex h-9 items-center gap-2 rounded-md bg-brand-600 px-3 text-xs font-semibold text-white hover:bg-brand-700 disabled:bg-zinc-300 shadow-sm transition" 
                            type="button" 
                            disabled={downloadingId === invoice.id} 
                            onClick={() => download(invoice)}
                          >
                            <Download className="h-4 w-4" />
                            {downloadingId === invoice.id ? "Preparing" : "Download"}
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {/* Accountant widget on the right */}
        <div className="space-y-4">
          <div className="rounded-lg border border-zinc-200 bg-white p-5 shadow-sm space-y-4">
            <div className="flex items-center gap-2 border-b border-zinc-100 pb-2">
              <FileSpreadsheet className="h-5 w-5 text-brand-600" />
              <h3 className="font-bold text-zinc-900">Accountant Export</h3>
            </div>
            
            <p className="text-xs text-zinc-500 leading-relaxed">
              Export all invoices, starting sequences, ending counters, and billed aggregates for a specific month as a printable PDF report for your accountant.
            </p>

            <div className="space-y-3">
              <div>
                <label className="block text-[10px] font-bold text-zinc-500 uppercase tracking-wider mb-1">Select Month</label>
                <select 
                  value={accountantMonth} 
                  onChange={(e) => setAccountantMonth(Number(e.target.value))}
                  className="h-9 w-full rounded border border-zinc-200 px-2 bg-white text-xs font-semibold"
                >
                  {Array.from({ length: 12 }, (_, i) => i + 1).map(m => (
                    <option key={m} value={m}>{new Date(2026, m - 1, 1).toLocaleString("en-US", { month: "long" })}</option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-[10px] font-bold text-zinc-500 uppercase tracking-wider mb-1">Select Year</label>
                <select 
                  value={accountantYear} 
                  onChange={(e) => setAccountantYear(Number(e.target.value))}
                  className="h-9 w-full rounded border border-zinc-200 px-2 bg-white text-xs font-semibold"
                >
                  {[2024, 2025, 2026, 2027].map(y => (
                    <option key={y} value={y}>{y}</option>
                  ))}
                </select>
              </div>

              <button
                type="button"
                disabled={isDownloadingSummary}
                onClick={downloadAccountantSummaryReport}
                className="w-full inline-flex h-9 items-center justify-center gap-2 rounded-md bg-brand-600 px-4 text-xs font-bold text-white hover:bg-brand-700 disabled:bg-zinc-300 shadow-sm"
              >
                <Download className="h-4 w-4" />
                {isDownloadingSummary ? "Generating Report" : "Download Summary PDF"}
              </button>
            </div>
          </div>
        </div>
      </section>

      {/* Premium Glassmorphic Invoice Details Modal */}
      {selectedInvoiceDetails && (
        <div className="fixed inset-0 z-50 grid place-items-center bg-zinc-950/60 backdrop-blur-sm px-4">
          <div className="w-full max-w-2xl rounded-xl bg-white p-6 shadow-2xl border border-zinc-100 max-h-[90vh] overflow-y-auto space-y-6">
            <div className="flex items-start justify-between border-b border-zinc-100 pb-3">
              <div>
                <h2 className="text-xl font-bold text-zinc-950 flex items-center gap-2">
                  <FileText className="h-5 w-5 text-brand-600" />
                  Invoice Details: #{selectedInvoiceDetails.invoice_number}
                </h2>
                <p className="text-xs text-zinc-500 mt-1">Date: {dateLabel(selectedInvoiceDetails.invoice_date)} · Status: <span className="font-semibold text-brand-700 uppercase">{selectedInvoiceDetails.status}</span></p>
              </div>
              <button 
                className="grid h-8 w-8 place-items-center rounded-md border border-zinc-200 text-zinc-400 hover:text-zinc-600 hover:bg-zinc-50 transition" 
                type="button" 
                onClick={() => setSelectedInvoiceDetails(null)}
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            {/* Billed To metadata section */}
            <div className="grid gap-4 md:grid-cols-2 bg-zinc-50 p-4 rounded-lg border border-zinc-150 text-sm">
              <div>
                <span className="block text-[10px] font-bold text-zinc-400 uppercase tracking-wider">Client / Customer</span>
                <span className="font-semibold text-zinc-900 block mt-1">{selectedInvoiceDetails.customer_name}</span>
                <span className="text-zinc-600 text-xs">{selectedInvoiceDetails.customer_phone || "No Phone number"}</span>
              </div>
              <div>
                <span className="block text-[10px] font-bold text-zinc-400 uppercase tracking-wider">Payment Method</span>
                <span className="font-semibold text-zinc-900 block mt-1">{selectedInvoiceDetails.payment_method}</span>
              </div>
            </div>

            {/* Chronological Payment Logs History Audit Log */}
            <div className="space-y-3">
              <span className="block text-xs font-bold text-zinc-500 uppercase tracking-wider">Chronological Payment Logs History</span>
              {(!(selectedInvoiceDetails.payment_collections || selectedInvoiceDetails.payments) || (selectedInvoiceDetails.payment_collections || selectedInvoiceDetails.payments || []).length === 0) ? (
                <div className="p-4 rounded-lg bg-zinc-50 text-xs text-zinc-500 text-center font-medium border border-dashed border-zinc-200">
                  No partial payments collected against this invoice. Only initial/advance amount applies.
                </div>
              ) : (
                <div className="overflow-hidden rounded-lg border border-zinc-200">
                  <table className="min-w-full divide-y divide-zinc-200 text-xs">
                    <thead className="bg-zinc-50 text-left font-semibold uppercase text-zinc-500">
                      <tr>
                        <th className="px-4 py-2.5">Allocation Date</th>
                        <th className="px-4 py-2.5">Receipt Mode (Cash/Bank)</th>
                        <th className="px-4 py-2.5 text-right">Amount Paid (Rs.)</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-zinc-100 bg-white">
                      {(selectedInvoiceDetails.payment_collections || selectedInvoiceDetails.payments || []).map((p: any, i: number) => (
                        <tr key={i} className="hover:bg-zinc-50/50">
                          <td className="px-4 py-2.5 text-zinc-600">{dateLabel(p.payment_date)}</td>
                          <td className="px-4 py-2.5 text-zinc-700 font-medium">{p.payment_mode}</td>
                          <td className="px-4 py-2.5 text-right font-semibold text-emerald-700">{money(p.amount_paid)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>

            {/* At the bottom of the invoice view layout: reactive balance dynamic fields */}
            <div className="grid gap-3 md:grid-cols-3 border-t border-zinc-100 pt-4 text-sm">
              <div className="p-3 bg-zinc-50 rounded-lg border border-zinc-150 flex flex-col">
                <span className="text-[10px] font-bold text-zinc-500 uppercase tracking-wider">Total Billed Amount</span>
                <span className="text-base font-bold text-zinc-900 mt-1">{money(selectedInvoiceDetails.bill_total)}</span>
              </div>
              <div className="p-3 bg-emerald-50 rounded-lg border border-emerald-100 flex flex-col">
                <span className="text-[10px] font-bold text-emerald-600 uppercase tracking-wider">Total Payments Received to Date</span>
                <span className="text-base font-bold text-emerald-800 mt-1">
                  Rs. {money(selectedInvoiceDetails.amount_paid)}
                </span>
              </div>
              <div className="p-3 bg-rose-50 rounded-lg border border-rose-100 flex flex-col">
                <span className="text-[10px] font-bold text-rose-600 uppercase tracking-wider">Remaining Balance Unsettled Dues</span>
                <span className="text-base font-bold text-rose-800 mt-1">
                  Rs. {money(Number(selectedInvoiceDetails.bill_total) - Number(selectedInvoiceDetails.amount_paid))}
                </span>
              </div>
            </div>

            <div className="flex items-center justify-end gap-3 pt-3 border-t border-zinc-100">
              <button 
                className="inline-flex h-10 items-center gap-2 rounded-md bg-brand-600 px-4 text-sm font-semibold text-white hover:bg-brand-700 shadow-sm transition"
                type="button"
                onClick={() => {
                  const invoiceUrl = `/api/sales/invoices/${selectedInvoiceDetails.id}/pdf?inline=true`;
                  window.open(invoiceUrl, '_blank');
                  setSelectedInvoiceDetails(null);
                }}
              >
                <Eye className="h-4 w-4" />
                View Invoice
              </button>
              <button 
                className="inline-flex h-10 items-center gap-2 rounded-md border border-zinc-200 bg-white px-4 text-sm font-semibold text-zinc-700 hover:bg-zinc-50 transition"
                type="button" 
                onClick={() => setSelectedInvoiceDetails(null)}
              >
                Close View
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-zinc-200 bg-white p-4 shadow-sm">
      <div className="text-xs font-semibold uppercase text-zinc-500">{label}</div>
      <div className="mt-2 text-xl font-bold text-zinc-950">{value}</div>
    </div>
  );
}
