import { Building2, CreditCard, Mail, Phone, RefreshCw, Save, UserRound, WalletCards, ShieldAlert, Send, CheckCircle2, ExternalLink } from "lucide-react";
import { FormEvent, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import axios from "axios";

import PasswordInput from "../components/PasswordInput";
import PhoneNumberInput from "../components/PhoneNumberInput";
import { isOwnerLevelRole, useAuth } from "../context/AuthContext";
import { getBillingHistory, getBillingStatus, updateUserProfile, changePassword, getFactoryProfile, updateFactoryProfile, connectTelegram, disconnectTelegram, api } from "../lib/api";
import type { BillingHistoryItem, BillingStatus } from "../lib/api";
import { splitE164Phone, validateLocalPhone } from "../lib/phoneCountries";

export default function ProfilePage() {
  const { user, updateUser } = useAuth();
  const navigate = useNavigate();
  const [isEditing, setIsEditing] = useState(false);
  const [toast, setToast] = useState("");
  const [billingStatus, setBillingStatus] = useState<BillingStatus | null>(null);
  const [billingHistory, setBillingHistory] = useState<BillingHistoryItem[]>([]);
  const [isBillingLoading, setIsBillingLoading] = useState(false);
  const [form, setForm] = useState({
    full_name: user?.full_name || user?.username || "",
    email: user?.user_id || "",
    phone_country_code: splitE164Phone(user?.phone_number).country.dialCode,
    phone_number: splitE164Phone(user?.phone_number).localNumber,
    preferred_language: (user?.preferred_language || "hinglish") as "en" | "hi" | "hinglish",
  });

  const [telegramCode, setTelegramCode] = useState("");
  const [isGeneratingCode, setIsGeneratingCode] = useState(false);
  const [isDisconnecting, setIsDisconnecting] = useState(false);

  const [passwordForm, setPasswordForm] = useState({
    current_password: "",
    new_password: "",
    confirm_password: ""
  });
  const [passwordError, setPasswordError] = useState("");
  const [passwordSuccess, setPasswordSuccess] = useState("");
  const [isChangingPassword, setIsChangingPassword] = useState(false);

  async function handlePasswordChange(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPasswordError("");
    setPasswordSuccess("");

    if (!passwordForm.current_password || !passwordForm.new_password || !passwordForm.confirm_password) {
      setPasswordError("All fields are required.");
      return;
    }

    if (passwordForm.new_password !== passwordForm.confirm_password) {
      setPasswordError("New Password and Confirm Password do not match.");
      return;
    }

    if (passwordForm.new_password.length < 8) {
      setPasswordError("Password must be at least 8 characters long.");
      return;
    }

    setIsChangingPassword(true);
    try {
      await changePassword({
        current_password: passwordForm.current_password,
        new_password: passwordForm.new_password,
        confirm_password: passwordForm.confirm_password
      });
      setPasswordSuccess("Password changed successfully.");
      setPasswordForm({
        current_password: "",
        new_password: "",
        confirm_password: ""
      });
    } catch (caught) {
      if (axios.isAxiosError(caught)) {
        setPasswordError(caught.response?.data?.detail || "Unable to change password. Please try again.");
      } else {
        setPasswordError("Unable to change password. Please try again.");
      }
    } finally {
      setIsChangingPassword(false);
    }
  }

  async function handleConnectTelegram() {
    setIsGeneratingCode(true);
    try {
      const response = await connectTelegram();
      setTelegramCode(response.data.code);
      setToast("Verification code generated!");
    } catch {
      setToast("Failed to generate verification code.");
    } finally {
      setIsGeneratingCode(false);
    }
  }

  async function handleDisconnectTelegram() {
    setIsDisconnecting(true);
    try {
      await disconnectTelegram();
      updateUser({ telegram_chat_id: null, telegram_id: null });
      setTelegramCode("");
      setToast("Telegram disconnected.");
    } catch {
      setToast("Failed to disconnect Telegram.");
    } finally {
      setIsDisconnecting(false);
    }
  }

  async function checkTelegramStatus() {
    try {
      const response = await api.get("/users/me");
      updateUser(response.data);
      if (response.data.telegram_chat_id) {
        setTelegramCode("");
        setToast("Telegram connected successfully!");
      } else {
        setToast("Not verified yet. Please message the bot.");
      }
    } catch {
      setToast("Failed to check status.");
    }
  }

  const [factoryProfile, setFactoryProfile] = useState<any>(null);
  const [isFactorySaving, setIsFactorySaving] = useState(false);

  useEffect(() => {
    if (isOwnerLevelRole(user?.role)) {
      void loadFactoryProfile();
    }
  }, [user]);

  async function loadFactoryProfile() {
    try {
      const response = await getFactoryProfile();
      setFactoryProfile(response.data);
    } catch (err) {
      console.error('Failed to load factory profile:', err);
    }
  }

  async function handleFactorySave(event: FormEvent) {
    event.preventDefault();
    if (!factoryProfile) return;
    setIsFactorySaving(true);
    try {
      await updateFactoryProfile({
        factory_name: factoryProfile.factory_name,
        address: factoryProfile.address || '',
        gst_number: factoryProfile.gst_number || '',
        advance_payment_discount_percentage: Number(factoryProfile.advance_payment_discount_percentage || 0),
        digital_signature_url: factoryProfile.digital_signature_url || '',
        bill_of_supply_start_seq: Number(factoryProfile.bill_of_supply_start_seq || 1),
        tax_invoice_start_seq: Number(factoryProfile.tax_invoice_start_seq || 1),
        bill_of_supply_simple_start_seq: Number(factoryProfile.bill_of_supply_simple_start_seq || 1),
      });
      setToast('Factory Settings saved successfully.');
      void loadFactoryProfile();
    } catch {
      setToast('Failed to save Factory Settings.');
    } finally {
      setIsFactorySaving(false);
    }
  }

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

  useEffect(() => {
    void loadBillingPanel();
  }, []);

  async function loadBillingPanel() {
    setIsBillingLoading(true);
    try {
      const [statusResponse, historyResponse] = await Promise.all([
        getBillingStatus(),
        isOwnerLevelRole(user?.role) ? getBillingHistory() : Promise.resolve({ data: [] as BillingHistoryItem[] })
      ]);
      setBillingStatus(statusResponse.data);
      setBillingHistory(historyResponse.data);
      updateUser({
        subscription_status: statusResponse.data.subscription_status,
        active_plan: statusResponse.data.active_plan,
        billing_cycle: statusResponse.data.billing_cycle,
        subscription_start_date: statusResponse.data.subscription_start_date,
        subscription_end_date: statusResponse.data.effective_expires_at || statusResponse.data.plan_expires_at || statusResponse.data.subscription_end_date,
        payment_status: statusResponse.data.payment_status
      });
    } catch {
      setToast("Billing details could not be loaded.");
    } finally {
      setIsBillingLoading(false);
    }
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!validateLocalPhone(form.phone_country_code, form.phone_number)) {
      setToast("Please enter a valid mobile number for the selected country.");
      return;
    }
    const response = await updateUserProfile({
      full_name: form.full_name,
      country_code: form.phone_country_code,
      phone_number: form.phone_number,
      preferred_language: form.preferred_language,
    });
    updateUser({
      full_name: response.data.full_name,
      phone_number: response.data.phone_number,
      user_id: response.data.user_id,
      preferred_language: response.data.preferred_language,
    });
    setIsEditing(false);
    setToast("Profile saved.");
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
            <div className="rounded-md border border-zinc-200 bg-zinc-50 p-4">
              <div className="mb-2 flex items-center gap-2 text-xs font-semibold uppercase text-zinc-500">
                <Phone className="h-4 w-4 text-brand-700" />
                Phone Number
              </div>
              <PhoneNumberInput
                countryCode={form.phone_country_code}
                disabled={!isEditing}
                label=""
                localNumber={form.phone_number}
                onCountryCodeChange={(phone_country_code) => setForm((current) => ({ ...current, phone_country_code }))}
                onLocalNumberChange={(phone_number) => setForm((current) => ({ ...current, phone_number }))}
              />
            </div>
            <div className="rounded-md border border-zinc-200 bg-zinc-50 p-4">
              <div className="flex items-center gap-2 text-xs font-semibold uppercase text-zinc-500">
                <Building2 className="h-4 w-4 text-brand-700" />
                Factory Workspace
              </div>
              <p className="mt-3 text-sm font-semibold text-zinc-950">{user?.factory_name ?? "Not assigned"}</p>
            </div>
            {isOwnerLevelRole(user?.role) ? (
              <label className="block rounded-md border border-zinc-200 bg-zinc-50 p-4">
                <span className="text-xs font-semibold uppercase text-zinc-500">Morning Briefing Language</span>
                <select
                  className="mt-3 h-10 w-full rounded-md border border-zinc-200 bg-white px-3 text-sm font-medium text-zinc-950 disabled:border-transparent disabled:bg-transparent disabled:px-0"
                  disabled={!isEditing}
                  value={form.preferred_language}
                  onChange={(event) => setForm((current) => ({
                    ...current,
                    preferred_language: event.target.value as "en" | "hi" | "hinglish",
                  }))}
                >
                  <option value="en">English</option>
                  <option value="hi">Hindi</option>
                  <option value="hinglish">Hinglish</option>
                </select>
              </label>
            ) : null}
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

      {isOwnerLevelRole(user?.role) && factoryProfile && (
        <section className="rounded-lg border border-zinc-200 bg-white shadow-sm">
          <div className="flex flex-col gap-1.5 border-b border-zinc-200 p-5">
            <h2 className="text-lg font-semibold text-zinc-950">Factory B2B Setup & Store Settings</h2>
            <p className="text-sm text-zinc-500">Configure your disposable factory's commercial settings and private B2B distributor portal parameters.</p>
          </div>
          <form className="p-5 space-y-4" onSubmit={handleFactorySave}>
            <div className="grid gap-4 md:grid-cols-2">
              <label className="block rounded-md border border-zinc-200 bg-zinc-50 p-4">
                <span className="text-xs font-semibold uppercase text-zinc-500">Company Name</span>
                <input
                  type="text"
                  className="mt-3 h-10 w-full rounded-md border border-zinc-200 bg-white px-3 text-sm font-medium text-zinc-950 outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-100"
                  value={factoryProfile.factory_name || ""}
                  onChange={(e) => setFactoryProfile({ ...factoryProfile, factory_name: e.target.value })}
                  required
                />
              </label>
              <label className="block rounded-md border border-zinc-200 bg-zinc-50 p-4">
                <span className="text-xs font-semibold uppercase text-zinc-500">GST Number (GSTIN)</span>
                <input
                  type="text"
                  placeholder="e.g. 07AAAAA1111A1Z1"
                  className="mt-3 h-10 w-full rounded-md border border-zinc-200 bg-white px-3 text-sm font-medium text-zinc-950 outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-100"
                  value={factoryProfile.gst_number || ""}
                  onChange={(e) => setFactoryProfile({ ...factoryProfile, gst_number: e.target.value })}
                />
              </label>
              <label className="block rounded-md border border-zinc-200 bg-zinc-50 p-4">
                <span className="text-xs font-semibold uppercase text-zinc-500">Advance payment discount percentage (%)</span>
                <input
                  type="number"
                  step="0.01"
                  min="0"
                  max="100"
                  className="mt-3 h-10 w-full rounded-md border border-zinc-200 bg-white px-3 text-sm font-medium text-zinc-950 outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-100"
                  value={factoryProfile.advance_payment_discount_percentage ?? 2.00}
                  onChange={(e) => setFactoryProfile({ ...factoryProfile, advance_payment_discount_percentage: e.target.value })}
                  required
                />
              </label>
              <label className="block rounded-md border border-zinc-200 bg-zinc-50 p-4">
                <span className="text-xs font-semibold uppercase text-zinc-500">Factory Address</span>
                <input
                  type="text"
                  className="mt-3 h-10 w-full rounded-md border border-zinc-200 bg-white px-3 text-sm font-medium text-zinc-950 outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-100"
                  value={factoryProfile.address || ""}
                  onChange={(e) => setFactoryProfile({ ...factoryProfile, address: e.target.value })}
                />
              </label>
              <div className="block rounded-md border border-zinc-200 bg-zinc-50 p-4">
                <span className="text-xs font-semibold uppercase text-zinc-500 block mb-2">Digital Signature Image</span>
                <input
                  type="file"
                  accept="image/*"
                  onChange={(e) => {
                    const file = e.target.files?.[0];
                    if (file) {
                      const reader = new FileReader();
                      reader.onloadend = () => {
                        const base64String = reader.result as string;
                        const finalUrl = base64String.length < 500 ? base64String : `/assets/signatures/${file.name}`;
                        setFactoryProfile({ ...factoryProfile, digital_signature_url: finalUrl });
                      };
                      reader.readAsDataURL(file);
                    }
                  }}
                  className="block w-full text-sm text-zinc-500 file:mr-4 file:py-2 file:px-4 file:rounded-md file:border-0 file:text-sm file:font-semibold file:bg-brand-50 file:text-brand-700 hover:file:bg-brand-100"
                />
                {factoryProfile.digital_signature_url && (
                  <div className="mt-3">
                    <span className="text-xs font-semibold text-zinc-400 block mb-1">Preview:</span>
                    <img src={factoryProfile.digital_signature_url} alt="Signature Preview" className="h-12 object-contain bg-white p-1 border rounded" />
                  </div>
                )}
              </div>
            </div>

            {/* ── Invoice Sequence Configuration ───────────────────────────── */}
            <div className="rounded-xl border border-brand-200 bg-brand-50/30 p-4">
              <p className="mb-1 text-xs font-bold uppercase tracking-widest text-brand-700">Invoice Sequence Configuration</p>
              <p className="mb-4 text-xs text-zinc-500">Set the starting number for each invoice type. The system will auto-increment from this value on each new save.</p>
              <div className="grid gap-4 md:grid-cols-3">
                <label className="block rounded-md border border-zinc-200 bg-white p-4">
                  <span className="text-xs font-semibold uppercase text-zinc-500">Starting Invoice Number for Tax Invoice (GST)</span>
                  <input
                    type="number"
                    min="1"
                    step="1"
                    className="mt-3 h-10 w-full rounded-md border border-zinc-200 bg-zinc-50 px-3 text-sm font-medium text-zinc-950 outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-100"
                    value={factoryProfile.tax_invoice_start_seq ?? factoryProfile.next_tax_invoice_number ?? 1}
                    onChange={(e) => setFactoryProfile({ ...factoryProfile, tax_invoice_start_seq: Number(e.target.value) })}
                  />
                </label>
                <label className="block rounded-md border border-zinc-200 bg-white p-4">
                  <span className="text-xs font-semibold uppercase text-zinc-500">Starting Invoice Number for Bill of Supply</span>
                  <input
                    type="number"
                    min="1"
                    step="1"
                    className="mt-3 h-10 w-full rounded-md border border-zinc-200 bg-zinc-50 px-3 text-sm font-medium text-zinc-950 outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-100"
                    value={factoryProfile.bill_of_supply_start_seq ?? factoryProfile.next_bill_of_supply_number ?? 1}
                    onChange={(e) => setFactoryProfile({ ...factoryProfile, bill_of_supply_start_seq: Number(e.target.value) })}
                  />
                </label>
                <label className="block rounded-md border border-zinc-200 bg-white p-4">
                  <span className="text-xs font-semibold uppercase text-zinc-500">Starting Invoice Number for Bill of Supply Simple</span>
                  <input
                    type="number"
                    min="1"
                    step="1"
                    className="mt-3 h-10 w-full rounded-md border border-zinc-200 bg-zinc-50 px-3 text-sm font-medium text-zinc-950 outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-100"
                    value={factoryProfile.bill_of_supply_simple_start_seq ?? factoryProfile.next_bill_of_supply_simple_number ?? 1}
                    onChange={(e) => setFactoryProfile({ ...factoryProfile, bill_of_supply_simple_start_seq: Number(e.target.value) })}
                  />
                </label>
              </div>
            </div>

            <div className="flex justify-end pt-2">
              <button
                type="submit"
                disabled={isFactorySaving}
                className="inline-flex h-10 items-center justify-center rounded-md bg-brand-600 px-4 text-sm font-semibold text-white hover:bg-brand-700 disabled:cursor-not-allowed disabled:bg-zinc-300 transition"
              >
                {isFactorySaving ? "Saving..." : "Save Settings"}
              </button>
            </div>
          </form>
        </section>
      )}

      <section className="rounded-lg border border-zinc-200 bg-white shadow-sm" data-testid="telegram-binding-section">
        <div className="flex flex-col gap-1.5 border-b border-zinc-200 p-5">
          <div className="flex items-center gap-2">
            <Send className="h-5 w-5 text-brand-600" />
            <h2 className="text-lg font-semibold text-zinc-950">Telegram Notifications</h2>
          </div>
          <p className="text-sm text-zinc-500">Connect your personal Telegram account to receive morning briefings and production alerts directly.</p>
        </div>
        <div className="p-5 space-y-4">
          <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <p className="text-sm font-medium text-zinc-700">Status</p>
              <div className="mt-1 flex items-center gap-2">
                {user?.telegram_chat_id ? (
                  <>
                    <span className="inline-flex items-center gap-1 rounded-full border border-emerald-200 bg-emerald-50 px-2.5 py-1 text-xs font-semibold text-emerald-700">
                      <CheckCircle2 className="h-3.5 w-3.5" aria-hidden="true" />
                      Connected
                    </span>
                    <span className="text-xs text-zinc-500">Chat ID: {user.telegram_chat_id}</span>
                  </>
                ) : (
                  <span className="inline-flex items-center gap-1 rounded-full border border-zinc-200 bg-zinc-50 px-2.5 py-1 text-xs font-semibold text-zinc-600">
                    Not Connected
                  </span>
                )}
              </div>
            </div>

            <div className="flex items-center gap-3">
              {user?.telegram_chat_id ? (
                <>
                  <button
                    type="button"
                    onClick={handleConnectTelegram}
                    disabled={isGeneratingCode}
                    className="inline-flex h-9 items-center justify-center rounded-md border border-zinc-200 bg-white px-4 text-sm font-semibold text-zinc-700 hover:bg-zinc-50 transition disabled:opacity-50"
                  >
                    Reconnect
                  </button>
                  <button
                    type="button"
                    onClick={handleDisconnectTelegram}
                    disabled={isDisconnecting}
                    className="inline-flex h-9 items-center justify-center rounded-md bg-red-600 px-4 text-sm font-semibold text-white hover:bg-red-700 transition disabled:opacity-50"
                  >
                    Disconnect
                  </button>
                </>
              ) : (
                <button
                  type="button"
                  onClick={handleConnectTelegram}
                  disabled={isGeneratingCode}
                  className="inline-flex h-9 items-center justify-center rounded-md bg-brand-600 px-4 text-sm font-semibold text-white hover:bg-brand-700 transition disabled:opacity-50"
                >
                  Connect Telegram
                </button>
              )}
            </div>
          </div>

          {telegramCode && (
            <div className="rounded-xl border border-brand-200 bg-brand-50/30 p-4 space-y-3">
              <p className="text-sm font-semibold text-brand-900">One-Time Binding Code</p>
              <div className="flex items-center gap-4">
                <span className="inline-block rounded-md bg-white border border-brand-200 px-4 py-2 text-2xl font-mono font-bold tracking-widest text-brand-700 shadow-sm">
                  {telegramCode}
                </span>
                <button
                  type="button"
                  onClick={checkTelegramStatus}
                  className="inline-flex h-9 items-center justify-center gap-1.5 rounded-md bg-brand-600 px-4 text-sm font-semibold text-white hover:bg-brand-700 transition"
                >
                  <RefreshCw className="h-4 w-4" />
                  Verify Status
                </button>
              </div>
              <p className="text-xs text-zinc-500">
                1. Open your factory's Telegram bot: {user?.telegram_bot_username ? (
                  <a
                    href={`https://t.me/${user.telegram_bot_username}`}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-0.5 text-brand-600 font-semibold hover:underline"
                  >
                    @{user.telegram_bot_username} <ExternalLink className="h-3 w-3" />
                  </a>
                ) : (
                  <span className="font-semibold">your Telegram bot</span>
                )}
                <br />
                2. Send the code <span className="font-semibold">{telegramCode}</span> directly to the bot.
                <br />
                3. Click <strong>Verify Status</strong> above to complete the connection. Code expires in 10 minutes.
              </p>
            </div>
          )}
        </div>
      </section>

      <section className="rounded-lg border border-zinc-200 bg-white shadow-sm" data-testid="change-password-section">
        <div className="flex flex-col gap-1.5 border-b border-zinc-200 p-5">
          <h2 className="text-lg font-semibold text-zinc-950">Change Password</h2>
          <p className="text-sm text-zinc-500">Ensure your account is protected with a highly secure password.</p>
        </div>
        <form className="p-5 space-y-4" onSubmit={handlePasswordChange}>
          <div className="grid gap-4 md:grid-cols-3">
            <PasswordInput
              id="current-password"
              label="Current Password"
              placeholder="Enter current password"
              value={passwordForm.current_password}
              onChange={(value) => setPasswordForm((prev) => ({ ...prev, current_password: value }))}
              data-testid="current-password-input"
              required
            />
            <PasswordInput
              id="new-password"
              label="New Password"
              placeholder="Min 8 characters, 1 letter, 1 number"
              value={passwordForm.new_password}
              onChange={(value) => setPasswordForm((prev) => ({ ...prev, new_password: value }))}
              data-testid="new-password-input"
              required
            />
            <PasswordInput
              id="confirm-new-password"
              label="Confirm New Password"
              placeholder="Repeat your new password"
              value={passwordForm.confirm_password}
              onChange={(value) => setPasswordForm((prev) => ({ ...prev, confirm_password: value }))}
              data-testid="confirm-new-password-input"
              required
            />
          </div>

          {passwordError && (
            <p className="text-sm font-medium text-red-600 rounded-md border border-red-200 bg-red-50 px-3 py-2" data-testid="change-password-error">
              {passwordError}
            </p>
          )}

          {passwordSuccess && (
            <p className="text-sm font-medium text-[#16A34A] rounded-md border border-green-200 bg-green-50 px-3 py-2" data-testid="change-password-success">
              {passwordSuccess}
            </p>
          )}

          <div className="flex justify-end pt-2">
            <button
              className="inline-flex h-10 items-center justify-center rounded-md bg-brand-600 px-4 text-sm font-semibold text-white hover:bg-brand-700 disabled:cursor-not-allowed disabled:bg-zinc-300 transition"
              type="submit"
              disabled={isChangingPassword}
              data-testid="change-password-submit"
            >
              {isChangingPassword ? "Updating..." : "Change Password"}
            </button>
          </div>
        </form>
      </section>

      <section className="rounded-lg border border-zinc-200 bg-white shadow-sm">
        <div className="flex flex-col gap-4 border-b border-zinc-200 p-5 md:flex-row md:items-center md:justify-between">
          <div>
            <div className="flex items-center gap-2">
              <WalletCards className="h-5 w-5 text-brand-700" />
              <h2 className="text-lg font-semibold text-zinc-950">Billing History</h2>
            </div>
            <p className="mt-1 text-sm text-zinc-500">Subscription cycles are stacked consecutively when renewed before expiry.</p>
          </div>
          <div className="flex flex-wrap gap-2">
            <button
              className="inline-flex h-10 items-center justify-center gap-2 rounded-md border border-zinc-200 bg-white px-4 text-sm font-semibold text-zinc-700 hover:bg-zinc-50"
              type="button"
              onClick={loadBillingPanel}
              disabled={isBillingLoading}
            >
              <RefreshCw className={`h-4 w-4 ${isBillingLoading ? "animate-spin" : ""}`} />
              Check Payment
            </button>
            {isOwnerLevelRole(user?.role) ? (
              <button
                className="inline-flex h-10 items-center justify-center gap-2 rounded-md bg-brand-600 px-4 text-sm font-semibold text-white hover:bg-brand-700"
                type="button"
                onClick={() => navigate("/billing")}
              >
                <CreditCard className="h-4 w-4" />
                Renew Plan
              </button>
            ) : null}
          </div>
        </div>

        <div className="grid gap-4 border-b border-zinc-200 p-5 md:grid-cols-4">
          <BillingMetric label="Plan Tier" value={billingStatus?.effective_plan || billingStatus?.active_plan || "Free Trial"} />
          <BillingMetric label="Status" value={billingStatus?.effective_status || billingStatus?.subscription_status || "Unknown"} />
          <BillingMetric label="Days Left" value={String(billingStatus?.days_left ?? "-")} />
          <BillingMetric label="Expires" value={formatDate(billingStatus?.effective_expires_at || billingStatus?.plan_expires_at || billingStatus?.subscription_end_date)} />
        </div>

        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-zinc-200 text-sm">
            <thead className="bg-zinc-50 text-left text-xs font-bold uppercase text-zinc-500">
              <tr>
                <th className="px-5 py-3">Plan Tier</th>
                <th className="px-5 py-3">Cycle</th>
                <th className="px-5 py-3">Activation Start</th>
                <th className="px-5 py-3">Expiry Benchmark</th>
                <th className="px-5 py-3">Status</th>
                <th className="px-5 py-3 text-right">Amount</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-100 bg-white">
              {billingHistory.length === 0 ? (
                <tr>
                  <td className="px-5 py-5 text-zinc-500" colSpan={6}>
                    No paid subscription cycles found.
                  </td>
                </tr>
              ) : (
                billingHistory.map((item) => (
                  <tr key={item.id}>
                    <td className="px-5 py-4 font-semibold text-zinc-950">{item.plan_code}</td>
                    <td className="px-5 py-4 text-zinc-600">{item.billing_cycle}</td>
                    <td className="px-5 py-4 text-zinc-600">{formatDate(item.subscription_start_date)}</td>
                    <td className="px-5 py-4 text-zinc-600">{formatDate(item.subscription_end_date)}</td>
                    <td className="px-5 py-4">
                      <span className="inline-flex rounded-full bg-emerald-50 px-2.5 py-1 text-xs font-bold text-emerald-700">{item.payment_status}</span>
                    </td>
                    <td className="px-5 py-4 text-right font-semibold text-zinc-950">
                      {item.currency} {(item.amount_paise / 100).toLocaleString("en-IN")}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}

function BillingMetric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border border-zinc-200 bg-zinc-50 p-4">
      <p className="text-xs font-bold uppercase text-zinc-500">{label}</p>
      <p className="mt-2 truncate text-sm font-semibold text-zinc-950">{value}</p>
    </div>
  );
}

function formatDate(value?: string | null) {
  if (!value) return "-";
  return new Date(value).toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "numeric" });
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
