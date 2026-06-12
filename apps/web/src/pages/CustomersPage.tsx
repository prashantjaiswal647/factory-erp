import { Check, Edit, FileText, Search, UserRound, Share2, Trash2, WalletCards, X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { createCustomerLedgerAdjustment, createSalesCustomer, searchCustomers, generateCustomerPortalLink, deleteDashboardCustomer, getCustomerLedger, updateSalesCustomer } from "../lib/api";
import type { CustomerCreate, CustomerLedgerEntry, CustomerSearchResult, CustomerUpdate } from "../lib/api";
import { useDataRefresh } from "../context/DataRefreshContext";
import { formatMoney, toNumber } from "../lib/format";

const initialForm: CustomerCreate = {
  phone_number: "",
  name: "",
  company_name: "",
  place: "",
  gst_number: "",
  previous_due: 0,
  total_due: 0,
  opening_balance: 0,
  legacy_dues: 0,
  opening_outstanding: 0,
  opening_outstanding_date: "",
  opening_outstanding_note: "",
  advance_balance: 0,
  advance_balance_date: "",
  advance_balance_note: ""
};

export default function CustomersPage() {
  const { refreshVersion, triggerDataRefresh } = useDataRefresh();
  const [form, setForm] = useState<CustomerCreate>(initialForm);
  const [toast, setToast] = useState("");
  const [error, setError] = useState("");
  const [isSaving, setIsSaving] = useState(false);
  const [customers, setCustomers] = useState<CustomerSearchResult[]>([]);
  const [listQuery, setListQuery] = useState("");
  const [isLoadingCustomers, setIsLoadingCustomers] = useState(true);

  const [sharingCustomer, setSharingCustomer] = useState<CustomerSearchResult | null>(null);
  const [generatedPortalLink, setGeneratedPortalLink] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [isGeneratingLink, setIsGeneratingLink] = useState(false);

  const [editingCustomer, setEditingCustomer] = useState<CustomerSearchResult | null>(null);
  const [editForm, setEditForm] = useState<CustomerUpdate>({});
  const [isUpdating, setIsUpdating] = useState(false);
  const [editError, setEditError] = useState("");
  const [adjustingCustomer, setAdjustingCustomer] = useState<CustomerSearchResult | null>(null);
  const [adjustmentType, setAdjustmentType] = useState<"add_balance" | "reduce_balance">("add_balance");
  const [adjustmentAmount, setAdjustmentAmount] = useState(0);
  const [adjustmentReason, setAdjustmentReason] = useState("");
  const [adjustmentError, setAdjustmentError] = useState("");
  const [isAdjusting, setIsAdjusting] = useState(false);
  const [ledgerCustomer, setLedgerCustomer] = useState<CustomerSearchResult | null>(null);
  const [ledgerEntries, setLedgerEntries] = useState<CustomerLedgerEntry[]>([]);
  const [isLedgerLoading, setIsLedgerLoading] = useState(false);

  async function handleSharePortal(customer: CustomerSearchResult) {
    setSharingCustomer(customer);
    setGeneratedPortalLink(null);
    setCopied(false);
    setIsGeneratingLink(true);
    try {
      const response = await generateCustomerPortalLink(customer.id);
      const storefrontUrl = `${window.location.origin}/storefront/${response.data.portal_access_token}`;
      setGeneratedPortalLink(storefrontUrl);
    } catch (err) {
      setToast("Failed to generate storefront link");
    } finally {
      setIsGeneratingLink(false);
    }
  }

  async function handleDeleteCustomer(customer: CustomerSearchResult) {
    if (!window.confirm(`Are you sure you want to delete customer "${customer.name}"? This will permanently remove their records.`)) {
      return;
    }
    try {
      await deleteDashboardCustomer(customer.id);
      setToast(`Customer "${customer.name}" deleted successfully.`);
      void loadCustomers();
    } catch (err) {
      setToast("Failed to delete customer. They might have active sales or invoices associated.");
    }
  }

  function openEditModal(customer: CustomerSearchResult) {
    setEditingCustomer(customer);
    setEditForm({
      name: customer.name,
      phone_number: customer.phone_number,
      place: customer.place,
      gst_number: customer.gst_number || "",
      company_name: customer.company_name || ""
    });
    setEditError("");
  }

  async function submitEdit() {
    if (!editingCustomer) return;
    if (!editForm.name?.trim() || !editForm.phone_number?.trim()) {
      setEditError("Name and Phone Number are required.");
      return;
    }
    setIsUpdating(true);
    setEditError("");
    try {
      const payload: CustomerUpdate = {
        name: editForm.name,
        phone_number: editForm.phone_number,
        place: editForm.place,
        gst_number: editForm.gst_number,
        company_name: editForm.company_name,
      };
      await updateSalesCustomer(editingCustomer.id, payload);
      setToast(`Customer "${editForm.name}" updated successfully.`);
      setEditingCustomer(null);
      await loadCustomers();
      triggerDataRefresh();
    } catch (caught) {
      const detail = (caught as { response?: { data?: { detail?: unknown } } }).response?.data?.detail;
      setEditError(typeof detail === "string" ? detail : "Customer update failed.");
    } finally {
      setIsUpdating(false);
    }
  }

  async function loadCustomers() {
    setIsLoadingCustomers(true);
    try {
      const response = await searchCustomers("");
      setCustomers(Array.isArray(response.data) ? response.data : []);
    } finally {
      setIsLoadingCustomers(false);
    }
  }

  useEffect(() => {
    void loadCustomers();
  }, [refreshVersion]);

  function openAdjustmentModal(customer: CustomerSearchResult) {
    setAdjustingCustomer(customer);
    setAdjustmentType("add_balance");
    setAdjustmentAmount(0);
    setAdjustmentReason("");
    setAdjustmentError("");
  }

  async function submitAdjustment() {
    if (!adjustingCustomer || adjustmentAmount <= 0 || !adjustmentReason.trim()) {
      setAdjustmentError("Amount and reason are required.");
      return;
    }
    const currentOutstanding = toNumber(adjustingCustomer.current_outstanding);
    if (adjustmentType === "reduce_balance" && adjustmentAmount > currentOutstanding) {
      setAdjustmentError("Reduction cannot exceed current outstanding.");
      return;
    }
    setIsAdjusting(true);
    setAdjustmentError("");
    try {
      const response = await createCustomerLedgerAdjustment(adjustingCustomer.id, {
        adjustment_type: adjustmentType,
        amount: adjustmentAmount,
        reason: adjustmentReason.trim(),
      });
      setToast(
        `Balance updated. Old: ${formatMoney(response.data.previous_outstanding)} | ` +
        `Adjustment: ${adjustmentType === "add_balance" ? "+" : "-"}${formatMoney(response.data.adjustment_amount)} | ` +
        `New: ${formatMoney(response.data.new_outstanding)}`
      );
      setAdjustingCustomer(null);
      await loadCustomers();
      triggerDataRefresh();
    } catch (caught) {
      const detail = (caught as { response?: { data?: { detail?: unknown } } }).response?.data?.detail;
      setAdjustmentError(typeof detail === "string" ? detail : "Balance adjustment failed.");
    } finally {
      setIsAdjusting(false);
    }
  }

  async function openLedger(customer: CustomerSearchResult) {
    setLedgerCustomer(customer);
    setLedgerEntries([]);
    setIsLedgerLoading(true);
    try {
      const response = await getCustomerLedger(customer.id);
      setLedgerEntries(response.data.entries || []);
    } finally {
      setIsLedgerLoading(false);
    }
  }

  const filteredCustomers = useMemo(() => {
    const cleanCustomers = Array.isArray(customers) ? customers : [];
    const query = listQuery.trim().toLowerCase();
    if (!query) return cleanCustomers;
    return cleanCustomers.filter((customer) =>
      [customer.name, customer.company_name || "", customer.phone_number, customer.place].some((value) => value.toLowerCase().includes(query))
    );
  }, [customers, listQuery]);

  async function submit() {
    setError("");
    if (!form.phone_number.trim() || !form.name.trim() || !form.company_name.trim()) {
      setError("Phone Number, Name, and Company Name are required.");
      return;
    }
    if (!form.place.trim()) {
      setError("Place is required.");
      return;
    }
    if ((form.opening_outstanding || 0) < 0) {
      setError("Opening outstanding cannot be negative.");
      return;
    }
    if ((form.advance_balance || 0) < 0) {
      setError("Advance balance cannot be negative.");
      return;
    }
    if ((form.opening_outstanding || 0) > 0 && (form.advance_balance || 0) > 0) {
      setError("A customer cannot have both opening outstanding and advance balance at the same time.");
      return;
    }

    setIsSaving(true);
    try {
      const response = await createSalesCustomer({
        ...form,
        phone_number: form.phone_number.trim(),
        name: form.name.trim(),
        company_name: form.company_name.trim(),
        place: form.place.trim(),
        gst_number: form.gst_number?.trim() || null,
        opening_outstanding_date: form.opening_outstanding_date?.trim()
          ? form.opening_outstanding_date
          : null,
        advance_balance_date: form.advance_balance_date?.trim()
          ? form.advance_balance_date
          : null
      });
      const newCustomer = response.data;
      setToast(`Customer ${newCustomer.name || ""} saved successfully`);
      setForm(initialForm);
      await loadCustomers();
    } catch {
      setError("Customer save failed. Check phone number duplication or backend logs.");
    } finally {
      setIsSaving(false);
    }
  }

  return (
    <div className="w-full max-w-full min-w-0 space-y-6 overflow-x-hidden">
      {toast ? <Toast message={toast} onClose={() => setToast("")} /> : null}
      <div>
        <h1 className="text-2xl font-semibold text-zinc-950">Customers</h1>
        <p className="mt-1 text-sm text-zinc-500">Create customers before invoice generation.</p>
      </div>

      <div className="grid min-w-0 gap-6 xl:grid-cols-[minmax(300px,420px)_minmax(0,1fr)]">
        <section className="min-w-0 space-y-4 rounded-lg border border-zinc-200 bg-white p-5 shadow-sm">
          <div className="mb-1 flex items-center gap-3">
            <span className="grid h-10 w-10 place-items-center rounded-md bg-brand-50 text-brand-700">
              <UserRound className="h-5 w-5" />
            </span>
            <h2 className="text-lg font-semibold text-zinc-950">Add Customer</h2>
          </div>

          <div className="grid gap-4">
            <NumberTextField label="Phone Number" value={form.phone_number} onChange={(phone_number) => setForm({ ...form, phone_number })} />
            <TextField label="Customer Name" value={form.name} onChange={(name) => setForm({ ...form, name })} />
            <TextField label="Company Name" value={form.company_name} selectOnFocus onChange={(company_name) => setForm({ ...form, company_name })} />
            <TextField label="Place / City" value={form.place} onChange={(place) => setForm({ ...form, place })} />
            <TextField label="GST Number" value={form.gst_number || ""} onChange={(gst_number) => setForm({ ...form, gst_number })} />
          </div>

          <div className="border-t border-zinc-100 pt-4 mt-2">
            <h3 className="text-sm font-semibold text-zinc-950 mb-1">Opening Balance / Advance</h3>
            <p className="text-xs text-zinc-500 mb-3">
              Previous due customer onboarding से पहले का बकाया है. Advance वह amount है जो customer ने future order के लिए पहले से दे दिया है.
            </p>
            <div className="grid gap-3">
              <NumberTextField label="Previous Due Amount (₹)" value={form.opening_outstanding?.toString() || "0"} onChange={(v) => setForm({ ...form, opening_outstanding: parseFloat(v) || 0 })} />
              <label className="block text-sm">
                <span className="font-medium text-zinc-700">Previous Due As of Date</span>
                <input type="date" className="mt-1 h-10 w-full rounded-md border border-zinc-200 px-3 outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-100" value={form.opening_outstanding_date || ""} onChange={(e) => setForm({ ...form, opening_outstanding_date: e.target.value })} />
              </label>
              <TextField label="Previous Due Note / Reason" value={form.opening_outstanding_note || ""} onChange={(v) => setForm({ ...form, opening_outstanding_note: v })} />
              
              <div className="border-t border-zinc-100 my-2"></div>
              
              <NumberTextField label="Advance Received Amount (₹)" value={form.advance_balance?.toString() || "0"} onChange={(v) => setForm({ ...form, advance_balance: parseFloat(v) || 0 })} />
              <label className="block text-sm">
                <span className="font-medium text-zinc-700">Advance Received Date</span>
                <input type="date" className="mt-1 h-10 w-full rounded-md border border-zinc-200 px-3 outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-100" value={form.advance_balance_date || ""} onChange={(e) => setForm({ ...form, advance_balance_date: e.target.value })} />
              </label>
              <TextField label="Advance Note / Reason" value={form.advance_balance_note || ""} onChange={(v) => setForm({ ...form, advance_balance_note: v })} />
            </div>
          </div>

          {error ? <p className="mt-4 rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{error}</p> : null}

          <button className="mt-5 inline-flex h-10 w-full items-center justify-center gap-2 rounded-md bg-brand-600 px-4 text-sm font-semibold text-white hover:bg-brand-700 disabled:bg-zinc-300" disabled={isSaving} type="button" onClick={submit}>
            <Check className="h-4 w-4" />
            {isSaving ? "Saving..." : "Save Customer"}
          </button>
        </section>

        <section className="min-w-0 overflow-hidden rounded-lg border border-zinc-200 bg-white shadow-sm">
          <div className="border-b border-zinc-200 p-5">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
              <div>
                <h2 className="text-lg font-semibold text-zinc-950">Customer List</h2>
                <p className="text-sm text-zinc-500">{customers.length} customers added</p>
              </div>
              <div className="relative w-full sm:max-w-xs">
                <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-zinc-400" />
                <input
                  className="h-10 w-full rounded-md border border-zinc-200 pl-9 pr-3 text-sm outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-100"
                  placeholder="Search name, company, or phone"
                  value={listQuery}
                  onChange={(event) => setListQuery(event.target.value)}
                />
              </div>
            </div>
          </div>

          <div className="max-h-[800px] min-w-0 overflow-y-auto overflow-x-hidden">
            {isLoadingCustomers ? (
              <div className="p-6 text-sm text-zinc-500">Loading customers...</div>
            ) : filteredCustomers.length === 0 ? (
              <div className="p-6 text-sm text-zinc-500">No customers found.</div>
            ) : (
              <div className="min-w-0 divide-y divide-zinc-100">
                <div className="sticky top-0 z-10 hidden min-w-0 grid-cols-[minmax(0,1.5fr)_minmax(0,.9fr)_minmax(0,.8fr)_minmax(0,.8fr)_minmax(0,1fr)_auto] gap-3 bg-zinc-50 px-4 py-3 text-xs font-semibold uppercase text-zinc-500 lg:grid">
                  <span>Customer</span>
                  <span>Phone</span>
                  <span>Receivable</span>
                  <span>Advance</span>
                  <span>Net / Status</span>
                  <span className="text-right">Actions</span>
                </div>
                {filteredCustomers.map((customer) => {
                    const outstanding = toNumber(customer.current_outstanding);
                    const advance = toNumber(customer.advance_balance);
                    let netBalanceText = "Settled";
                    if (outstanding > advance) {
                      netBalanceText = `${formatMoney(outstanding - advance)} receivable`;
                    } else if (advance > outstanding) {
                      netBalanceText = `${formatMoney(advance - outstanding)} advance available`;
                    }

                    let statusText = "Normal";
                    let badgeColor = "bg-zinc-50 text-zinc-600 border border-zinc-200";
                    if (outstanding > 0) {
                      statusText = "Due";
                      badgeColor = "bg-amber-50 text-amber-700 border border-amber-200";
                    } else if (advance > 0) {
                      statusText = "Advance";
                      badgeColor = "bg-emerald-50 text-emerald-700 border border-emerald-200";
                    } else {
                      statusText = "Settled";
                    }

                    return (
                      <article key={customer.id} className="min-w-0 p-4 hover:bg-zinc-50">
                        <div className="grid min-w-0 gap-3 lg:grid-cols-[minmax(0,1.5fr)_minmax(0,.9fr)_minmax(0,.8fr)_minmax(0,.8fr)_minmax(0,1fr)_auto] lg:items-center">
                          <div className="min-w-0">
                            <div className="truncate font-medium text-zinc-950" title={customer.name}>{customer.name}</div>
                            <div className="truncate text-xs text-zinc-500" title={customer.company_name || "-"}>{customer.company_name || "-"}</div>
                          </div>
                          <Metric label="Phone" value={customer.phone_number} />
                          <Metric label="Receivable" value={formatMoney(outstanding)} />
                          <Metric label="Advance" value={formatMoney(advance)} />
                          <div className="min-w-0">
                            <span className="text-xs font-medium uppercase text-zinc-400 lg:hidden">Net Balance</span>
                            <div className="break-words text-sm font-semibold text-zinc-800">{netBalanceText}</div>
                            <div className="mt-1 text-[10px] leading-4 text-zinc-500">
                              Old {formatMoney(customer.opening_outstanding_remaining || 0)} · Invoice {formatMoney(customer.invoice_outstanding_remaining || 0)} · Manual {formatMoney(customer.manual_adjustment_remaining || 0)}
                            </div>
                            <span className={`mt-1 inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${badgeColor}`}>
                              {statusText}
                            </span>
                          </div>
                          <div className="flex min-w-0 flex-wrap gap-2 lg:max-w-[230px] lg:justify-end">
                            <button
                              onClick={() => handleSharePortal(customer)}
                              className="inline-flex h-8 items-center gap-1 rounded-md border border-zinc-200 px-2 text-xs font-bold text-brand-700 hover:bg-brand-50"
                              type="button"
                            >
                              <Share2 className="h-3.5 w-3.5" />
                              Portal
                            </button>
                            <button
                              onClick={() => void openLedger(customer)}
                              className="inline-flex h-8 items-center gap-1 rounded-md border border-zinc-200 px-2 text-xs font-semibold text-zinc-700 hover:bg-zinc-50"
                              type="button"
                            >
                              <FileText className="h-3.5 w-3.5" />
                              View Ledger
                            </button>
                            <button
                              onClick={() => openAdjustmentModal(customer)}
                              className="inline-flex h-8 items-center gap-1 rounded-md bg-brand-600 px-2 text-xs font-semibold text-white hover:bg-brand-700"
                              type="button"
                            >
                              <WalletCards className="h-3.5 w-3.5" />
                              Adjust Balance
                            </button>
                            <button
                              onClick={() => openEditModal(customer)}
                              className="inline-flex h-8 items-center gap-1 rounded-md border border-zinc-200 px-2 text-xs font-semibold text-zinc-700 hover:bg-zinc-50"
                              type="button"
                            >
                              <Edit className="h-3.5 w-3.5" />
                              Edit
                            </button>
                            <button
                              onClick={() => handleDeleteCustomer(customer)}
                              className="inline-flex h-8 items-center gap-1 rounded-md border border-red-200 bg-red-50/50 px-2 text-xs font-semibold text-red-600 hover:bg-red-50 hover:border-red-300"
                              type="button"
                            >
                              <Trash2 className="h-3.5 w-3.5" />
                              Delete
                            </button>
                          </div>
                        </div>
                      </article>
                    );
                  })}
              </div>
            )}
          </div>
        </section>
      </div>

      {sharingCustomer && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm">
          <div className="w-full max-w-md rounded-xl border border-zinc-200 bg-white p-6 shadow-2xl space-y-5 animate-in fade-in zoom-in-95 duration-200 text-left">
            <div className="flex items-center justify-between border-b border-zinc-100 pb-3">
              <div>
                <h3 className="text-lg font-bold text-zinc-950">Distributor Storefront</h3>
                <p className="text-xs text-zinc-500 mt-0.5">Private B2B ordering portal for customer</p>
              </div>
              <button 
                type="button" 
                onClick={() => setSharingCustomer(null)}
                className="text-zinc-400 hover:text-zinc-600 font-semibold text-lg p-1"
              >
                ✕
              </button>
            </div>

            <div className="space-y-4">
              <div>
                <p className="text-xs font-semibold text-zinc-500 uppercase tracking-wider">Customer Details</p>
                <div className="mt-2 rounded-lg bg-zinc-50 border border-zinc-100 p-3 space-y-1 text-sm">
                  <p className="font-semibold text-zinc-900">{sharingCustomer.name}</p>
                  <p className="text-zinc-600">{sharingCustomer.company_name || "No Company Specified"}</p>
                  <p className="text-zinc-500 text-xs">{sharingCustomer.place} | {sharingCustomer.phone_number}</p>
                </div>
              </div>

              <div>
                <p className="text-xs font-semibold text-zinc-500 uppercase tracking-wider">Storefront Link</p>
                {isGeneratingLink ? (
                  <div className="mt-2 flex h-11 items-center justify-center rounded-lg border border-dashed border-zinc-200 bg-zinc-50/50 text-xs text-zinc-500">
                    <span className="animate-pulse">Generating secure link...</span>
                  </div>
                ) : generatedPortalLink ? (
                  <div className="mt-2 flex gap-2">
                    <input
                      readOnly
                      type="text"
                      value={generatedPortalLink}
                      className="h-11 flex-1 rounded-lg border border-zinc-200 bg-zinc-50 px-3 text-xs text-zinc-700 font-medium select-all outline-none"
                    />
                    <button
                      type="button"
                      onClick={() => {
                        navigator.clipboard.writeText(generatedPortalLink);
                        setCopied(true);
                        setTimeout(() => setCopied(false), 2000);
                      }}
                      className={`px-4 rounded-lg text-xs font-bold transition-all duration-300 ${
                        copied 
                          ? "bg-emerald-600 text-white" 
                          : "bg-brand-600 hover:bg-brand-700 text-white"
                      }`}
                    >
                      {copied ? "Copied!" : "Copy"}
                    </button>
                  </div>
                ) : (
                  <p className="text-xs text-red-500 mt-2">Failed to load link.</p>
                )}
              </div>

              <div className="bg-emerald-50/80 border border-emerald-100 rounded-lg p-3.5 space-y-1.5 text-xs text-emerald-800">
                <p className="font-bold flex items-center gap-1">
                  <span>✨</span> B2B UPI Terms Enabled
                </p>
                <p className="font-medium text-emerald-700">
                  Customers ordering through this link get access to live factory stock. Under "UPI / QR Advance" payment terms, they receive an instant discount configured inside their profile.
                </p>
              </div>

              {generatedPortalLink && (
                <a
                  href={`https://wa.me/${sharingCustomer.phone_number.replace(/\D/g, "")}?text=${encodeURIComponent(
                    `Hello ${sharingCustomer.name},\n\nHere is your private distributor storefront portal link for placing orders directly from our live stock:\n\n${generatedPortalLink}\n\nChoose 'UPI / QR Advance' at checkout to receive instant discounts on full advance payment!\n\nBest Regards,\nMunshi AI Factory Operations`
                  )}`}
                  target="_blank"
                  rel="noreferrer"
                  className="flex h-11 w-full items-center justify-center gap-2 rounded-lg bg-[#25D366] text-white text-sm font-bold shadow-md hover:bg-[#20ba59] active:scale-[0.98] transition-all"
                >
                  Share on WhatsApp
                </a>
              )}
            </div>
          </div>
        </div>
      )}

      {adjustingCustomer && (
        <div className="fixed inset-0 z-50 grid place-items-center bg-black/60 p-4 backdrop-blur-sm">
          <div className="flex max-h-[90vh] w-[95vw] max-w-3xl flex-col overflow-x-hidden rounded-xl bg-white shadow-2xl">
            <div className="overflow-y-auto overflow-x-hidden p-6 max-h-[75vh]">
            <div className="flex items-start justify-between">
              <div>
                <h3 className="text-lg font-bold text-zinc-950">Adjust Balance</h3>
                <p className="text-sm text-zinc-500">{adjustingCustomer.name}</p>
              </div>
              <button className="grid h-9 w-9 place-items-center rounded-md border border-zinc-200" type="button" onClick={() => setAdjustingCustomer(null)}>
                <X className="h-4 w-4" />
              </button>
            </div>
            <div className="mt-5 grid gap-4">
              <label className="grid gap-1 text-sm font-medium text-zinc-700">
                Action
                <select className="h-10 rounded-md border border-zinc-200 px-3" value={adjustmentType} onChange={(event) => setAdjustmentType(event.target.value as "add_balance" | "reduce_balance")}>
                  <option value="add_balance">Add Balance</option>
                  <option value="reduce_balance">Reduce Balance</option>
                </select>
              </label>
              <label className="grid gap-1 text-sm font-medium text-zinc-700">
                Adjustment Amount
                <input className="h-10 rounded-md border border-zinc-200 px-3" type="number" min="0.01" step="0.01" value={adjustmentAmount || ""} onChange={(event) => setAdjustmentAmount(Number(event.target.value))} />
              </label>
              <label className="grid gap-1 text-sm font-medium text-zinc-700">
                Reason
                <textarea className="min-h-20 rounded-md border border-zinc-200 px-3 py-2" value={adjustmentReason} onChange={(event) => setAdjustmentReason(event.target.value)} />
              </label>
              <div className="rounded-md border border-amber-200 bg-amber-50 p-4 text-sm text-amber-950">
                <p>Current Outstanding: <strong>{formatMoney(adjustingCustomer.current_outstanding || 0)}</strong></p>
                <p>Adjustment Amount: <strong>{adjustmentType === "add_balance" ? "+" : "-"}{formatMoney(adjustmentAmount)}</strong></p>
                <p>New Outstanding: <strong>{formatMoney(Math.max(0, toNumber(adjustingCustomer.current_outstanding) + (adjustmentType === "add_balance" ? adjustmentAmount : -adjustmentAmount)))}</strong></p>
              </div>
              {adjustmentError ? <p className="text-sm text-red-700">{adjustmentError}</p> : null}
            </div>
            <div className="mt-6 flex justify-end gap-3">
              <button className="h-10 rounded-md border border-zinc-200 px-4 text-sm font-semibold" type="button" onClick={() => setAdjustingCustomer(null)}>Cancel</button>
              <button className="h-10 rounded-md bg-brand-600 px-4 text-sm font-semibold text-white disabled:bg-zinc-300" type="button" disabled={isAdjusting || adjustmentAmount <= 0 || !adjustmentReason.trim()} onClick={submitAdjustment}>
                {isAdjusting ? "Updating..." : "Confirm Adjustment"}
              </button>
            </div>
            </div>
          </div>
        </div>
      )}

      {ledgerCustomer && (
        <div className="fixed inset-0 z-50 grid place-items-center bg-black/60 p-4 backdrop-blur-sm">
          <div className="flex max-h-[90vh] w-[95vw] max-w-4xl flex-col overflow-hidden rounded-xl bg-white shadow-2xl">
            <div className="flex items-start justify-between border-b border-zinc-200 p-5">
              <div>
                <h3 className="text-lg font-bold text-zinc-950">Customer Ledger</h3>
                <p className="text-sm text-zinc-500">{ledgerCustomer.name}</p>
              </div>
              <button className="grid h-9 w-9 place-items-center rounded-md border border-zinc-200" type="button" onClick={() => setLedgerCustomer(null)}>
                <X className="h-4 w-4" />
              </button>
            </div>
            <div className="overflow-y-auto overflow-x-hidden p-5">
              {isLedgerLoading ? (
                <p className="text-sm text-zinc-500">Loading ledger...</p>
              ) : ledgerEntries.length === 0 ? (
                <p className="text-sm text-zinc-500">No ledger entries.</p>
              ) : (
                <div className="space-y-3">
                  {ledgerEntries.map((entry, index) => (
                    <div key={`${entry.source}-${entry.date_time}-${index}`} className="grid min-w-0 gap-2 rounded-lg border border-zinc-200 p-4 md:grid-cols-[140px_minmax(0,1fr)_120px_120px]">
                      <div className="text-xs text-zinc-500">{new Date(entry.date_time).toLocaleString("en-IN")}</div>
                      <div className="min-w-0">
                        <div className="font-semibold capitalize text-zinc-900">{entry.type.replace(/_/g, " ")}</div>
                        <div className="break-words text-xs text-zinc-500">{entry.source} · {entry.notes || "No notes"}</div>
                        <div className="text-[10px] text-zinc-400">By {entry.created_by || "System"} · Stock impact: {entry.stock_impact ? "Yes" : "No"}</div>
                      </div>
                      <div className="text-sm">
                        <span className="block text-[10px] uppercase text-zinc-400">{Number(entry.debit) > 0 ? "Debit" : "Credit"}</span>
                        <span className={Number(entry.debit) > 0 ? "font-semibold text-red-700" : "font-semibold text-emerald-700"}>
                          {formatMoney(Number(entry.debit) > 0 ? entry.debit : entry.credit)}
                        </span>
                      </div>
                      <div className="text-sm font-semibold text-zinc-900">
                        <span className="block text-[10px] uppercase text-zinc-400">Running Balance</span>
                        {formatMoney(entry.running_balance)}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {editingCustomer && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm">
          <div className="flex max-h-[90vh] w-[95vw] max-w-3xl flex-col overflow-x-hidden rounded-xl border border-zinc-200 bg-white text-left shadow-2xl animate-in fade-in zoom-in-95 duration-200">
            <div className="flex items-center justify-between border-b border-zinc-100 p-5">
              <div>
                <h3 className="text-lg font-bold text-zinc-950">Edit Customer</h3>
                <p className="text-xs text-zinc-500 mt-0.5">Update customer details</p>
              </div>
              <button
                type="button"
                onClick={() => setEditingCustomer(null)}
                className="grid h-9 w-9 place-items-center rounded-md border border-zinc-200 text-zinc-400 hover:text-zinc-600 hover:bg-zinc-50"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            <div className="max-h-[75vh] flex-1 space-y-4 overflow-y-auto overflow-x-hidden p-5">
              <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
                <TextField label="Customer Name" value={editForm.name || ""} onChange={(name) => setEditForm({ ...editForm, name })} />
                <NumberTextField label="Phone Number" value={editForm.phone_number || ""} onChange={(phone_number) => setEditForm({ ...editForm, phone_number })} />
                <TextField label="Company Name" value={editForm.company_name || ""} onChange={(company_name) => setEditForm({ ...editForm, company_name })} />
                <TextField label="Place / City" value={editForm.place || ""} onChange={(place) => setEditForm({ ...editForm, place })} />
                <div className="md:col-span-2">
                  <TextField label="GST Number" value={editForm.gst_number || ""} onChange={(gst_number) => setEditForm({ ...editForm, gst_number })} />
                </div>
              </div>

              <div className="border-t border-zinc-100 pt-4">
                <h4 className="text-sm font-semibold text-zinc-950">Customer Balance</h4>
                <p className="mt-1 text-xs text-amber-700">Balance fields are read-only. Use Adjust Balance button.</p>
                <div className="mt-3 grid gap-4 md:grid-cols-2">
                  <ReadOnlyMoneyField label="Current Outstanding" value={editingCustomer.current_outstanding} />
                  <ReadOnlyMoneyField label="Advance Available" value={editingCustomer.advance_balance} />
                </div>
                <button className="mt-4 h-10 rounded-md bg-brand-600 px-4 text-sm font-semibold text-white hover:bg-brand-700" type="button" onClick={() => {
                  setEditingCustomer(null);
                  openAdjustmentModal(editingCustomer);
                }}>
                  Adjust Balance
                </button>
              </div>
              
              <div className="hidden">
                <h4 className="text-sm font-semibold text-zinc-950 mb-1">Opening Balance / Advance</h4>
                <p className="text-xs text-zinc-500 mb-3">
                  Opening balance is for onboarding-time balance only. Do not use this for regular payment correction. Previous due customer onboarding से पहले का बकाया है. Advance वह amount है जो customer ने future order के लिए पहले से दे दिया है.
                </p>
                <div className="grid gap-4 md:grid-cols-2">
                  <NumberTextField label="Previous Due Amount (₹)" value={editForm.opening_outstanding?.toString() || "0"} onChange={(v) => setEditForm({ ...editForm, opening_outstanding: parseFloat(v) || 0 })} />
                  <label className="block text-sm">
                    <span className="font-medium text-zinc-700">Previous Due As of Date</span>
                    <input type="date" className="mt-1 h-10 w-full rounded-md border border-zinc-200 px-3 outline-none focus:border-brand-500" value={editForm.opening_outstanding_date || ""} onChange={(e) => setEditForm({ ...editForm, opening_outstanding_date: e.target.value })} />
                  </label>
                  <div className="md:col-span-2">
                    <TextField label="Previous Due Note / Reason" value={editForm.opening_outstanding_note || ""} onChange={(v) => setEditForm({ ...editForm, opening_outstanding_note: v })} />
                  </div>
                  
                  <div className="md:col-span-2 border-t border-zinc-100 my-2"></div>
                  
                  <NumberTextField label="Advance Received Amount (₹)" value={editForm.advance_balance?.toString() || "0"} onChange={(v) => setEditForm({ ...editForm, advance_balance: parseFloat(v) || 0 })} />
                  <label className="block text-sm">
                    <span className="font-medium text-zinc-700">Advance Received Date</span>
                    <input type="date" className="mt-1 h-10 w-full rounded-md border border-zinc-200 px-3 outline-none focus:border-brand-500" value={editForm.advance_balance_date || ""} onChange={(e) => setEditForm({ ...editForm, advance_balance_date: e.target.value })} />
                  </label>
                  <div className="md:col-span-2">
                    <TextField label="Advance Note / Reason" value={editForm.advance_balance_note || ""} onChange={(v) => setEditForm({ ...editForm, advance_balance_note: v })} />
                  </div>
                </div>
              </div>
            </div>

            {editError ? <p className="px-5 py-2 border-t border-red-100 bg-red-50 text-sm text-red-700">{editError}</p> : null}

            <div className="sticky bottom-0 flex flex-wrap justify-end gap-3 rounded-b-xl border-t border-zinc-100 bg-zinc-50 p-5">
              <button
                className="h-10 rounded-md border border-zinc-200 px-4 text-sm font-semibold text-zinc-700 bg-white hover:bg-zinc-50"
                type="button"
                onClick={() => setEditingCustomer(null)}
              >
                Cancel
              </button>
              <button
                className="h-10 rounded-md bg-brand-600 px-4 text-sm font-semibold text-white hover:bg-brand-700 disabled:bg-zinc-300"
                type="button"
                disabled={isUpdating}
                onClick={submitEdit}
              >
                {isUpdating ? "Updating..." : "Save Changes"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function TextField({ label, value, selectOnFocus = false, onChange }: { label: string; value: string; selectOnFocus?: boolean; onChange: (value: string) => void }) {
  return (
    <label className="block text-sm">
      <span className="font-medium text-zinc-700">{label}</span>
      <input className="mt-1 h-10 w-full rounded-md border border-zinc-200 px-3 outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-100" value={value} onFocus={selectOnFocus ? (event) => event.target.select() : undefined} onChange={(event) => onChange(event.target.value)} />
    </label>
  );
}

function NumberTextField({ label, value, onChange }: { label: string; value: string; onChange: (value: string) => void }) {
  return (
    <label className="block text-sm">
      <span className="font-medium text-zinc-700">{label}</span>
      <input className="mt-1 h-10 w-full rounded-md border border-zinc-200 px-3 outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-100" inputMode="numeric" value={value} onFocus={(event) => event.target.select()} onChange={(event) => onChange(event.target.value)} />
    </label>
  );
}
function ReadOnlyMoneyField({ label, value }: { label: string; value?: string | number | null }) {
  return (
    <label className="block text-sm">
      <span className="font-medium text-zinc-700">{label}</span>
      <input className="mt-1 h-10 w-full rounded-md border border-zinc-200 bg-zinc-100 px-3 text-zinc-700" readOnly value={formatMoney(value || 0)} />
    </label>
  );
}
function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0">
      <span className="text-xs font-medium uppercase text-zinc-400 lg:hidden">{label}</span>
      <div className="truncate text-sm text-zinc-700" title={value}>{value}</div>
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

