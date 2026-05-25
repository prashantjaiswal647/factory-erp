import { Check, Factory, PackageCheck, Plus, Settings, Trash2, UserRound } from "lucide-react";
import { useEffect, useState } from "react";

import { createBlankStock, createBottomStock, createBoxPackagingStock, createMachineOnboarding, createMachines, createPlasticStock, createWorker, getFinalStockOptions, getMachineLimits, listMachineTemplates, saveFinalProductOpeningStock } from "../lib/api";
import type { BoxPackagingStockCreate, FinalStockOption, MachineCreate, MachineLimitUsage, MachineTemplateRecord, PlasticStockCreate, WorkerCreate, OpeningAttendancePayload } from "../lib/api";
import ConfigurationOverview from "../components/ConfigurationOverview";
import PhoneNumberInput from "../components/PhoneNumberInput";
import { useAuth } from "../context/AuthContext";
import { useUpgrade } from "../context/UpgradeContext";

const todayWorker: WorkerCreate = { name: "", country_code: "+91", phone: "", daily_wages: 0, duty_hours: 8 };
const blankStockDraft = { material_name: "Blank", size_ml: 210, kg_per_sack: 20, total_sacks: 0 };
const bottomStockDraft = { bottom_size_mm: 68, bag_weight_kg: null as number | null, rolls_per_bag: null as number | null, total_bags: null as number | null, total_rolls: null as number | null, total_weight_kg: null as number | null };
const boxStockDraft: BoxPackagingStockCreate = { box_type: "Small Box", quantity: 0, price_per_box: 0 };
const plasticStockDraft: PlasticStockCreate = { plastic_size_name: "", cup_size_ml: 210, total_boras: 0, weight_per_bora_kg: 20, price_per_kg: 0 };
const finalProductStockDraft = { product_id: 0, initial_quantity: 0 };
const machineDraft: MachineCreate = {
  machine_type: "Paper Cup",
  machine_number: "",
  mould_size_ml: 210,
  bottom_size_mm: 68,
  speed_per_minute: 55
};
type DynamicField = { label: string; value: string; source: "template" | "custom" };

export default function OnboardingPage() {
  const [step, setStep] = useState(0);
  const [toast, setToast] = useState("");
  const [worker, setWorker] = useState<WorkerCreate>(todayWorker);
  const [showOpeningAttendance, setShowOpeningAttendance] = useState(false);
  const [openingAttendance, setOpeningAttendance] = useState<OpeningAttendancePayload>({
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
  const [machine, setMachine] = useState<MachineCreate>(machineDraft);
  const [machines, setMachines] = useState<MachineCreate[]>([]);
  const [machineTemplates, setMachineTemplates] = useState<MachineTemplateRecord[]>([]);
  const [dynamicMachineFields, setDynamicMachineFields] = useState<DynamicField[]>([]);
  const [blankStock, setBlankStock] = useState(blankStockDraft);
  const [bottomStock, setBottomStock] = useState(bottomStockDraft);
  const [boxStock, setBoxStock] = useState<BoxPackagingStockCreate>(boxStockDraft);
  const [plasticStock, setPlasticStock] = useState<PlasticStockCreate>(plasticStockDraft);
  const [finalProductStock, setFinalProductStock] = useState(finalProductStockDraft);
  const [finalProducts, setFinalProducts] = useState<FinalStockOption[]>([]);
  const [machineUsage, setMachineUsage] = useState<MachineLimitUsage | null>(null);
  const [isSaving, setIsSaving] = useState(false);
  const { showToast, showUpgradeModal } = useUpgrade();
  const { updateUser, user } = useAuth();

  // Dynamic & Custom Final Product opening stock metrics states
  const [isCustomMode, setIsCustomMode] = useState(false);
  const [isCustomSizeOverride, setIsCustomSizeOverride] = useState(false);
  const [customSize, setCustomSize] = useState("");
  const [selectedSize, setSelectedSize] = useState("");
  const [customVariety, setCustomVariety] = useState("Standard/White");
  const [customPackagingName, setCustomPackagingName] = useState("");
  const [customPiecesPerPacket, setCustomPiecesPerPacket] = useState(100);
  const [customPacketsPerBox, setCustomPacketsPerBox] = useState(10);
  const [initialQuantity, setInitialQuantity] = useState(0);

  useEffect(() => {
    void loadFinalProducts();
    void loadMachineUsage();
    void loadMachineTemplates();
  }, []);

  useEffect(() => {
    applyTemplateFields(machine.machine_type);
  }, [machineTemplates]);

  async function loadFinalProducts() {
    try {
      const response = await getFinalStockOptions();
      setFinalProducts(response.data);
      setFinalProductStock((current) => ({
        ...current,
        product_id: current.product_id || response.data[0]?.id || 0
      }));
    } catch (err) {
      console.error("Failed to load final product options:", err);
      setFinalProducts([]);
    }
  }

  async function loadMachineUsage() {
    try {
      const response = await getMachineLimits();
      setMachineUsage(response.data);
      updateUser({
        machines_used: response.data.used,
        machine_limit: response.data.limit,
        machine_plan: response.data.plan
      });
      if (response.data.nearing_limit && !response.data.limit_reached) {
        showToast(`You have ${response.data.used}/${response.data.limit} machines used`, "warning");
      }
    } catch (err) {
      console.error("Failed to load machine limits/usage:", err);
      setMachineUsage(null);
    }
  }

  async function loadMachineTemplates() {
    try {
      const templates = await listMachineTemplates();
      setMachineTemplates(templates.filter((template) => template.status === "approved"));
    } catch (err) {
      console.error("Failed to load machine templates:", err);
      setMachineTemplates([]);
    }
  }

  function applyTemplateFields(machineType: MachineCreate["machine_type"]) {
    const template = machineTemplates.find((item) => item.machine_type === machineType && item.status === "approved");
    if (!template) {
      setDynamicMachineFields([]);
      return;
    }
    const fields = Object.keys({ ...template.base_config, ...template.custom_fields }).map((label) => ({
      label,
      value: "",
      source: "template" as const
    }));
    setDynamicMachineFields(fields);
  }

  async function saveWorker() {
    if (!worker.name.trim()) return;
    if (showOpeningAttendance) {
      if (!openingAttendance.period_start || !openingAttendance.period_end) {
        setToast("Opening attendance start and end dates are required.");
        return;
      }
      if (new Date(openingAttendance.period_start) > new Date(openingAttendance.period_end)) {
        setToast("Opening attendance start date must be before or equal to end date.");
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
        setToast("Opening attendance values cannot be negative.");
        return;
      }
    }

    setIsSaving(true);
    try {
      const payload: WorkerCreate = {
        ...worker,
        opening_attendance: showOpeningAttendance ? {
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
        } : undefined
      };

      const response = await createWorker(payload);
      const newWorker = response.data;
      setToast(`Worker ${newWorker.name || ""} saved`);
      setWorker(todayWorker);
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
      setStep(1);
    } catch (caught) {
      console.error("Failed to save worker during onboarding:", caught);
      setToast("Worker save failed.");
    } finally {
      setIsSaving(false);
    }
  }

  async function saveMachines() {
    if (machines.length === 0 && !machine.machine_number.trim()) return;
    const saveCount = machines.length ? machines.length : 1;
    if (machineUsage && machineUsage.used + saveCount > machineUsage.limit) {
      showUpgradeModal({
        code: "UPGRADE_REQUIRED",
        message: `You have reached your limit of ${machineUsage.limit} machines.`,
        used: machineUsage.used,
        limit: machineUsage.limit,
        plan: machineUsage.plan
      });
      return;
    }
    setIsSaving(true);
    try {
      await createMachines(machines.length ? machines : [machine]);
      if (dynamicMachineFields.length > 0) {
        await createMachineOnboarding({
          machine_type: machine.machine_type,
          base_config: {},
          custom_fields: dynamicMachineFields.reduce<Record<string, string>>((acc, field) => {
            if (field.label.trim()) acc[field.label.trim()] = field.value;
            return acc;
          }, {})
        });
      }
      setToast("Machines saved");
      setStep(2);
      await loadMachineUsage();
    } catch (caught) {
      console.error("Failed to save machines during onboarding:", caught);
      setToast("Machine save failed.");
    } finally {
      setIsSaving(false);
    }
  }

  async function addBlankStock() {
    setIsSaving(true);
    try {
      await createBlankStock(blankStock);
      setToast("Blank stock saved");
      setBlankStock(blankStockDraft);
    } catch (caught) {
      console.error("Failed to save blank stock during onboarding:", caught);
      setToast("Blank stock save failed.");
    } finally {
      setIsSaving(false);
    }
  }

  async function addBottomStock() {
    setIsSaving(true);
    try {
      await createBottomStock(bottomStock);
      setToast("Bottom stock saved");
      setBottomStock(bottomStockDraft);
    } catch (caught) {
      console.error("Failed to save bottom stock during onboarding:", caught);
      setToast("Bottom stock save failed.");
    } finally {
      setIsSaving(false);
    }
  }

  async function addBoxStock() {
    setIsSaving(true);
    try {
      await createBoxPackagingStock(boxStock);
      setToast("Box stock saved");
      setBoxStock(boxStockDraft);
    } catch (caught) {
      console.error("Failed to save box stock during onboarding:", caught);
      setToast("Box stock save failed.");
    } finally {
      setIsSaving(false);
    }
  }

  async function addPlasticStock() {
    setIsSaving(true);
    try {
      await createPlasticStock(plasticStock);
      setToast("Plastic stock saved");
      setPlasticStock(plasticStockDraft);
    } catch (caught) {
      console.error("Failed to save plastic stock during onboarding:", caught);
      setToast("Plastic stock save failed.");
    } finally {
      setIsSaving(false);
    }
  }

  async function addFinalProductStock() {
    setIsSaving(true);
    try {
      let payload: any;
      if (isCustomMode) {
        const productSize = isCustomSizeOverride ? Number(customSize) : Number(selectedSize);
        if (!productSize || isNaN(productSize)) {
          setToast("Please select or enter a valid Product Size (ML).");
          setIsSaving(false);
          return;
        }

        payload = {
          factory_id: String(user?.factory_id || localStorage.getItem("factory_id") || ""),
          product_size_ml: productSize,
          variety: String(customVariety || "Standard/White"),
          packaging_size: String(customPackagingName || `${productSize}ml Standard Box`),
          packaging_size_name: String(customPackagingName || `${productSize}ml Standard Box`),
          pieces_per_packet: Number(customPiecesPerPacket) || 100,
          packets_per_box_limit: Number(customPacketsPerBox) || 1000,
          initial_quantity: Number(initialQuantity) || 0,
          current_quantity: Number(initialQuantity) || 0,
          total_boxes: Number(initialQuantity) || 0,
          loose_packets: 0
        };
      } else {
        if (!finalProductStock.product_id) {
          setToast("Please select a product.");
          setIsSaving(false);
          return;
        }

        payload = {
          factory_id: String(user?.factory_id || localStorage.getItem("factory_id") || ""),
          product_id: Number(finalProductStock.product_id),
          initial_quantity: Number(finalProductStock.initial_quantity),
          current_quantity: Number(finalProductStock.initial_quantity),
          total_boxes: Number(finalProductStock.initial_quantity)
        };
      }

      await saveFinalProductOpeningStock(payload);
      setToast("Final product opening stock saved");
      
      // Reset custom inputs on success
      setCustomSize("");
      setSelectedSize("");
      setCustomVariety("Standard/White");
      setCustomPackagingName("");
      setCustomPiecesPerPacket(100);
      setCustomPacketsPerBox(10);
      setInitialQuantity(0);
      setFinalProductStock(finalProductStockDraft);
      
      await loadFinalProducts();
    } catch (caught) {
      console.error("Failed to save final product opening stock during onboarding:", caught);
      setToast("Final product stock save failed.");
    } finally {
      setIsSaving(false);
    }
  }

  function updateBottomStock(patch: Partial<typeof bottomStockDraft>) {
    const previousSuggestedRolls = (bottomStock.rolls_per_bag || 0) * (bottomStock.total_bags || 0);
    const previousSuggestedWeight = Number(((bottomStock.bag_weight_kg || 0) * (bottomStock.total_bags || 0)).toFixed(3));
    const next = { ...bottomStock, ...patch };
    const nextSuggestedRolls = (next.rolls_per_bag || 0) * (next.total_bags || 0);
    const nextSuggestedWeight = Number(((next.bag_weight_kg || 0) * (next.total_bags || 0)).toFixed(3));

    setBottomStock({
      ...next,
      total_rolls:
        next.total_rolls === null || next.total_rolls === previousSuggestedRolls
          ? nextSuggestedRolls
          : next.total_rolls,
      total_weight_kg:
        next.total_weight_kg === null || next.total_weight_kg === previousSuggestedWeight
          ? nextSuggestedWeight
          : next.total_weight_kg
    });
  }

  return (
    <div className="mx-auto max-w-5xl space-y-5">
      {toast ? <Toast message={toast} onClose={() => setToast("")} /> : null}
      <header>
        <h1 className="text-2xl font-semibold text-zinc-950">Onboarding Wizard</h1>
        <p className="mt-1 text-sm text-zinc-500">Workers, machines, and material metrics.</p>
      </header>

      <ConfigurationOverview />

      <div className="grid gap-3 md:grid-cols-4">
        {["Workers", "Machines", "Raw Materials", "Final Product Stock"].map((label, index) => (
          <button
            key={label}
            className={`flex h-12 items-center justify-center rounded-md border text-sm font-semibold ${
              step === index ? "border-[#6D28D9] bg-[#F3E8FF] text-[#4C1D95]" : "border-[#E5E7EB] bg-white text-[#4B5563]"
            }`}
            type="button"
            onClick={() => setStep(index)}
          >
            {label}
          </button>
        ))}
      </div>

      {step === 0 ? (
        <Panel icon={UserRound} title="Worker">
          <div className="grid gap-3 md:grid-cols-3">
            <TextInput label="Name" value={worker.name} onChange={(name) => setWorker({ ...worker, name })} />
            <PhoneNumberInput
              countryCode={worker.country_code || "+91"}
              localNumber={worker.phone || ""}
              onCountryCodeChange={(country_code) => setWorker({ ...worker, country_code })}
              onLocalNumberChange={(phone) => setWorker({ ...worker, phone })}
            />
            <NumberInput label="Daily wages" value={worker.daily_wages} onChange={(daily_wages) => setWorker({ ...worker, daily_wages })} />
            <NumberInput label="Duty hours" value={worker.duty_hours} onChange={(duty_hours) => setWorker({ ...worker, duty_hours })} />
          </div>

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
              <div className="space-y-4 p-4 bg-zinc-50 rounded-lg border border-zinc-200 shadow-inner" data-testid="opening-attendance-section">
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
                <div className="grid grid-cols-3 gap-3">
                  <label className="block text-xs">
                    <span className="font-semibold text-zinc-600">Present</span>
                    <input
                      type="number"
                      step="0.5"
                      placeholder="0"
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
                      placeholder="0"
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
                      placeholder="0"
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
                      placeholder="0"
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
                      placeholder="0"
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
                      placeholder="0"
                      className="mt-1 h-9 w-full rounded border border-zinc-200 px-2 outline-none text-xs"
                      value={openingAttendance.paid_leave_days || ""}
                      onChange={(e) => setOpeningAttendance({ ...openingAttendance, paid_leave_days: Number(e.target.value) })}
                    />
                  </label>
                  <label className="block text-xs">
                    <span className="font-semibold text-zinc-600">Overtime Hours</span>
                    <input
                      type="number"
                      placeholder="0"
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
                    className="mt-1 w-full rounded border border-zinc-200 p-2 outline-none text-xs"
                    rows={2}
                    placeholder="Add some notes..."
                    value={openingAttendance.notes}
                    onChange={(e) => setOpeningAttendance({ ...openingAttendance, notes: e.target.value })}
                  />
                </label>
              </div>
            )}
          </div>

          <SaveButton label="Save Worker" isSaving={isSaving} onClick={saveWorker} />
        </Panel>
      ) : null}

      {step === 1 ? (
        <Panel icon={Factory} title="Machines">
          {machineUsage ? (
            <div className={`mb-4 rounded-md border px-4 py-3 text-sm ${machineUsage.limit_reached ? "border-red-200 bg-red-50 text-red-700" : machineUsage.nearing_limit ? "border-amber-200 bg-amber-50 text-amber-800" : "border-zinc-200 bg-zinc-50 text-zinc-600"}`}>
              {machineUsage.limit_reached
                ? `You have reached your limit of ${machineUsage.limit} machines.`
                : `Machine usage: ${machineUsage.used}/${machineUsage.limit}`}
            </div>
          ) : null}
          <div className="grid gap-3 md:grid-cols-5">
            <TextInput label="Machine no." value={machine.machine_number} onChange={(machine_number) => setMachine({ ...machine, machine_number })} />
            <SelectInput label="Type" value={machine.machine_type} options={["Paper Cup", "Dona", "Paper Bag"]} onChange={(machine_type) => {
              const nextType = machine_type as MachineCreate["machine_type"];
              setMachine({ ...machine, machine_type: nextType });
              applyTemplateFields(nextType);
            }} />
            <NumberInput label="Mould ml" value={machine.mould_size_ml} onChange={(mould_size_ml) => setMachine({ ...machine, mould_size_ml })} />
            <NumberInput label="Bottom mm" value={machine.bottom_size_mm} onChange={(bottom_size_mm) => setMachine({ ...machine, bottom_size_mm })} />
            <NumberInput label="Speed/min" value={machine.speed_per_minute} onChange={(speed_per_minute) => setMachine({ ...machine, speed_per_minute })} />
          </div>
          <div className="mt-4 rounded-md border border-zinc-200 bg-zinc-50 p-4">
            <div className="flex items-center justify-between gap-3">
              <div>
                <p className="text-sm font-semibold text-zinc-800">Template Fields</p>
                <p className="mt-1 text-xs text-zinc-500">Fields load from approved machine templates. Add extra parameters when needed.</p>
              </div>
              <button
                className="inline-flex h-9 items-center gap-2 rounded-md border border-zinc-200 bg-white px-3 text-xs font-semibold text-zinc-700"
                type="button"
                onClick={() => setDynamicMachineFields([...dynamicMachineFields, { label: "", value: "", source: "custom" }])}
              >
                <Plus className="h-3.5 w-3.5" />
                Add Custom Field
              </button>
            </div>
            {dynamicMachineFields.length > 0 ? (
              <div className="mt-4 grid gap-3 md:grid-cols-2">
                {dynamicMachineFields.map((field, index) => (
                  <div key={`${field.source}-${field.label}-${index}`} className="grid grid-cols-[1fr_1fr_auto] gap-2">
                    <input
                      className="h-10 rounded-md border border-zinc-200 px-3 text-sm outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-100"
                      placeholder="Label"
                      value={field.label}
                      readOnly={field.source === "template"}
                      onChange={(event) => setDynamicMachineFields(dynamicMachineFields.map((item, itemIndex) => itemIndex === index ? { ...item, label: event.target.value } : item))}
                    />
                    <input
                      className="h-10 rounded-md border border-zinc-200 px-3 text-sm outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-100"
                      placeholder="Value"
                      value={field.value}
                      onChange={(event) => setDynamicMachineFields(dynamicMachineFields.map((item, itemIndex) => itemIndex === index ? { ...item, value: event.target.value } : item))}
                    />
                    <button className="grid h-10 w-10 place-items-center rounded-md border border-zinc-200 text-zinc-500 hover:text-red-600" type="button" onClick={() => setDynamicMachineFields(dynamicMachineFields.filter((_, itemIndex) => itemIndex !== index))}>
                      <Trash2 className="h-4 w-4" />
                    </button>
                  </div>
                ))}
              </div>
            ) : (
              <p className="mt-4 text-sm text-zinc-500">No approved template fields found for this machine type yet.</p>
            )}
          </div>
          <div className="mt-4 flex gap-2">
            <button
              className="inline-flex h-10 items-center gap-2 rounded-md border border-zinc-200 bg-white px-3 text-sm font-semibold text-zinc-700"
              type="button"
              disabled={machineUsage ? machineUsage.used + machines.length >= machineUsage.limit : false}
              title={machineUsage && machineUsage.used + machines.length >= machineUsage.limit ? "Machine limit reached" : "Add row"}
              onClick={() => {
                if (!machine.machine_number.trim()) return;
                if (machineUsage && machineUsage.used + machines.length >= machineUsage.limit) {
                  showUpgradeModal({
                    code: "UPGRADE_REQUIRED",
                    message: `You have reached your limit of ${machineUsage.limit} machines.`,
                    used: machineUsage.used,
                    limit: machineUsage.limit,
                    plan: machineUsage.plan
                  });
                  return;
                }
                setMachines([...machines, machine]);
                setMachine({ ...machineDraft, machine_number: "" });
              }}
            >
              <Plus className="h-4 w-4" />
              Add row
            </button>
            <SaveButton label="Save Machines" isSaving={isSaving} disabled={Boolean(machineUsage?.limit_reached)} onClick={saveMachines} />
          </div>
          <List rows={machines.map((row) => `${row.machine_number} / ${row.mould_size_ml}ml / ${row.speed_per_minute} per min`)} onRemove={(index) => setMachines(machines.filter((_, itemIndex) => itemIndex !== index))} />
        </Panel>
      ) : null}

      {step === 2 ? (
        <Panel icon={Settings} title="Raw Materials">
          <div className="grid gap-5 xl:grid-cols-2">
            <MaterialCard title="Blank Stock">
              <div className="grid gap-3 md:grid-cols-2">
                <TextInput label="Material Name" value={blankStock.material_name} onChange={(material_name) => setBlankStock({ ...blankStock, material_name })} />
                <NumberInput label="Size (ml)" value={blankStock.size_ml} onChange={(size_ml) => setBlankStock({ ...blankStock, size_ml })} />
                <NumberInput label="KG per Sack" value={blankStock.kg_per_sack} onChange={(kg_per_sack) => setBlankStock({ ...blankStock, kg_per_sack })} />
                <NumberInput label="Total Sacks" value={blankStock.total_sacks} onChange={(total_sacks) => setBlankStock({ ...blankStock, total_sacks })} />
              </div>
              <Readout label="Total Weight (KG)" value={Number((blankStock.kg_per_sack * blankStock.total_sacks).toFixed(3))} />
              <StockButton label="Add Blank Stock" color="green" isSaving={isSaving} onClick={addBlankStock} />
            </MaterialCard>

            <MaterialCard title="Bottom Stock">
              <div className="mt-3 grid gap-3 md:grid-cols-4">
                <NumberInput label="Bottom Size (mm)" value={bottomStock.bottom_size_mm} onChange={(bottom_size_mm) => updateBottomStock({ bottom_size_mm })} />
                <OptionalNumberInput label="Bag Weight (kg)" value={bottomStock.bag_weight_kg} onChange={(bag_weight_kg) => updateBottomStock({ bag_weight_kg })} />
                <OptionalNumberInput label="Individual Rolls per Bag" value={bottomStock.rolls_per_bag} onChange={(rolls_per_bag) => updateBottomStock({ rolls_per_bag })} />
                <OptionalNumberInput label="Total Number of Bags" value={bottomStock.total_bags} onChange={(total_bags) => updateBottomStock({ total_bags })} />
              </div>
              <div className="mt-4 grid gap-3 md:grid-cols-2">
                <OptionalNumberInput label="Total Individual Rolls" value={bottomStock.total_rolls} onChange={(total_rolls) => setBottomStock({ ...bottomStock, total_rolls })} />
                <OptionalNumberInput label="Total Weight (KG)" value={bottomStock.total_weight_kg} onChange={(total_weight_kg) => setBottomStock({ ...bottomStock, total_weight_kg })} />
              </div>
              <StockButton label="Add Bottom Stock" color="teal" isSaving={isSaving} onClick={addBottomStock} />
            </MaterialCard>

            <MaterialCard title="Box Packaging Stock">
              <div className="grid gap-3 md:grid-cols-3">
                <SelectInput label="Box Type" value={boxStock.box_type} options={["Small Box", "Big Box"]} onChange={(box_type) => setBoxStock({ ...boxStock, box_type: box_type as BoxPackagingStockCreate["box_type"] })} />
                <NumberInput label="Box Quantity (Pieces)" value={boxStock.quantity} onChange={(quantity) => setBoxStock({ ...boxStock, quantity })} />
                <NumberInput label="Price per Box (Rs)" value={boxStock.price_per_box} onChange={(price_per_box) => setBoxStock({ ...boxStock, price_per_box })} />
              </div>
              <StockButton label="Add Box Stock" color="blue" isSaving={isSaving} onClick={addBoxStock} />
            </MaterialCard>

            <MaterialCard title="PP Plastic Packaging Stock">
              <div className="grid gap-3 md:grid-cols-2">
                <TextInput label="Plastic Size/Type" value={plasticStock.plastic_size_name} onChange={(plastic_size_name) => setPlasticStock({ ...plasticStock, plastic_size_name })} />
                <SelectInput label="Used for Cup Size (ml)" value={String(plasticStock.cup_size_ml)} options={["65", "100", "150", "210", "250"]} onChange={(cup_size_ml) => setPlasticStock({ ...plasticStock, cup_size_ml: Number(cup_size_ml) })} />
                <NumberInput label="Total Boras (Sacks)" value={plasticStock.total_boras} onChange={(total_boras) => setPlasticStock({ ...plasticStock, total_boras })} />
                <NumberInput label="Weight per Bora (KG)" value={plasticStock.weight_per_bora_kg} onChange={(weight_per_bora_kg) => setPlasticStock({ ...plasticStock, weight_per_bora_kg })} />
                <NumberInput label="Price per KG (Rs)" value={plasticStock.price_per_kg} onChange={(price_per_kg) => setPlasticStock({ ...plasticStock, price_per_kg })} />
              </div>
              <div className="mt-4 grid gap-3 md:grid-cols-1">
                <Readout label="Total Plastic (KG)" value={Number((plasticStock.total_boras * plasticStock.weight_per_bora_kg).toFixed(3))} />
              </div>
              <StockButton label="Add Plastic Stock" color="purple" isSaving={isSaving} onClick={addPlasticStock} />
            </MaterialCard>
          </div>
        </Panel>
      ) : null}

      {step === 3 ? (
        <Panel icon={PackageCheck} title="Final Product Stock">
          {/* Mode Selector Tab Group */}
          <div className="flex rounded-lg bg-zinc-100 p-1 mb-5 max-w-md">
            <button
              type="button"
              className={`flex-1 py-1.5 text-xs font-semibold rounded-md transition-all ${
                !isCustomMode
                  ? "bg-white text-zinc-900 shadow-sm"
                  : "text-zinc-600 hover:text-zinc-900"
              }`}
              onClick={() => setIsCustomMode(false)}
            >
              Select Existing Product
            </button>
            <button
              type="button"
              className={`flex-1 py-1.5 text-xs font-semibold rounded-md transition-all ${
                isCustomMode
                  ? "bg-white text-zinc-900 shadow-sm"
                  : "text-zinc-600 hover:text-zinc-900"
              }`}
              onClick={() => setIsCustomMode(true)}
            >
              Create Custom Entry
            </button>
          </div>

          {!isCustomMode ? (
            /* Mode 1: Select Existing Product */
            <div className="space-y-4">
              <div className="grid gap-3 md:grid-cols-[2fr_1fr]">
                <SelectInput
                  label="Product"
                  value={String(finalProductStock.product_id)}
                  options={finalProducts.map((product) => ({
                    label: `${product.product_size_ml}ml ${product.variety} / ${product.packaging_size_name} - current ${product.current_quantity ?? product.total_boxes} boxes`,
                    value: String(product.id)
                  }))}
                  onChange={(product_id) => setFinalProductStock({ ...finalProductStock, product_id: Number(product_id) })}
                />
                <NumberInput
                  label="Initial Quantity (Boxes)"
                  value={finalProductStock.initial_quantity}
                  onChange={(initial_quantity) => setFinalProductStock({ ...finalProductStock, initial_quantity })}
                />
              </div>
              {finalProducts.length === 0 ? (
                <p className="mt-4 rounded-md bg-amber-50 p-3 text-sm text-amber-800">
                  No existing finished goods products found in the database. Please use the "Create Custom Entry" tab to enter stock directly, or add product packaging metrics in the previous step.
                </p>
              ) : null}
              <SaveButton
                label="Save Opening Stock"
                isSaving={isSaving}
                disabled={finalProducts.length === 0}
                onClick={addFinalProductStock}
              />
            </div>
          ) : (
            /* Mode 2: Create Custom Entry (Hybrid Combo-box Component) */
            <div className="space-y-5">
              <div className="grid gap-4 md:grid-cols-2 bg-zinc-50/50 p-5 rounded-xl border border-zinc-200 shadow-sm">
                {/* Hybrid Combo-box Product Size (ML) block */}
                <div>
                  <label className="block text-sm font-semibold text-zinc-700">
                    Product Size (ML)
                  </label>
                  <div className="mt-1 relative">
                    {!isCustomSizeOverride ? (
                      <select
                        className="h-10 w-full rounded-md border border-zinc-200 px-3 outline-none bg-white focus:border-brand-500 focus:ring-2 focus:ring-brand-100 text-sm font-medium text-zinc-800"
                        value={selectedSize}
                        onChange={(e) => setSelectedSize(e.target.value)}
                      >
                        <option value="">-- Choose processed size --</option>
                        {Array.from(new Set([
                          ...machines.map(m => Number(m.mould_size_ml)),
                          ...finalProducts.map(p => Number(p.product_size_ml)).filter(Boolean)
                        ])).sort((a, b) => a - b).map((size) => (
                          <option key={size} value={size}>
                            {size} ml
                          </option>
                        ))}
                      </select>
                    ) : (
                      <input
                        type="text"
                        placeholder="Type custom size (e.g. 120)"
                        className="h-10 w-full rounded-md border border-zinc-200 px-3 outline-none bg-white focus:border-brand-500 focus:ring-2 focus:ring-brand-100 text-sm font-medium text-zinc-800"
                        value={customSize}
                        onChange={(e) => setCustomSize(e.target.value.replace(/\D/g, ""))}
                      />
                    )}
                  </div>
                  <label className="flex items-center gap-1.5 mt-2 cursor-pointer select-none text-xs text-brand-600 font-semibold hover:text-brand-700">
                    <input
                      type="checkbox"
                      className="h-3.5 w-3.5 rounded border-zinc-300 text-brand-600 focus:ring-brand-500"
                      checked={isCustomSizeOverride}
                      onChange={(e) => {
                        setIsCustomSizeOverride(e.target.checked);
                        if (!e.target.checked) {
                          setCustomSize("");
                        }
                      }}
                    />
                    <span>Enter custom size manually (e.g., 120ml override)</span>
                  </label>
                </div>

                <div>
                  <TextInput
                    label="Variety / Design"
                    value={customVariety}
                    onChange={(val) => setCustomVariety(val)}
                  />
                  <p className="mt-1 text-[11px] text-zinc-400">e.g., Standard/White, Printed, Brown Kraft</p>
                </div>

                <div>
                  <TextInput
                    label="Packaging Size Name (Optional)"
                    value={customPackagingName}
                    onChange={(val) => setCustomPackagingName(val)}
                  />
                  <p className="mt-1 text-[11px] text-zinc-400">e.g., Big Box, Small Box. (Auto-generates if empty)</p>
                </div>

                <div className="grid grid-cols-2 gap-3">
                  <NumberInput
                    label="Pcs / Packet"
                    value={customPiecesPerPacket}
                    onChange={(val) => setCustomPiecesPerPacket(val)}
                  />
                  <NumberInput
                    label="Packets / Box"
                    value={customPacketsPerBox}
                    onChange={(val) => setCustomPacketsPerBox(val)}
                  />
                </div>
              </div>

              <div className="grid gap-3 md:grid-cols-2">
                <NumberInput
                  label="Initial Quantity (Boxes)"
                  value={initialQuantity}
                  onChange={(val) => setInitialQuantity(val)}
                />
              </div>

              <SaveButton
                label="Save Custom Opening Stock"
                isSaving={isSaving}
                onClick={addFinalProductStock}
              />
            </div>
          )}
        </Panel>
      ) : null}
    </div>
  );

}

function Panel({ icon: Icon, title, children }: { icon: typeof UserRound; title: string; children: React.ReactNode }) {
  return (
    <section className="rounded-lg border border-zinc-200 bg-white p-5 shadow-sm">
      <div className="mb-5 flex items-center gap-3">
        <span className="grid h-10 w-10 place-items-center rounded-md bg-brand-50 text-brand-700">
          <Icon className="h-5 w-5" />
        </span>
        <h2 className="text-lg font-semibold text-zinc-950">{title}</h2>
      </div>
      {children}
    </section>
  );
}

function TextInput({ label, value, onChange }: { label: string; value: string; onChange: (value: string) => void }) {
  return (
    <label className="block text-sm">
      <span className="font-medium text-zinc-700">{label}</span>
      <input className="mt-1 h-10 w-full rounded-md border border-zinc-200 px-3 outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-100" value={value} onChange={(event) => onChange(event.target.value)} />
    </label>
  );
}

function NumberInput({ label, value, onChange, readOnly = false }: { label: string; value: number; onChange: (value: number) => void; readOnly?: boolean }) {
  return (
    <label className="block text-sm">
      {label ? <span className="font-medium text-zinc-700">{label}</span> : null}
      <input className={`${label ? "mt-1" : ""} h-10 w-full rounded-md border border-zinc-200 px-3 outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-100 read-only:bg-zinc-50 read-only:text-zinc-500`} placeholder="0" type="number" value={!readOnly && value === 0 ? "" : value} readOnly={readOnly} onChange={(event) => onChange(event.target.value === "" ? 0 : Number(event.target.value))} />
    </label>
  );
}

function OptionalNumberInput({ label, value, onChange }: { label: string; value: number | null; onChange: (value: number | null) => void }) {
  return (
    <label className="block text-sm">
      <span className="font-medium text-zinc-700">{label}</span>
      <input
        className="mt-1 h-10 w-full rounded-md border border-zinc-200 px-3 outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-100"
        type="number"
        placeholder="0"
        value={value ?? ""}
        onChange={(event) => onChange(event.target.value === "" ? null : Number(event.target.value))}
      />
    </label>
  );
}

function SelectInput({ label, value, options, onChange }: { label: string; value: string; options: Array<string | { label: string; value: string }>; onChange: (value: string) => void }) {
  return (
    <label className="block text-sm">
      <span className="font-medium text-zinc-700">{label}</span>
      <select className="mt-1 h-10 w-full rounded-md border border-zinc-200 px-3 outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-100" value={value} onChange={(event) => onChange(event.target.value)}>
        {options.map((option) => {
          const normalized = typeof option === "string" ? { label: option, value: option } : option;
          return <option key={normalized.value} value={normalized.value}>{normalized.label}</option>;
        })}
      </select>
    </label>
  );
}

function SaveButton({ label, isSaving, disabled = false, onClick }: { label: string; isSaving: boolean; disabled?: boolean; onClick: () => void }) {
  return (
    <button className="mt-5 inline-flex h-10 items-center gap-2 rounded-md bg-brand-600 px-4 text-sm font-semibold text-white hover:bg-brand-700 disabled:bg-zinc-300" disabled={isSaving || disabled} type="button" onClick={onClick}>
      <Check className="h-4 w-4" />
      {isSaving ? "Saving..." : label}
    </button>
  );
}

function List({ rows, onRemove }: { rows: string[]; onRemove: (index: number) => void }) {
  if (rows.length === 0) return null;
  return (
    <div className="mt-4 divide-y divide-zinc-100 rounded-md border border-zinc-200">
      {rows.map((row, index) => (
        <div key={`${row}-${index}`} className="flex items-center justify-between px-3 py-2 text-sm">
          <span>{row}</span>
          <button className="text-zinc-400 hover:text-red-600" type="button" onClick={() => onRemove(index)}>
            <Trash2 className="h-4 w-4" />
          </button>
        </div>
      ))}
    </div>
  );
}

function MaterialCard({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="rounded-lg border border-zinc-200 bg-white p-4 shadow-sm">
      <h3 className="text-sm font-semibold text-zinc-950">{title}</h3>
      <div className="mt-4 space-y-4">{children}</div>
    </section>
  );
}

function StockButton({ label, color, isSaving, onClick }: { label: string; color: "green" | "teal" | "blue" | "purple"; isSaving: boolean; onClick: () => void }) {
  const colors = {
    green: "bg-[#6D28D9] hover:bg-[#4C1D95]",
    teal: "bg-[#6D28D9] hover:bg-[#4C1D95]",
    blue: "bg-[#6D28D9] hover:bg-[#4C1D95]",
    purple: "bg-[#6D28D9] hover:bg-[#4C1D95]"
  };
  return (
    <button className={`inline-flex h-10 items-center gap-2 rounded-md px-4 text-sm font-semibold text-white disabled:bg-[#E5E7EB] ${colors[color]}`} disabled={isSaving} type="button" onClick={onClick}>
      <Plus className="h-4 w-4" />
      {isSaving ? "Saving..." : `+ ${label}`}
    </button>
  );
}

function Readout({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-md bg-zinc-50 p-3">
      <p className="text-xs font-medium uppercase text-zinc-500">{label}</p>
      <p className="mt-1 text-lg font-semibold text-zinc-950">{value}</p>
    </div>
  );
}

function Toast({ message, onClose }: { message: string; onClose: () => void }) {
  return (
    <button className="fixed right-5 top-20 z-50 rounded-md bg-[#16A34A] px-4 py-3 text-sm font-semibold text-white shadow-lg" type="button" onClick={onClose}>
      {message}
    </button>
  );
}
