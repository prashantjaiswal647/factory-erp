import {
  BadgeCheck,
  Boxes,
  Building2,
  Check,
  ChevronDown,
  Edit3,
  Factory,
  Plus,
  Save,
  Trash2,
  UsersRound
} from "lucide-react";
import type { Dispatch, SetStateAction } from "react";
import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";

import { completeOnboarding } from "../lib/api";
import type { OnboardingPayload } from "../lib/api";

type SectionKey = "factory" | "machines" | "materials" | "workers";
type MaterialType = OnboardingPayload["raw_materials"][number]["type"];
type MaterialUnit = OnboardingPayload["raw_materials"][number]["unit"];

type FactoryInfo = {
  factoryName: string;
  primaryCupSize: number;
  defaultGsm: number;
  expectedShift: string;
};

const sectionOrder: SectionKey[] = ["factory", "machines", "materials", "workers"];

const initialFactoryInfo: FactoryInfo = {
  factoryName: "",
  primaryCupSize: 210,
  defaultGsm: 185,
  expectedShift: "Day"
};

const initialPayload: OnboardingPayload = {
  machines: [],
  raw_materials: [],
  packaging_profiles: [],
  material_yields: [],
  costing_master: {
    paper_price_per_kg: 0,
    bottom_roll_price_per_kg: 0,
    polybag_price: 0,
    carton_price: 0,
    labour_cost_per_box: 0,
    electricity_cost_per_box: 0
  },
  workers: [],
  customers: []
};

const defaultMachine = {
  name: "",
  speed_bpm: 55,
  current_mould_size: "",
  current_bottom_size: "",
  can_swap_moulds: true
};

const defaultMaterial = {
  name: "",
  type: "Paper Blank" as MaterialType,
  size_ml: 210,
  gsm: 185,
  stock_quantity: 0,
  price_per_unit: 0,
  unit: "kg" as MaterialUnit
};

const defaultWorker = {
  name: "",
  daily_salary: 0,
  shift_type: "Day"
};

export default function OnboardingPage() {
  const [factoryInfo, setFactoryInfo] = useState<FactoryInfo>(initialFactoryInfo);
  const [payload, setPayload] = useState<OnboardingPayload>(initialPayload);
  const [openSection, setOpenSection] = useState<SectionKey>("factory");
  const [completedSections, setCompletedSections] = useState<Record<SectionKey, boolean>>({
    factory: false,
    machines: false,
    materials: false,
    workers: false
  });
  const [machineDraft, setMachineDraft] = useState(defaultMachine);
  const [materialDraft, setMaterialDraft] = useState(defaultMaterial);
  const [workerDraft, setWorkerDraft] = useState(defaultWorker);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const navigate = useNavigate();

  const completedCount = sectionOrder.filter((key) => completedSections[key]).length;
  const canSave = completedCount === sectionOrder.length;
  const progress = Math.round((completedCount / sectionOrder.length) * 100);

  const validation = useMemo(
    () => ({
      factory: factoryInfo.factoryName.trim().length > 1 && factoryInfo.primaryCupSize > 0 && factoryInfo.defaultGsm > 0,
      machines: payload.machines.length > 0,
      materials:
        payload.raw_materials.length > 0 &&
        payload.packaging_profiles.length > 0 &&
        payload.material_yields.length >= 2 &&
        payload.costing_master.paper_price_per_kg > 0 &&
        payload.costing_master.bottom_roll_price_per_kg > 0,
      workers: payload.workers.length > 0
    }),
    [factoryInfo, payload]
  );

  function completeSection(section: SectionKey) {
    if (!validation[section]) {
      return;
    }

    setCompletedSections((current) => ({ ...current, [section]: true }));
    const nextSection = sectionOrder[sectionOrder.indexOf(section) + 1];
    if (nextSection) {
      window.setTimeout(() => setOpenSection(nextSection), 160);
    }
  }

  function editSection(section: SectionKey) {
    setCompletedSections((current) => ({ ...current, [section]: false }));
    setOpenSection(section);
  }

  async function saveAll() {
    if (!canSave) {
      return;
    }

    setIsSaving(true);
    setError(null);
    try {
      await completeOnboarding(payload);
      navigate("/");
    } catch {
      setError("Onboarding could not be saved. Please check the entered setup data.");
    } finally {
      setIsSaving(false);
    }
  }

  return (
    <div className="min-h-[calc(100vh-8rem)] bg-gray-50 pb-24">
      <div className="mx-auto max-w-5xl px-4 py-6">
        <header className="mb-6 rounded-xl border border-gray-200 bg-white p-5 shadow-md">
          <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
            <div className="flex items-start gap-4">
              <div className="grid h-12 w-12 shrink-0 place-items-center rounded-xl bg-brand-600 text-white shadow-md">
                <Factory className="h-6 w-6" />
              </div>
              <div>
                <p className="text-sm font-semibold text-brand-700">Factory Setup</p>
                <h1 className="mt-1 text-2xl font-semibold text-gray-950">Paper Cup Onboarding</h1>
                <p className="mt-1 text-sm text-gray-500">Configure your factory workspace in one focused flow.</p>
              </div>
            </div>
            <div className="min-w-48 rounded-xl bg-gray-50 p-3">
              <div className="mb-2 flex items-center justify-between text-xs font-semibold text-gray-500">
                <span>{completedCount}/{sectionOrder.length} complete</span>
                <span>{progress}%</span>
              </div>
              <div className="h-2 overflow-hidden rounded-full bg-gray-200">
                <div className="h-full rounded-full bg-brand-600 transition-all duration-300" style={{ width: `${progress}%` }} />
              </div>
            </div>
          </div>
        </header>

        <main className="space-y-3">
          <AccordionSection
            icon={Building2}
            title="1. Factory Info"
            summary={factorySummary(factoryInfo)}
            isOpen={openSection === "factory"}
            isComplete={completedSections.factory}
            onOpen={() => setOpenSection("factory")}
            onEdit={() => editSection("factory")}
          >
            <div className="grid gap-4 md:grid-cols-4">
              <TextField label="Factory Name" value={factoryInfo.factoryName} onChange={(value) => setFactoryInfo((draft) => ({ ...draft, factoryName: value }))} className="md:col-span-2" />
              <NumberField label="Primary Cup Size" value={factoryInfo.primaryCupSize} onChange={(value) => {
                setFactoryInfo((draft) => ({ ...draft, primaryCupSize: value }));
                setMaterialDraft((draft) => ({ ...draft, size_ml: value }));
              }} />
              <NumberField label="Default GSM" value={factoryInfo.defaultGsm} onChange={(value) => {
                setFactoryInfo((draft) => ({ ...draft, defaultGsm: value }));
                setMaterialDraft((draft) => ({ ...draft, gsm: value }));
              }} />
            </div>
            <div className="mt-5 flex justify-end">
              <CompleteButton disabled={!validation.factory} onClick={() => completeSection("factory")} />
            </div>
          </AccordionSection>

          <AccordionSection
            icon={Factory}
            title="2. Machines"
            summary={`${payload.machines.length} machine${payload.machines.length === 1 ? "" : "s"} added`}
            isOpen={openSection === "machines"}
            isComplete={completedSections.machines}
            onOpen={() => setOpenSection("machines")}
            onEdit={() => editSection("machines")}
          >
            <QuickMachineRow draft={machineDraft} setDraft={setMachineDraft} onAdd={() => {
              if (!machineDraft.name.trim()) {
                return;
              }
              setPayload((draft) => ({ ...draft, machines: [...draft.machines, { ...machineDraft, name: machineDraft.name.trim() }] }));
              setMachineDraft({ ...defaultMachine, name: `Machine ${payload.machines.length + 2}` });
            }} />
            <ChipGrid>
              {payload.machines.map((machine, index) => (
                <DataChip key={`${machine.name}-${index}`} title={machine.name} meta={`${machine.speed_bpm} BPM · ${machine.current_mould_size || "No mould"}`} onRemove={() => removeArrayItem(setPayload, "machines", index)} />
              ))}
            </ChipGrid>
            <div className="mt-5 flex justify-end">
              <CompleteButton disabled={!validation.machines} onClick={() => completeSection("machines")} />
            </div>
          </AccordionSection>

          <AccordionSection
            icon={Boxes}
            title="3. Materials"
            summary={`${payload.raw_materials.length} materials · ${payload.packaging_profiles.length} package profile${payload.packaging_profiles.length === 1 ? "" : "s"}`}
            isOpen={openSection === "materials"}
            isComplete={completedSections.materials}
            onOpen={() => setOpenSection("materials")}
            onEdit={() => editSection("materials")}
          >
            <div className="grid gap-5 xl:grid-cols-[1.15fr_0.85fr]">
              <div className="space-y-5">
                <QuickMaterialRow draft={materialDraft} setDraft={setMaterialDraft} onAdd={() => {
                  setPayload((draft) => ({ ...draft, raw_materials: [...draft.raw_materials, normalizeMaterial(materialDraft)] }));
                  setMaterialDraft({ ...defaultMaterial, size_ml: factoryInfo.primaryCupSize, gsm: factoryInfo.defaultGsm });
                }} />
                <ChipGrid>
                  {payload.raw_materials.map((material, index) => (
                    <DataChip key={`${material.type}-${index}`} title={material.name || material.type} meta={`${material.size_ml || "-"}ml · ${material.stock_quantity} ${material.unit || ""}`} onRemove={() => removeArrayItem(setPayload, "raw_materials", index)} />
                  ))}
                </ChipGrid>
              </div>

              <div className="space-y-4 rounded-xl border border-gray-200 bg-gray-50 p-4">
                <h3 className="text-sm font-semibold text-gray-900">Default packaging and costing</h3>
                <div className="grid gap-3 sm:grid-cols-2">
                  <NumberField label="Cups/Polybag" value={payload.packaging_profiles[0]?.cups_per_polybag ?? 100} onChange={(value) => setPrimaryPackaging(setPayload, factoryInfo, "cups_per_polybag", value)} />
                  <NumberField label="Polybags/Box" value={payload.packaging_profiles[0]?.polybags_per_box ?? 10} onChange={(value) => setPrimaryPackaging(setPayload, factoryInfo, "polybags_per_box", value)} />
                  <NumberField label="Paper/kg" value={payload.costing_master.paper_price_per_kg} onChange={(value) => setCosting(setPayload, "paper_price_per_kg", value)} />
                  <NumberField label="Bottom/kg" value={payload.costing_master.bottom_roll_price_per_kg} onChange={(value) => setCosting(setPayload, "bottom_roll_price_per_kg", value)} />
                  <NumberField label="Polybag" value={payload.costing_master.polybag_price} onChange={(value) => setCosting(setPayload, "polybag_price", value)} />
                  <NumberField label="Carton" value={payload.costing_master.carton_price} onChange={(value) => setCosting(setPayload, "carton_price", value)} />
                  <NumberField label="Labour/Box" value={payload.costing_master.labour_cost_per_box} onChange={(value) => setCosting(setPayload, "labour_cost_per_box", value)} />
                  <NumberField label="Electricity/Box" value={payload.costing_master.electricity_cost_per_box} onChange={(value) => setCosting(setPayload, "electricity_cost_per_box", value)} />
                </div>
                <button
                  type="button"
                  onClick={() => seedMaterialYield(setPayload, factoryInfo)}
                  className="inline-flex h-10 items-center gap-2 rounded-xl border border-gray-200 bg-white px-3 text-sm font-semibold text-gray-700 shadow-sm transition hover:border-brand-200 hover:text-brand-700"
                >
                  <Plus className="h-4 w-4" />
                  Add default yield
                </button>
              </div>
            </div>
            <div className="mt-5 flex justify-end">
              <CompleteButton disabled={!validation.materials} onClick={() => completeSection("materials")} />
            </div>
          </AccordionSection>

          <AccordionSection
            icon={UsersRound}
            title="4. Workers"
            summary={`${payload.workers.length} worker${payload.workers.length === 1 ? "" : "s"} added`}
            isOpen={openSection === "workers"}
            isComplete={completedSections.workers}
            onOpen={() => setOpenSection("workers")}
            onEdit={() => editSection("workers")}
          >
            <QuickWorkerRow draft={workerDraft} setDraft={setWorkerDraft} onAdd={() => {
              if (!workerDraft.name.trim()) {
                return;
              }
              setPayload((draft) => ({ ...draft, workers: [...draft.workers, { ...workerDraft, name: workerDraft.name.trim() }] }));
              setWorkerDraft({ ...defaultWorker, shift_type: factoryInfo.expectedShift });
            }} />
            <ChipGrid>
              {payload.workers.map((worker, index) => (
                <DataChip key={`${worker.name}-${index}`} title={worker.name} meta={`${worker.shift_type || "Shift"} · ₹${worker.daily_salary}/day`} onRemove={() => removeArrayItem(setPayload, "workers", index)} />
              ))}
            </ChipGrid>
            <div className="mt-5 flex justify-end">
              <CompleteButton disabled={!validation.workers} onClick={() => completeSection("workers")} />
            </div>
          </AccordionSection>
        </main>
      </div>

      <div className="fixed inset-x-0 bottom-0 z-20 border-t border-gray-200 bg-white/95 px-4 py-3 shadow-lg backdrop-blur">
        <div className="mx-auto flex max-w-5xl flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <p className="text-sm font-semibold text-gray-900">Ready to save setup</p>
            <p className="text-xs text-gray-500">All sections must be completed and collapsed before saving.</p>
            {error ? <p className="mt-1 text-xs font-semibold text-red-600">{error}</p> : null}
          </div>
          <button
            type="button"
            disabled={!canSave || isSaving}
            onClick={saveAll}
            className="inline-flex h-11 items-center justify-center gap-2 rounded-xl bg-brand-600 px-5 text-sm font-semibold text-white shadow-md transition hover:bg-brand-700 disabled:cursor-not-allowed disabled:bg-gray-300 disabled:shadow-none"
          >
            <Save className="h-4 w-4" />
            {isSaving ? "Saving..." : "Save All to Database"}
          </button>
        </div>
      </div>
    </div>
  );
}

function AccordionSection({
  icon: Icon,
  title,
  summary,
  isOpen,
  isComplete,
  onOpen,
  onEdit,
  children
}: {
  icon: typeof Factory;
  title: string;
  summary: string;
  isOpen: boolean;
  isComplete: boolean;
  onOpen: () => void;
  onEdit: () => void;
  children: React.ReactNode;
}) {
  return (
    <section className="overflow-hidden rounded-xl border border-gray-200 bg-white shadow-md transition-all duration-300">
      <button
        type="button"
        onClick={isComplete ? onEdit : onOpen}
        className="flex w-full items-center justify-between gap-4 px-5 py-4 text-left"
      >
        <span className="flex min-w-0 items-center gap-3">
          <span className={["grid h-10 w-10 shrink-0 place-items-center rounded-xl", isComplete ? "bg-emerald-50 text-emerald-700" : "bg-gray-100 text-gray-700"].join(" ")}>
            {isComplete ? <Check className="h-5 w-5" /> : <Icon className="h-5 w-5" />}
          </span>
          <span className="min-w-0">
            <span className="block text-base font-semibold text-gray-950">{title}</span>
            <span className="block truncate text-sm text-gray-500">{isComplete ? summary : "Complete this section to continue"}</span>
          </span>
        </span>
        <span className="flex shrink-0 items-center gap-2">
          {isComplete ? (
            <span className="inline-flex h-9 items-center gap-2 rounded-xl border border-emerald-200 bg-emerald-50 px-3 text-sm font-semibold text-emerald-700">
              <BadgeCheck className="h-4 w-4" />
              Done
              <Edit3 className="h-4 w-4" />
            </span>
          ) : (
            <ChevronDown className={["h-5 w-5 text-gray-400 transition-transform duration-300", isOpen ? "rotate-180" : ""].join(" ")} />
          )}
        </span>
      </button>
      <div className={["grid transition-all duration-300", isOpen && !isComplete ? "grid-rows-[1fr]" : "grid-rows-[0fr]"].join(" ")}>
        <div className="overflow-hidden">
          <div className="border-t border-gray-100 px-5 py-5">{children}</div>
        </div>
      </div>
    </section>
  );
}

function QuickMachineRow({
  draft,
  setDraft,
  onAdd
}: {
  draft: typeof defaultMachine;
  setDraft: Dispatch<SetStateAction<typeof defaultMachine>>;
  onAdd: () => void;
}) {
  return (
    <div className="grid gap-3 rounded-xl border border-gray-200 bg-gray-50 p-4 md:grid-cols-[1.2fr_0.8fr_1fr_1fr_auto]">
      <TextField label="Machine" value={draft.name} onChange={(value) => setDraft((current) => ({ ...current, name: value }))} />
      <NumberField label="BPM" value={draft.speed_bpm} onChange={(value) => setDraft((current) => ({ ...current, speed_bpm: value }))} />
      <TextField label="Mould" value={draft.current_mould_size} onChange={(value) => setDraft((current) => ({ ...current, current_mould_size: value }))} />
      <TextField label="Bottom" value={draft.current_bottom_size} onChange={(value) => setDraft((current) => ({ ...current, current_bottom_size: value }))} />
      <AddButton onClick={onAdd} />
    </div>
  );
}

function QuickMaterialRow({
  draft,
  setDraft,
  onAdd
}: {
  draft: typeof defaultMaterial;
  setDraft: Dispatch<SetStateAction<typeof defaultMaterial>>;
  onAdd: () => void;
}) {
  return (
    <div className="grid gap-3 rounded-xl border border-gray-200 bg-gray-50 p-4 md:grid-cols-[1fr_0.7fr_0.7fr_0.8fr_0.8fr_auto]">
      <label className="space-y-1 text-sm">
        <span className="font-semibold text-gray-700">Type</span>
        <select className="h-10 w-full rounded-xl border border-gray-200 bg-white px-3 outline-none transition focus:border-brand-500 focus:ring-2 focus:ring-brand-100" value={draft.type} onChange={(event) => setDraft((current) => ({
          ...current,
          type: event.target.value as MaterialType,
          unit: event.target.value === "Polybag" || event.target.value === "Carton Box" ? "pieces" : "kg"
        }))}>
          {["Paper Blank", "Bottom Roll", "Polybag", "Carton Box"].map((option) => <option key={option} value={option}>{option}</option>)}
        </select>
      </label>
      <NumberField label="ML" value={draft.size_ml ?? 0} onChange={(value) => setDraft((current) => ({ ...current, size_ml: value }))} />
      <NumberField label="GSM" value={draft.gsm ?? 0} onChange={(value) => setDraft((current) => ({ ...current, gsm: value }))} />
      <NumberField label="Stock" value={draft.stock_quantity} onChange={(value) => setDraft((current) => ({ ...current, stock_quantity: value }))} />
      <NumberField label="Price" value={draft.price_per_unit} onChange={(value) => setDraft((current) => ({ ...current, price_per_unit: value }))} />
      <AddButton onClick={onAdd} />
    </div>
  );
}

function QuickWorkerRow({
  draft,
  setDraft,
  onAdd
}: {
  draft: typeof defaultWorker;
  setDraft: Dispatch<SetStateAction<typeof defaultWorker>>;
  onAdd: () => void;
}) {
  return (
    <div className="grid gap-3 rounded-xl border border-gray-200 bg-gray-50 p-4 md:grid-cols-[1.2fr_0.8fr_0.8fr_auto]">
      <TextField label="Worker" value={draft.name} onChange={(value) => setDraft((current) => ({ ...current, name: value }))} />
      <NumberField label="Daily Salary" value={draft.daily_salary} onChange={(value) => setDraft((current) => ({ ...current, daily_salary: value }))} />
      <TextField label="Shift" value={draft.shift_type ?? ""} onChange={(value) => setDraft((current) => ({ ...current, shift_type: value }))} />
      <AddButton onClick={onAdd} />
    </div>
  );
}

function TextField({ label, value, onChange, className = "" }: { label: string; value: string; onChange: (value: string) => void; className?: string }) {
  return (
    <label className={["space-y-1 text-sm", className].join(" ")}>
      <span className="font-semibold text-gray-700">{label}</span>
      <input className="h-10 w-full rounded-xl border border-gray-200 bg-white px-3 outline-none transition focus:border-brand-500 focus:ring-2 focus:ring-brand-100" value={value} onChange={(event) => onChange(event.target.value)} />
    </label>
  );
}

function NumberField({ label, value, onChange }: { label: string; value: number; onChange: (value: number) => void }) {
  return (
    <label className="space-y-1 text-sm">
      <span className="font-semibold text-gray-700">{label}</span>
      <input className="h-10 w-full rounded-xl border border-gray-200 bg-white px-3 outline-none transition focus:border-brand-500 focus:ring-2 focus:ring-brand-100" min="0" type="number" value={value} onChange={(event) => onChange(Number(event.target.value))} />
    </label>
  );
}

function AddButton({ onClick }: { onClick: () => void }) {
  return (
    <button type="button" onClick={onClick} className="mt-auto inline-flex h-10 items-center justify-center gap-2 rounded-xl bg-gray-950 px-4 text-sm font-semibold text-white shadow-md transition hover:bg-gray-800">
      <Plus className="h-4 w-4" />
      Add
    </button>
  );
}

function CompleteButton({ disabled, onClick }: { disabled: boolean; onClick: () => void }) {
  return (
    <button type="button" disabled={disabled} onClick={onClick} className="inline-flex h-10 items-center gap-2 rounded-xl bg-brand-600 px-4 text-sm font-semibold text-white shadow-md transition hover:bg-brand-700 disabled:cursor-not-allowed disabled:bg-gray-300 disabled:shadow-none">
      <Check className="h-4 w-4" />
      Complete Section
    </button>
  );
}

function ChipGrid({ children }: { children: React.ReactNode }) {
  return <div className="mt-4 flex flex-wrap gap-2">{children}</div>;
}

function DataChip({ title, meta, onRemove }: { title: string; meta: string; onRemove: () => void }) {
  return (
    <span className="inline-flex max-w-full items-center gap-3 rounded-xl border border-gray-200 bg-white px-3 py-2 text-sm shadow-sm">
      <span className="min-w-0">
        <span className="block truncate font-semibold text-gray-900">{title}</span>
        <span className="block truncate text-xs text-gray-500">{meta}</span>
      </span>
      <button type="button" onClick={onRemove} className="grid h-7 w-7 shrink-0 place-items-center rounded-lg text-gray-400 transition hover:bg-red-50 hover:text-red-600" aria-label={`Remove ${title}`}>
        <Trash2 className="h-4 w-4" />
      </button>
    </span>
  );
}

function factorySummary(factoryInfo: FactoryInfo) {
  if (!factoryInfo.factoryName.trim()) {
    return "Factory details pending";
  }
  return `${factoryInfo.factoryName} · ${factoryInfo.primaryCupSize}ml · ${factoryInfo.defaultGsm}gsm`;
}

function normalizeMaterial(material: typeof defaultMaterial) {
  const name = [material.type, material.size_ml ? `${material.size_ml}ml` : "", material.gsm ? `${material.gsm}gsm` : ""]
    .filter(Boolean)
    .join(" ");
  return {
    ...material,
    name,
    size_ml: material.size_ml || null,
    gsm: material.gsm || null
  };
}

function seedMaterialYield(setPayload: Dispatch<SetStateAction<OnboardingPayload>>, factoryInfo: FactoryInfo) {
  setPayload((draft) => ({
    ...draft,
    packaging_profiles: [
      {
        product_name_ml: factoryInfo.primaryCupSize,
        cups_per_polybag: draft.packaging_profiles[0]?.cups_per_polybag ?? 100,
        polybags_per_box: draft.packaging_profiles[0]?.polybags_per_box ?? 10,
        box_size_name: `${factoryInfo.primaryCupSize}ml Carton`
      }
    ],
    material_yields: [
      { material_type: "Blank", size_ml: factoryInfo.primaryCupSize, gsm: factoryInfo.defaultGsm, pieces_per_kg: 380 },
      { material_type: "Bottom", size_ml: factoryInfo.primaryCupSize, gsm: factoryInfo.defaultGsm, pieces_per_kg: 2500 }
    ]
  }));
}

function setPrimaryPackaging(
  setPayload: Dispatch<SetStateAction<OnboardingPayload>>,
  factoryInfo: FactoryInfo,
  field: "cups_per_polybag" | "polybags_per_box",
  value: number
) {
  setPayload((draft) => ({
    ...draft,
    packaging_profiles: [
      {
        product_name_ml: factoryInfo.primaryCupSize,
        cups_per_polybag: field === "cups_per_polybag" ? value : draft.packaging_profiles[0]?.cups_per_polybag ?? 100,
        polybags_per_box: field === "polybags_per_box" ? value : draft.packaging_profiles[0]?.polybags_per_box ?? 10,
        box_size_name: draft.packaging_profiles[0]?.box_size_name ?? `${factoryInfo.primaryCupSize}ml Carton`
      }
    ]
  }));
}

function setCosting<K extends keyof OnboardingPayload["costing_master"]>(
  setPayload: Dispatch<SetStateAction<OnboardingPayload>>,
  key: K,
  value: number
) {
  setPayload((draft) => ({
    ...draft,
    costing_master: { ...draft.costing_master, [key]: value }
  }));
}

function removeArrayItem<K extends keyof Pick<OnboardingPayload, "machines" | "raw_materials" | "workers">>(
  setPayload: Dispatch<SetStateAction<OnboardingPayload>>,
  key: K,
  index: number
) {
  setPayload((draft) => ({
    ...draft,
    [key]: (draft[key] as unknown[]).filter((_, itemIndex) => itemIndex !== index)
  }));
}
