import { Download, FileText, RefreshCw } from "lucide-react";
import { useEffect, useState } from "react";

import { downloadInvoicePdf, getInvoiceDocuments } from "../lib/api";
import type { InvoiceDashboardResponse, InvoiceDocumentSummary } from "../lib/api";

function money(value: string | number) {
  return `Rs ${Number(value || 0).toFixed(2)}`;
}

function dateLabel(value: string) {
  if (!value) return "-";
  return new Date(value).toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "numeric" });
}

function apiErrorMessage(error: unknown) {
  const detail = (error as { response?: { data?: { detail?: unknown } } }).response?.data?.detail;
  return typeof detail === "string" ? detail : "Invoice request failed";
}

export default function InvoicesPage() {
  const [data, setData] = useState<InvoiceDashboardResponse | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [downloadingId, setDownloadingId] = useState<number | null>(null);
  const [message, setMessage] = useState("");

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
  }, []);

  async function download(invoice: InvoiceDocumentSummary) {
    setDownloadingId(invoice.id);
    try {
      const response = await downloadInvoicePdf(invoice.id);
      const blob = new Blob([response.data], { type: "application/pdf" });
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `invoice_${invoice.invoice_number}.pdf`;
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

  const invoices = data?.invoices || [];

  return (
    <div className="mx-auto max-w-7xl space-y-5">
      <header className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-zinc-950">Invoices</h1>
          <p className="mt-1 text-sm text-zinc-500">Factory invoice records saved from sales. PDFs are generated only when downloaded.</p>
        </div>
        <button className="inline-flex h-10 items-center gap-2 rounded-md border border-zinc-200 bg-white px-4 text-sm font-semibold text-zinc-700 hover:bg-zinc-50" type="button" onClick={loadInvoices}>
          <RefreshCw className="h-4 w-4" />
          Refresh
        </button>
      </header>

      {message ? <div className="rounded-md border border-zinc-200 bg-white px-4 py-3 text-sm font-semibold text-zinc-700">{message}</div> : null}

      <section className="grid gap-3 md:grid-cols-4">
        <Metric label="Invoices" value={String(data?.total_invoices ?? 0)} />
        <Metric label="Billed" value={money(data?.total_billed || 0)} />
        <Metric label="Paid" value={money(data?.total_paid || 0)} />
        <Metric label="Due" value={money(data?.total_due || 0)} />
      </section>

      <section className="overflow-hidden rounded-lg border border-zinc-200 bg-white shadow-sm">
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
                      <button className="inline-flex h-9 items-center gap-2 rounded-md bg-brand-600 px-3 text-xs font-semibold text-white hover:bg-brand-700 disabled:bg-zinc-300" type="button" disabled={downloadingId === invoice.id} onClick={() => download(invoice)}>
                        <Download className="h-4 w-4" />
                        {downloadingId === invoice.id ? "Preparing" : "Download"}
                      </button>
                    </td>
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

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-zinc-200 bg-white p-4 shadow-sm">
      <div className="text-xs font-semibold uppercase text-zinc-500">{label}</div>
      <div className="mt-2 text-xl font-bold text-zinc-950">{value}</div>
    </div>
  );
}
