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
  getProductionWorkerSummary,
  rejectDailyProduction,
} from "../lib/api";
import type {
  DailyProductionCreate,
  ProductionBatchCreate,
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
  const [workerRows, setWorkerRows] = useState([{
    worker_id: 0,
    boxes_made: 0,
    loose_packets_made: 0,
    blank_used_bora: 0,
    bottom_used_roll: 0,
    note: "",
  }]);
  const [shiftWastageKg, setShiftWastageKg] = useState(0);
  const [wastageNote, setWastageNote] = useState("");

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

  const selectedProduct = useMemo(
    () => finalStockOptions.find((item) => item.id === form.product_id),
    [finalStockOptions, form.product_id],
  );
  const packagingOptions = useMemo(
    () => selectedProduct
      ? finalStockOptions.filter(
          (item) =>
            item.product_size_ml === selectedProduct.product_size_ml
            && item.variety.trim().toLowerCase() === selectedProduct.variety.trim().toLowerCase(),
        )
      : [],
    [finalStockOptions, selectedProduct],
  );

  async function loadProductionVisibility() {
    const [summaryResponse, historyResponse] = await Promise.all([
      getProductionWorkerSummary(todayDate()),
      getDailyProductionHistory(todayDate()),
    ]);
    setSummary(summaryResponse.data);
    setHistory(historyResponse.data);
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
    if (!form.machine_id || !form.product_id || !selectedProduct) {
      setError("Inventory mapping incomplete for this SKU.");
      return;
    }
    if (!workerRows.length || workerRows.some((row) => !row.worker_id)) {
      setError("Select a worker for every production row.");
      return;
    }
    setIsSaving(true);
    setError("");
    try {
      const normalizedDate = dateOnly(form.date);
      const machineId = numberOrDefault(form.machine_id);
      const payload: ProductionBatchCreate = {
        date: normalizedDate,
        shift: String(form.shift || "Day"),
        machine_id: machineId,
        finished_good_id: numberOrDefault(form.product_id),
        product_size_ml: numberOrDefault(form.product_size_ml),
        variety_design: String(form.variety || "Standard/White").trim(),
        packaging_size_name: String(form.packaging_size_name || form.packaging_size || "").trim(),
        carton_type: String(selectedProduct.carton_type || ""),
        pcs_per_packet: numberOrDefault(form.pieces_per_packet, 1) || 1,
        packets_per_box: numberOrDefault(form.packets_per_box_limit, 1) || 1,
        worker_rows: workerRows.map((row) => ({
          worker_id: row.worker_id,
          boxes_made: numberOrDefault(row.boxes_made),
          loose_packets_made: numberOrDefault(row.loose_packets_made),
          blank_used_bora: numberOrDefault(row.blank_used_bora),
          bottom_used_roll: numberOrDefault(row.bottom_used_roll),
          note: row.note.trim() || null,
        })),
        shift_wastage_kg: numberOrDefault(shiftWastageKg),
        wastage_note: wastageNote.trim() || null,
      };
      const response = await createDailyProductionBatch(payload);
      setToast("Shift production batch saved successfully.");
      window.dispatchEvent(new CustomEvent("production:daily-saved", { detail: response.data }));
      window.dispatchEvent(new CustomEvent("attendance:updated", { detail: response.data }));
      window.dispatchEvent(new CustomEvent("inventory:updated", { detail: response.data }));
      void loadOptions();
      void loadProductionVisibility();
      setWorkerRows([{ worker_id: workers[0]?.id || 0, boxes_made: 0, loose_packets_made: 0, blank_used_bora: 0, bottom_used_roll: 0, note: "" }]);
      setShiftWastageKg(0);
      setWastageNote("");
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
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead><tr className="border-b text-zinc-500"><th className="py-2">Worker</th><th>Product</th><th>Production</th><th>Raw Material</th><th>Machine</th><th>Status</th><th /></tr></thead>
            <tbody>{history.map((entry) => <tr key={entry.id} className="border-b"><td className="py-3">{entry.worker_name}</td><td>{entry.product_size_ml}ml {entry.product_type}</td><td>{entry.quantity_boxes.toLocaleString()} boxes / {entry.loose_packets_made.toLocaleString()} loose</td><td>Blank: {entry.blank_used_bora} bora / {entry.blank_used_kg} KG<br />Bottom: {entry.bottom_used_rolls} roll</td><td>{entry.machine_name}</td><td className={entry.status === "REJECTED" ? "text-red-700" : "text-green-700"}>{entry.status}</td><td className="text-right">{entry.status === "ACTIVE" ? <button className="font-semibold text-red-700" type="button" onClick={() => setRejecting(entry)}>Reject</button> : null}</td></tr>)}</tbody>
          </table>
        </div>
      </section>

      <section className="rounded-lg border border-zinc-200 bg-white p-5 shadow-sm">
        <div className="mb-5 flex items-center gap-3">
          <span className="grid h-10 w-10 place-items-center rounded-md bg-brand-50 text-brand-700">
            <Factory className="h-5 w-5" />
          </span>
          <h2 className="text-lg font-semibold text-zinc-950">Daily Production</h2>
        </div>

        <h3 className="mb-3 text-sm font-semibold uppercase tracking-wide text-zinc-500">Shift Header</h3>
        <div className="grid gap-4 md:grid-cols-3">
          <Field label="Date" type="date" value={form.date} onChange={(date) => setForm({ ...form, date })} />
          <StringSelectField label="Shift" value={form.shift} onChange={(shift) => setForm({ ...form, shift: shift as "Day" | "Night" | "Custom" })} options={["Day", "Night", "Custom"]} />
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
          <ProductSelectField
            label="Product"
            value={form.product_id || 0}
            options={finalStockOptions}
            disabled={!form.machine_id}
            onChange={(product_id) => {
              const selected = finalStockOptions.find((item) => item.id === product_id);
              const firstPackaging = finalStockOptions.find(
                (item) =>
                  item.product_size_ml === selected?.product_size_ml
                  && item.variety.trim().toLowerCase() === selected?.variety.trim().toLowerCase(),
              );
              setForm({
                ...form,
                product_id: firstPackaging?.id || product_id,
                product_size_ml: selected?.product_size_ml || form.product_size_ml,
                variety: selected?.variety || form.variety,
                packaging_size: firstPackaging?.packaging_size || firstPackaging?.packaging_size_name || "",
                packaging_size_name: firstPackaging?.packaging_size_name || "",
                pieces_per_packet: firstPackaging?.pieces_per_packet || form.pieces_per_packet,
                packets_per_box_limit: firstPackaging?.packets_per_box || firstPackaging?.packets_per_box_limit || form.packets_per_box_limit
              });
            }}
          />
          <p className="self-end pb-2 text-xs text-zinc-500">Only products compatible with selected machine are shown.</p>
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
              + Add New Packing / Finished Good Variant
            </button>
          </div>
          <VariationSelectField
            label="Packaging Size Variation"
            value={form.product_id || 0}
            options={packagingOptions}
            disabled={!selectedProduct}
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
          <div className="self-end rounded-md border border-zinc-200 bg-zinc-50 px-3 py-2 text-sm text-zinc-700">
            Carton: <strong>{selectedProduct?.carton_type || "Not configured"}</strong>
          </div>
          <NumberField label="Pieces per Packet" value={form.pieces_per_packet} onChange={(pieces_per_packet) => setForm({ ...form, pieces_per_packet })} />
          <NumberField label="Packets per Box" value={form.packets_per_box_limit} onChange={(packets_per_box_limit) => setForm({ ...form, packets_per_box_limit })} />
        </div>

        <div className="mt-6 rounded-lg border border-zinc-200 bg-zinc-50 p-4">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-semibold uppercase tracking-wide text-zinc-500">Worker Production Rows</h3>
            <button className="rounded-md border bg-white px-3 py-2 text-sm font-semibold" type="button" onClick={() => setWorkerRows((rows) => [...rows, { worker_id: 0, boxes_made: 0, loose_packets_made: 0, blank_used_bora: 0, bottom_used_roll: 0, note: "" }])}>Add Worker Row</button>
          </div>
          <div className="mt-3 space-y-3">
            {workerRows.map((row, index) => (
              <div className="grid gap-3 rounded-md border bg-white p-3 md:grid-cols-6" key={index}>
                <SelectField label="Worker" value={row.worker_id} onChange={(worker_id) => setWorkerRows((rows) => rows.map((item, rowIndex) => rowIndex === index ? { ...item, worker_id } : item))}>
                  <option value={0}>Select Worker</option>
                  {workers.map((worker) => <option key={worker.id} value={worker.id}>{worker.name}</option>)}
                </SelectField>
                <NumberField label="Boxes Made" value={row.boxes_made} onChange={(boxes_made) => setWorkerRows((rows) => rows.map((item, rowIndex) => rowIndex === index ? { ...item, boxes_made } : item))} />
                <NumberField label="Loose Packets" value={row.loose_packets_made} onChange={(loose_packets_made) => setWorkerRows((rows) => rows.map((item, rowIndex) => rowIndex === index ? { ...item, loose_packets_made } : item))} />
                <NumberField label="Blank Used (Bora)" value={row.blank_used_bora} onChange={(blank_used_bora) => setWorkerRows((rows) => rows.map((item, rowIndex) => rowIndex === index ? { ...item, blank_used_bora } : item))} />
                <NumberField label="Bottom Used (Roll)" value={row.bottom_used_roll} onChange={(bottom_used_roll) => setWorkerRows((rows) => rows.map((item, rowIndex) => rowIndex === index ? { ...item, bottom_used_roll } : item))} />
                <div className="flex items-end gap-2">
                  <input className="h-10 min-w-0 flex-1 rounded-md border px-2 text-sm" placeholder="Optional note" value={row.note} onChange={(event) => setWorkerRows((rows) => rows.map((item, rowIndex) => rowIndex === index ? { ...item, note: event.target.value } : item))} />
                  <button className="h-10 rounded-md border px-3 text-red-700 disabled:text-zinc-300" disabled={workerRows.length === 1} type="button" onClick={() => setWorkerRows((rows) => rows.filter((_, rowIndex) => rowIndex !== index))}>Remove</button>
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="mt-6 rounded-lg border border-amber-200 bg-amber-50 p-4">
          <div className="flex items-center gap-2">
            <AlertTriangle className="h-4 w-4 text-amber-700" />
            <h3 className="text-sm font-semibold uppercase tracking-wide text-amber-800">Daily Wastage</h3>
          </div>
          <div className="mt-3 grid gap-4 md:grid-cols-2">
            <NumberField label="Total Shift Wastage (KG)" value={shiftWastageKg} onChange={setShiftWastageKg} />
            <label className="text-sm font-medium text-zinc-700">Wastage Note / Reason<input className="mt-1 h-10 w-full rounded-md border bg-white px-3" value={wastageNote} onChange={(event) => setWastageNote(event.target.value)} /></label>
          </div>
        </div>

        <BatchPreview workerRows={workerRows} packetsPerBox={numberOrDefault(form.packets_per_box_limit, 1)} previousLoose={numberOrDefault(selectedProduct?.loose_packets)} cartonType={selectedProduct?.carton_type || "Carton"} wastageKg={shiftWastageKg} />

        {error ? <div className="mt-4 rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{error}</div> : null}

        <button className="mt-5 inline-flex h-10 items-center gap-2 rounded-md bg-brand-600 px-4 text-sm font-semibold text-white hover:bg-brand-700 disabled:bg-zinc-300" data-test-id="save-production-button" disabled={isSaving} type="button" onClick={submit}>
          <Check className="h-4 w-4" />
          {isSaving ? "Saving..." : "Save Production"}
        </button>
      </section>

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

function BatchPreview({
  workerRows,
  packetsPerBox,
  previousLoose,
  cartonType,
  wastageKg,
}: {
  workerRows: Array<{ boxes_made: number; loose_packets_made: number; blank_used_bora: number; bottom_used_roll: number }>;
  packetsPerBox: number;
  previousLoose: number;
  cartonType: string;
  wastageKg: number;
}) {
  const boxes = workerRows.reduce((total, row) => total + numberOrDefault(row.boxes_made), 0);
  const loose = workerRows.reduce((total, row) => total + numberOrDefault(row.loose_packets_made), 0);
  const converted = Math.floor((previousLoose + loose) / Math.max(packetsPerBox, 1)) - Math.floor(previousLoose / Math.max(packetsPerBox, 1));
  const remaining = (previousLoose + loose) % Math.max(packetsPerBox, 1);
  const blank = workerRows.reduce((total, row) => total + numberOrDefault(row.blank_used_bora), 0);
  const bottom = workerRows.reduce((total, row) => total + numberOrDefault(row.bottom_used_roll), 0);
  return (
    <div className="mt-6 rounded-lg border border-brand-200 bg-brand-50 p-4">
      <h3 className="text-sm font-semibold uppercase tracking-wide text-brand-800">Preview Before Save</h3>
      <div className="mt-3 grid gap-2 text-sm md:grid-cols-3">
        <p>Total boxes made: <strong>{boxes}</strong></p>
        <p>Total loose packets: <strong>{loose}</strong></p>
        <p>Converted loose boxes: <strong>{converted}</strong></p>
        <p>Remaining loose packets: <strong>{remaining}</strong></p>
        <p>Finished goods to add: <strong>{boxes + converted} boxes</strong></p>
        <p>{cartonType} stock to deduct: <strong>{boxes + converted}</strong></p>
        <p>Blank to deduct: <strong>{blank} bora</strong></p>
        <p>Bottom to deduct: <strong>{bottom} rolls</strong></p>
        <p>Shift wastage: <strong>{wastageKg} kg</strong></p>
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
