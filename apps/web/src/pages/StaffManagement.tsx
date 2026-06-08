import React, { useEffect, useMemo, useState } from "react";
import axios from "axios";
import {
  Check,
  Search,
  ShieldCheck,
  Trash2,
  UserCog,
  Edit3,
  Unlock,
  Send,
  Loader2,
  Lock,
  X,
  KeyRound,
  ShieldAlert,
  Bot
} from "lucide-react";

import PasswordInput from "../components/PasswordInput";
import PhoneNumberInput from "../components/PhoneNumberInput";
import {
  getStaffMembers,
  createStaffMember,
  updateStaffMember,
  deleteStaffMember,
  deleteWorker,
  changePassword,
  requestFactoryId,
  verifyFactoryId,
  createStaffOpeningAttendance,
  deleteStaffOpeningAttendance
} from "../lib/api";
import type { StaffMember, OpeningAttendancePayload, OpeningAttendanceResponse } from "../lib/api";
import { useAuth } from "../context/AuthContext";
import { validateLocalPhone } from "../lib/phoneCountries";

export default function StaffManagement() {
  const { user } = useAuth();
  const isPrimaryOwner = user?.role === "Owner";
  const [staff, setStaff] = useState<StaffMember[]>([]);
  const [query, setQuery] = useState("");
  const [error, setError] = useState("");
  const [toast, setToast] = useState("");
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);

  // Staff Creation Form State
  const [createForm, setCreateForm] = useState({
    name: "",
    country_code: "+91",
    phone: "",
    password: "",
    confirm_password: "",
    role: "supervisor" as "sub_owner" | "supervisor" | "worker"
  });

  const [showOpeningAttendance, setShowOpeningAttendance] = useState(false);
  const [openingAttendance, setOpeningAttendance] = useState({
    period_start: "",
    period_end: "",
    present_days: 0,
    half_days: 0,
    absent_days: 0,
    paid_leave_days: 0,
    overtime_hours: 0,
    advance_paid: 0,
    deductions: 0,
    notes: ""
  });

  // Edit Modal State
  const [editModal, setEditModal] = useState<{
    member: StaffMember;
    name: string;
    phone: string;
    role: "sub_owner" | "supervisor" | "worker";
    password?: string;
    confirm_password?: string;
    opening_attendance?: OpeningAttendanceResponse | null;
  } | null>(null);
  const [editError, setEditError] = useState("");
  const [isUpdating, setIsUpdating] = useState(false);

  // Delete Caution Modal State
  const [deleteModal, setDeleteModal] = useState<StaffMember | null>(null);
  const [isDeleting, setIsDeleting] = useState(false);

  // OTP Identity Audit Panel State
  const [showAuditModal, setShowAuditModal] = useState(false);
  const [auditPhone, setAuditPhone] = useState("");
  const [auditOtp, setAuditOtp] = useState("");
  const [auditStep, setAuditStep] = useState<"request" | "verify">("request");
  const [auditLoading, setAuditLoading] = useState(false);
  const [auditError, setAuditError] = useState("");
  const [auditedFactoryId, setAuditedFactoryId] = useState<string | null>(null);

  // Load staff records
  async function loadStaff() {
    setIsLoading(true);
    setError("");
    try {
      const response = await getStaffMembers();
      setStaff(Array.isArray(response.data) ? response.data : []);
    } catch (caught) {
      setError("Staff list load failed.");
    } finally {
      setIsLoading(false);
    }
  }

  async function handleRemoveWorker(member: StaffMember) {
    if (!canManageMember(member)) {
      setToast("You cannot remove this staff member.");
      return;
    }
    if (!member.worker_id) {
      setError("Worker ID not found.");
      return;
    }
    const confirmed = window.confirm(
      "Are you sure you want to remove this worker? This will not delete their production metrics history."
    );
    if (!confirmed) return;

    setError("");
    setToast("");
    try {
      await deleteWorker(member.worker_id);
      setToast("Worker removed successfully.");
      void loadStaff();
    } catch (caught) {
      setError("Failed to remove worker.");
    }
  }

  useEffect(() => {
    void loadStaff();
  }, []);

  // Filter staff by search query
  const filteredStaff = useMemo(() => {
    const cleanStaff = Array.isArray(staff) ? staff : [];
    const loweredQuery = query.trim().toLowerCase();
    if (!loweredQuery) return cleanStaff;
    return cleanStaff.filter((member) =>
      [member.full_name || "", member.phone_number || "", displayRole(member.role)].some((value) =>
        value.toLowerCase().includes(loweredQuery)
      )
    );
  }, [query, staff]);

  function canManageMember(member: StaffMember) {
    if (member.role === "Owner") return false;
    if (user?.role === "Sub-Owner" && member.role === "Sub-Owner") return false;
    return user?.role === "Owner" || user?.role === "Sub-Owner";
  }

  // Handle staff creation
  async function handleCreateSubmit() {
    setError("");
    setToast("");

    if (!createForm.name.trim() || !createForm.phone.trim() || !createForm.password.trim()) {
      setError("Name, Phone, and Password are required fields.");
      return;
    }

    if (!validateLocalPhone(createForm.country_code, createForm.phone)) {
      setError("Please enter a valid mobile number for the selected country.");
      return;
    }

    if (createForm.password.length < 8) {
      setError("Password must be at least 8 characters long.");
      return;
    }

    if (createForm.password !== createForm.confirm_password) {
      setError("Password and Confirm Password do not match.");
      return;
    }

    if (createForm.role === "worker" && showOpeningAttendance) {
      if (!openingAttendance.period_start || !openingAttendance.period_end) {
        setError("Opening attendance period start and end dates are required.");
        return;
      }
      if (new Date(openingAttendance.period_start) > new Date(openingAttendance.period_end)) {
        setError("Opening attendance start date must be before or equal to end date.");
        return;
      }
      if (
        Number(openingAttendance.present_days) < 0 ||
        Number(openingAttendance.half_days) < 0 ||
        Number(openingAttendance.absent_days) < 0 ||
        Number(openingAttendance.paid_leave_days) < 0 ||
        Number(openingAttendance.overtime_hours) < 0 ||
        Number(openingAttendance.advance_paid) < 0 ||
        Number(openingAttendance.deductions) < 0
      ) {
        setError("Opening attendance values cannot be negative.");
        return;
      }
    }

    setIsSaving(true);
    try {
      const payload: any = {
        name: createForm.name.trim(),
        phone: createForm.phone.trim(),
        password: createForm.password,
        confirm_password: createForm.confirm_password,
        role: createForm.role,
        status: "active"
      };

      if (createForm.role === "worker" && showOpeningAttendance) {
        payload.opening_attendance = {
          period_start: openingAttendance.period_start,
          period_end: openingAttendance.period_end,
          present_days: Number(openingAttendance.present_days),
          half_days: Number(openingAttendance.half_days),
          absent_days: Number(openingAttendance.absent_days),
          paid_leave_days: Number(openingAttendance.paid_leave_days),
          overtime_hours: Number(openingAttendance.overtime_hours),
          advance_paid: Number(openingAttendance.advance_paid),
          deductions: Number(openingAttendance.deductions),
          notes: openingAttendance.notes ? openingAttendance.notes.trim() : undefined
        };
      }

      const response = await createStaffMember(payload);
      const newStaff = response.data;
      setStaff((current) => {
        const cleanCurrent = Array.isArray(current) ? current : [];
        if (cleanCurrent.some((item) => item.id === newStaff.id)) {
          return cleanCurrent;
        }
        return [...cleanCurrent, newStaff];
      });

      setToast("Staff account created successfully");
      
      // Flush create form
      setCreateForm({
        name: "",
        country_code: "+91",
        phone: "",
        password: "",
        confirm_password: "",
        role: "supervisor"
      });

      setShowOpeningAttendance(false);
      setOpeningAttendance({
        period_start: "",
        period_end: "",
        present_days: 0,
        half_days: 0,
        absent_days: 0,
        paid_leave_days: 0,
        overtime_hours: 0,
        advance_paid: 0,
        deductions: 0,
        notes: ""
      });

      // Reload list to ensure dynamic fields (like last login time) match backend completely
      await loadStaff();
    } catch (caught) {
      if (axios.isAxiosError(caught)) {
        setError(caught.response?.data?.detail || "Staff creation failed.");
      } else {
        setError("Staff creation failed.");
      }
    } finally {
      setIsSaving(false);
    }
  }

  // Handle staff edit submit
  async function handleEditSubmit() {
    if (!editModal) return;
    setEditError("");
    setIsUpdating(true);

    try {
      const { member, name, phone, role, password, confirm_password } = editModal;

      if (!name.trim() || !phone.trim()) {
        setEditError("Name and Phone fields are required.");
        setIsUpdating(false);
        return;
      }

      // Update basic fields
      await updateStaffMember(member.id, {
        name: name.trim(),
        phone: phone.trim(),
        role: role
      });

      // Reset password if provided
      if (password && password.trim()) {
        if (password.length < 8) {
          setEditError("Password must be at least 8 characters long.");
          setIsUpdating(false);
          return;
        }
        if (password !== confirm_password) {
          setEditError("Password and Confirm Password do not match.");
          setIsUpdating(false);
          return;
        }

        await changePassword({
          new_password: password,
          confirm_password: confirm_password,
          user_id: member.id
        });
      }

      // Save opening attendance if provided
      if (editModal.role === "worker" && editModal.opening_attendance) {
        const oa = editModal.opening_attendance;
        if (oa.period_start && oa.period_end) {
          if (new Date(oa.period_start) > new Date(oa.period_end)) {
            setEditError("Opening attendance start date must be before or equal to end date.");
            setIsUpdating(false);
            return;
          }
          await createStaffOpeningAttendance(member.id, {
            period_start: oa.period_start,
            period_end: oa.period_end,
            present_days: Number(oa.present_days || 0),
            half_days: Number(oa.half_days || 0),
            absent_days: Number(oa.absent_days || 0),
            paid_leave_days: Number(oa.paid_leave_days || 0),
            overtime_hours: Number(oa.overtime_hours || 0),
            advance_paid: Number(oa.advance_paid || 0),
            deductions: Number(oa.deductions || 0),
            notes: oa.notes || undefined
          });
        }
      }

      setToast("Staff account updated successfully");
      setEditModal(null);
      await loadStaff();
    } catch (caught) {
      if (axios.isAxiosError(caught)) {
        setEditError(caught.response?.data?.detail || "Staff update failed.");
      } else {
        setEditError("Staff update failed.");
      }
    } finally {
      setIsUpdating(false);
    }
  }

  // Handle staff deletion
  async function handleDeleteConfirm() {
    if (!deleteModal) return;
    if (!canManageMember(deleteModal)) {
      setToast("You cannot remove this staff member.");
      setDeleteModal(null);
      return;
    }
    setIsDeleting(true);
    try {
      await deleteStaffMember(deleteModal.id);
      setToast("System access revoked for staff member");
      setDeleteModal(null);
      await loadStaff();
    } catch (caught) {
      setToast("Deletion failed. Please try again.");
    } finally {
      setIsDeleting(false);
    }
  }

  async function handleStatusToggle(member: StaffMember) {
    if (!canManageMember(member)) {
      setToast("You cannot change this staff member's status.");
      return;
    }
    setError("");
    try {
      await updateStaffMember(member.id, {
        status: member.is_active === false ? "active" : "inactive"
      });
      setToast(member.is_active === false ? "Staff account activated." : "Staff account deactivated.");
      await loadStaff();
    } catch (caught) {
      if (axios.isAxiosError(caught)) {
        setError(caught.response?.data?.detail || "Status update failed.");
      } else {
        setError("Status update failed.");
      }
    }
  }

  // Mock OTP request
  async function triggerOtpRequest() {
    setAuditError("");
    setAuditLoading(true);
    try {
      await requestFactoryId({ phone_number: auditPhone });
      setAuditStep("verify");
    } catch (caught) {
      if (axios.isAxiosError(caught)) {
        setAuditError(caught.response?.data?.detail || "Request failed. Check phone number.");
      } else {
        setAuditError("OTP request failed.");
      }
    } finally {
      setAuditLoading(false);
    }
  }

  // Mock OTP verification
  async function triggerOtpVerify() {
    setAuditError("");
    setAuditLoading(true);
    try {
      const response = await verifyFactoryId({
        phone_number: auditPhone,
        otp_code: auditOtp
      });
      setAuditedFactoryId(response.data);
    } catch (caught) {
      if (axios.isAxiosError(caught)) {
        setAuditError(caught.response?.data?.detail || "Invalid verification code.");
      } else {
        setAuditError("OTP verification failed.");
      }
    } finally {
      setAuditLoading(false);
    }
  }

  function resetAuditState() {
    setAuditPhone("");
    setAuditOtp("");
    setAuditStep("request");
    setAuditError("");
    setAuditedFactoryId(null);
  }

  return (
    <div className="space-y-6" data-testid="staff-management-page">
      {toast ? (
        <button
          className="fixed right-5 top-20 z-50 rounded-md bg-[#16A34A] px-4 py-3 text-sm font-semibold text-white shadow-lg border border-green-600 transition duration-150 hover:bg-[#15803d]"
          type="button"
          onClick={() => setToast("")}
        >
          {toast}
        </button>
      ) : null}

      <header className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-zinc-950">Staff Management</h1>
          <p className="mt-1 text-sm text-zinc-500">Create, edit, and audit operator or supervisor login accounts for this factory workspace.</p>
        </div>
        
        {/* Auditor floating/dedicated action panel */}
        <button
          onClick={() => {
            resetAuditState();
            setShowAuditModal(true);
          }}
          className="inline-flex h-10 items-center justify-center gap-2 rounded-md border border-[#E5E7EB] bg-white px-4 text-sm font-semibold text-[#6D28D9] hover:bg-[#F3E8FF] transition shadow-sm"
          type="button"
          title="Audit Workspace Identity"
        >
          <KeyRound className="h-4 w-4 text-[#6D28D9]" />
          Audit Workspace Identity
        </button>
      </header>

      <div className="grid gap-6 xl:grid-cols-[420px_1fr]">
        
        {/* Creation panel */}
        <section className="rounded-lg border border-zinc-200 bg-white p-5 shadow-sm h-fit">
          <div className="mb-5 flex items-center gap-3">
            <span className="grid h-10 w-10 place-items-center rounded-md bg-[#F3E8FF] text-[#6D28D9]">
              <UserCog className="h-5 w-5" />
            </span>
            <div>
              <h2 className="text-lg font-semibold text-zinc-950">Add Staff Member</h2>
              <p className="text-sm text-zinc-500">Staff will log in with their phone number.</p>
            </div>
          </div>

          <div className="grid gap-4">
            <label className="block text-sm">
              <span className="font-semibold text-zinc-700">Full Name</span>
              <input
                type="text"
                className="mt-1 h-11 w-full rounded-lg border border-zinc-200 px-3 text-sm outline-none transition focus:border-[#6D28D9] focus:ring-2 focus:ring-[#F3E8FF]"
                placeholder="Enter full name"
                value={createForm.name}
                onChange={(e) => setCreateForm({ ...createForm, name: e.target.value })}
                data-testid="staff-full-name-input"
              />
            </label>

            <PhoneNumberInput
              countryCode={createForm.country_code}
              localNumber={createForm.phone}
              onCountryCodeChange={(code) => setCreateForm({ ...createForm, country_code: code })}
              onLocalNumberChange={(phone) => setCreateForm({ ...createForm, phone: phone })}
              data-testid="staff-phone-input"
            />

            <PasswordInput
              label="Password"
              placeholder="Minimum 8 characters"
              value={createForm.password}
              onChange={(value) => setCreateForm({ ...createForm, password: value })}
              data-testid="staff-password-input"
            />

            <PasswordInput
              label="Confirm Password"
              placeholder="Confirm new password"
              value={createForm.confirm_password}
              onChange={(value) => setCreateForm({ ...createForm, confirm_password: value })}
              data-testid="staff-confirm-password-input"
            />

            <label className="block text-sm">
              <span className="font-semibold text-zinc-700">Role</span>
              <select
                className="mt-1 h-11 w-full rounded-lg border border-zinc-200 bg-white px-3 outline-none transition focus:border-[#6D28D9] focus:ring-2 focus:ring-[#F3E8FF] text-sm"
                value={createForm.role}
                onChange={(e) => setCreateForm({ ...createForm, role: e.target.value as any })}
                data-testid="staff-role-select"
              >
                {isPrimaryOwner ? <option value="sub_owner">Sub Owner</option> : null}
                <option value="supervisor">Supervisor</option>
                <option value="worker">Worker (Operator)</option>
              </select>
              {createForm.role === "sub_owner" ? (
                <p className="mt-2 text-xs text-zinc-500">
                  Owner jaise full access, lekin Owner ko remove ya edit nahi kar sakta.
                </p>
              ) : null}
            </label>

            {createForm.role === "worker" && (
              <div className="mt-4 border-t border-zinc-100 pt-4 space-y-4">
                <label className="flex items-center gap-2 cursor-pointer select-none">
                  <input
                    type="checkbox"
                    checked={showOpeningAttendance}
                    onChange={(e) => setShowOpeningAttendance(e.target.checked)}
                    className="h-4 w-4 rounded border-zinc-300 text-[#6D28D9] focus:ring-[#6D28D9]"
                    data-testid="opening-attendance-toggle"
                  />
                  <span className="text-sm font-semibold text-zinc-700">Add previous attendance details?</span>
                </label>

                {showOpeningAttendance && (
                  <div className="space-y-3 p-3 bg-zinc-50 rounded-lg border border-zinc-100" data-testid="opening-attendance-section">
                    <p className="text-xs text-zinc-500">
                      Enter historical attendance details before onboarding the worker to Munshi AI.
                    </p>
                    <div className="grid grid-cols-2 gap-3">
                      <label className="block text-xs">
                        <span className="font-semibold text-zinc-600">Period Start</span>
                        <input
                          type="date"
                          className="mt-1 h-9 w-full rounded border border-zinc-200 px-2 outline-none text-xs"
                          value={openingAttendance.period_start}
                          onChange={(e) => setOpeningAttendance({ ...openingAttendance, period_start: e.target.value })}
                          data-testid="opening-period-start"
                        />
                      </label>
                      <label className="block text-xs">
                        <span className="font-semibold text-zinc-600">Period End</span>
                        <input
                          type="date"
                          className="mt-1 h-9 w-full rounded border border-zinc-200 px-2 outline-none text-xs"
                          value={openingAttendance.period_end}
                          onChange={(e) => setOpeningAttendance({ ...openingAttendance, period_end: e.target.value })}
                          data-testid="opening-period-end"
                        />
                      </label>
                    </div>
                    <div className="grid grid-cols-3 gap-2">
                      <label className="block text-xs">
                        <span className="font-semibold text-zinc-600">Present</span>
                        <input
                          type="number"
                          step="0.5"
                          className="mt-1 h-9 w-full rounded border border-zinc-200 px-2 outline-none text-xs"
                          value={openingAttendance.present_days || ""}
                          onChange={(e) => setOpeningAttendance({ ...openingAttendance, present_days: Number(e.target.value) })}
                          data-testid="opening-present-days"
                        />
                      </label>
                      <label className="block text-xs">
                        <span className="font-semibold text-zinc-600">Half Days</span>
                        <input
                          type="number"
                          step="0.5"
                          className="mt-1 h-9 w-full rounded border border-zinc-200 px-2 outline-none text-xs"
                          value={openingAttendance.half_days || ""}
                          onChange={(e) => setOpeningAttendance({ ...openingAttendance, half_days: Number(e.target.value) })}
                          data-testid="opening-half-days"
                        />
                      </label>
                      <label className="block text-xs">
                        <span className="font-semibold text-zinc-600">Absent</span>
                        <input
                          type="number"
                          step="0.5"
                          className="mt-1 h-9 w-full rounded border border-zinc-200 px-2 outline-none text-xs"
                          value={openingAttendance.absent_days || ""}
                          onChange={(e) => setOpeningAttendance({ ...openingAttendance, absent_days: Number(e.target.value) })}
                          data-testid="opening-absent-days"
                        />
                      </label>
                    </div>
                    <div className="grid grid-cols-2 gap-3">
                      <label className="block text-xs">
                        <span className="font-semibold text-zinc-600">Advance Paid</span>
                        <input
                          type="number"
                          className="mt-1 h-9 w-full rounded border border-zinc-200 px-2 outline-none text-xs"
                          value={openingAttendance.advance_paid || ""}
                          onChange={(e) => setOpeningAttendance({ ...openingAttendance, advance_paid: Number(e.target.value) })}
                          data-testid="opening-advance-paid"
                        />
                      </label>
                      <label className="block text-xs">
                        <span className="font-semibold text-zinc-600">Deductions</span>
                        <input
                          type="number"
                          className="mt-1 h-9 w-full rounded border border-zinc-200 px-2 outline-none text-xs"
                          value={openingAttendance.deductions || ""}
                          onChange={(e) => setOpeningAttendance({ ...openingAttendance, deductions: Number(e.target.value) })}
                        />
                      </label>
                    </div>
                    <div className="grid grid-cols-2 gap-3">
                      <label className="block text-xs">
                        <span className="font-semibold text-zinc-600">Paid Leave</span>
                        <input
                          type="number"
                          className="mt-1 h-9 w-full rounded border border-zinc-200 px-2 outline-none text-xs"
                          value={openingAttendance.paid_leave_days || ""}
                          onChange={(e) => setOpeningAttendance({ ...openingAttendance, paid_leave_days: Number(e.target.value) })}
                        />
                      </label>
                      <label className="block text-xs">
                        <span className="font-semibold text-zinc-600">Overtime Hours</span>
                        <input
                          type="number"
                          className="mt-1 h-9 w-full rounded border border-zinc-200 px-2 outline-none text-xs"
                          value={openingAttendance.overtime_hours || ""}
                          onChange={(e) => setOpeningAttendance({ ...openingAttendance, overtime_hours: Number(e.target.value) })}
                          data-testid="opening-overtime-hours"
                        />
                      </label>
                    </div>
                    <label className="block text-xs">
                      <span className="font-semibold text-zinc-600">Notes (Optional)</span>
                      <textarea
                        className="mt-1 w-full rounded border border-[#E5E7EB] p-2 outline-none text-xs"
                        rows={2}
                        placeholder="Add some notes..."
                        value={openingAttendance.notes}
                        onChange={(e) => setOpeningAttendance({ ...openingAttendance, notes: e.target.value })}
                      />
                    </label>
                  </div>
                )}
              </div>
            )}
          </div>

          {error ? (
            <p className="mt-4 rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm font-semibold text-red-700">
              {error}
            </p>
          ) : null}

          <button
            className="mt-5 inline-flex h-11 w-full items-center justify-center gap-2 rounded-lg bg-[#6D28D9] px-4 text-sm font-bold text-white hover:bg-[#4C1D95] disabled:cursor-not-allowed disabled:bg-zinc-300 shadow-md transition"
            disabled={isSaving}
            type="button"
            onClick={handleCreateSubmit}
            data-testid="save-staff-button"
          >
            <Check className="h-4 w-4" />
            {isSaving ? "Creating..." : "Create Staff Account"}
          </button>
        </section>

        {/* Visual Rendering Table Matrix */}
        <section className="overflow-hidden rounded-lg border border-zinc-200 bg-white shadow-sm flex flex-col">
          <div className="border-b border-zinc-200 p-5">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
              <div>
                <h2 className="text-lg font-semibold text-zinc-950">Active Staff Registry</h2>
                <p className="text-sm text-zinc-500">{staff.length} staff login profiles verified</p>
              </div>
              <div className="relative w-full sm:max-w-xs">
                <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-zinc-400" />
                <input
                  className="h-10 w-full rounded-md border border-zinc-200 pl-9 pr-3 text-sm outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-100"
                  placeholder="Search by name, phone or role"
                  value={query}
                  onChange={(event) => setQuery(event.target.value)}
                />
              </div>
            </div>
          </div>

          <div className="max-h-[600px] overflow-y-auto w-full overflow-x-auto block">
            {isLoading ? (
              <div className="p-6 text-sm text-zinc-500">Loading staff...</div>
            ) : filteredStaff.length === 0 ? (
              <div className="p-6 text-sm text-zinc-500">No staff accounts registered.</div>
            ) : (
              <table className="min-w-full divide-y divide-zinc-200 text-sm" data-testid="staff-table">
                <thead className="sticky top-0 z-10 bg-zinc-50 text-left text-xs font-semibold uppercase text-zinc-500">
                  <tr>
                    <th className="px-5 py-3">Staff Name</th>
                    <th className="px-5 py-3">Phone Number</th>
                    <th className="px-5 py-3">Role</th>
                    <th className="px-5 py-3">Last Login</th>
                    <th className="px-5 py-3 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-zinc-100 bg-white">
                  {filteredStaff.map((member) => (
                    <tr key={member.id} className="hover:bg-zinc-50 transition">
                      <td className="px-5 py-4 font-semibold text-zinc-950">
                        <div>{member.full_name || "-"}</div>
                        {member.opening_attendance && (
                          <div 
                            className="mt-1 text-xs font-normal text-zinc-500" 
                            data-testid="staff-opening-attendance-summary"
                          >
                            Prev Att: {member.opening_attendance.present_days}P / {member.opening_attendance.half_days}H ({member.opening_attendance.period_start} to {member.opening_attendance.period_end})
                          </div>
                        )}
                      </td>
                      <td className="px-5 py-4 text-zinc-700">{member.phone_number || "-"}</td>
                      <td className="px-5 py-4">
                        <span className="inline-flex items-center gap-1 rounded-md bg-[#F3E8FF] px-2.5 py-1 text-xs font-bold text-[#6D28D9]">
                          <ShieldCheck className="h-3.5 w-3.5" />
                          {displayRole(member.role)}
                        </span>
                      </td>
                      <td className="px-5 py-4 text-zinc-500">
                        {member.last_login_at
                          ? new Date(member.last_login_at).toLocaleString("en-IN", {
                              day: "2-digit",
                              month: "short",
                              hour: "2-digit",
                              minute: "2-digit"
                            })
                          : "Never"}
                      </td>
                      <td className="px-5 py-4 text-right">
                        <div className="inline-flex gap-2">
                          {canManageMember(member) ? <button
                            className="inline-grid h-9 w-9 place-items-center rounded-md border border-zinc-200 text-zinc-600 hover:bg-[#F3E8FF] hover:text-[#6D28D9] transition"
                            type="button"
                            title="Edit Staff Member"
                            onClick={() =>
                              setEditModal({
                                member,
                                name: member.full_name || "",
                                phone: member.phone_number || "",
                                role:
                                  member.role === "Sub-Owner"
                                    ? "sub_owner"
                                    : member.role === "Supervisor"
                                      ? "supervisor"
                                      : "worker",
                                opening_attendance: member.opening_attendance ? { ...member.opening_attendance } : null
                              })
                            }
                            data-testid="edit-staff-button"
                          >
                            <Edit3 className="h-4 w-4" />
                          </button> : null}
                          {canManageMember(member) ? (
                            <button
                              className="inline-grid h-9 w-9 place-items-center rounded-md border border-zinc-200 text-zinc-500 hover:bg-amber-50 hover:text-amber-700 transition"
                              type="button"
                              title={member.is_active === false ? "Activate Staff Member" : "Deactivate Staff Member"}
                              onClick={() => void handleStatusToggle(member)}
                              data-testid="toggle-staff-status-button"
                            >
                              {member.is_active === false ? <Unlock className="h-4 w-4" /> : <Lock className="h-4 w-4" />}
                            </button>
                          ) : null}
                          {canManageMember(member) ? (
                            <button
                              className="inline-grid h-9 w-9 place-items-center rounded-md border border-zinc-200 text-zinc-400 hover:bg-red-50 hover:text-red-600 transition"
                              type="button"
                              title="Revoke Credentials"
                              onClick={() => setDeleteModal(member)}
                              data-testid="delete-staff-button"
                            >
                              <Trash2 className="h-4 w-4" />
                            </button>
                          ) : null}
                          {canManageMember(member) && member.role === "Operator" && member.worker_id && (
                            <button
                              className="inline-flex h-9 items-center gap-1.5 px-3 rounded-md border border-red-200 bg-red-50 text-red-600 hover:bg-red-100 hover:text-red-700 transition font-semibold text-xs"
                              type="button"
                              title="Remove Worker"
                              onClick={() => handleRemoveWorker(member)}
                              data-testid="remove-worker-button"
                            >
                              <Trash2 className="h-3.5 w-3.5" />
                              Remove
                            </button>
                          )}
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

      {/* Edit Overlay / Slide Modal */}
      {editModal ? (
        <div className="fixed inset-0 z-50 flex items-center justify-end bg-black/50 p-4 transition-all animate-fadeIn">
          <div className="w-full max-w-md rounded-2xl bg-white p-6 shadow-2xl animate-slideLeft flex flex-col gap-4 border border-zinc-200">
            <div className="flex items-center justify-between border-b border-zinc-100 pb-3">
              <h3 className="text-lg font-black text-zinc-950">Edit Staff Account</h3>
              <button
                onClick={() => {
                  setEditModal(null);
                  setEditError("");
                }}
                className="rounded-full p-1 text-zinc-400 hover:bg-zinc-100 hover:text-zinc-700"
                type="button"
              >
                <X className="h-5 w-5" />
              </button>
            </div>

            <div className="max-h-[60vh] overflow-y-auto pr-1 space-y-4">
              <label className="block text-sm">
                <span className="font-semibold text-zinc-700">Full Name</span>
                <input
                  type="text"
                  className="mt-1 h-11 w-full rounded-lg border border-zinc-200 px-3 text-sm outline-none focus:border-[#6D28D9] focus:ring-2 focus:ring-[#F3E8FF]"
                  value={editModal.name}
                  onChange={(e) => setEditModal({ ...editModal, name: e.target.value })}
                />
              </label>

              <label className="block text-sm">
                <span className="font-semibold text-zinc-700">Phone Number</span>
                <input
                  type="text"
                  className="mt-1 h-11 w-full rounded-lg border border-zinc-200 px-3 text-sm outline-none focus:border-[#6D28D9] focus:ring-2 focus:ring-[#F3E8FF]"
                  value={editModal.phone}
                  onChange={(e) => setEditModal({ ...editModal, phone: e.target.value })}
                />
              </label>

              <label className="block text-sm">
                <span className="font-semibold text-zinc-700">Role</span>
                <select
                  className="mt-1 h-11 w-full rounded-lg border border-zinc-200 bg-white px-3 outline-none focus:border-[#6D28D9] focus:ring-2 focus:ring-[#F3E8FF] text-sm"
                  value={editModal.role}
                  onChange={(e) => setEditModal({ ...editModal, role: e.target.value as any })}
                >
                  {isPrimaryOwner && editModal.member.role === "Sub-Owner" ? (
                    <option value="sub_owner">Sub Owner</option>
                  ) : null}
                  <option value="supervisor">Supervisor</option>
                  <option value="worker">Worker (Operator)</option>
                </select>
              </label>

              <div className="border-t border-zinc-100 pt-4 space-y-4">
                <h4 className="text-sm font-bold text-[#6D28D9] flex items-center gap-1.5">
                  <Lock className="h-4 w-4 text-[#6D28D9]" />
                  Reset Staff Password (Optional)
                </h4>
                <PasswordInput
                  label="New Password"
                  placeholder="Min 8 characters"
                  value={editModal.password || ""}
                  onChange={(value) => setEditModal({ ...editModal, password: value })}
                />
                <PasswordInput
                  label="Confirm New Password"
                  placeholder="Repeat new password"
                  value={editModal.confirm_password || ""}
                  onChange={(value) => setEditModal({ ...editModal, confirm_password: value })}
                />
              </div>

              {editModal.role === "worker" && (() => {
                const currentOA = editModal.opening_attendance || {
                  id: editModal.member.opening_attendance?.id || 0,
                  worker_id: editModal.member.opening_attendance?.worker_id || 0,
                  period_start: "",
                  period_end: "",
                  present_days: 0,
                  half_days: 0,
                  absent_days: 0,
                  paid_leave_days: 0,
                  overtime_hours: 0,
                  advance_paid: 0,
                  deductions: 0,
                };
                
                return (
                  <div className="border-t border-zinc-100 pt-4 space-y-4">
                    <h4 className="text-sm font-bold text-[#6D28D9] flex items-center gap-1.5">
                      Previous Attendance (Opening)
                    </h4>
                    <div className="grid grid-cols-2 gap-3">
                      <label className="block text-xs">
                        <span className="font-semibold text-zinc-700">Period Start</span>
                        <input
                          type="date"
                          className="mt-1 h-9 w-full rounded border border-zinc-200 px-2 outline-none text-xs"
                          value={currentOA.period_start}
                          onChange={(e) => setEditModal({
                            ...editModal,
                            opening_attendance: {
                              ...currentOA,
                              period_start: e.target.value
                            }
                          })}
                        />
                      </label>
                      <label className="block text-xs">
                        <span className="font-semibold text-zinc-700">Period End</span>
                        <input
                          type="date"
                          className="mt-1 h-9 w-full rounded border border-zinc-200 px-2 outline-none text-xs"
                          value={currentOA.period_end}
                          onChange={(e) => setEditModal({
                            ...editModal,
                            opening_attendance: {
                              ...currentOA,
                              period_end: e.target.value
                            }
                          })}
                        />
                      </label>
                    </div>
                    <div className="grid grid-cols-3 gap-2">
                      <label className="block text-xs">
                        <span className="font-semibold text-zinc-700">Present</span>
                        <input
                          type="number"
                          step="0.5"
                          className="mt-1 h-9 w-full rounded border border-zinc-200 px-2 outline-none text-xs"
                          value={currentOA.present_days ?? ""}
                          onChange={(e) => setEditModal({
                            ...editModal,
                            opening_attendance: {
                              ...currentOA,
                              present_days: Number(e.target.value)
                            }
                          })}
                        />
                      </label>
                      <label className="block text-xs">
                        <span className="font-semibold text-zinc-700">Half Days</span>
                        <input
                          type="number"
                          step="0.5"
                          className="mt-1 h-9 w-full rounded border border-zinc-200 px-2 outline-none text-xs"
                          value={currentOA.half_days ?? ""}
                          onChange={(e) => setEditModal({
                            ...editModal,
                            opening_attendance: {
                              ...currentOA,
                              half_days: Number(e.target.value)
                            }
                          })}
                        />
                      </label>
                      <label className="block text-xs">
                        <span className="font-semibold text-zinc-700">Absent</span>
                        <input
                          type="number"
                          step="0.5"
                          className="mt-1 h-9 w-full rounded border border-zinc-200 px-2 outline-none text-xs"
                          value={currentOA.absent_days ?? ""}
                          onChange={(e) => setEditModal({
                            ...editModal,
                            opening_attendance: {
                              ...currentOA,
                              absent_days: Number(e.target.value)
                            }
                          })}
                        />
                      </label>
                    </div>
                    <div className="grid grid-cols-2 gap-3">
                      <label className="block text-xs">
                        <span className="font-semibold text-zinc-700">Advance Paid</span>
                        <input
                          type="number"
                          className="mt-1 h-9 w-full rounded border border-zinc-200 px-2 outline-none text-xs"
                          value={currentOA.advance_paid ?? ""}
                          onChange={(e) => setEditModal({
                            ...editModal,
                            opening_attendance: {
                              ...currentOA,
                              advance_paid: Number(e.target.value)
                            }
                          })}
                        />
                      </label>
                      <label className="block text-xs">
                        <span className="font-semibold text-zinc-700">Deductions</span>
                        <input
                          type="number"
                          className="mt-1 h-9 w-full rounded border border-zinc-200 px-2 outline-none text-xs"
                          value={currentOA.deductions ?? ""}
                          onChange={(e) => setEditModal({
                            ...editModal,
                            opening_attendance: {
                              ...currentOA,
                              deductions: Number(e.target.value)
                            }
                          })}
                        />
                      </label>
                    </div>
                  {canManageMember(editModal.member) && editModal.member.opening_attendance && (
                    <button
                      type="button"
                      className="mt-1 text-xs text-red-600 hover:text-red-800 font-semibold flex items-center gap-1 bg-transparent border-none p-0 cursor-pointer"
                      onClick={async () => {
                        if (window.confirm("Are you sure you want to delete this worker's opening attendance?")) {
                          try {
                            await deleteStaffOpeningAttendance(editModal.member.id);
                            setToast("Opening attendance deleted successfully");
                            setEditModal({
                              ...editModal,
                              opening_attendance: null,
                              member: {
                                ...editModal.member,
                                opening_attendance: null
                              }
                            });
                            await loadStaff();
                          } catch (caught) {
                            setEditError("Failed to delete opening attendance.");
                          }
                        }
                      }}
                    >
                      <Trash2 className="h-3 w-3" /> Remove Previous Attendance
                    </button>
                  )}
                </div>
              );})()}
            </div>

            {editError ? (
              <p className="rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm font-semibold text-red-700">
                {editError}
              </p>
            ) : null}

            <div className="flex justify-end gap-3 border-t border-zinc-100 pt-4">
              <button
                className="h-10 rounded-md border border-zinc-200 px-4 text-sm font-semibold text-zinc-700 hover:bg-zinc-50"
                onClick={() => {
                  setEditModal(null);
                  setEditError("");
                }}
                disabled={isUpdating}
                type="button"
              >
                Cancel
              </button>
              <button
                className="h-10 rounded-md bg-[#6D28D9] px-4 text-sm font-bold text-white hover:bg-[#4C1D95] disabled:cursor-not-allowed disabled:bg-zinc-300"
                disabled={isUpdating}
                onClick={handleEditSubmit}
                type="button"
              >
                {isUpdating ? "Saving..." : "Save Changes"}
              </button>
            </div>
          </div>
        </div>
      ) : null}

      {/* Delete Confirmation Overlay Modal */}
      {deleteModal ? (
        <div className="fixed inset-0 z-50 grid place-items-center bg-black/50 p-4 transition-all">
          <div className="w-full max-w-md rounded-2xl bg-white p-6 shadow-2xl border border-zinc-200">
            <div className="flex items-start gap-4">
              <div className="grid h-12 w-12 shrink-0 place-items-center rounded-full bg-red-50 text-red-600">
                <ShieldAlert className="h-6 w-6 text-red-600" />
              </div>
              <div className="space-y-2">
                <h3 className="text-lg font-black text-zinc-950">Revoke System Access</h3>
                <p className="text-sm text-zinc-500">
                  Are you sure you want to revoke system access credentials for this staff member?
                </p>
                <div className="rounded-md bg-zinc-50 p-3 text-sm text-zinc-700 border border-zinc-100 space-y-1">
                  <p><strong>Name:</strong> {deleteModal.full_name}</p>
                  <p><strong>Phone:</strong> {deleteModal.phone_number}</p>
                  <p><strong>Role:</strong> {displayRole(deleteModal.role)}</p>
                </div>
              </div>
            </div>

            <div className="mt-6 flex justify-end gap-3 border-t border-zinc-100 pt-4">
              <button
                className="h-10 rounded-md border border-zinc-200 px-4 text-sm font-semibold text-zinc-700 hover:bg-zinc-50"
                onClick={() => setDeleteModal(null)}
                disabled={isDeleting}
                type="button"
              >
                Cancel
              </button>
              <button
                className="h-10 rounded-md bg-red-600 px-4 text-sm font-bold text-white hover:bg-red-700 disabled:cursor-not-allowed disabled:bg-zinc-300"
                onClick={handleDeleteConfirm}
                disabled={isDeleting}
                type="button"
                data-testid="confirm-delete-staff-button"
              >
                {isDeleting ? "Revoking..." : "Revoke Access"}
              </button>
            </div>
          </div>
        </div>
      ) : null}

      {/* OTP Identity Audit Panel Overlay */}
      {showAuditModal ? (
        <div className="fixed inset-0 z-50 grid place-items-center bg-black/60 p-4 transition-all">
          <div className="w-full max-w-md rounded-2xl bg-white p-6 shadow-2xl border border-zinc-200 flex flex-col gap-4">
            <div className="flex items-center justify-between border-b border-zinc-100 pb-3">
              <div className="flex items-center gap-2">
                <KeyRound className="h-5 w-5 text-[#6D28D9]" />
                <h3 className="text-lg font-black text-zinc-950">Identity Auditor</h3>
              </div>
              <button
                onClick={() => setShowAuditModal(false)}
                className="rounded-full p-1 text-zinc-400 hover:bg-zinc-100 hover:text-zinc-700"
                type="button"
              >
                <X className="h-5 w-5" />
              </button>
            </div>

            {!auditedFactoryId ? (
              <div className="space-y-4">
                <p className="text-sm text-zinc-500 leading-normal">
                  To securely audit your hidden workspace identity boundary (factory_id), verify your primary account credentials via a secure OTP flow.
                </p>

                {auditStep === "request" ? (
                  <div className="space-y-3">
                    <label className="block text-sm">
                      <span className="font-semibold text-zinc-700">Registered Phone Number</span>
                      <input
                        type="text"
                        className="mt-1 h-11 w-full rounded-lg border border-zinc-200 px-3 text-sm outline-none focus:border-[#6D28D9] focus:ring-2 focus:ring-[#F3E8FF]"
                        placeholder="e.g. 9999999999"
                        value={auditPhone}
                        onChange={(e) => setAuditPhone(e.target.value)}
                      />
                    </label>
                    {auditError ? <p className="text-xs font-semibold text-red-600">{auditError}</p> : null}
                    <button
                      onClick={triggerOtpRequest}
                      disabled={auditLoading || !auditPhone}
                      className="inline-flex h-11 w-full items-center justify-center gap-2 rounded-lg bg-[#6D28D9] text-sm font-bold text-white hover:bg-[#4C1D95] disabled:cursor-not-allowed disabled:bg-zinc-300 transition"
                      type="button"
                    >
                      {auditLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
                      Request Verification Code
                    </button>
                  </div>
                ) : (
                  <div className="space-y-3">
                    <div className="rounded-md bg-green-50 px-3 py-2 border border-green-200 text-xs font-medium text-[#16A34A]">
                      Verification code has been successfully dispatched to +91 {auditPhone} (mock).
                    </div>
                    <label className="block text-sm">
                      <span className="font-semibold text-zinc-700">6-Digit Verification Code</span>
                      <input
                        type="text"
                        className="mt-1 h-11 w-full rounded-lg border border-zinc-200 px-3 text-sm outline-none tracking-widest text-center font-bold focus:border-[#6D28D9] focus:ring-2 focus:ring-[#F3E8FF]"
                        placeholder="000000"
                        maxLength={6}
                        value={auditOtp}
                        onChange={(e) => setAuditOtp(e.target.value)}
                      />
                    </label>
                    {auditError ? <p className="text-xs font-semibold text-red-600">{auditError}</p> : null}
                    <div className="flex gap-2">
                      <button
                        onClick={() => setAuditStep("request")}
                        className="h-11 flex-1 rounded-lg border border-zinc-200 text-sm font-semibold text-zinc-700 hover:bg-zinc-50"
                        type="button"
                      >
                        Back
                      </button>
                      <button
                        onClick={triggerOtpVerify}
                        disabled={auditLoading || auditOtp.length < 4}
                        className="inline-flex h-11 flex-1 items-center justify-center gap-2 rounded-lg bg-[#6D28D9] text-sm font-bold text-white hover:bg-[#4C1D95] disabled:cursor-not-allowed disabled:bg-zinc-300 transition"
                        type="button"
                      >
                        {auditLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Check className="h-4 w-4" />}
                        Verify OTP
                      </button>
                    </div>
                  </div>
                )}
              </div>
            ) : (
              <div className="space-y-4 text-center py-4">
                <div className="mx-auto grid h-14 w-14 place-items-center rounded-full bg-green-50 text-[#16A34A] border border-green-200">
                  <Check className="h-6 w-6 text-[#16A34A]" />
                </div>
                <h4 className="text-lg font-black text-zinc-950">Boundary Audit Verified</h4>
                <p className="text-sm text-zinc-500">
                  Your secure, multi-tenant workspace identity matches the boundary token below:
                </p>
                <div className="mx-auto rounded-lg bg-zinc-900 px-6 py-4 border border-zinc-800 shadow-inner w-fit font-mono text-2xl font-bold tracking-widest text-white">
                  {auditedFactoryId}
                </div>
                <div className="text-xs text-zinc-400 flex items-center justify-center gap-1.5 pt-2">
                  <Bot className="h-4 w-4 text-zinc-400" />
                  Secured by Munshi AI ERP Shield
                </div>
              </div>
            )}
          </div>
        </div>
      ) : null}
    </div>
  );
}

function displayRole(role: string) {
  if (role === "Operator") return "Worker";
  if (role === "Sub-Owner") return "Sub Owner";
  return role;
}
