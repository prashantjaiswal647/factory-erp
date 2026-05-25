import { AlertTriangle, Check, Factory, Loader2, Activity } from "lucide-react";
import axios from "axios";
import { useEffect, useState } from "react";

import { createDailyProduction, getDashboardMachines, getDashboardWorkers, getFinalStockOptions } from "../lib/api";
import type { DailyProductionCreate, DashboardMachine, DashboardWorker, FinalStockOption } from "../lib/api";

const todayDate = () => new Date().toISOString().slice(0, 10);
const numberOrDefault = (value: unknown, fallback = 0) => {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
};
const dateOnly = (value: unknown) => {
  const raw = String(value || "").trim();
  return /^\d{4}-\d{2}-\d{2}$/.test(raw) ? raw : todayDate();
};

const initialForm: DailyProductionCreate = {
  date: todayDate(),
  worker_id: 0,
  machine_id: 0,
  product_id: null,
  product_size_ml: null,
  variety: "Plain White",
  packaging_size: "210ml Standard Box",
  packaging_size_name: "210ml Standard Box",
  pieces_per_packet: 100,
  packets_per_box_limit: 10,
  shift: "Day",
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
  const [finalStockOptions, setFinalStockOptions] = useState<FinalStockOption[]>([]);
  const [toast, setToast] = useState("");
  const [error, setError] = useState("");
  const [isSaving, setIsSaving] = useState(false);
  const [syncLatency, setSyncLatency] = useState(124);

  useEffect(() => {
    const interval = setInterval(() => {
      setSyncLatency(Math.floor(110 + Math.random() * 30));
    }, 1500);
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    void loadOptions();
  }, []);

  async function loadOptions() {
    let cleanWorkers: DashboardWorker[] = [];
    let cleanMachines: DashboardMachine[] = [];
    let variations: FinalStockOption[] = [];

    try {
      const workerRes = await getDashboardWorkers();
      cleanWorkers = Array.isArray(workerRes.data) ? workerRes.data : [];
    } catch (err) {
      console.error("Failed to load dashboard workers:", err);
    }

    try {
      const machineRes = await getDashboardMachines();
      cleanMachines = Array.isArray(machineRes.data) ? machineRes.data : [];
    } catch (err) {
      console.error("Failed to load dashboard machines:", err);
    }

    try {
      const finalStockRes = await getFinalStockOptions();
      variations = Array.isArray(finalStockRes.data) ? finalStockRes.data : [];
    } catch (err) {
      console.error("Failed to load final stock options:", err);
    }

    const firstVariation = variations[0];
    setWorkers(cleanWorkers);
    setMachines(cleanMachines);
    setFinalStockOptions(variations);
    setForm((current) => ({
      ...current,
      worker_id: current.worker_id || cleanWorkers[0]?.id || 0,
      machine_id: current.machine_id || cleanMachines[0]?.id || 0,
      product_id: current.product_id || firstVariation?.id || null,
      product_size_ml: current.product_size_ml || firstVariation?.product_size_ml || cleanMachines[0]?.mould_size_ml || null,
      variety: current.variety || firstVariation?.variety || "Plain White",
      packaging_size: current.packaging_size || firstVariation?.packaging_size || firstVariation?.packaging_size_name || current.packaging_size_name,
      packaging_size_name: firstVariation?.packaging_size_name || (cleanMachines[0]?.mould_size_ml ? `${cleanMachines[0].mould_size_ml}ml Standard Box` : current.packaging_size_name),
      pieces_per_packet: firstVariation?.pieces_per_packet || current.pieces_per_packet,
      packets_per_box_limit: firstVariation?.packets_per_box || firstVariation?.packets_per_box_limit || current.packets_per_box_limit
    }));
  }

  async function submit() {
    setIsSaving(true);
    setError("");
    try {
      const normalizedDate = dateOnly(form.date);
      const workerId = numberOrDefault(form.worker_id);
      const machineId = numberOrDefault(form.machine_id);
      const payload: DailyProductionCreate = {
        factory_id: String(localStorage.getItem("factory_id") || ""),
        date: normalizedDate,
        operator_id: workerId > 0 ? workerId : null,
        worker_id: workerId,
        machine_id: machineId,
        product_id: numberOrDefault(form.product_id) > 0 ? numberOrDefault(form.product_id) : null,
        product_size_ml: numberOrDefault(form.product_size_ml) > 0 ? numberOrDefault(form.product_size_ml) : null,
        variety: String(form.variety || "Standard/White").trim(),
        packaging_size: form.packaging_size ? String(form.packaging_size).trim() : null,
        packaging_size_name: String(form.packaging_size_name || form.packaging_size || "").trim(),
        pieces_per_packet: numberOrDefault(form.pieces_per_packet, 1) || 1,
        packets_per_box_limit: numberOrDefault(form.packets_per_box_limit, 1) || 1,
        shift: form.shift === "Night" ? "Night" : "Day",
        total_boxes_made: numberOrDefault(form.total_boxes_made),
        loose_packets_made: numberOrDefault(form.loose_packets_made),
        blank_used_bori: numberOrDefault(form.blank_used_bori),
        bottom_used_rolls: numberOrDefault(form.bottom_used_rolls),
        wastage_kg: numberOrDefault(form.wastage_kg),
        remarks: null
      };
      console.log("daily production payload", payload);
      const response = await createDailyProduction(payload);
      setToast("Daily Production Saved Successfully! Attendance automatically marked as 'Present' for the worker.");
      window.dispatchEvent(new CustomEvent("production:daily-saved", { detail: response.data }));
      window.dispatchEvent(new CustomEvent("attendance:updated", { detail: response.data }));
      window.dispatchEvent(new CustomEvent("inventory:updated", { detail: response.data }));
      void loadOptions();
      setForm({
        ...initialForm,
        worker_id: workers[0]?.id || 0,
        machine_id: machines[0]?.id || 0,
        product_id: finalStockOptions[0]?.id || null,
        product_size_ml: finalStockOptions[0]?.product_size_ml || null,
        variety: finalStockOptions[0]?.variety || initialForm.variety,
        packaging_size: finalStockOptions[0]?.packaging_size || finalStockOptions[0]?.packaging_size_name || initialForm.packaging_size,
        packaging_size_name: finalStockOptions[0]?.packaging_size_name || initialForm.packaging_size_name,
        pieces_per_packet: finalStockOptions[0]?.pieces_per_packet || initialForm.pieces_per_packet,
        packets_per_box_limit: finalStockOptions[0]?.packets_per_box || finalStockOptions[0]?.packets_per_box_limit || initialForm.packets_per_box_limit
      });
    } catch (caught) {
      if (axios.isAxiosError(caught)) {
        console.error("daily production error response", caught.response?.data || caught.message);
        const detail = caught.response?.data?.detail;
        const message = Array.isArray(detail)
          ? detail.map((item) => `${item.loc?.join(".") || "field"}: ${item.msg}`).join("; ")
          : typeof detail === "string"
            ? detail
            : caught.message;
        setError(`Production save failed: ${message}`);
      } else {
        console.error("daily production unexpected error", caught);
        setError(caught instanceof Error ? caught.message : "Production save failed");
      }
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
          <ProductSelectField
            label="Product"
            value={form.product_id || 0}
            options={finalStockOptions}
            onChange={(product_id) => {
              const selected = finalStockOptions.find((item) => item.id === product_id);
              setForm({
                ...form,
                product_id,
                product_size_ml: selected?.product_size_ml || form.product_size_ml,
                variety: selected?.variety || form.variety,
                packaging_size: selected?.packaging_size || selected?.packaging_size_name || form.packaging_size,
                packaging_size_name: selected?.packaging_size_name || form.packaging_size_name,
                pieces_per_packet: selected?.pieces_per_packet || form.pieces_per_packet,
                packets_per_box_limit: selected?.packets_per_box || selected?.packets_per_box_limit || form.packets_per_box_limit
              });
            }}
          />
          <VariationSelectField
            label="Packaging Size Variation"
            value={form.product_id || 0}
            options={finalStockOptions}
            onChange={(product_id) => {
              const selected = finalStockOptions.find((item) => item.id === product_id);
              setForm({
                ...form,
                product_id,
                product_size_ml: selected?.product_size_ml || form.product_size_ml,
                variety: selected?.variety || form.variety,
                packaging_size: selected?.packaging_size || selected?.packaging_size_name || form.packaging_size,
                packaging_size_name: selected?.packaging_size_name || form.packaging_size_name,
                pieces_per_packet: selected?.pieces_per_packet || form.pieces_per_packet,
                packets_per_box_limit: selected?.packets_per_box || selected?.packets_per_box_limit || form.packets_per_box_limit
              });
            }}
          />
          <StringSelectField label="Shift" value={form.shift} onChange={(shift) => setForm({ ...form, shift: shift as "Day" | "Night" })} options={["Day", "Night"]} />
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
      <input className="mt-1 h-10 w-full rounded-md border border-zinc-200 px-3 outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-100" inputMode="decimal" placeholder="0" type="number" value={value === 0 ? "" : value} onChange={(event) => onChange(event.target.value === "" ? 0 : Number(event.target.value))} />
    </label>
  );
}

function ProductSelectField({ label, value, options, onChange }: { label: string; value: number; options: FinalStockOption[]; onChange: (value: number) => void }) {
  const cleanOptions = Array.isArray(options) ? options : [];
  const uniqueProducts = Array.from(new Map(cleanOptions.map((item) => [`${item.product_size_ml}-${item.variety}`, item])).values());
  return (
    <label className="block text-sm">
      <span className="font-medium text-zinc-700">{label}</span>
      <select className="mt-1 h-10 w-full rounded-md border border-zinc-200 px-3 outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-100" value={value} onChange={(event) => onChange(Number(event.target.value))}>
        <option value={0}>Select Product</option>
        {uniqueProducts.map((option) => (
          <option key={option.id} value={option.id}>
            {option.product_size_ml}ml - {option.variety}
          </option>
        ))}
      </select>
    </label>
  );
}

function VariationSelectField({ label, value, options, onChange }: { label: string; value: number; options: FinalStockOption[]; onChange: (value: number) => void }) {
  const cleanOptions = Array.isArray(options) ? options : [];
  return (
    <label className="block text-sm">
      <span className="font-medium text-zinc-700">{label}</span>
      <select className="mt-1 h-10 w-full rounded-md border border-zinc-200 px-3 outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-100" value={value} onChange={(event) => onChange(Number(event.target.value))}>
        <option value={0}>Select Variation</option>
        {cleanOptions.map((option) => (
          <option key={option.id} value={option.id}>
            {option.product_size_ml}ml - {option.pieces_per_packet || 0} Pcs/Pkt - {option.packaging_size || option.packaging_size_name}
          </option>
        ))}
      </select>
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
