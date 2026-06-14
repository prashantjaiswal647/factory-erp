import { Download, FileText, RefreshCw, Plus, Trash2, Calendar, FileSpreadsheet, Check, UserRound, Eye, Info, X, Mail, Send, Printer, Search, Archive } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { deleteInvoice, downloadInvoicePdf, downloadMonthlyInvoices, getInvoiceDeliveryHistory, getInvoiceDocuments, getDashboardCustomers, getAccountantSummary, reprintInvoice, sendInvoiceEmail, sendInvoiceTelegram, api, hardDeleteInvoice } from "../lib/api";
import type { InvoiceDashboardResponse, InvoiceDeliveryHistoryItem, InvoiceDocumentSummary, DashboardCustomer } from "../lib/api";
import { useAuth } from "../context/AuthContext";
import { toNumber } from "../lib/format";

function money(value: string | number) {
  return `Rs ${toNumber(value).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
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
  
  const totalPaise = Math.round(toNumber(num) * 100);
  const rupees = Math.floor(totalPaise / 100);
  const paise = totalPaise % 100;
  
  let word = convert(rupees) + " Rupees";
  if (paise > 0) {
    word += " and " + g(paise) + " Paise";
  }
  return word + " Only";
}

export default function InvoicesPage() {
  const { user } = useAuth();
  const [data, setData] = useState<InvoiceDashboardResponse | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [downloadingId, setDownloadingId] = useState<number | null>(null);
  const [viewingId, setViewingId] = useState<number | null>(null);
  const [selectedInvoiceDetails, setSelectedInvoiceDetails] = useState<InvoiceDocumentSummary | null>(null);
  const [message, setMessage] = useState("");
  const [deliveryHistory, setDeliveryHistory] = useState<InvoiceDeliveryHistoryItem[]>([]);
  const [deliveryId, setDeliveryId] = useState<number | null>(null);
  
  const [searchQuery, setSearchQuery] = useState("");
  const [dateFilter, setDateFilter] = useState("");
  const [paymentFilter, setPaymentFilter] = useState("all");
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
  const [customers, setCustomers] = useState<DashboardCustomer[]>([]);
  const [goodsSuggestions] = useState(["65ml Standard Cup"]);
  const [showSuggestions, setShowSuggestions] = useState(false);

  // Accountant Report state
  const [accountantMonth, setAccountantMonth] = useState(new Date().getMonth() + 1);
  const [accountantYear, setAccountantYear] = useState(new Date().getFullYear());
  const [isDownloadingSummary, setIsDownloadingSummary] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<InvoiceDocumentSummary | null>(null);
  const [deleteConfirmation, setDeleteConfirmation] = useState("");
  const [isDeleting, setIsDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState("");
  const [deleteAction, setDeleteAction] = useState<"reverse" | "archive" | "cancel" | "hard_delete">("reverse");
  const [showAllocations, setShowAllocations] = useState(false);
  const [showBulkDownload, setShowBulkDownload] = useState(false);
  const [hardDeleteReason, setHardDeleteReason] = useState("");
  const [confirmTestCheckbox, setConfirmTestCheckbox] = useState(false);
  const [reversePayments, setReversePayments] = useState(true);
  const [bulkMonth, setBulkMonth] = useState(new Date().getMonth() + 1);
  const [bulkYear, setBulkYear] = useState(new Date().getFullYear());
  const [bulkType, setBulkType] = useState<"all" | "tax_invoice" | "bill_of_supply" | "simple_bill_of_supply">("all");
  const [isBulkDownloading, setIsBulkDownloading] = useState(false);

  async function loadCustomers() {
    try {
      const response = await getDashboardCustomers();
      setCustomers(response.data);
    } catch (error) {
      console.error("Failed to load customers:", error);
    }
  }

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

  useEffect(() => {
    void loadInvoices();
    void loadCustomers();
  }, []);

  async function handleCreateInvoice() {
    setMessage("Invoice creation is available from the Sales page.");
  }

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

  async function loadDeliveryHistory(invoiceId: number) {
    try {
      const response = await getInvoiceDeliveryHistory(invoiceId);
      setDeliveryHistory(response.data);
    } catch {
      setDeliveryHistory([]);
    }
  }

  async function openDetails(invoice: InvoiceDocumentSummary) {
    setSelectedInvoiceDetails(invoice);
    await loadDeliveryHistory(invoice.id);
  }

  async function reprint(invoice: InvoiceDocumentSummary) {
    setDeliveryId(invoice.id);
    try {
      await reprintInvoice(invoice.id);
      await download(invoice);
      setMessage("Reprint PDF prepared.");
      await loadDeliveryHistory(invoice.id);
    } catch (error) {
      setMessage(apiErrorMessage(error));
    } finally {
      setDeliveryId(null);
    }
  }

  async function sendTelegram(invoice: InvoiceDocumentSummary) {
    setDeliveryId(invoice.id);
    try {
      await sendInvoiceTelegram(invoice.id, "owner");
      setMessage("Invoice sent to Owner Telegram.");
      await loadDeliveryHistory(invoice.id);
    } catch (error) {
      setMessage(apiErrorMessage(error));
    } finally {
      setDeliveryId(null);
    }
  }

  async function sendEmail(invoice: InvoiceDocumentSummary) {
    const email = window.prompt("Customer email address", invoice.customer_email || "");
    if (!email) return;
    setDeliveryId(invoice.id);
    try {
      await sendInvoiceEmail(invoice.id, email);
      setMessage("Invoice email sent.");
      await loadDeliveryHistory(invoice.id);
    } catch (error) {
      setMessage(apiErrorMessage(error));
    } finally {
      setDeliveryId(null);
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

  async function confirmDeleteInvoice() {
    if (!deleteTarget) return;
    setDeleteError("");
    if (deleteAction === "hard_delete") {
      if (deleteConfirmation !== deleteTarget.invoice_number) return;
      if (!confirmTestCheckbox) return;
      if (!hardDeleteReason.trim()) return;
      setIsDeleting(true);
      try {
        await hardDeleteInvoice(deleteTarget.id, {
          reason: hardDeleteReason,
          confirm_invoice_number: deleteConfirmation,
          confirm_test_invoice: confirmTestCheckbox,
          reverse_payments: reversePayments,
        });
        setMessage(`Invoice ${deleteTarget.invoice_number} permanently deleted.`);
        setDeleteTarget(null);
        setDeleteConfirmation("");
        setHardDeleteReason("");
        setConfirmTestCheckbox(false);
        setDeleteError("");
        await loadInvoices();
        await loadCustomers();
      } catch (error) {
        setDeleteError(apiErrorMessage(error));
        setMessage(apiErrorMessage(error));
      } finally {
        setIsDeleting(false);
      }
      return;
    }
    const requiredConf = deleteAction === "archive" ? "ARCHIVE INVOICE" : (deleteAction === "cancel" ? "CANCEL INVOICE" : "DELETE INVOICE");
    if (deleteConfirmation !== requiredConf) return;
    setIsDeleting(true);
    try {
      await deleteInvoice(deleteTarget.id, deleteConfirmation, deleteAction);
      setMessage(`Invoice ${deleteTarget.invoice_number} ${deleteAction === "archive" ? "archived" : deleteAction === "cancel" ? "cancelled" : "deleted"}.`);
      setDeleteTarget(null);
      setDeleteConfirmation("");
      setDeleteError("");
      await loadInvoices();
      await loadCustomers();
    } catch (error) {
      setDeleteError(apiErrorMessage(error));
      setMessage(apiErrorMessage(error));
    } finally {
      setIsDeleting(false);
    }
  }

  async function handleBulkDownload() {
    setIsBulkDownloading(true);
    try {
      const response = await downloadMonthlyInvoices(bulkMonth, bulkYear, bulkType);
      const blob = new Blob([response.data], { type: "application/zip" });
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `invoices_${bulkYear}-${String(bulkMonth).padStart(2, "0")}_${bulkType}.zip`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);
      setShowBulkDownload(false);
      setMessage("Monthly invoice ZIP download started.");
    } catch (error) {
      setMessage(apiErrorMessage(error));
    } finally {
      setIsBulkDownloading(false);
    }
  }

  const invoices = data?.invoices || [];
  const filteredInvoices = useMemo(() => invoices.filter((invoice) => {
    const query = searchQuery.trim().toLowerCase();
    const matchesQuery = !query
      || invoice.customer_name.toLowerCase().includes(query)
      || invoice.invoice_number.toLowerCase().includes(query);
    const matchesDate = !dateFilter || invoice.invoice_date.slice(0, 10) === dateFilter;
    const due = toNumber(invoice.customer_total_due);
    const paid = toNumber(invoice.amount_paid);
    const status = due <= 0 ? "paid" : paid > 0 ? "partial" : "unpaid";
    return matchesQuery && matchesDate && (paymentFilter === "all" || paymentFilter === status);
  }), [invoices, searchQuery, dateFilter, paymentFilter]);
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
          <button className="inline-flex h-10 items-center gap-2 rounded-md border border-zinc-200 bg-white px-4 text-sm font-semibold text-zinc-700 hover:bg-zinc-50" type="button" onClick={loadInvoices}>
            <RefreshCw className="h-4 w-4" />
            Refresh
          </button>
          <button className="inline-flex h-10 items-center gap-2 rounded-md bg-brand-600 px-4 text-sm font-semibold text-white hover:bg-brand-700" type="button" onClick={() => setShowBulkDownload(true)}>
            <Download className="h-4 w-4" />
            Monthly Bulk Download
          </button>
        </div>
      </header>

      {message ? <div className="rounded-md border border-zinc-200 bg-brand-50 px-4 py-3 text-sm font-semibold text-brand-900">{message}</div> : null}

      <section className="grid gap-3 rounded-lg border border-zinc-200 bg-white p-4 md:grid-cols-[1fr_180px_180px]">
        <label className="relative">
          <Search className="absolute left-3 top-3 h-4 w-4 text-zinc-400" />
          <input className="h-10 w-full rounded-md border border-zinc-200 pl-9 pr-3 text-sm" value={searchQuery} onChange={(event) => setSearchQuery(event.target.value)} placeholder="Search customer or invoice number" />
        </label>
        <input className="h-10 rounded-md border border-zinc-200 px-3 text-sm" type="date" value={dateFilter} onChange={(event) => setDateFilter(event.target.value)} />
        <select className="h-10 rounded-md border border-zinc-200 px-3 text-sm" value={paymentFilter} onChange={(event) => setPaymentFilter(event.target.value)}>
          <option value="all">All payment statuses</option>
          <option value="unpaid">Unpaid</option>
          <option value="partial">Partial Paid</option>
          <option value="paid">Paid</option>
        </select>
      </section>
      {false && (
        <section className="hidden">
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
          ) : filteredInvoices.length === 0 ? (
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
                  {filteredInvoices.map((invoice) => (
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
                            onClick={() => void openDetails(invoice)}
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
                            data-test-id="download-invoice-button"
                            type="button" 
                            disabled={downloadingId === invoice.id} 
                            onClick={() => download(invoice)}
                          >
                            <Download className="h-4 w-4" />
                            {downloadingId === invoice.id ? "Preparing" : "Download"}
                          </button>
                          <button className="inline-flex h-9 items-center gap-1 rounded-md border px-2 text-xs font-semibold" disabled={deliveryId === invoice.id} onClick={() => void reprint(invoice)}>
                            <Printer className="h-4 w-4" /> Reprint
                          </button>
                          <button className="inline-flex h-9 items-center gap-1 rounded-md border px-2 text-xs font-semibold text-sky-700" disabled={deliveryId === invoice.id} onClick={() => void sendTelegram(invoice)}>
                            <Send className="h-4 w-4" /> Telegram
                          </button>
                          <button className="inline-flex h-9 items-center gap-1 rounded-md border px-2 text-xs font-semibold text-violet-700" disabled={deliveryId === invoice.id} onClick={() => void sendEmail(invoice)}>
                            <Mail className="h-4 w-4" /> Email
                          </button>
                          {user?.role === "Owner" ? (
                            <>
                              <button className="inline-flex h-9 items-center gap-1 rounded-md border border-zinc-200 px-2 text-xs font-semibold text-zinc-700 hover:bg-zinc-50" onClick={() => { setDeleteTarget(invoice); setDeleteConfirmation(""); setDeleteAction("archive"); setShowAllocations(false); setDeleteError(""); }}>
                                <Archive className="h-4 w-4" /> Archive Invoice
                              </button>
                              <button className="inline-flex h-9 items-center gap-1 rounded-md border border-red-200 px-2 text-xs font-semibold text-red-700 hover:bg-red-50" onClick={() => { setDeleteTarget(invoice); setDeleteConfirmation(""); setDeleteAction("hard_delete"); setHardDeleteReason(""); setConfirmTestCheckbox(false); setReversePayments(true); setDeleteError(""); }}>
                                <Trash2 className="h-4 w-4" /> Delete Test Invoice
                              </button>
                            </>
                          ) : null}
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
      {showBulkDownload && (
        <div className="fixed inset-0 z-50 grid place-items-center bg-zinc-950/60 px-4">
          <div className="w-full max-w-md space-y-4 rounded-xl bg-white p-6 shadow-2xl">
            <div className="flex items-center justify-between">
              <h2 className="text-lg font-bold text-zinc-950">Monthly Bulk Download</h2>
              <button type="button" onClick={() => setShowBulkDownload(false)}><X className="h-5 w-5" /></button>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <select className="h-10 rounded-md border px-3 text-sm" value={bulkMonth} onChange={(event) => setBulkMonth(Number(event.target.value))}>
                {Array.from({ length: 12 }, (_, index) => index + 1).map((month) => <option key={month} value={month}>{new Date(2026, month - 1).toLocaleString("en-IN", { month: "long" })}</option>)}
              </select>
              <select className="h-10 rounded-md border px-3 text-sm" value={bulkYear} onChange={(event) => setBulkYear(Number(event.target.value))}>
                {Array.from({ length: 7 }, (_, index) => new Date().getFullYear() - 3 + index).map((year) => <option key={year} value={year}>{year}</option>)}
              </select>
            </div>
            <select className="h-10 w-full rounded-md border px-3 text-sm" value={bulkType} onChange={(event) => setBulkType(event.target.value as typeof bulkType)}>
              <option value="all">All</option>
              <option value="tax_invoice">Tax Invoice</option>
              <option value="bill_of_supply">Bill of Supply</option>
              <option value="simple_bill_of_supply">Simple Bill of Supply</option>
            </select>
            <button type="button" disabled={isBulkDownloading} onClick={() => void handleBulkDownload()} className="h-10 w-full rounded-md bg-brand-600 text-sm font-bold text-white disabled:bg-zinc-300">
              {isBulkDownloading ? "Preparing ZIP..." : "Download ZIP"}
            </button>
          </div>
        </div>
      )}

      {deleteTarget && deleteAction !== "hard_delete" && (
        <div className="fixed inset-0 z-50 grid place-items-center bg-zinc-950/60 px-4 backdrop-blur-sm">
          <div className="w-full max-w-xl space-y-5 rounded-2xl bg-white p-6 shadow-2xl border border-zinc-100 animate-in fade-in duration-200">
            <div>
              <h2 className="text-xl font-bold text-zinc-950 flex items-center gap-2">
                {deleteAction === "archive" ? <Archive className="h-5 w-5 text-zinc-900" /> : <Trash2 className="h-5 w-5 text-red-600" />}
                {toNumber(deleteTarget.customer_total_due) <= 0 && toNumber(deleteTarget.bill_total) > 0 ? "Archive Invoice" : "Delete or Archive Invoice?"}
              </h2>
              <p className="text-xs text-zinc-500 mt-1">Invoice: #{deleteTarget.invoice_number} · Customer: {deleteTarget.customer_name}</p>
            </div>

            {/* Metrics summary */}
            <div className="grid grid-cols-3 gap-3 bg-zinc-50 p-3 rounded-lg border border-zinc-100 text-center text-sm">
              <div>
                <div className="text-[10px] font-bold text-zinc-500 uppercase">Invoice Amount</div>
                <div className="font-semibold text-zinc-800 mt-0.5">{money(deleteTarget.bill_total)}</div>
              </div>
              <div>
                <div className="text-[10px] font-bold text-zinc-500 uppercase">Total Paid</div>
                <div className="font-semibold text-emerald-700 mt-0.5">{money(deleteTarget.amount_paid)}</div>
              </div>
              <div>
                <div className="text-[10px] font-bold text-zinc-500 uppercase">Outstanding</div>
                <div className="font-semibold text-red-700 mt-0.5">{money(deleteTarget.customer_total_due)}</div>
              </div>
            </div>

            {/* Stock Impact info */}
            <div className="rounded-lg bg-blue-50/50 border border-blue-100 p-3 text-xs text-blue-900 flex justify-between">
              <span className="font-medium">Stock Impact:</span>
              <span className="font-semibold">{deleteAction === "reverse" || deleteAction === "cancel" ? "Items will be returned to Stock" : "No Stock changes will be made"}</span>
            </div>

            {/* Choice selection */}
            {toNumber(deleteTarget.customer_total_due) <= 0 && toNumber(deleteTarget.bill_total) > 0 ? (
              <div className="text-sm border border-zinc-100 rounded-lg p-3 bg-zinc-50/80">
                <div className="font-semibold text-zinc-800">Archive Only</div>
                <p className="text-xs text-zinc-600 mt-1">This invoice is fully paid. It cannot be deleted/reversed to preserve accounting records. It will be archived and hidden from active views.</p>
              </div>
            ) : (
              <div className="space-y-2">
                <label className="block text-xs font-bold text-zinc-500 uppercase">Select Action</label>
                <div className="grid grid-cols-3 gap-3">
                  <button
                    type="button"
                    onClick={() => { setDeleteAction("reverse"); setDeleteConfirmation(""); setDeleteError(""); }}
                    className={`flex flex-col text-left p-3 rounded-xl border transition ${
                      deleteAction === "reverse" ? "border-red-600 bg-red-50/20" : "border-zinc-200 bg-white hover:bg-zinc-50"
                    }`}
                  >
                    <span className="text-sm font-bold text-zinc-950">Reverse Invoice</span>
                    <span className="text-[10px] text-zinc-500 mt-1">Return stock, reverse outstanding balance. Only if unpaid.</span>
                  </button>
                  <button
                    type="button"
                    onClick={() => { setDeleteAction("cancel"); setDeleteConfirmation(""); setDeleteError(""); }}
                    className={`flex flex-col text-left p-3 rounded-xl border transition ${
                      deleteAction === "cancel" ? "border-amber-600 bg-amber-50/30" : "border-zinc-200 bg-white hover:bg-zinc-50"
                    }`}
                  >
                    <span className="text-sm font-bold text-zinc-950">Cancel Invoice Number</span>
                    <span className="text-[10px] text-zinc-500 mt-1">Keep the number in history as cancelled and return unpaid stock.</span>
                  </button>
                  <button
                    type="button"
                    onClick={() => { setDeleteAction("archive"); setDeleteConfirmation(""); setDeleteError(""); }}
                    className={`flex flex-col text-left p-3 rounded-xl border transition ${
                      deleteAction === "archive" ? "border-zinc-900 bg-zinc-50" : "border-zinc-200 bg-white hover:bg-zinc-50"
                    }`}
                  >
                    <span className="text-sm font-bold text-zinc-950">Archive Invoice</span>
                    <span className="text-[10px] text-zinc-500 mt-1">Keep payment history, hide from active list, no stock change.</span>
                  </button>
                </div>
              </div>
            )}

            {/* Reversal validation warnings */}
            {deleteAction === "reverse" && toNumber(deleteTarget.amount_paid) > 0 && (
              <div className="space-y-2 rounded-lg bg-red-50 border border-red-200 p-3 text-xs text-red-800">
                <div className="flex items-center gap-1.5 font-bold">
                  <span>⚠️ Payments must be reversed first.</span>
                </div>
                <p>This invoice has received payments. You must delete or reallocate payments first before reversing the invoice.</p>
                <div className="pt-1">
                  <button
                    type="button"
                    className="inline-flex h-8 items-center rounded-md border border-red-300 bg-white px-3 text-xs font-bold text-red-700 hover:bg-red-50"
                    onClick={() => setShowAllocations(!showAllocations)}
                  >
                    {showAllocations ? "Hide Allocations" : "View Allocations"}
                  </button>
                </div>
                {showAllocations && (
                  <div className="mt-2 space-y-1.5 border-t border-red-200 pt-2">
                    {(deleteTarget.payments || []).map((p, idx) => (
                      <div key={idx} className="flex justify-between font-semibold">
                        <span>{dateLabel(p.payment_date)} ({p.payment_mode})</span>
                        <span>{money(p.amount_paid)}</span>
                      </div>
                    ))}
                    {(deleteTarget.payments || []).length === 0 && (
                      <div className="text-zinc-500 italic">No payments logged in this summary.</div>
                    )}
                  </div>
                )}
              </div>
            )}

            {deleteError && (
              <div className="rounded-lg bg-red-50 border border-red-200 p-3 text-xs text-red-800 font-semibold">
                {deleteError}
              </div>
            )}

            <label className="block text-sm font-semibold text-zinc-700">
              Type <span className="font-bold text-zinc-900">{deleteAction === "archive" ? "ARCHIVE INVOICE" : (deleteAction === "cancel" ? "CANCEL INVOICE" : "DELETE INVOICE")}</span> to confirm
              <input autoFocus className="mt-2 h-10 w-full rounded-md border border-zinc-300 px-3 text-sm focus:border-zinc-500 focus:outline-none" value={deleteConfirmation} onChange={(event) => setDeleteConfirmation(event.target.value)} />
            </label>

            <div className="flex justify-end gap-3 pt-2">
              <button type="button" className="h-10 rounded-md border px-4 text-sm font-semibold hover:bg-zinc-50 transition" onClick={() => { setDeleteTarget(null); setDeleteConfirmation(""); setDeleteError(""); }}>Cancel</button>
              <button
                type="button"
                disabled={
                  deleteConfirmation !== (deleteAction === "archive" ? "ARCHIVE INVOICE" : (deleteAction === "cancel" ? "CANCEL INVOICE" : "DELETE INVOICE")) ||
                  isDeleting ||
                  (deleteAction === "reverse" && toNumber(deleteTarget.amount_paid) > 0)
                }
                className={`h-10 rounded-md px-4 text-sm font-bold text-white transition disabled:bg-zinc-200 disabled:text-zinc-400 ${
                  deleteAction === "archive" ? "bg-zinc-900 hover:bg-zinc-800" : "bg-red-600 hover:bg-red-700"
                }`}
                onClick={() => void confirmDeleteInvoice()}
              >
                {isDeleting ? "Processing..." : deleteAction === "archive" ? "Archive Invoice" : "Delete Invoice"}
              </button>
            </div>
          </div>
        </div>
      )}

      {deleteTarget && deleteAction === "hard_delete" && (
        <div className="fixed inset-0 z-50 grid place-items-center bg-zinc-950/60 px-4 backdrop-blur-sm">
          <div className="w-full max-w-xl space-y-5 rounded-2xl bg-white p-6 shadow-2xl border border-zinc-100 animate-in fade-in duration-200">
            <div>
              <h2 className="text-xl font-bold text-red-600 flex items-center gap-2">
                <Trash2 className="h-5 w-5 text-red-600" />
                Permanently Delete Invoice?
              </h2>
              <p className="text-xs text-zinc-500 mt-1">Invoice: #{deleteTarget.invoice_number} · Customer: {deleteTarget.customer_name}</p>
            </div>

            {/* Metrics summary */}
            <div className="grid grid-cols-3 gap-3 bg-zinc-50 p-3 rounded-lg border border-zinc-100 text-center text-sm">
              <div>
                <div className="text-[10px] font-bold text-zinc-500 uppercase">Invoice Amount</div>
                <div className="font-semibold text-zinc-800 mt-0.5">{money(deleteTarget.bill_total)}</div>
              </div>
              <div>
                <div className="text-[10px] font-bold text-zinc-500 uppercase">Total Paid</div>
                <div className="font-semibold text-emerald-700 mt-0.5">{money(deleteTarget.amount_paid)}</div>
              </div>
              <div>
                <div className="text-[10px] font-bold text-zinc-500 uppercase">Outstanding</div>
                <div className="font-semibold text-red-700 mt-0.5">{money(deleteTarget.customer_total_due)}</div>
              </div>
            </div>

            {/* Warning text */}
            <div className="rounded-lg bg-amber-50 border border-amber-200 p-3 text-xs text-amber-900 space-y-1">
              <p className="font-bold">⚠️ Warning</p>
              <p>This invoice may already be part of accounting/payment records. If you delete it, invoice, payment allocation and outstanding history related to this invoice will be removed/reversed. Use this only for test or wrongly generated invoices.</p>
            </div>

            <div className="rounded-lg bg-red-50 border border-red-200 p-3 text-xs text-red-900 space-y-1">
              <p className="font-bold">⚠️ Secondary Warning</p>
              <p>Deleting this invoice will allow this invoice number to be reused. Make sure this invoice was not shared with customer/accountant/GST records.</p>
            </div>

            {/* Form details */}
            <div className="space-y-4 text-sm">
              <div>
                <label className="block text-xs font-semibold text-zinc-600 mb-1">Mandatory Deletion Reason</label>
                <textarea
                  value={hardDeleteReason}
                  onChange={(e) => setHardDeleteReason(e.target.value)}
                  placeholder="Why are you deleting this invoice?"
                  className="w-full rounded-md border border-zinc-300 p-2 text-sm outline-none focus:border-zinc-500"
                  rows={2}
                />
              </div>

              {toNumber(deleteTarget.amount_paid) > 0 && (
                <label className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    checked={reversePayments}
                    onChange={(e) => setReversePayments(e.target.checked)}
                    className="h-4 w-4 rounded border-zinc-300 text-brand-600 focus:ring-brand-500"
                  />
                  <span className="text-xs text-zinc-700">Reverse/delete payment allocations ({money(deleteTarget.amount_paid)} allocated)</span>
                </label>
              )}

              <label className="flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={confirmTestCheckbox}
                  onChange={(e) => setConfirmTestCheckbox(e.target.checked)}
                  className="h-4 w-4 rounded border-zinc-300 text-brand-600 focus:ring-brand-500"
                />
                <span className="text-xs text-zinc-700">I understand this is a test/wrong invoice and want to delete it.</span>
              </label>

              {deleteError && (
                <div className="rounded-lg bg-red-50 border border-red-200 p-3 text-xs text-red-800 font-semibold mb-3">
                  {deleteError}
                </div>
              )}

              <label className="block">
                <span className="block text-xs font-semibold text-zinc-700 mb-1">
                  Type <span className="font-bold text-zinc-900">{deleteTarget.invoice_number}</span> to confirm
                </span>
                <input
                  className="h-10 w-full rounded-md border border-zinc-300 px-3 text-sm focus:border-zinc-500 focus:outline-none"
                  value={deleteConfirmation}
                  onChange={(event) => setDeleteConfirmation(event.target.value)}
                />
              </label>
            </div>

            <div className="flex justify-end gap-3 pt-2">
              <button type="button" className="h-10 rounded-md border px-4 text-sm font-semibold hover:bg-zinc-50 transition" onClick={() => { setDeleteTarget(null); setDeleteConfirmation(""); setDeleteError(""); }}>Cancel</button>
              <button
                type="button"
                disabled={
                  deleteConfirmation !== deleteTarget.invoice_number ||
                  isDeleting ||
                  !confirmTestCheckbox ||
                  !hardDeleteReason.trim()
                }
                className="h-10 rounded-md px-4 text-sm font-bold text-white transition disabled:bg-zinc-200 disabled:text-zinc-400 bg-red-600 hover:bg-red-700"
                onClick={() => void confirmDeleteInvoice()}
              >
                {isDeleting ? "Processing..." : "Delete Invoice Permanently"}
              </button>
            </div>
          </div>
        </div>
      )}

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

            <div className="space-y-3">
              <span className="block text-xs font-bold uppercase tracking-wider text-zinc-500">Download & Delivery History</span>
              {deliveryHistory.length === 0 ? (
                <p className="rounded-lg border border-dashed p-3 text-center text-xs text-zinc-500">No delivery activity recorded yet.</p>
              ) : (
                <div className="divide-y rounded-lg border">
                  {deliveryHistory.map((entry) => (
                    <div key={entry.id} className="flex items-center justify-between gap-3 px-3 py-2 text-xs">
                      <span className="font-semibold">{entry.channel}</span>
                      <span className="text-zinc-500">{entry.destination_masked || "Local PDF"}</span>
                      <span className={entry.status === "FAILED" ? "font-semibold text-red-700" : "font-semibold text-emerald-700"}>{entry.status}</span>
                      <span className="text-zinc-500">{dateLabel(entry.created_at)}</span>
                    </div>
                  ))}
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
                  Rs. {money(toNumber(selectedInvoiceDetails.bill_total) - toNumber(selectedInvoiceDetails.amount_paid))}
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
