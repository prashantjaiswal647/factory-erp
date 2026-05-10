import { AlertTriangle, Check, Factory } from "lucide-react";
import { useEffect, useState } from "react";

import { createDailyProduction, getDashboardMachines, getDashboardWorkers } from "../lib/api";
import type { DailyProductionCreate, DashboardMachine, DashboardWorker } from "../lib/api";

const initialForm: DailyProductionCreate = {
  date: new Date().toISOString().slice(0, 10),
  worker_id: 0,
  machine_id: 0,
  variety: "Plain White",
  packaging_size_name: "210ml Standard Box",
  pieces_per_packet: 50,
  packets_per_box_limit: 20,
  total_boxes_made: 0,
  loose_packets_made: 0,
  blank_used_bori: 0,
  bottom_used_rolls: 0,
  wastage_kg: 0
};

export default function ProductionPage() {
  const [form, setForm] = useState<DailyProductionCreate>(initialForm);
  const [workers, setWorkers] = useState<DashboardWorker[]>([]);
  const [machines, setMachines] = useState<DashboardMachine[]>([]);
  const [toast, setToast] = useState("");
  const [error, setError] = useState("");
  const [isSaving, setIsSaving] = useState(false);

  useEffect(() => {
    void loadOptions();
  }, []);

  async function loadOptions() {
    const [workerRes, machineRes] = await Promise.all([getDashboardWorkers(), getDashboardMachines()]);
    setWorkers(workerRes.data);
    setMachines(machineRes.data);
    setForm((current) => ({
      ...current,
      worker_id: current.worker_id || workerRes.data[0]?.id || 0,
      machine_id: current.machine_id || machineRes.data[0]?.id || 0,
      packaging_size_name: machineRes.data[0]?.mould_size_ml ? `${machineRes.data[0].mould_size_ml}ml Standard Box` : current.packaging_size_name
    }));
  }

  async function submit() {
    setIsSaving(true);
    setError("");
    try {
      await createDailyProduction(form);
      setToast("Production saved");
      setForm({ ...initialForm, worker_id: workers[0]?.id || 0, machine_id: machines[0]?.id || 0 });
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Production save failed");
    } finally {
      setIsSaving(false);
    }
  }

  return (
    <div className="mx-auto max-w-5xl space-y-5">
      {toast ? <Toast message={toast} onClose={() => setToast("")} /> : null}
      <header>
        <h1 className="text-2xl font-semibold text-zinc-950">Production Entry</h1>
        <p className="mt-1 text-sm text-zinc-500">Daily boxes, packets, sacks, and bottom rolls.</p>
      </header>

      <section className="rounded-lg border border-zinc-200 bg-white p-5 shadow-sm">
        <div className="mb-5 flex items-center gap-3">
          <span className="grid h-10 w-10 place-items-center rounded-md bg-brand-50 text-brand-700">
            <Factory className="h-5 w-5" />
          </span>
          <h2 className="text-lg font-semibold text-zinc-950">Daily Production</h2>
        </div>

        <div className="grid gap-4 md:grid-cols-3">
          <Field label="Date" type="date" value={form.date} onChange={(date) => setForm({ ...form, date })} />
          <SelectField label="Worker" value={form.worker_id} onChange={(worker_id) => setForm({ ...form, worker_id })}>
            {workers.map((worker) => (
              <option key={worker.id} value={worker.id}>
                {worker.id} - {worker.name}
              </option>
            ))}
          </SelectField>
          <SelectField
            label="Machine"
            value={form.machine_id}
            onChange={(machine_id) => {
              const machine = machines.find((item) => item.id === machine_id);
              setForm({
                ...form,
                machine_id,
                packaging_size_name: machine?.mould_size_ml ? `${machine.mould_size_ml}ml Standard Box` : form.packaging_size_name
              });
            }}
          >
            {machines.map((machine) => (
              <option key={machine.id} value={machine.id}>
                {machine.machine_number || machine.id} - {machine.machine_type} {machine.mould_size_ml || ""}ml
              </option>
            ))}
          </SelectField>
          <StringSelectField label="Variety" value={form.variety} onChange={(variety) => setForm({ ...form, variety })} options={["Plain White", "Multicolor", "Custom Print"]} />
          <Field label="Packaging" value={form.packaging_size_name} onChange={(packaging_size_name) => setForm({ ...form, packaging_size_name })} />
          <NumberField label="Pieces per Packet" value={form.pieces_per_packet} onChange={(pieces_per_packet) => setForm({ ...form, pieces_per_packet })} />
          <NumberField label="Packets per Box" value={form.packets_per_box_limit} onChange={(packets_per_box_limit) => setForm({ ...form, packets_per_box_limit })} />
          <NumberField label="Total Boxes Made" value={form.total_boxes_made} onChange={(total_boxes_made) => setForm({ ...form, total_boxes_made })} />
          <NumberField label="Loose Packets Made" value={form.loose_packets_made} onChange={(loose_packets_made) => setForm({ ...form, loose_packets_made })} />
        </div>

        <div className="mt-6 rounded-lg border border-zinc-200 bg-zinc-50 p-4">
          <h3 className="text-sm font-semibold uppercase tracking-wide text-zinc-500">Raw Material Consumption</h3>
          <div className="mt-3 grid gap-4 md:grid-cols-2">
            <NumberField label="Blank Used (Bora)" value={form.blank_used_bori} onChange={(blank_used_bori) => setForm({ ...form, blank_used_bori })} />
            <NumberField label="Bottom Used (Roll)" value={form.bottom_used_rolls} onChange={(bottom_used_rolls) => setForm({ ...form, bottom_used_rolls })} />
          </div>
        </div>

        <div className="mt-6 rounded-lg border border-amber-200 bg-amber-50 p-4">
          <div className="flex items-center gap-2">
            <AlertTriangle className="h-4 w-4 text-amber-700" />
            <h3 className="text-sm font-semibold uppercase tracking-wide text-amber-800">Daily Wastage</h3>
          </div>
          <div className="mt-3 grid gap-4 md:grid-cols-2">
            <NumberField label="Wastage Amount (KG)" value={form.wastage_kg} onChange={(wastage_kg) => setForm({ ...form, wastage_kg })} />
            <div className="rounded-md border border-amber-200 bg-white px-4 py-3 text-sm text-amber-900">
              Wastage 2% se zyada hua to Munshi Alert dashboard par red reminder dikhayega.
            </div>
          </div>
        </div>

        {error ? <div className="mt-4 rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{error}</div> : null}

        <button className="mt-5 inline-flex h-10 items-center gap-2 rounded-md bg-brand-600 px-4 text-sm font-semibold text-white hover:bg-brand-700 disabled:bg-zinc-300" disabled={isSaving} type="button" onClick={submit}>
          <Check className="h-4 w-4" />
          {isSaving ? "Saving..." : "Save Production"}
        </button>
      </section>
    </div>
  );
}

function Field({ label, value, type = "text", onChange }: { label: string; value: string; type?: string; onChange: (value: string) => void }) {
  return (
    <label className="block text-sm">
      <span className="font-medium text-zinc-700">{label}</span>
      <input className="mt-1 h-10 w-full rounded-md border border-zinc-200 px-3 outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-100" type={type} value={value} onChange={(event) => onChange(event.target.value)} />
    </label>
  );
}

function SelectField({ label, value, onChange, children }: { label: string; value: number; onChange: (value: number) => void; children: React.ReactNode }) {
  return (
    <label className="block text-sm">
      <span className="font-medium text-zinc-700">{label}</span>
      <select className="mt-1 h-10 w-full rounded-md border border-zinc-200 px-3 outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-100" value={value} onChange={(event) => onChange(Number(event.target.value))}>
        <option value={0}>Select {label}</option>
        {children}
      </select>
    </label>
  );
}

function StringSelectField({ label, value, options, onChange }: { label: string; value: string; options: string[]; onChange: (value: string) => void }) {
  return (
    <label className="block text-sm">
      <span className="font-medium text-zinc-700">{label}</span>
      <select className="mt-1 h-10 w-full rounded-md border border-zinc-200 px-3 outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-100" value={value} onChange={(event) => onChange(event.target.value)}>
        {options.map((option) => <option key={option}>{option}</option>)}
      </select>
    </label>
  );
}

function NumberField({ label, value, onChange }: { label: string; value: number; onChange: (value: number) => void }) {
  return (
    <label className="block text-sm">
      <span className="font-medium text-zinc-700">{label}</span>
      <input className="mt-1 h-10 w-full rounded-md border border-zinc-200 px-3 outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-100" inputMode="decimal" type="number" value={value} onFocus={(event) => event.target.select()} onChange={(event) => onChange(Number(event.target.value))} />
    </label>
  );
}

function Toast({ message, onClose }: { message: string; onClose: () => void }) {
  return (
    <button className="fixed right-5 top-20 z-50 rounded-md bg-emerald-600 px-4 py-3 text-sm font-semibold text-white shadow-lg" type="button" onClick={onClose}>
      {message}
    </button>
  );
}
