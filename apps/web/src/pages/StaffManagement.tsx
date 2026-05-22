import { Check, Search, ShieldCheck, Trash2, UserCog } from "lucide-react";
import axios from "axios";
import { useEffect, useMemo, useState } from "react";

import PhoneNumberInput from "../components/PhoneNumberInput";
import { createStaffMember, deleteStaffMember, getStaffMembers } from "../lib/api";
import type { StaffCreate, StaffMember, StaffRoleCreate } from "../lib/api";
import { validateLocalPhone } from "../lib/phoneCountries";

const initialForm: StaffCreate = {
  full_name: "",
  country_code: "+91",
  phone_number: "",
  password: "",
  role: "supervisor"
};

export default function StaffManagement() {
  const [form, setForm] = useState<StaffCreate>(initialForm);
  const [staff, setStaff] = useState<StaffMember[]>([]);
  const [query, setQuery] = useState("");
  const [error, setError] = useState("");
  const [toast, setToast] = useState("");
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);

  async function loadStaff() {
    setIsLoading(true);
    try {
      const response = await getStaffMembers();
      setStaff(response.data);
    } finally {
      setIsLoading(false);
    }
  }

  useEffect(() => {
    void loadStaff();
  }, []);

  const filteredStaff = useMemo(() => {
    const loweredQuery = query.trim().toLowerCase();
    if (!loweredQuery) return staff;
    return staff.filter((member) =>
      [member.full_name || "", member.phone_number || "", displayRole(member.role)].some((value) =>
        value.toLowerCase().includes(loweredQuery)
      )
    );
  }, [query, staff]);

  async function submit() {
    setError("");
    if (!form.full_name.trim() || !form.phone_number.trim() || !form.password.trim()) {
      setError("Name, phone number, and password are required.");
      return;
    }
    if (!validateLocalPhone(form.country_code || "+91", form.phone_number)) {
      setError("Please enter a valid mobile number for the selected country.");
      return;
    }
    if (form.password.length < 6) {
      setError("Password must be at least 6 characters.");
      return;
    }

    setIsSaving(true);
    try {
      await createStaffMember({
        ...form,
        full_name: form.full_name.trim(),
        country_code: form.country_code,
        phone_number: form.phone_number.trim()
      });
      setToast("Staff account created");
      setForm(initialForm);
      await loadStaff();
    } catch (caught) {
      if (axios.isAxiosError(caught)) {
        setError(caught.response?.data?.detail || "Staff account creation failed.");
      } else {
        setError("Staff account creation failed.");
      }
    } finally {
      setIsSaving(false);
    }
  }

  return (
    <div className="space-y-6">
      {toast ? <Toast message={toast} onClose={() => setToast("")} /> : null}
      <header>
        <h1 className="text-2xl font-semibold text-zinc-950">Staff Management</h1>
        <p className="mt-1 text-sm text-zinc-500">Create Sub-Owner, supervisor, and worker login accounts for this factory.</p>
      </header>

      <div className="grid gap-6 xl:grid-cols-[420px_1fr]">
        <section className="rounded-lg border border-zinc-200 bg-white p-5 shadow-sm">
          <div className="mb-5 flex items-center gap-3">
            <span className="grid h-10 w-10 place-items-center rounded-md bg-brand-50 text-brand-700">
              <UserCog className="h-5 w-5" />
            </span>
            <div>
              <h2 className="text-lg font-semibold text-zinc-950">Create Staff Account</h2>
              <p className="text-sm text-zinc-500">Staff will log in with phone number and password.</p>
            </div>
          </div>

          <div className="grid gap-4">
            <TextField label="Name" value={form.full_name} onChange={(full_name) => setForm({ ...form, full_name })} />
            <PhoneNumberInput
              countryCode={form.country_code || "+91"}
              localNumber={form.phone_number}
              onCountryCodeChange={(country_code) => setForm({ ...form, country_code })}
              onLocalNumberChange={(phone_number) => setForm({ ...form, phone_number })}
            />
            <TextField label="Password" value={form.password} type="password" onChange={(password) => setForm({ ...form, password })} />
            <label className="block text-sm">
              <span className="font-medium text-zinc-700">Role</span>
              <select
                className="mt-1 h-10 w-full rounded-md border border-zinc-200 bg-white px-3 outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-100"
                value={form.role}
                onChange={(event) => setForm({ ...form, role: event.target.value as StaffRoleCreate })}
              >
                <option value="sub_owner">Sub-Owner</option>
                <option value="supervisor">Supervisor</option>
                <option value="worker">Worker</option>
              </select>
            </label>
          </div>

          {error ? <p className="mt-4 rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{error}</p> : null}

          <button className="mt-5 inline-flex h-10 items-center gap-2 rounded-md bg-brand-600 px-4 text-sm font-semibold text-white hover:bg-brand-700 disabled:bg-zinc-300" disabled={isSaving} type="button" onClick={submit}>
            <Check className="h-4 w-4" />
            {isSaving ? "Creating..." : "Create Staff"}
          </button>
        </section>

        <section className="overflow-hidden rounded-lg border border-zinc-200 bg-white shadow-sm">
          <div className="border-b border-zinc-200 p-5">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
              <div>
                <h2 className="text-lg font-semibold text-zinc-950">Current Staff</h2>
                <p className="text-sm text-zinc-500">{staff.length} staff accounts</p>
              </div>
              <div className="relative w-full sm:max-w-xs">
                <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-zinc-400" />
                <input
                  className="h-10 w-full rounded-md border border-zinc-200 pl-9 pr-3 text-sm outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-100"
                  placeholder="Search staff"
                  value={query}
                  onChange={(event) => setQuery(event.target.value)}
                />
              </div>
            </div>
          </div>

          <div className="max-h-[600px] overflow-y-auto">
            {isLoading ? (
              <div className="p-6 text-sm text-zinc-500">Loading staff...</div>
            ) : filteredStaff.length === 0 ? (
              <div className="p-6 text-sm text-zinc-500">No staff accounts found.</div>
            ) : (
              <table className="min-w-full divide-y divide-zinc-200 text-sm">
                <thead className="sticky top-0 z-10 bg-zinc-50 text-left text-xs font-semibold uppercase text-zinc-500">
                  <tr>
                    <th className="px-5 py-3">Name</th>
                    <th className="px-5 py-3">Phone Number</th>
                    <th className="px-5 py-3">Role</th>
                    <th className="px-5 py-3">Factory ID</th>
                    <th className="px-5 py-3 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-zinc-100">
                  {filteredStaff.map((member) => (
                    <tr key={member.id} className="hover:bg-zinc-50">
                      <td className="px-5 py-3 font-medium text-zinc-950">{member.full_name || "-"}</td>
                      <td className="px-5 py-3 text-zinc-700">{member.phone_number || "-"}</td>
                      <td className="px-5 py-3">
                        <span className="inline-flex items-center gap-1 rounded-md bg-brand-50 px-2 py-1 font-semibold text-brand-700">
                          <ShieldCheck className="h-3.5 w-3.5" />
                          {displayRole(member.role)}
                        </span>
                      </td>
                      <td className="px-5 py-3 text-zinc-700">{member.factory_id}</td>
                      <td className="px-5 py-3 text-right">
                        <button className="inline-grid h-9 w-9 place-items-center rounded-md text-zinc-400 hover:bg-red-50 hover:text-red-600" type="button" title="Delete staff" onClick={() => removeStaff(member.id)}>
                          <Trash2 className="h-4 w-4" />
                        </button>
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

  async function removeStaff(id: number) {
    setError("");
    try {
      await deleteStaffMember(id);
      setToast("Staff account deleted");
      await loadStaff();
    } catch (caught) {
      if (axios.isAxiosError(caught)) {
        setError(caught.response?.data?.detail || "Staff account deletion failed.");
      } else {
        setError("Staff account deletion failed.");
      }
    }
  }
}

function displayRole(role: StaffMember["role"]) {
  return role === "Operator" ? "Worker" : role;
}

function TextField({
  inputMode,
  label,
  onChange,
  type = "text",
  value
}: {
  inputMode?: "tel";
  label: string;
  onChange: (value: string) => void;
  type?: string;
  value: string;
}) {
  return (
    <label className="block text-sm">
      <span className="font-medium text-zinc-700">{label}</span>
      <input
        className="mt-1 h-10 w-full rounded-md border border-zinc-200 px-3 outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-100"
        inputMode={inputMode}
        type={type}
        value={value}
        onChange={(event) => onChange(event.target.value)}
      />
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
