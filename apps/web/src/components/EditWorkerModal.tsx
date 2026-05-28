import axios from "axios";
import { useEffect, useState } from "react";

import { updateWorkerProfile } from "../lib/api";
import type { WorkerProfile } from "../lib/api";

type EditableWorker = {
  id?: number;
  worker_id?: number;
  name?: string;
  worker_name?: string;
  phone?: string | null;
  daily_wage_rate?: string | number | null;
  daily_wages?: string | number | null;
  duty_hours?: string | number | null;
  previous_attendance?: string | number | null;
  previous_attendance_count?: string | number | null;
  opening_attendance?: { present_days?: string | number | null } | null;
  shift_timing?: string | null;
  shift_type?: string | null;
};

function workerId(worker: EditableWorker) {
  return worker.id ?? worker.worker_id;
}

function workerName(worker: EditableWorker) {
  return worker.name ?? worker.worker_name ?? "";
}

export function EditWorkerModal({
  worker,
  onClose,
  onSaved
}: {
  worker: EditableWorker;
  onClose: () => void;
  onSaved: (worker: WorkerProfile) => Promise<void> | void;
}) {
  const [name, setName] = useState(workerName(worker));
  const [phone, setPhone] = useState(worker.phone ?? "");
  const [dailyWageRate, setDailyWageRate] = useState(String(worker.daily_wage_rate ?? worker.daily_wages ?? ""));
  const [dutyHours, setDutyHours] = useState(String(worker.duty_hours ?? ""));
  const [previousAttendance, setPreviousAttendance] = useState(String(worker.previous_attendance ?? worker.previous_attendance_count ?? worker.opening_attendance?.present_days ?? ""));
  const [shiftType, setShiftType] = useState(worker.shift_type ?? "");
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    setName(workerName(worker));
    setPhone(worker.phone ?? "");
    setDailyWageRate(String(worker.daily_wage_rate ?? worker.daily_wages ?? ""));
    setDutyHours(String(worker.duty_hours ?? ""));
    setPreviousAttendance(String(worker.previous_attendance ?? worker.previous_attendance_count ?? worker.opening_attendance?.present_days ?? ""));
    setShiftType(worker.shift_type ?? "");
    setError("");
  }, [worker]);

  async function handleSubmit() {
    const id = workerId(worker);
    if (!id) return;
    setIsSaving(true);
    setError("");
    try {
      const response = await updateWorkerProfile(id, {
        name: name.trim(),
        phone_number: phone.trim(),
        daily_wage_rate: Number(dailyWageRate || 0),
        daily_wages: Number(dailyWageRate || 0),
        duty_hours: dutyHours ? Number(dutyHours) : undefined,
        previous_attendance: Number(previousAttendance || 0),
        previous_attendance_count: Number(previousAttendance || 0),
        shift_type: shiftType.trim() || null
      });
      
      // Cleanly flush the locally cached object states context to reflect modified numbers instantly
      await onSaved(response.data);
      onClose();
    } catch (caught) {
      const detail = axios.isAxiosError(caught) ? caught.response?.data?.detail || caught.message : "Worker update failed";
      setError(String(detail));
    } finally {
      setIsSaving(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-zinc-950/40 px-4">
      <section className="w-full max-w-lg rounded-xl border border-zinc-200 bg-white p-6 shadow-2xl flex flex-col gap-5">
        <div className="flex items-center justify-between border-b border-zinc-100 pb-3">
          <h2 className="text-lg font-semibold text-zinc-950">Edit Worker Profile</h2>
          <button className="grid h-9 w-9 place-items-center rounded-md border border-zinc-200 text-zinc-600 hover:bg-zinc-50 transition" type="button" onClick={onClose}>x</button>
        </div>
        <div className="grid gap-4">
          <Field label="Full Name" value={name} onChange={setName} placeholder="Enter full name" />
          <Field label="Phone Number" value={phone} onChange={setPhone} placeholder="Enter phone number" />
          <Field label="Daily Wage" value={dailyWageRate} onChange={setDailyWageRate} type="number" placeholder="Enter daily wage rate" />
          <Field label="Duty Hours" value={dutyHours} onChange={setDutyHours} type="number" placeholder="Enter standard duty hours" />
          <Field label="Previous Attendance Days" value={previousAttendance} onChange={setPreviousAttendance} type="number" placeholder="Enter previous attendance days" />
          <Field label="Shift Type" value={shiftType} onChange={setShiftType} placeholder="Enter shift type" />
        </div>
        {error ? <p className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm font-medium text-red-700">{error}</p> : null}
        <div className="flex justify-end gap-3 border-t border-zinc-100 pt-4">
          <button className="h-10 rounded-md border border-zinc-200 px-4 text-sm font-semibold text-zinc-700 hover:bg-zinc-50" type="button" onClick={onClose}>Cancel</button>
          <button className="h-10 rounded-md bg-brand-600 px-4 text-sm font-semibold text-white hover:bg-brand-700 disabled:bg-zinc-300 transition" type="button" onClick={handleSubmit} disabled={isSaving}>
            {isSaving ? "Saving..." : "Save Worker"}
          </button>
        </div>
      </section>
    </div>
  );
}

function Field({ label, value, onChange, type = "text", placeholder }: { label: string; value: string; onChange: (value: string) => void; type?: string; placeholder?: string }) {
  return (
    <label className="block text-sm">
      <span className="font-semibold text-zinc-700">{label}</span>
      <input
        type={type}
        className="mt-1 h-11 w-full rounded-lg border border-zinc-200 px-3 text-sm outline-none transition focus:border-[#6D28D9] focus:ring-2 focus:ring-[#F3E8FF]"
        placeholder={placeholder}
        value={value}
        onChange={(event) => onChange(event.target.value)}
      />
    </label>
  );
}
