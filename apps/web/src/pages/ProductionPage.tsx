import { AlertTriangle, Check, ChevronDown, ChevronRight, Factory, Loader2, Activity, Plus, X } from "lucide-react";
import axios from "axios";
import { useEffect, useMemo, useState } from "react";

import {
  createDailyProductionBatch,
  createFinishedGoodVariant,
  getDashboardMachines,
  getDashboardWorkers,
  getFinalStockOptions,
  getDailyProductionHistory,
  getDailyProductionBatches,
  getProductionWorkerSummary,
  rejectDailyProduction,
  getInventory,
  saveShiftWastage,
  getShiftWastage,
} from "../lib/api";
import type {
  DailyProductionCreate,
  ProductionBatchCreate,
  ProductionBatchHistory,
  DashboardMachine,
  DashboardWorker,
  FinalStockOption,
  FinishedGoodVariantCreate,
  FinishedGoodVariantResponse,
  ProductionHistoryEntry,
  ProductionWorkerSummary,
} from "../lib/api";

type NewVariantForm = {
  product_size_ml: string;
  variety: string;
  packaging_size_name: string;
  pieces_per_packet: string;
  packets_per_box_limit: string;
  opening_stock_boxes: string;
};

type WorkerOutputDraft = {
  finished_good_id: number;
  boxes_made: number;
  loose_packets_made: number;
};

type WorkerCardDraft = {
  worker_id: number;
  blank_used_bora: number;
  bottom_used_roll: number;
  note: string;
  outputs: WorkerOutputDraft[];
};

const emptyOutput = (): WorkerOutputDraft => ({
  finished_good_id: 0,
  boxes_made: 0,
  loose_packets_made: 0,
});

const emptyWorkerCard = (workerId = 0): WorkerCardDraft => ({
  worker_id: workerId,
  blank_used_bora: 0,
  bottom_used_roll: 0,
  note: "",
  outputs: [emptyOutput()],
});

const emptyNewVariant: NewVariantForm = {
  product_size_ml: "",
  variety: "Plain White",
  packaging_size_name: "",
  pieces_per_packet: "100",
  packets_per_box_limit: "10",
  opening_stock_boxes: "0",
};

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
  packaging_size: "",
  packaging_size_name: "",
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
  const [mappingMessage, setMappingMessage] = useState("");
  const [isSaving, setIsSaving] = useState(false);
  const [syncLatency, setSyncLatency] = useState(124);
  const [showNewVariantModal, setShowNewVariantModal] = useState(false);
  const [newVariantForm, setNewVariantForm] = useState<NewVariantForm>(emptyNewVariant);
  const [isSubmittingVariant, setIsSubmittingVariant] = useState(false);
  const [variantError, setVariantError] = useState("");
  const [variantDuplicate, setVariantDuplicate] = useState<{
    existing_product_id: number;
    existing: FinishedGoodVariantResponse;
  } | null>(null);
  const [summary, setSummary] = useState<ProductionWorkerSummary | null>(null);
  const [history, setHistory] = useState<ProductionHistoryEntry[]>([]);
  const [expandedWorker, setExpandedWorker] = useState<number | null>(null);
  const [rejecting, setRejecting] = useState<ProductionHistoryEntry | null>(null);
  const [rejectReason, setRejectReason] = useState("");
  const [shiftWastageKg, setShiftWastageKg] = useState(0);
  const [wastageNote, setWastageNote] = useState("");
  const [wastageDate, setWastageDate] = useState(todayDate());
  const [wastageShift, setWastageShift] = useState<"Day" | "Night" | "Custom">("Day");
  const [isSavingWastage, setIsSavingWastage] = useState(false);
  const [hasExistingWastage, setHasExistingWastage] = useState(false);
  const [workerCards, setWorkerCards] = useState<WorkerCardDraft[]>([emptyWorkerCard()]);
  const [batchHistory, setBatchHistory] = useState<ProductionBatchHistory[]>([]);
  const [expandedBatchWorker, setExpandedBatchWorker] = useState<number | null>(null);

  useEffect(() => {
    const interval = setInterval(() => {
      setSyncLatency(Math.floor(110 + Math.random() * 30));
    }, 1500);
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    void loadOptions();
    void loadProductionVisibility();
  }, []);

  useEffect(() => {
    async function loadShiftWastage() {
      try {
        const res = await getShiftWastage(dateOnly(wastageDate), wastageShift);
        if (res.data) {
          setShiftWastageKg(res.data.wastage_kg);
          setWastageNote(res.data.note || "");
          setHasExistingWastage(true);
        } else {
          setShiftWastageKg(0);
          setWastageNote("");
          setHasExistingWastage(false);
        }
      } catch (err) {
        console.error("Failed to load shift wastage:", err);
        setHasExistingWastage(false);
      }
    }
    void loadShiftWastage();
  }, [wastageDate, wastageShift]);

  async function submitWastage() {
    setIsSavingWastage(true);
    try {
      await saveShiftWastage({
        date: dateOnly(wastageDate),
        shift: wastageShift,
        wastage_kg: Number(shiftWastageKg || 0),
        note: wastageNote.trim() || null,
      });
      setToast("Shift wastage saved successfully.");
      setHasExistingWastage(true);
    } catch (err) {
      console.error("Failed to save shift wastage:", err);
      setError(axios.isAxiosError(err) ? String(err.response?.data?.detail || err.message) : "Failed to save wastage");
    } finally {
      setIsSavingWastage(false);
    }
  }

  async function loadProductionVisibility() {
    const [summaryResponse, historyResponse, batchResponse] = await Promise.all([
      getProductionWorkerSummary(todayDate()),
      getDailyProductionHistory(todayDate()),
      getDailyProductionBatches(todayDate()),
    ]);
    setSummary(summaryResponse.data);
    setHistory(historyResponse.data);
    setBatchHistory(batchResponse.data);
  }

  async function loadOptions() {
    let cleanWorkers: DashboardWorker[] = [];
    let cleanMachines: DashboardMachine[] = [];

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

    setWorkers(cleanWorkers);
    setMachines(Array.from(new Map(cleanMachines.map((machine) => [machine.id, machine])).values()));
    setFinalStockOptions([]);
    setWorkerCards([emptyWorkerCard(cleanWorkers[0]?.id || 0)]);
    setForm((current) => ({
      ...current,
      worker_id: current.worker_id || cleanWorkers[0]?.id || 0,
      machine_id: 0,
      product_id: null,
      product_size_ml: null,
      packaging_size: "",
      packaging_size_name: "",
    }));
  }

  async function selectMachine(machineId: number) {
    const machine = machines.find((item) => item.id === machineId);
    setForm((current) => ({
      ...current,
      machine_id: machineId,
      product_id: null,
      product_size_ml: machine?.mould_size_ml || null,
      variety: "Plain White",
      packaging_size: "",
      packaging_size_name: "",
    }));
    setFinalStockOptions([]);
    setWorkerCards((cards) => cards.map((card) => ({
      ...card,
      outputs: [emptyOutput()],
    })));
    if (!machineId) return;
    try {
      const response = await getFinalStockOptions(undefined, true, { machineId });
      const options = Array.isArray(response.data) ? response.data : [];
      setFinalStockOptions(options);
      setMappingMessage(options.length ? "" : "Inventory mapping incomplete for this SKU.");
    } catch (err) {
      console.error("Failed to load compatible products:", err);
      setMappingMessage("Inventory mapping incomplete for this SKU.");
    }
  }

  async function submit() {
    if (!form.machine_id) {
      setError("Select a machine.");
      return;
    }
    if (!workerCards.length || workerCards.some((card) => !card.worker_id || !card.outputs.length)) {
      setError("Every worker card needs a worker and at least one output.");
      return;
    }
    if (workerCards.some((card) => card.outputs.some((output) => !output.finished_good_id || (!output.boxes_made && !output.loose_packets_made)))) {
      setError("Select a finished good and enter production on every output line.");
      return;
    }
    setIsSaving(true);
    setError("");
    try {
      const normalizedDate = dateOnly(form.date);
      const payload: ProductionBatchCreate = {
        date: normalizedDate,
        shift: String(form.shift || "Day"),
        machine_id: numberOrDefault(form.machine_id),
        worker_cards: workerCards.map((card) => ({
          worker_id: card.worker_id,
          blank_used_bora: numberOrDefault(card.blank_used_bora),
          bottom_used_roll: numberOrDefault(card.bottom_used_roll),
          note: card.note.trim() || null,
          outputs: card.outputs.map((output) => ({
            finished_good_id: output.finished_good_id,
            boxes_made: numberOrDefault(output.boxes_made),
            loose_packets_made: numberOrDefault(output.loose_packets_made),
          })),
        })),
        shift_wastage_kg: numberOrDefault(shiftWastageKg),
        wastage_note: wastageNote.trim() || null,
      };
      const response = await createDailyProductionBatch(payload);
      setToast("Shift production saved successfully.");
      window.dispatchEvent(new CustomEvent("production:daily-saved", { detail: response.data }));
      window.dispatchEvent(new CustomEvent("attendance:updated", { detail: response.data }));
      window.dispatchEvent(new CustomEvent("inventory:updated", { detail: response.data }));
      void loadOptions();
      void loadProductionVisibility();
      setWorkerCards([emptyWorkerCard(workers[0]?.id || 0)]);
      setShiftWastageKg(0);
      setWastageNote("");
    } catch (caught) {
      if (axios.isAxiosError(caught)) {
        console.error("daily production error response", caught.response?.data || caught.message);
        const detail = caught.response?.data?.detail;
        const message = Array.isArray(detail)
          ? detail.map((item) => `${item.loc?.join(".") || "field"}: ${item.msg}`).join("; ")
          : typeof detail === "string"
            ? detail
            : caught.message;
        setError(message);
      } else {
        console.error("daily production unexpected error", caught);
        setError(caught instanceof Error ? caught.message : "Production save failed");
      }
    } finally {
      setIsSaving(false);
    }
  }

  async function confirmReject() {
    if (!rejecting || rejectReason.trim().length < 3) return;
    setIsSaving(true);
    try {
      await rejectDailyProduction(rejecting.id, rejectReason.trim());
      setToast("Production rejected and finished goods inventory reversed.");
      setRejecting(null);
      setRejectReason("");
      await Promise.all([loadProductionVisibility(), loadOptions()]);
    } catch (caught) {
      setError(axios.isAxiosError(caught) ? String(caught.response?.data?.detail || caught.message) : "Production reject failed.");
    } finally {
      setIsSaving(false);
    }
  }

  async function handleCreateNewVariant() {
    setVariantError("");
    setVariantDuplicate(null);
    // client-side validation
    const size_ml = Number(newVariantForm.product_size_ml);
    const pieces = Number(newVariantForm.pieces_per_packet);
    const pkts_per_box = Number(newVariantForm.packets_per_box_limit);
    const opening = Number(newVariantForm.opening_stock_boxes || 0);
    if (!size_ml || size_ml <= 0) {
      setVariantError("Product size (ml) is required and must be > 0.");
      return;
    }
    const selectedMachine = machines.find((machine) => machine.id === form.machine_id);
    if (selectedMachine?.mould_size_ml && size_ml !== selectedMachine.mould_size_ml) {
      setVariantError(`Product size must match selected machine size (${selectedMachine.mould_size_ml}ml).`);
      return;
    }
    if (!newVariantForm.packaging_size_name.trim()) {
      setVariantError("Packaging size name is required.");
      return;
    }
    if (!pieces || pieces <= 0) {
      setVariantError("Pieces per packet is required and must be > 0.");
      return;
    }
    if (!pkts_per_box || pkts_per_box <= 0) {
      setVariantError("Packets per box is required and must be > 0.");
      return;
    }
    setIsSubmittingVariant(true);
    try {
      const payload: FinishedGoodVariantCreate = {
        product_size_ml: size_ml,
        variety: newVariantForm.variety || "Plain White",
        packaging_size_name: newVariantForm.packaging_size_name.trim(),
        pieces_per_packet: pieces,
        packets_per_box_limit: pkts_per_box,
        opening_stock_boxes: opening,
      };
      const res = await createFinishedGoodVariant(payload);
      if (res.data.created_existing || res.data.status === "exists") {
        setToast("This packing variant already exists and has been selected.");
      } else {
        setToast(`New variant created: ${res.data.product_size_ml}ml ${res.data.variety} ${res.data.packaging_size_name}`);
      }
      // Keep the selected machine and make the new SKU immediately reusable.
      setFinalStockOptions((current) => {
        const exists = current.some((item) => item.id === res.data.id);
        return exists ? current : [...current, {
          id: res.data.id,
          product_size_ml: res.data.product_size_ml,
          variety: res.data.variety,
          packaging_size: res.data.packaging_size_name,
          packaging_size_name: res.data.packaging_size_name,
          pieces_per_packet: res.data.pieces_per_packet,
          packets_per_box: res.data.packets_per_box_limit,
          current_quantity: res.data.current_quantity,
          total_boxes: res.data.total_boxes,
          loose_packets: res.data.loose_packets,
          packets_per_box_limit: res.data.packets_per_box_limit,
        }];
      });
      setForm((current) => ({
        ...current,
        product_id: res.data.id,
        product_size_ml: res.data.product_size_ml,
        variety: res.data.variety,
        packaging_size: res.data.packaging_size_name,
        packaging_size_name: res.data.packaging_size_name,
        pieces_per_packet: res.data.pieces_per_packet,
        packets_per_box_limit: res.data.packets_per_box_limit,
      }));
      setShowNewVariantModal(false);
      setNewVariantForm(emptyNewVariant);
      window.dispatchEvent(new CustomEvent("inventory:updated", { detail: res.data }));
    } catch (caught) {
      if (axios.isAxiosError(caught)) {
        const detail = caught.response?.data?.detail;
        if (caught.response?.status === 409 && detail && typeof detail === "object") {
          // Duplicate — offer to select the existing one
          setVariantDuplicate({
            existing_product_id: detail.existing_product_id,
            existing: {
              id: detail.existing.id,
              factory_id: detail.existing.factory_id || 0,
              product_size_ml: detail.existing.product_size_ml,
              variety: detail.existing.variety,
              packaging_size_name: detail.existing.packaging_size_name,
              pieces_per_packet: detail.existing.pieces_per_packet,
              packets_per_box_limit: detail.existing.packets_per_box_limit,
              current_quantity: detail.existing.current_quantity,
              total_boxes: 0,
              loose_packets: 0,
              created_existing: true,
            },
          });
          setVariantError(detail.message || "A variant with these specs already exists.");
        } else {
          const message = Array.isArray(detail)
            ? detail.map((item) => `${item.loc?.join(".") || "field"}: ${item.msg}`).join("; ")
            : typeof detail === "string"
              ? detail
              : caught.message;
          setVariantError(`Could not create variant: ${message}`);
        }
      } else {
        setVariantError(caught instanceof Error ? caught.message : "Could not create variant");
      }
    } finally {
      setIsSubmittingVariant(false);
    }
  }

  function applyExistingVariant() {
    if (!variantDuplicate) return;
    const existing = variantDuplicate.existing;
    setForm((current) => ({
      ...current,
      product_id: existing.id,
      product_size_ml: existing.product_size_ml,
      variety: existing.variety,
      packaging_size: existing.packaging_size_name,
      packaging_size_name: existing.packaging_size_name,
      pieces_per_packet: existing.pieces_per_packet,
      packets_per_box_limit: existing.packets_per_box_limit,
    }));
    setShowNewVariantModal(false);
    setVariantDuplicate(null);
    setNewVariantForm(emptyNewVariant);
    setToast(`Existing variant selected: ${existing.product_size_ml}ml ${existing.variety} ${existing.packaging_size_name}`);
  }

  return (
    <div className="mx-auto max-w-5xl space-y-5">
      {toast ? <Toast message={toast} onClose={() => setToast("")} /> : null}
      {error ? <ErrorToast message={error} onClose={() => setError("")} /> : null}
      <header>
        <h1 className="text-2xl font-semibold text-zinc-950">Production Entry</h1>
        <p className="mt-1 text-sm text-zinc-500">Daily boxes, packets, sacks, and bottom rolls.</p>
        {mappingMessage ? <p className="mt-2 rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-sm font-medium text-amber-800">{mappingMessage}</p> : null}
      </header>

      <section className="rounded-lg border border-zinc-200 bg-white p-5 shadow-sm">
        <h2 className="text-lg font-semibold text-zinc-950">Today's Worker Production</h2>
        <p className="mb-4 text-sm text-zinc-500">Total: {(summary?.total_quantity || 0).toLocaleString()} boxes</p>
        <div className="space-y-2">
          {(summary?.workers || []).map((worker) => {
            const key = worker.worker_id || 0;
            const open = expandedWorker === key;
            return (
              <div key={key} className="rounded-md border border-zinc-200">
                <button className="flex w-full items-center justify-between px-4 py-3" type="button" onClick={() => setExpandedWorker(open ? null : key)}>
                  <span className="flex items-center gap-2 font-semibold">{open ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}{worker.worker_name}</span>
                  <span className="font-semibold text-brand-700">{worker.total_quantity.toLocaleString()} boxes</span>
                </button>
                {open ? <div className="border-t px-4 py-2">{worker.products.map((product) => <div key={product.production_id} className="flex justify-between py-1 text-sm"><span>{product.product_size_ml}ml {product.product_type}</span><span>{product.quantity.toLocaleString()} boxes</span></div>)}</div> : null}
              </div>
            );
          })}
          {!summary?.workers.length ? <p className="text-sm text-zinc-500">No production recorded today.</p> : null}
        </div>
      </section>

      <section className="rounded-lg border border-zinc-200 bg-white p-5 shadow-sm">
        <h2 className="mb-3 text-lg font-semibold">Today's Entries</h2>
        <div className="space-y-3">
          {batchHistory.map((batch) => (
            <div key={batch.id} className="rounded-lg border border-zinc-200">
              <div className="grid gap-2 bg-zinc-50 px-4 py-3 text-sm md:grid-cols-5">
                <strong>{batch.shift} Shift</strong>
                <span>{batch.worker_lines.length} workers</span>
                <span>{batch.total_boxes} boxes / {batch.total_loose_packets} loose</span>
                <span>Blank {batch.total_blank_bora} / Bottom {batch.total_bottom_roll}</span>
                <span>Wastage {batch.shift_wastage_kg} KG</span>
              </div>
              {batch.worker_lines.map((worker) => {
                const open = expandedBatchWorker === worker.id;
                return (
                  <div key={worker.id} className="border-t">
                    <button className="flex w-full items-center justify-between px-4 py-3 text-left" type="button" onClick={() => setExpandedBatchWorker(open ? null : worker.id)}>
                      <span className="font-semibold">{open ? <ChevronDown className="mr-2 inline h-4 w-4" /> : <ChevronRight className="mr-2 inline h-4 w-4" />}{worker.worker_name}</span>
                      <span className="text-sm">Blank {worker.blank_used_bora} bora / Bottom {worker.bottom_used_roll} roll</span>
                    </button>
                    {open ? <div className="border-t bg-white px-4 py-2">{worker.outputs.map((output) => <div key={output.id} className="flex flex-wrap justify-between gap-2 border-b py-2 text-sm last:border-0"><span>{output.product_size_ml}ml {output.variety} - {output.packaging_size_name}</span><span>{output.boxes_made} boxes / {output.loose_packets_made} loose / {output.carton_type}</span></div>)}</div> : null}
                  </div>
                );
              })}
            </div>
          ))}
          {!batchHistory.length ? <p className="text-sm text-zinc-500">No shift batches recorded today.</p> : null}
        </div>
      </section>

      <div className="grid gap-5 md:grid-cols-3">
        {/* Main Production Entry Card */}
        <section className="rounded-lg border border-zinc-200 bg-white p-5 shadow-sm md:col-span-2">
          <div className="mb-5 flex items-center gap-3">
            <span className="grid h-10 w-10 place-items-center rounded-md bg-brand-50 text-brand-700">
              <Factory className="h-5 w-5" />
            </span>
            <h2 className="text-lg font-semibold text-zinc-950">Daily Production</h2>
          </div>

          <h3 className="mb-3 text-sm font-semibold uppercase tracking-wide text-zinc-500">Production Form</h3>
          <div className="grid gap-4 md:grid-cols-2">
            <Field label="Date" type="date" value={form.date} onChange={(date) => setForm({ ...form, date })} />
            <StringSelectField label="Shift" value={form.shift} onChange={(shift) => setForm({ ...form, shift: shift as "Day" | "Night" })} options={["Day", "Night"]} />
            <SelectField
              label="Machine"
              value={form.machine_id}
              onChange={(machine_id) => void selectMachine(machine_id)}
            >
              <option value={0}>Select Machine</option>
              {machines.map((machine) => (
                <option key={machine.id} value={machine.id}>
                  {machine.machine_number || machine.id} - {machine.machine_name || machine.machine_type} - {machine.mould_size_ml || "No mould"}{machine.mould_size_ml ? " ml" : ""}
                </option>
              ))}
            </SelectField>
            <div className="flex flex-col justify-end">
              <span className="text-sm font-medium text-zinc-700">Need a new variant?</span>
              <button
                className="mt-1 inline-flex h-10 items-center justify-center gap-2 rounded-md border border-dashed border-brand-300 bg-brand-50 px-3 text-sm font-semibold text-brand-700 hover:bg-brand-100"
                type="button"
                disabled={!form.machine_id}
                onClick={() => {
                  setNewVariantForm({
                    ...emptyNewVariant,
                    product_size_ml: form.product_size_ml ? String(form.product_size_ml) : "",
                    variety: form.variety || "Plain White",
                    packaging_size_name: form.packaging_size_name || "",
                    pieces_per_packet: form.pieces_per_packet ? String(form.pieces_per_packet) : "100",
                    packets_per_box_limit: form.packets_per_box_limit ? String(form.packets_per_box_limit) : "10",
                  });
                  setVariantError("");
                  setVariantDuplicate(null);
                  setShowNewVariantModal(true);
                }}
              >
                <Plus className="h-4 w-4" />
                Add Variant
              </button>
            </div>
          </div>

          <div className="mt-5 space-y-4">
            {workerCards.map((card, cardIndex) => (
              <div key={cardIndex} className="rounded-xl border border-zinc-200 bg-zinc-50 p-4">
                <div className="flex items-center justify-between gap-3">
                  <h3 className="font-semibold text-zinc-950">Worker Production {cardIndex + 1}</h3>
                  {workerCards.length > 1 ? (
                    <button className="text-sm font-semibold text-red-600" type="button" onClick={() => setWorkerCards((cards) => cards.filter((_, index) => index !== cardIndex))}>
                      Remove Worker
                    </button>
                  ) : null}
                </div>
                <div className="mt-3 grid gap-3 md:grid-cols-3">
                  <SelectField label="Worker" value={card.worker_id} onChange={(worker_id) => setWorkerCards((cards) => cards.map((item, index) => index === cardIndex ? { ...item, worker_id } : item))}>
                    <option value={0}>Select Worker</option>
                    {workers.map((worker) => <option key={worker.id} value={worker.id}>{worker.name}</option>)}
                  </SelectField>
                  <NumberField label="Blank Used (Bora)" value={card.blank_used_bora} onChange={(blank_used_bora) => setWorkerCards((cards) => cards.map((item, index) => index === cardIndex ? { ...item, blank_used_bora } : item))} />
                  <NumberField label="Bottom Used (Roll)" value={card.bottom_used_roll} onChange={(bottom_used_roll) => setWorkerCards((cards) => cards.map((item, index) => index === cardIndex ? { ...item, bottom_used_roll } : item))} />
                </div>
                <label className="mt-3 block text-sm">
                  <span className="font-medium text-zinc-700">Worker Note</span>
                  <input className="mt-1 h-10 w-full rounded-md border border-zinc-200 bg-white px-3" value={card.note} onChange={(event) => setWorkerCards((cards) => cards.map((item, index) => index === cardIndex ? { ...item, note: event.target.value } : item))} />
                </label>
                <div className="mt-4 overflow-x-auto">
                  <table className="w-full min-w-[760px] text-left text-sm">
                    <thead><tr className="border-b text-zinc-500"><th className="pb-2">Product / Packaging</th><th>Carton</th><th>PCS / Packet</th><th>Packets / Box</th><th>Boxes</th><th>Loose</th><th /></tr></thead>
                    <tbody>
                      {card.outputs.map((output, outputIndex) => {
                        const sku = finalStockOptions.find((item) => item.id === output.finished_good_id);
                        return (
                          <tr key={outputIndex} className="border-b border-zinc-200">
                            <td className="py-2 pr-2">
                              <select className="h-10 w-full rounded-md border border-zinc-200 bg-white px-2" value={output.finished_good_id} onChange={(event) => {
                                const finished_good_id = Number(event.target.value);
                                setWorkerCards((cards) => cards.map((item, index) => index === cardIndex ? {
                                  ...item,
                                  outputs: item.outputs.map((line, lineIndex) => lineIndex === outputIndex ? { ...line, finished_good_id } : line),
                                } : item));
                              }}>
                                <option value={0}>Select SKU</option>
                                {finalStockOptions.map((item) => <option key={item.id} value={item.id}>{item.product_size_ml}ml {item.variety} - {item.packaging_size_name}</option>)}
                              </select>
                            </td>
                            <td>{sku?.carton_type || "--"}</td>
                            <td>{sku?.pieces_per_packet || "--"}</td>
                            <td>{sku?.packets_per_box || sku?.packets_per_box_limit || "--"}</td>
                            <td><input className="h-9 w-20 rounded border px-2" min={0} type="number" value={output.boxes_made} onChange={(event) => {
                              const boxes_made = numberOrDefault(event.target.value);
                              setWorkerCards((cards) => cards.map((item, index) => index === cardIndex ? { ...item, outputs: item.outputs.map((line, lineIndex) => lineIndex === outputIndex ? { ...line, boxes_made } : line) } : item));
                            }} /></td>
                            <td><input className="h-9 w-20 rounded border px-2" min={0} type="number" value={output.loose_packets_made} onChange={(event) => {
                              const loose_packets_made = numberOrDefault(event.target.value);
                              setWorkerCards((cards) => cards.map((item, index) => index === cardIndex ? { ...item, outputs: item.outputs.map((line, lineIndex) => lineIndex === outputIndex ? { ...line, loose_packets_made } : line) } : item));
                            }} /></td>
                            <td>{card.outputs.length > 1 ? <button className="text-red-600" type="button" onClick={() => setWorkerCards((cards) => cards.map((item, index) => index === cardIndex ? { ...item, outputs: item.outputs.filter((_, lineIndex) => lineIndex !== outputIndex) } : item))}>Remove</button> : null}</td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
                <button className="mt-3 inline-flex items-center gap-2 rounded-md border border-brand-300 px-3 py-2 text-sm font-semibold text-brand-700" type="button" onClick={() => setWorkerCards((cards) => cards.map((item, index) => index === cardIndex ? { ...item, outputs: [...item.outputs, emptyOutput()] } : item))}>
                  <Plus className="h-4 w-4" /> Add Output Line
                </button>
              </div>
            ))}
            <button className="inline-flex items-center gap-2 rounded-md bg-zinc-900 px-4 py-2 text-sm font-semibold text-white" type="button" onClick={() => setWorkerCards((cards) => [...cards, emptyWorkerCard()])}>
              <Plus className="h-4 w-4" /> Add Worker Production
            </button>
          </div>

          <ShiftBatchPreview workerCards={workerCards} options={finalStockOptions} wastage={shiftWastageKg} />

          {error ? <div className="mt-4 rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{error}</div> : null}

          <button className="mt-5 inline-flex h-10 items-center gap-2 rounded-md bg-brand-600 px-4 text-sm font-semibold text-white hover:bg-brand-700 disabled:bg-zinc-300" data-test-id="save-production-button" disabled={isSaving} type="button" onClick={submit}>
            <Check className="h-4 w-4" />
            {isSaving ? "Saving..." : "Save Shift Production"}
          </button>
        </section>

        {/* Shift Wastage Entry Card */}
        <section className="rounded-lg border border-zinc-200 bg-white p-5 shadow-sm self-start">
          <div className="mb-5 flex items-center gap-3">
            <span className="grid h-10 w-10 place-items-center rounded-md bg-amber-50 text-amber-700">
              <AlertTriangle className="h-5 w-5" />
            </span>
            <h2 className="text-lg font-semibold text-zinc-950">Shift Wastage Entry</h2>
          </div>

          <div className="space-y-4">
            <Field label="Date" type="date" value={wastageDate} onChange={(date) => setWastageDate(date)} />
            <StringSelectField label="Shift" value={wastageShift} onChange={(shift) => setWastageShift(shift as "Day" | "Night" | "Custom")} options={["Day", "Night", "Custom"]} />
            <NumberField label="Total Shift Wastage (KG)" value={shiftWastageKg} onChange={setShiftWastageKg} />
            <label className="block text-sm">
              <span className="font-medium text-zinc-700">Wastage Note / Reason</span>
              <input className="mt-1 h-10 w-full rounded-md border border-zinc-200 px-3 outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-100" value={wastageNote} onChange={(event) => setWastageNote(event.target.value)} />
            </label>

            <button className="w-full inline-flex h-10 items-center justify-center gap-2 rounded-md bg-amber-600 px-4 text-sm font-semibold text-white hover:bg-amber-700 disabled:bg-zinc-300" disabled={isSavingWastage} type="button" onClick={submitWastage}>
              <Check className="h-4 w-4" />
              {isSavingWastage ? "Saving..." : hasExistingWastage ? "Update Wastage" : "Save Wastage"}
            </button>
          </div>
        </section>
      </div>

      {showNewVariantModal ? (
        <div className="fixed inset-0 z-50 grid place-items-center bg-black/40 px-4" role="dialog" aria-modal="true" aria-label="Add new finished good variant">
          <div className="w-full max-w-lg rounded-xl bg-white p-5 shadow-xl">
            <div className="flex items-center justify-between">
              <h3 className="text-base font-semibold text-zinc-950">+ Add New Packing / Finished Good Variant</h3>
              <button
                aria-label="Close"
                className="grid h-8 w-8 place-items-center rounded-md text-zinc-500 hover:bg-zinc-100"
                type="button"
                onClick={() => {
                  setShowNewVariantModal(false);
                  setVariantError("");
                  setVariantDuplicate(null);
                }}
              >
                <X className="h-4 w-4" />
              </button>
            </div>
            <p className="mt-1 text-xs text-zinc-500">
              New variant will be available immediately in the Product / Variation dropdown.
            </p>

            <div className="mt-4 grid gap-3 md:grid-cols-2">
              <label className="block text-sm">
                <span className="font-medium text-zinc-700">Product Size (ml)</span>
                <input
                  className="mt-1 h-10 w-full rounded-md border border-zinc-200 px-3 outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-100"
                  inputMode="numeric"
                  placeholder="e.g. 250"
                  type="number"
                  value={newVariantForm.product_size_ml}
                  onChange={(event) => setNewVariantForm({ ...newVariantForm, product_size_ml: event.target.value })}
                />
              </label>
              <label className="block text-sm">
                <span className="font-medium text-zinc-700">Variety / Design</span>
                <input
                  className="mt-1 h-10 w-full rounded-md border border-zinc-200 px-3 outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-100"
                  placeholder="e.g. Plain White"
                  type="text"
                  value={newVariantForm.variety}
                  onChange={(event) => setNewVariantForm({ ...newVariantForm, variety: event.target.value })}
                />
              </label>
              <label className="block text-sm md:col-span-2">
                <span className="font-medium text-zinc-700">Packaging Size Name</span>
                <input
                  className="mt-1 h-10 w-full rounded-md border border-zinc-200 px-3 outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-100"
                  placeholder="e.g. 250ML - Plain White"
                  type="text"
                  value={newVariantForm.packaging_size_name}
                  onChange={(event) => setNewVariantForm({ ...newVariantForm, packaging_size_name: event.target.value })}
                />
              </label>
              <label className="block text-sm">
                <span className="font-medium text-zinc-700">Pieces per Packet</span>
                <input
                  className="mt-1 h-10 w-full rounded-md border border-zinc-200 px-3 outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-100"
                  inputMode="numeric"
                  type="number"
                  value={newVariantForm.pieces_per_packet}
                  onChange={(event) => setNewVariantForm({ ...newVariantForm, pieces_per_packet: event.target.value })}
                />
              </label>
              <label className="block text-sm">
                <span className="font-medium text-zinc-700">Packets per Box</span>
                <input
                  className="mt-1 h-10 w-full rounded-md border border-zinc-200 px-3 outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-100"
                  inputMode="numeric"
                  type="number"
                  value={newVariantForm.packets_per_box_limit}
                  onChange={(event) => setNewVariantForm({ ...newVariantForm, packets_per_box_limit: event.target.value })}
                />
              </label>
              <label className="block text-sm md:col-span-2">
                <span className="font-medium text-zinc-700">Opening Stock (boxes, default 0)</span>
                <input
                  className="mt-1 h-10 w-full rounded-md border border-zinc-200 px-3 outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-100"
                  inputMode="numeric"
                  type="number"
                  value={newVariantForm.opening_stock_boxes}
                  onChange={(event) => setNewVariantForm({ ...newVariantForm, opening_stock_boxes: event.target.value })}
                />
              </label>
            </div>

            {variantError ? (
              <div className="mt-3 rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800">
                {variantError}
              </div>
            ) : null}

            {variantDuplicate ? (
              <div className="mt-3 rounded-md border border-blue-200 bg-blue-50 px-3 py-2 text-sm text-blue-900">
                <p>
                  Existing variant: <strong>{variantDuplicate.existing.product_size_ml}ml {variantDuplicate.existing.variety}</strong>{" "}
                  {variantDuplicate.existing.packaging_size_name} (Stock: {variantDuplicate.existing.current_quantity})
                </p>
                <button
                  className="mt-2 inline-flex h-8 items-center rounded-md bg-blue-600 px-3 text-xs font-semibold text-white hover:bg-blue-700"
                  type="button"
                  onClick={applyExistingVariant}
                >
                  Select Existing Variant Instead
                </button>
              </div>
            ) : null}

            <div className="mt-5 flex justify-end gap-2">
              <button
                className="inline-flex h-10 items-center rounded-md border border-zinc-200 bg-white px-4 text-sm font-semibold text-zinc-700 hover:bg-zinc-50"
                type="button"
                onClick={() => {
                  setShowNewVariantModal(false);
                  setVariantError("");
                  setVariantDuplicate(null);
                }}
              >
                Cancel
              </button>
              <button
                className="inline-flex h-10 items-center gap-2 rounded-md bg-brand-600 px-4 text-sm font-semibold text-white hover:bg-brand-700 disabled:bg-zinc-300"
                disabled={isSubmittingVariant}
                type="button"
                onClick={handleCreateNewVariant}
              >
                {isSubmittingVariant ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />}
                {isSubmittingVariant ? "Saving..." : "Save New Variant"}
              </button>
            </div>
          </div>
        </div>
      ) : null}
      {rejecting ? (
        <div className="fixed inset-0 z-50 grid place-items-center bg-black/40 p-4">
          <div className="w-full max-w-md rounded-lg bg-white p-6 shadow-xl">
            <h2 className="text-lg font-semibold">Reject Production Entry</h2>
            <div className="mt-3 space-y-1 text-sm"><p>Worker: <strong>{rejecting.worker_name}</strong></p><p>Product: <strong>{rejecting.product_size_ml}ml {rejecting.product_type}</strong></p><p>Quantity: <strong>{rejecting.quantity_boxes.toLocaleString()}</strong></p><p>Date: <strong>{rejecting.date}</strong></p></div>
            <p className="mt-4 rounded-md border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">Rejecting this production will reverse inventory impact.</p>
            <label className="mt-4 block text-sm font-medium">Reason<textarea className="mt-1 min-h-24 w-full rounded-md border p-3" value={rejectReason} onChange={(event) => setRejectReason(event.target.value)} /></label>
            <div className="mt-5 flex justify-end gap-2"><button className="rounded-md border px-4 py-2" type="button" onClick={() => { setRejecting(null); setRejectReason(""); }}>Cancel</button><button className="rounded-md bg-red-700 px-4 py-2 font-semibold text-white disabled:bg-zinc-300" disabled={rejectReason.trim().length < 3 || isSaving} type="button" onClick={() => void confirmReject()}>Reject Production</button></div>
          </div>
        </div>
      ) : null}
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

function ProductSelectField({ label, value, options, disabled, onChange }: { label: string; value: number; options: FinalStockOption[]; disabled?: boolean; onChange: (value: number) => void }) {
  const cleanOptions = Array.isArray(options) ? options : [];
  const uniqueProducts = Array.from(new Map(cleanOptions.map((item) => [`${item.product_size_ml}-${item.variety}`, item])).values());
  return (
    <label className="block text-sm">
      <span className="font-medium text-zinc-700">{label}</span>
      <select disabled={disabled} className="mt-1 h-10 w-full rounded-md border border-zinc-200 px-3 outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-100 disabled:bg-zinc-100" value={value} onChange={(event) => onChange(Number(event.target.value))}>
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

function VariationSelectField({ label, value, options, disabled, onChange }: { label: string; value: number; options: FinalStockOption[]; disabled?: boolean; onChange: (value: number) => void }) {
  const cleanOptions = Array.isArray(options) ? options : [];
  return (
    <label className="block text-sm">
      <span className="font-medium text-zinc-700">{label}</span>
      <select disabled={disabled} className="mt-1 h-10 w-full rounded-md border border-zinc-200 px-3 outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-100 disabled:bg-zinc-100" value={value} onChange={(event) => onChange(Number(event.target.value))}>
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

function ShiftBatchPreview({
  workerCards,
  options,
  wastage,
}: {
  workerCards: WorkerCardDraft[];
  options: FinalStockOption[];
  wastage: number;
}) {
  const outputs = workerCards.flatMap((card) => card.outputs);
  const totalBoxes = outputs.reduce((sum, output) => sum + numberOrDefault(output.boxes_made), 0);
  const totalLoose = outputs.reduce((sum, output) => sum + numberOrDefault(output.loose_packets_made), 0);
  const totalBlank = workerCards.reduce((sum, card) => sum + numberOrDefault(card.blank_used_bora), 0);
  const totalBottom = workerCards.reduce((sum, card) => sum + numberOrDefault(card.bottom_used_roll), 0);
  const cartons = new Map<string, number>();
  const finished = new Map<string, string>();
  for (const output of outputs) {
    const sku = options.find((item) => item.id === output.finished_good_id);
    if (!sku) continue;
    const packetsPerBox = numberOrDefault(sku.packets_per_box || sku.packets_per_box_limit, 1);
    const converted = Math.floor((numberOrDefault(sku.loose_packets) + output.loose_packets_made) / packetsPerBox)
      - Math.floor(numberOrDefault(sku.loose_packets) / packetsPerBox);
    const added = output.boxes_made + converted;
    const carton = sku.carton_type || "Unmapped carton";
    cartons.set(carton, (cartons.get(carton) || 0) + added);
    finished.set(`${sku.product_size_ml}ml ${sku.variety} ${sku.packaging_size_name}`, `${added} boxes`);
  }
  return (
    <div className="mt-6 rounded-lg border border-brand-200 bg-brand-50 p-4">
      <h3 className="text-sm font-semibold uppercase tracking-wide text-brand-800">Shift Preview</h3>
      <div className="mt-3 grid gap-2 text-sm md:grid-cols-3">
        <p>Total workers: <strong>{workerCards.length}</strong></p>
        <p>Total boxes: <strong>{totalBoxes}</strong></p>
        <p>Total loose packets: <strong>{totalLoose}</strong></p>
        <p>Blank to deduct: <strong>{totalBlank} bora</strong></p>
        <p>Bottom to deduct: <strong>{totalBottom} rolls</strong></p>
        <p>Shift wastage: <strong>{numberOrDefault(wastage)} KG</strong></p>
      </div>
      <div className="mt-3 grid gap-3 md:grid-cols-2">
        <div><p className="font-semibold text-brand-900">Box stock to deduct</p>{Array.from(cartons).map(([name, value]) => <p key={name} className="text-sm">{name}: {value}</p>)}</div>
        <div><p className="font-semibold text-brand-900">Finished goods to add</p>{Array.from(finished).map(([name, value]) => <p key={name} className="text-sm">{name}: {value}</p>)}</div>
      </div>
    </div>
  );
}

function ErrorToast({ message, onClose }: { message: string; onClose: () => void }) {
  return (
    <button className="fixed right-5 top-20 z-50 max-w-md whitespace-pre-line rounded-md bg-red-700 px-4 py-3 text-left text-sm font-semibold text-white shadow-lg" type="button" onClick={onClose}>
      {message}
    </button>
  );
}
