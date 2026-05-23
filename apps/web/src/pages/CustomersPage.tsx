import { Check, Edit, FileText, Search, UserRound } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { createSalesCustomer, searchCustomers } from "../lib/api";
import type { CustomerCreate, CustomerSearchResult } from "../lib/api";

const initialForm: CustomerCreate = {
  phone_number: "",
  name: "",
  company_name: "",
  place: "",
  gst_number: "",
  previous_due: 0,
  total_due: 0
};

export default function CustomersPage() {
  const [form, setForm] = useState<CustomerCreate>(initialForm);
  const [toast, setToast] = useState("");
  const [error, setError] = useState("");
  const [isSaving, setIsSaving] = useState(false);
  const [customers, setCustomers] = useState<CustomerSearchResult[]>([]);
  const [listQuery, setListQuery] = useState("");
  const [isLoadingCustomers, setIsLoadingCustomers] = useState(true);

  async function loadCustomers() {
    setIsLoadingCustomers(true);
    try {
      const response = await searchCustomers("");
      setCustomers(response.data);
    } finally {
      setIsLoadingCustomers(false);
    }
  }

  useEffect(() => {
    void loadCustomers();
  }, []);

  const filteredCustomers = useMemo(() => {
    const query = listQuery.trim().toLowerCase();
    if (!query) return customers;
    return customers.filter((customer) =>
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
                          <button className="inline-flex h-8 items-center gap-1 rounded-md border border-zinc-200 px-2 text-xs font-semibold text-zinc-700 hover:bg-zinc-50" type="button">
                            <FileText className="h-3.5 w-3.5" />
                            View Ledger
                          </button>
                          <button className="inline-flex h-8 items-center gap-1 rounded-md border border-zinc-200 px-2 text-xs font-semibold text-zinc-700 hover:bg-zinc-50" type="button">
                            <Edit className="h-3.5 w-3.5" />
                            Edit
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
