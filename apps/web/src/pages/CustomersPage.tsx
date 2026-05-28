import { Check, Edit, FileText, Search, UserRound, Share2, Trash2, X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";

import { createSalesCustomer, searchCustomers, generateCustomerPortalLink, deleteDashboardCustomer, updateSalesCustomer } from "../lib/api";
import type { CustomerCreate, CustomerSearchResult, CustomerUpdate } from "../lib/api";

const initialForm: CustomerCreate = {
  phone_number: "",
  name: "",
  company_name: "",
  place: "",
  gst_number: "",
  previous_due: 0,
  total_due: 0,
  opening_balance: 0,
  legacy_dues: 0
};

export default function CustomersPage() {
  const navigate = useNavigate();
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
      company_name: customer.company_name || "",
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
      await updateSalesCustomer(editingCustomer.id, editForm);
      setToast(`Customer "${editForm.name}" updated successfully.`);
      setEditingCustomer(null);
      await loadCustomers();
    } catch {
      setEditError("Update failed. Phone number might already be in use.");
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
  }, []);

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

    setIsSaving(true);
    try {
      const response = await createSalesCustomer({
        ...form,
        phone_number: form.phone_number.trim(),
        name: form.name.trim(),
        company_name: form.company_name.trim(),
        place: form.place.trim(),
        gst_number: form.gst_number?.trim() || null
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
    <div className="space-y-6">
      {toast ? <Toast message={toast} onClose={() => setToast("")} /> : null}
      <div>
        <h1 className="text-2xl font-semibold text-zinc-950">Customers</h1>
        <p className="mt-1 text-sm text-zinc-500">Create customers before invoice generation.</p>
      </div>

      <div className="grid gap-6 xl:grid-cols-[420px_1fr]">
        <section className="rounded-lg border border-zinc-200 bg-white p-5 shadow-sm">
          <div className="mb-5 flex items-center gap-3">
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

          {error ? <p className="mt-4 rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{error}</p> : null}

          <button className="mt-5 inline-flex h-10 items-center gap-2 rounded-md bg-brand-600 px-4 text-sm font-semibold text-white hover:bg-brand-700 disabled:bg-zinc-300" disabled={isSaving} type="button" onClick={submit}>
            <Check className="h-4 w-4" />
            {isSaving ? "Saving..." : "Save Customer"}
          </button>
        </section>

        <section className="overflow-hidden rounded-lg border border-zinc-200 bg-white shadow-sm">
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

          <div className="max-h-[600px] overflow-y-auto">
            {isLoadingCustomers ? (
              <div className="p-6 text-sm text-zinc-500">Loading customers...</div>
            ) : filteredCustomers.length === 0 ? (
              <div className="p-6 text-sm text-zinc-500">No customers found.</div>
            ) : (
              <table className="min-w-full divide-y divide-zinc-200 text-sm">
                <thead className="sticky top-0 z-10 bg-zinc-50 text-left text-xs font-semibold uppercase text-zinc-500">
                  <tr>
                    <th className="px-5 py-3">Phone Number</th>
                    <th className="px-5 py-3">Customer Name</th>
                    <th className="px-5 py-3">Company</th>
                    <th className="px-5 py-3">Place / City</th>
                    <th className="px-5 py-3">GST Number</th>
                    <th className="px-5 py-3 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-zinc-100">
                  {filteredCustomers.map((customer) => (
                    <tr key={customer.id} className="hover:bg-zinc-50">
                      <td className="px-5 py-3">
                        <span className="rounded-md bg-brand-50 px-2 py-1 font-semibold text-brand-700">
                          {customer.phone_number}
                        </span>
                      </td>
                      <td className="px-5 py-3 font-medium text-zinc-950">{customer.name}</td>
                      <td className="px-5 py-3 text-zinc-700">{customer.company_name || "-"}</td>
                      <td className="px-5 py-3 text-zinc-600">{customer.place}</td>
                      <td className="px-5 py-3 text-zinc-600">{customer.gst_number || "-"}</td>
                      <td className="px-5 py-3">
                        <div className="flex justify-end gap-2">
                          <button
                            onClick={() => handleSharePortal(customer)}
                            className="inline-flex h-8 items-center gap-1 rounded-md border border-zinc-200 px-2 text-xs font-bold text-brand-700 hover:bg-brand-50"
                            type="button"
                          >
                            <Share2 className="h-3.5 w-3.5" />
                            Portal
                          </button>
                          <button
                            onClick={() => navigate("/outstanding")}
                            className="inline-flex h-8 items-center gap-1 rounded-md border border-zinc-200 px-2 text-xs font-semibold text-zinc-700 hover:bg-zinc-50"
                            type="button"
                          >
                            <FileText className="h-3.5 w-3.5" />
                            View Ledger
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
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
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

      {editingCustomer && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm">
          <div className="w-full max-w-md rounded-xl border border-zinc-200 bg-white p-6 shadow-2xl space-y-5 animate-in fade-in zoom-in-95 duration-200 text-left">
            <div className="flex items-center justify-between border-b border-zinc-100 pb-3">
              <div>
                <h3 className="text-lg font-bold text-zinc-950">Edit Customer</h3>
                <p className="text-xs text-zinc-500 mt-0.5">Update customer details</p>
              </div>
              <button
                type="button"
                onClick={() => setEditingCustomer(null)}
                className="grid h-9 w-9 place-items-center rounded-md border border-zinc-200 text-zinc-600 hover:bg-zinc-50"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            <div className="grid gap-4">
              <TextField label="Customer Name" value={editForm.name || ""} onChange={(name) => setEditForm({ ...editForm, name })} />
              <NumberTextField label="Phone Number" value={editForm.phone_number || ""} onChange={(phone_number) => setEditForm({ ...editForm, phone_number })} />
              <TextField label="Company Name" value={editForm.company_name || ""} onChange={(company_name) => setEditForm({ ...editForm, company_name })} />
              <TextField label="Place / City" value={editForm.place || ""} onChange={(place) => setEditForm({ ...editForm, place })} />
              <TextField label="GST Number" value={editForm.gst_number || ""} onChange={(gst_number) => setEditForm({ ...editForm, gst_number })} />
            </div>

            {editError ? <p className="rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{editError}</p> : null}

            <div className="flex justify-end gap-3 pt-2">
              <button
                className="h-10 rounded-md border border-zinc-200 px-4 text-sm font-semibold text-zinc-700 hover:bg-zinc-50"
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

function Toast({ message, onClose }: { message: string; onClose: () => void }) {
  return (
    <button className="fixed right-5 top-20 z-50 rounded-md bg-[#16A34A] px-4 py-3 text-sm font-semibold text-white shadow-lg" type="button" onClick={onClose}>
      {message}
    </button>
  );
}
