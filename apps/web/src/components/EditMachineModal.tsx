import axios from "axios";
import { useEffect, useState } from "react";
import { updateMachine } from "../lib/api";

type EditableMachine = {
  id: number;
  machine_number?: string | null;
  machine_sequence_number?: string | null;
  machine_type?: string;
  mould_size_ml?: number | null;
  bottom_size_mm?: number | null;
  speed_per_minute?: number | null;
  machine_name?: string | null;
  default_speed?: number | null;
  target_output_per_shift?: number | null;
  raw_materials_mapped?: string[];
};

export function EditMachineModal({
  machine,
  onClose,
  onSaved
}: {
  machine: EditableMachine;
  onClose: () => void;
  onSaved: () => Promise<void> | void;
}) {
  const [machineNumber, setMachineNumber] = useState(machine.machine_number || machine.machine_sequence_number || "");
  const [machineType, setMachineType] = useState(machine.machine_type || machine.machine_name || "");
  const [mouldSizeMl, setMouldSizeMl] = useState(String(machine.mould_size_ml || ""));
  const [bottomSizeMm, setBottomSizeMm] = useState(String(machine.bottom_size_mm || ""));
  const [speedPerMinute, setSpeedPerMinute] = useState(String(machine.default_speed || machine.speed_per_minute || ""));
  const [machineName, setMachineName] = useState(machine.machine_name || "");
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    setMachineNumber(machine.machine_number || machine.machine_sequence_number || "");
    setMachineType(machine.machine_type || machine.machine_name || "");
    setMouldSizeMl(String(machine.mould_size_ml || ""));
    setBottomSizeMm(String(machine.bottom_size_mm || ""));
    setSpeedPerMinute(String(machine.default_speed || machine.speed_per_minute || ""));
    setMachineName(machine.machine_name || "");
    setError("");
  }, [machine]);

  async function handleSubmit() {
    const normalizedName = (machineName || machineType).trim();
    if (!normalizedName) {
      setError("Machine name is required");
      return;
    }
    setIsSaving(true);
    setError("");
    try {
      await updateMachine(machine.id, {
        machine_number: machineNumber.trim() || undefined,
        machine_type: machineType.trim() || normalizedName,
        mould_size_ml: mouldSizeMl ? Number(mouldSizeMl) : undefined,
        bottom_size_mm: bottomSizeMm ? Number(bottomSizeMm) : undefined,
        speed_per_minute: Number(speedPerMinute || 0),
        default_speed: Number(speedPerMinute || 0),
        machine_name: normalizedName
      });
      await onSaved();
      onClose();
    } catch (caught) {
      const detail = axios.isAxiosError(caught) ? caught.response?.data?.detail || caught.message : "Machine update failed";
      setError(String(detail));
    } finally {
      setIsSaving(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-zinc-950/40 px-4">
      <section className="w-full max-w-lg rounded-lg bg-white p-5 shadow-xl">
        <div className="mb-5 flex items-center justify-between gap-4">
          <h2 className="text-lg font-semibold text-zinc-950 font-sans">Edit Machine</h2>
          <button className="grid h-9 w-9 place-items-center rounded-md border border-zinc-200 text-zinc-600 text-sm font-semibold hover:bg-zinc-50" type="button" onClick={onClose}>✕</button>
        </div>
        <div className="grid gap-4">
          <Field label="Machine No. (Optional)" value={machineNumber} onChange={setMachineNumber} />
          <Field label="Machine Name / Custom Type" value={machineName} onChange={(value) => { setMachineName(value); setMachineType(value); }} placeholder="e.g., Hydraulic Plate Press" />
          <Field label="Mould Size (ml)" value={mouldSizeMl} onChange={setMouldSizeMl} type="number" />
          <Field label="Bottom Size (mm)" value={bottomSizeMm} onChange={setBottomSizeMm} type="number" />
          <Field label="Speed per Minute" value={speedPerMinute} onChange={setSpeedPerMinute} type="number" />
        </div>
        {error ? <p className="mt-4 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm font-medium text-red-700 font-sans">{error}</p> : null}
        <div className="mt-5 flex justify-end gap-3 font-sans">
          <button className="h-10 rounded-md border border-zinc-200 px-4 text-sm font-semibold text-zinc-700 hover:bg-zinc-50" type="button" onClick={onClose}>Cancel</button>
          <button className="h-10 rounded-md bg-brand-600 px-4 text-sm font-semibold text-white hover:bg-brand-700 disabled:bg-zinc-300" type="button" onClick={handleSubmit} disabled={isSaving}>
            {isSaving ? "Saving..." : "Save Machine"}
          </button>
        </div>
      </section>
    </div>
  );
}

function Field({ label, value, onChange, placeholder, type = "text" }: { label: string; value: string; onChange: (value: string) => void; placeholder?: string; type?: string }) {
  return (
    <label className="grid gap-1 text-sm font-medium text-zinc-700">
      {label}
      <input 
        className="h-10 rounded-md border border-zinc-200 px-3 outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-100" 
        type={type} 
        value={value} 
        placeholder={placeholder}
        onChange={(event) => onChange(event.target.value)} 
      />
    </label>
  );
}
