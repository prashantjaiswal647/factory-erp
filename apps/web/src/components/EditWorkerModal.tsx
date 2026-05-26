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
  const [previousAttendance, setPreviousAttendance] = useState(String(worker.previous_attendance ?? worker.opening_attendance?.present_days ?? ""));
  const [shiftType, setShiftType] = useState(worker.shift_type ?? "");
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    setName(workerName(worker));
    setPhone(worker.phone ?? "");
    setDailyWageRate(String(worker.daily_wage_rate ?? worker.daily_wages ?? ""));
    setDutyHours(String(worker.duty_hours ?? ""));
    setPreviousAttendance(String(worker.previous_attendance ?? worker.opening_attendance?.present_days ?? ""));
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
        shift_type: shiftType.trim() || null
      });
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
      <section className="w-full max-w-lg rounded-lg bg-white p-5 shadow-xl">
        <div className="mb-5 flex items-center justify-between gap-4">
          <h2 className="text-lg font-semibold text-zinc-950">Edit Worker</h2>
          <button className="grid h-9 w-9 place-items-center rounded-md border border-zinc-200 text-zinc-600" type="button" onClick={onClose}>x</button>
        </div>
        <div className="grid gap-4">
          <Field label="Name" value={name} onChange={setName} />
          <Field label="Phone Number" value={phone} onChange={setPhone} />
          <Field label="Daily Wage" value={dailyWageRate} onChange={setDailyWageRate} type="number" />
          <Field label="Duty Hours" value={dutyHours} onChange={setDutyHours} type="number" />
          <Field label="Previous Attendance" value={previousAttendance} onChange={setPreviousAttendance} type="number" />
          <Field label="Shift Type" value={shiftType} onChange={setShiftType} />
        </div>
        {error ? <p className="mt-4 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm font-medium text-red-700">{error}</p> : null}
        <div className="mt-5 flex justify-end gap-3">
          <button className="h-10 rounded-md border border-zinc-200 px-4 text-sm font-semibold text-zinc-700" type="button" onClick={onClose}>Cancel</button>
          <button className="h-10 rounded-md bg-brand-600 px-4 text-sm font-semibold text-white disabled:bg-zinc-300" type="button" onClick={handleSubmit} disabled={isSaving}>
            {isSaving ? "Saving..." : "Save Worker"}
          </button>
        </div>
      </section>
    </div>
  );
}

function Field({ label, value, onChange, type = "text" }: { label: string; value: string; onChange: (value: string) => void; type?: string }) {
  return (
    <label className="grid gap-1 text-sm font-medium text-zinc-700">
      {label}
      <input className="h-10 rounded-md border border-zinc-200 px-3 outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-100" type={type} value={value} onChange={(event) => onChange(event.target.value)} />
    </label>
  );
}
