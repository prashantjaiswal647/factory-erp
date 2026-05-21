import { Building2, Mail, Phone, Save, UserRound } from "lucide-react";
import { FormEvent, useMemo, useState } from "react";

import { useAuth } from "../context/AuthContext";

export default function ProfilePage() {
  const { user, updateUser } = useAuth();
  const [isEditing, setIsEditing] = useState(false);
  const [toast, setToast] = useState("");
  const [form, setForm] = useState({
    full_name: user?.full_name || user?.username || "",
    email: user?.user_id || "",
    phone_number: user?.phone_number || ""
  });

  const displayName = form.full_name || user?.username || "User";
  const initials = useMemo(() => {
    return (
      displayName
        .split(" ")
        .filter(Boolean)
        .slice(0, 2)
        .map((part) => part[0]?.toUpperCase())
        .join("") || "U"
    );
  }, [displayName]);

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    updateUser({
      full_name: form.full_name,
      phone_number: form.phone_number,
      user_id: form.email
    });
    setIsEditing(false);
    setToast("Profile saved locally. API connection can be added when the backend endpoint is ready.");
  }

  return (
    <div className="space-y-6">
      {toast ? (
        <button
          className="fixed right-5 top-20 z-50 rounded-md bg-[#16A34A] px-4 py-3 text-sm font-semibold text-white shadow-lg"
          type="button"
          onClick={() => setToast("")}
        >
          {toast}
        </button>
      ) : null}

      <header>
        <h1 className="text-2xl font-semibold text-zinc-950">My Profile</h1>
        <p className="mt-1 text-sm text-zinc-500">Manage your account details and factory assignment.</p>
      </header>

      <section className="rounded-lg border border-zinc-200 bg-white shadow-sm">
        <div className="flex flex-col gap-5 border-b border-zinc-200 p-5 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-center gap-4">
            <div className="grid h-16 w-16 place-items-center rounded-full bg-brand-600 text-lg font-bold text-white shadow-sm">
              {initials}
            </div>
            <div>
              <h2 className="text-lg font-semibold text-zinc-950">{displayName}</h2>
              <p className="text-sm text-zinc-500">{user?.role || "Team Member"}</p>
            </div>
          </div>
          <button
            className="inline-flex h-10 items-center justify-center gap-2 rounded-md border border-zinc-200 bg-white px-4 text-sm font-semibold text-zinc-700 hover:bg-zinc-50"
            type="button"
            onClick={() => setIsEditing((current) => !current)}
          >
            <UserRound className="h-4 w-4" />
            {isEditing ? "Cancel Edit" : "Edit Profile"}
          </button>
        </div>

        <form className="p-5" onSubmit={handleSubmit}>
          <div className="grid gap-4 md:grid-cols-2">
            <ProfileField
              icon={UserRound}
              label="Name"
              value={form.full_name}
              placeholder="Enter full name"
              disabled={!isEditing}
              onChange={(value) => setForm((current) => ({ ...current, full_name: value }))}
            />
            <ProfileField
              icon={Mail}
              label="Email"
              value={form.email}
              placeholder="Enter email"
              disabled={!isEditing}
              onChange={(value) => setForm((current) => ({ ...current, email: value }))}
            />
            <ProfileField
              icon={Phone}
              label="Phone Number"
              value={form.phone_number}
              placeholder="Enter phone number"
              disabled={!isEditing}
              onChange={(value) => setForm((current) => ({ ...current, phone_number: value }))}
            />
            <div className="rounded-md border border-zinc-200 bg-zinc-50 p-4">
              <div className="flex items-center gap-2 text-xs font-semibold uppercase text-zinc-500">
                <Building2 className="h-4 w-4 text-brand-700" />
                Factory ID
              </div>
              <p className="mt-3 text-sm font-semibold text-zinc-950">{user?.factory_id ?? "Not assigned"}</p>
            </div>
          </div>

          {isEditing ? (
            <div className="mt-5 flex justify-end">
              <button className="inline-flex h-10 items-center gap-2 rounded-md bg-brand-600 px-4 text-sm font-semibold text-white hover:bg-brand-700" type="submit">
                <Save className="h-4 w-4" />
                Save Changes
              </button>
            </div>
          ) : null}
        </form>
      </section>
    </div>
  );
}

function ProfileField({
  disabled,
  icon: Icon,
  label,
  onChange,
  placeholder,
  value
}: {
  disabled: boolean;
  icon: typeof UserRound;
  label: string;
  onChange: (value: string) => void;
  placeholder: string;
  value: string;
}) {
  return (
    <label className="block rounded-md border border-zinc-200 bg-zinc-50 p-4">
      <span className="flex items-center gap-2 text-xs font-semibold uppercase text-zinc-500">
        <Icon className="h-4 w-4 text-brand-700" />
        {label}
      </span>
      <input
        className="mt-3 h-10 w-full rounded-md border border-zinc-200 bg-white px-3 text-sm font-medium text-zinc-950 outline-none transition disabled:border-transparent disabled:bg-transparent disabled:px-0 focus:border-brand-500 focus:ring-2 focus:ring-brand-100"
        disabled={disabled}
        placeholder={placeholder}
        type="text"
        value={value}
        onChange={(event) => onChange(event.target.value)}
      />
    </label>
  );
}
