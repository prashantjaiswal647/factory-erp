import { Check, Factory, PackageCheck, Plus, Settings, Trash2, UserRound } from "lucide-react";
import { useEffect, useState } from "react";

import { createBlankStock, createBottomStock, createBoxPackagingStock, createMachines, createPlasticStock, createWorker, getFinalStockOptions, getMachineLimits, onboardFinishedGoods, getOnboardingOverview, deleteDashboardMachine, getFactoryProfile, updateFactoryProfile, createManualActivityLog, setupDynamicMachine } from "../lib/api";
import type { BoxPackagingStockCreate, FinalStockOption, MachineCreate, MachineLimitUsage, PlasticStockCreate, WorkerCreate, OpeningAttendancePayload } from "../lib/api";
import { EditMachineModal } from "../components/EditMachineModal";
import ConfigurationOverview from "../components/ConfigurationOverview";
import PhoneNumberInput from "../components/PhoneNumberInput";
import { useAuth } from "../context/AuthContext";
import { useUpgrade } from "../context/UpgradeContext";

const todayWorker: WorkerCreate = { name: "", country_code: "+91", phone: "", daily_wages: 0, duty_hours: 8 };
const blankStockDraft = { material_name: "Blank", size_ml: 210, kg_per_sack: 20, total_sacks: 0 };
const bottomStockDraft = { bottom_size_mm: 68, bag_weight_kg: null as number | null, rolls_per_bag: null as number | null, total_bags: null as number | null, total_rolls: null as number | null, total_weight_kg: null as number | null };
const boxStockDraft: BoxPackagingStockCreate = { box_type: "Small Box", box_quantity: 0, price_per_box: 0 };
const plasticStockDraft: PlasticStockCreate = { plastic_size_name: "", cup_size_ml: 210, total_boras: 0, weight_per_bora_kg: 20, price_per_kg: 0 };
const machineDraft: MachineCreate = {
  machine_type: "",
  machine_number: "",
  mould_size_ml: null,
  bottom_size_mm: null,
  speed_per_minute: 0,
  machine_name: "",
  default_speed: 0,
  target_output_per_shift: 0,
  raw_materials_mapped: [""],
  is_active: true
};

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
  const [savedMachines, setSavedMachines] = useState<any[]>([]);
  const [editingMachine, setEditingMachine] = useState<any | null>(null);
  const [telemetryStates, setTelemetryStates] = useState<Record<number, {
    status: "Running" | "Stopped";
    speed: number;
    actualProduction: number;
    downtimeReason: string;
    activeMould: number;
    mouldLogs: Array<{ mould: number; timestamp: string }>;
    downtimeLogs: Array<{ reason: string; timestamp: string }>;
    expanded: boolean;
  }>>({});
  const [blankStock, setBlankStock] = useState(blankStockDraft);
  const [bottomStock, setBottomStock] = useState(bottomStockDraft);
  const [boxStock, setBoxStock] = useState<BoxPackagingStockCreate>(boxStockDraft);
  const [plasticStock, setPlasticStock] = useState<PlasticStockCreate>(plasticStockDraft);
  const [finalProducts, setFinalProducts] = useState<FinalStockOption[]>([]);
  const [machineUsage, setMachineUsage] = useState<MachineLimitUsage | null>(null);
  const [isSaving, setIsSaving] = useState(false);
  const { showToast, showUpgradeModal } = useUpgrade();
  const { updateUser, user } = useAuth();
  const canDelete = user?.role === "Owner";

  // Manual Finished Goods Stock States
  const [productSizeMl, setProductSizeMl] = useState<number>(0);
  const [varietyDesign, setVarietyDesign] = useState("Standard/White");
  const [packagingSizeName, setPackagingSizeName] = useState("");
  const [pcsPerPacket, setPcsPerPacket] = useState<number>(100);
  const [packetsPerBox, setPacketsPerBox] = useState<number>(10);
  const [initialQuantityBoxes, setInitialQuantityBoxes] = useState<number>(0);

  // Company Profile states
  const [companyName, setCompanyName] = useState("");
  const [companyAddress, setCompanyAddress] = useState("");
  const [companyGST, setCompanyGST] = useState("");
  const [startingInvoiceNum, setStartingInvoiceNum] = useState(1);
  const [billOfSupplyStartSeq, setBillOfSupplyStartSeq] = useState(1);
  const [taxInvoiceStartSeq, setTaxInvoiceStartSeq] = useState(1);
  const [billOfSupplySimpleStartSeq, setBillOfSupplySimpleStartSeq] = useState(1);
  const [advanceDiscountNum, setAdvanceDiscountNum] = useState(2.00);
  const [invoicePrefix, setInvoicePrefix] = useState("INV-");

  useEffect(() => {
    void loadFinalProducts();
    void loadMachineUsage();
    void loadSavedMachines();
    
    async function loadFactoryProfile() {
      try {
        const response = await getFactoryProfile();
        const profile = response.data;
        if (profile) {
          setCompanyName(profile.factory_name || "");
          setCompanyAddress(profile.address || "");
          setCompanyGST(profile.gst_number || "");
          setStartingInvoiceNum(profile.initial_invoice_number || 1);
          setBillOfSupplyStartSeq(profile.bill_of_supply_start_seq || profile.next_bill_of_supply_number || 1);
          setTaxInvoiceStartSeq(profile.tax_invoice_start_seq || profile.next_tax_invoice_number || 1);
          setBillOfSupplySimpleStartSeq(profile.bill_of_supply_simple_start_seq || profile.next_bill_of_supply_simple_number || 1);
          setAdvanceDiscountNum(profile.advance_payment_discount_percentage || 2.00);
        }
      } catch (err) {
        console.error("Failed to load factory profile:", err);
      }
    }
    void loadFactoryProfile();
  }, []);

  async function loadSavedMachines() {
    try {
      const response = await getOnboardingOverview();
      setSavedMachines(response.data.machines || []);
    } catch (err) {
      console.error("Failed to load saved machines:", err);
    }
  }

  async function loadFinalProducts() {
    try {
      const response = await getFinalStockOptions();
      setFinalProducts(response.data);
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
    if (machines.length === 0 && !(machine.machine_name || machine.machine_type).trim()) return;
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
      const saveList = machines.length ? machines : [machine];
      await Promise.all(
        saveList.map((entry) =>
          setupDynamicMachine({
            machine_name: (entry.machine_name || entry.machine_type).trim(),
            default_speed: Number(entry.default_speed ?? entry.speed_per_minute ?? 0),
            target_output_per_shift: Number(entry.target_output_per_shift ?? 0),
            raw_materials_mapped: (entry.raw_materials_mapped || []).map((item) => item.trim()).filter(Boolean),
            is_active: entry.is_active ?? true
          })
        )
      );
      setToast("Machines saved");
      setStep(2);
      setMachines([]);
      setMachine(machineDraft);
      await loadMachineUsage();
      await loadSavedMachines();
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
    if (productSizeMl <= 0) {
      setToast("Please enter a valid Product Size (ML).");
      return;
    }
    if (!varietyDesign.trim()) {
      setToast("Please enter a variety or design name.");
      return;
    }
    if (pcsPerPacket <= 0 || packetsPerBox <= 0) {
      setToast("Pcs/Packet and Packets/Box must be greater than 0.");
      return;
    }

    setIsSaving(true);
    try {
      const payload = {
        product_size_ml: Number(productSizeMl),
        variety_design: varietyDesign.trim(),
        packaging_size_name: packagingSizeName.trim() || undefined,
        pcs_per_packet: Number(pcsPerPacket),
        packets_per_box: Number(packetsPerBox),
        initial_quantity_boxes: Number(initialQuantityBoxes),
      };

      const result = await onboardFinishedGoods(payload);
      setToast("Finished goods stock successfully onboarded!");

      // Update finalProducts locally without page refresh
      setFinalProducts((prev) => {
        const idx = prev.findIndex(
          (p) =>
            p.product_size_ml === result.product_size_ml &&
            p.variety.toLowerCase() === result.variety.toLowerCase() &&
            p.packaging_size_name.toLowerCase() === result.packaging_size_name.toLowerCase()
        );
        if (idx >= 0) {
          const updated = [...prev];
          updated[idx] = result;
          return updated;
        } else {
          return [...prev, result];
        }
      });

      // Reset states
      setProductSizeMl(0);
      setVarietyDesign("Standard/White");
      setPackagingSizeName("");
      setPcsPerPacket(100);
      setPacketsPerBox(10);
      setInitialQuantityBoxes(0);

    } catch (caught: any) {
      console.error("Failed to onboard finished goods:", caught);
      setToast(caught?.response?.data?.detail || "Finished goods onboarding failed.");
    } finally {
      setIsSaving(false);
    }
  }

  async function saveCompanyProfile() {
    if (!companyName.trim()) {
      setToast("Company Name is required.");
      return;
    }
    setIsSaving(true);
    try {
      await updateFactoryProfile({
        factory_name: companyName.trim(),
        address: companyAddress.trim(),
        gst_number: companyGST.trim(),
        initial_invoice_number: startingInvoiceNum,
        bill_of_supply_start_seq: billOfSupplyStartSeq || 1,
        tax_invoice_start_seq: taxInvoiceStartSeq || 1,
        bill_of_supply_simple_start_seq: billOfSupplySimpleStartSeq || 1,
        advance_payment_discount_percentage: Number(advanceDiscountNum || 0),
        invoice_prefix: invoicePrefix.trim()
      });
      setToast("Company Profile saved successfully");
      setStep(1); // Proceed to Workers
    } catch (err) {
      console.error("Failed to save factory profile:", err);
      setToast("Failed to save Company Profile.");
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

      <div className="grid gap-3 grid-cols-2 md:grid-cols-5">
        {["Company Profile", "Workers", "Machines", "Raw Materials", "Final Product Stock"].map((label, index) => (
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
        <Panel icon={Factory} title="Company Profile Details">
          <div className="space-y-4">
            <p className="text-sm text-zinc-500">
              Set up your factory profile and default invoice preferences. These details are used to auto-generate beautiful GST Invoices and Bill of Supply documents.
            </p>
            <div className="grid gap-4 md:grid-cols-2">
              <TextInput
                label="Company / Factory Name"
                placeholder="e.g. Maruti Disposable Products"
                value={companyName}
                onChange={setCompanyName}
              />
              <TextInput
                label="GST Number (GSTIN) - Optional"
                placeholder="e.g. 07AAAAA1111A1Z1"
                value={companyGST}
                onChange={setCompanyGST}
              />
            </div>
            <div className="grid gap-4 md:grid-cols-4">
              <TextInput
                label="Factory Address / Place"
                placeholder="e.g. Wazirpur Industrial Area, New Delhi"
                value={companyAddress}
                onChange={setCompanyAddress}
              />
              <TextInput
                label="Invoice Prefix"
                placeholder="e.g. INV-"
                value={invoicePrefix}
                onChange={setInvoicePrefix}
              />
              <NumberInput
                label="Starting Invoice Number Counter"
                value={startingInvoiceNum}
                onChange={setStartingInvoiceNum}
              />
              <NumberInput
                label="Advance UPI Discount (%)"
                value={advanceDiscountNum}
                onChange={setAdvanceDiscountNum}
              />
            </div>
            <div className="grid gap-4 md:grid-cols-3">
              <NumberInput
                label="Starting Invoice Number for Bill of Supply"
                value={billOfSupplyStartSeq}
                onChange={setBillOfSupplyStartSeq}
              />
              <NumberInput
                label="Starting Invoice Number for Tax Invoice (GST)"
                value={taxInvoiceStartSeq}
                onChange={setTaxInvoiceStartSeq}
              />
              <NumberInput
                label="Starting Invoice Number for Bill of Supply Simple"
                value={billOfSupplySimpleStartSeq}
                onChange={setBillOfSupplySimpleStartSeq}
              />
            </div>
            <SaveButton
              label="Save Company Profile"
              isSaving={isSaving}
              onClick={saveCompanyProfile}
            />
          </div>
        </Panel>
      ) : null}

      {step === 1 ? (
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

      {step === 2 ? (
        <Panel icon={Factory} title="Machines">
          {machineUsage ? (
            <div className={`mb-4 rounded-md border px-4 py-3 text-sm ${machineUsage.limit_reached ? "border-red-200 bg-red-50 text-red-700" : machineUsage.nearing_limit ? "border-amber-200 bg-amber-50 text-amber-800" : "border-zinc-200 bg-zinc-50 text-zinc-600"}`}>
              {machineUsage.limit_reached
                ? `You have reached your limit of ${machineUsage.limit} machines.`
                : `Machine usage: ${machineUsage.used}/${machineUsage.limit}`}
            </div>
          ) : null}
          <div className="grid gap-3 md:grid-cols-3">
            <TextInput
              label="Machine Name / Custom Type"
              placeholder="e.g., Hydraulic Plate Press"
              value={machine.machine_name || machine.machine_type}
              onChange={(machine_name) => setMachine({ ...machine, machine_name, machine_type: machine_name })}
            />
            <NumberInput
              label="Default Operating Speed"
              value={Number(machine.default_speed ?? machine.speed_per_minute ?? 0)}
              onChange={(default_speed) => setMachine({ ...machine, default_speed, speed_per_minute: default_speed })}
            />
            <NumberInput
              label="Target Output / Shift"
              value={Number(machine.target_output_per_shift ?? 0)}
              onChange={(target_output_per_shift) => setMachine({ ...machine, target_output_per_shift })}
            />
          </div>
          <div className="mt-4 rounded-md border border-zinc-200 bg-zinc-50 p-4">
            <div className="flex items-center justify-between gap-3">
              <div>
                <p className="text-sm font-semibold text-zinc-800">Raw Materials Mapped</p>
                <p className="mt-1 text-xs text-zinc-500">Add every material this machine can consume in production.</p>
              </div>
              <button
                className="inline-flex h-9 items-center gap-2 rounded-md border border-zinc-200 bg-white px-3 text-xs font-semibold text-zinc-700"
                type="button"
                onClick={() => setMachine({ ...machine, raw_materials_mapped: [...(machine.raw_materials_mapped || []), ""] })}
              >
                <Plus className="h-3.5 w-3.5" />
                Add Material
              </button>
            </div>
            <div className="mt-4 grid gap-3 md:grid-cols-2">
              {(machine.raw_materials_mapped || [""]).map((material, index) => (
                <div key={`material-${index}`} className="grid grid-cols-[1fr_auto] gap-2">
                  <input
                    className="h-10 rounded-md border border-zinc-200 px-3 text-sm outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-100"
                    placeholder="e.g., Bottom Reel, PE Paper Blank"
                    value={material}
                    onChange={(event) => setMachine({
                      ...machine,
                      raw_materials_mapped: (machine.raw_materials_mapped || [""]).map((item, itemIndex) => itemIndex === index ? event.target.value : item)
                    })}
                  />
                  <button className="grid h-10 w-10 place-items-center rounded-md border border-zinc-200 text-zinc-500 hover:text-red-600" type="button" onClick={() => setMachine({ ...machine, raw_materials_mapped: (machine.raw_materials_mapped || []).filter((_, itemIndex) => itemIndex !== index) })}>
                    <Trash2 className="h-4 w-4" />
                  </button>
                </div>
              ))}
            </div>
          </div>
          <div className="mt-4 flex gap-2">
            <button
              className="inline-flex h-10 items-center gap-2 rounded-md border border-zinc-200 bg-white px-3 text-sm font-semibold text-zinc-700"
              type="button"
              disabled={machineUsage ? machineUsage.used + machines.length >= machineUsage.limit : false}
              title={machineUsage && machineUsage.used + machines.length >= machineUsage.limit ? "Machine limit reached" : "Add row"}
              onClick={() => {
                if (!(machine.machine_name || machine.machine_type).trim()) return;
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
                setMachine(machineDraft);
              }}
            >
              <Plus className="h-4 w-4" />
              Add row
            </button>
            <SaveButton label="Save Machines" isSaving={isSaving} disabled={Boolean(machineUsage?.limit_reached)} onClick={saveMachines} />
          </div>
          <List rows={machines.map((row) => `${row.machine_name || row.machine_type} / ${row.default_speed || row.speed_per_minute || 0} speed / ${(row.raw_materials_mapped || []).filter(Boolean).join(", ") || "No materials mapped"}`)} onRemove={(index) => setMachines(machines.filter((_, itemIndex) => itemIndex !== index))} />

          {savedMachines.length > 0 && (
            <div className="mt-6 border-t border-zinc-100 pt-6">
              <h3 className="text-sm font-semibold text-zinc-950 mb-3">Saved Machines ({savedMachines.length})</h3>
              <div className="space-y-4">
                {savedMachines.map((m) => {
                  const machineLabel = m.machine_name || m.machine_type || m.machine_number || `Machine ${m.id}`;
                  const mappedMaterials = (m.raw_materials_mapped || []).filter(Boolean);
                  const optimalSpeed = m.default_speed || m.speed_per_minute || 0;
                  const expectedTarget = m.target_output_per_shift || optimalSpeed * 60 * 8;

                  const state = telemetryStates[m.id] || {
                    status: "Running",
                    speed: optimalSpeed,
                    actualProduction: 22000,
                    downtimeReason: "",
                    activeMould: m.mould_size_ml || 210,
                    mouldLogs: [],
                    downtimeLogs: [],
                    expanded: false
                  };

                  const actualCups = state.status === "Stopped" ? 0 : (state.actualProduction !== undefined ? state.actualProduction : 22000);
                  const oeeScore = expectedTarget > 0 ? Math.min(100, Math.round((actualCups / expectedTarget) * 100)) : 0;
                  const currentSpeedRPM = state.status === "Stopped" ? 0 : Math.round(actualCups / (60 * 8));

                  return (
                    <div key={m.id} className="rounded-lg border border-zinc-200 bg-white p-4 transition shadow-sm hover:border-zinc-300">
                      <div className="flex items-center justify-between text-sm">
                        <div className="flex flex-col">
                          <span className="font-semibold text-zinc-800 flex items-center gap-2">
                            {machineLabel}
                            <span className={`px-2 py-0.5 rounded-full text-[10px] font-semibold ${
                              m.is_active === false ? "bg-red-100 text-red-800" : state.status === "Running" ? "bg-emerald-100 text-emerald-800" : "bg-red-100 text-red-800"
                            }`}>
                              {m.is_active === false ? "Inactive" : state.status}
                            </span>
                          </span>
                          <span className="text-xs text-zinc-500 mt-1">
                            Speed: {optimalSpeed} | Target/shift: {expectedTarget} | Materials: {mappedMaterials.join(", ") || "Not mapped"} | OEE: {oeeScore}%
                          </span>
                        </div>
                        <div className="flex items-center gap-2">
                          <button
                            className="inline-flex h-8 items-center gap-1 rounded-md border border-zinc-200 px-2 text-xs font-semibold text-brand-700 hover:bg-brand-50"
                            type="button"
                            onClick={() => setTelemetryStates({
                              ...telemetryStates,
                              [m.id]: { ...state, expanded: !state.expanded }
                            })}
                          >
                            📊 {state.expanded ? "Close Telemetry" : "Open Telemetry"}
                          </button>
                          <button
                            className="inline-flex h-8 w-8 items-center justify-center rounded-md border border-zinc-200 text-zinc-600 hover:bg-zinc-50 hover:text-brand-600"
                            type="button"
                            onClick={() => setEditingMachine(m)}
                            title="Edit Machine"
                          >
                            <Settings className="h-4 w-4" />
                          </button>
                          {canDelete ? (
                            <button
                              className="inline-flex h-8 w-8 items-center justify-center rounded-md border border-zinc-200 text-zinc-600 hover:bg-zinc-50 hover:text-red-600"
                              type="button"
                              onClick={async () => {
                                if (confirm("Are you sure you want to delete this machine?")) {
                                  try {
                                    await deleteDashboardMachine(m.id);
                                    setToast("Machine deleted");
                                    await loadSavedMachines();
                                    await loadMachineUsage();
                                  } catch (err) {
                                    console.error("Failed to delete machine:", err);
                                    setToast("Failed to delete machine");
                                  }
                                }
                              }}
                              title="Delete Machine"
                            >
                              <Trash2 className="h-4 w-4" />
                            </button>
                          ) : null}
                        </div>
                      </div>

                      {/* Expended OEE & Telemetry Panel */}
                      {state.expanded && (
                        <div className="mt-4 border-t border-zinc-100 pt-4 grid gap-4 md:grid-cols-2 bg-zinc-50/50 p-3 rounded-lg border border-zinc-100">
                          {/* Left Column: Live Gauges & Controls */}
                          <div className="space-y-4">
                            <h4 className="text-xs font-semibold uppercase text-zinc-500 tracking-wider">Live Controls & OEE</h4>
                            
                            {/* OEE Progress bar */}
                            <div>
                              <div className="flex items-center justify-between text-xs font-semibold text-zinc-600 mb-1">
                                <span>Overall Equipment Effectiveness (OEE)</span>
                                <span className={oeeScore >= 80 ? "text-emerald-600" : oeeScore >= 50 ? "text-amber-600" : "text-red-600"}>{oeeScore}% Score</span>
                              </div>
                              <div className="w-full bg-zinc-200 h-2.5 rounded-full overflow-hidden flex">
                                <div 
                                  className={`h-full transition-all duration-300 ${
                                    oeeScore >= 80 ? "bg-emerald-500" : oeeScore >= 50 ? "bg-amber-500" : "bg-red-500"
                                  }`}
                                  style={{ width: `${oeeScore}%` }}
                                />
                              </div>
                            </div>

                            {/* Status and Speed Controls */}
                            <div className="grid gap-3 grid-cols-2">
                              <div>
                                <label className="block text-xs font-semibold text-zinc-600 mb-1">Machine Status</label>
                                <select
                                  value={state.status}
                                  onChange={(e) => {
                                    const nextStatus = e.target.value as "Running" | "Stopped";
                                    setTelemetryStates({
                                      ...telemetryStates,
                                      [m.id]: { ...state, status: nextStatus }
                                    });
                                    createManualActivityLog({
                                      event_type: "machine_telemetry",
                                      description: `Machine ${m.machine_number || m.name || m.id} status changed to ${nextStatus}`
                                    }).catch(err => console.error(err));
                                  }}
                                  className="h-9 w-full rounded border border-zinc-200 px-2 bg-white text-xs"
                                >
                                  <option value="Running">Running</option>
                                  <option value="Stopped">Stopped</option>
                                </select>
                              </div>
                              <div>
                                <label className="block text-xs font-semibold text-zinc-600 mb-1">Actual Cups Produced (8h Shift)</label>
                                <input
                                  type="number"
                                  value={state.status === "Stopped" ? 0 : (state.actualProduction !== undefined ? state.actualProduction : 22000)}
                                  disabled={state.status === "Stopped"}
                                  onChange={(e) => {
                                    const nextProd = Number(e.target.value);
                                    setTelemetryStates({
                                      ...telemetryStates,
                                      [m.id]: { ...state, actualProduction: nextProd }
                                    });
                                  }}
                                  className="h-9 w-full rounded border border-zinc-200 px-2 bg-white text-xs"
                                />
                              </div>
                            </div>

                            {/* Designed Speed and Target Read-only block */}
                            <div className="grid gap-3 grid-cols-2 bg-white p-2 rounded border border-zinc-150 text-[10px]">
                              <div>
                                <span className="font-semibold text-zinc-500">Optimal Design Speed:</span>
                                <p className="font-bold text-zinc-800">{optimalSpeed} RPM</p>
                              </div>
                              <div>
                                <span className="font-semibold text-zinc-500">Expected Shift Target:</span>
                                <p className="font-bold text-zinc-800">{expectedTarget.toLocaleString()} cups</p>
                              </div>
                            </div>

                            {/* Active Mould Selector */}
                            <div>
                              <label className="block text-xs font-semibold text-zinc-600 mb-1">Active Mould size</label>
                              <select
                                value={state.activeMould}
                                onChange={(e) => {
                                  const nextMould = Number(e.target.value);
                                  const timestamp = new Date().toLocaleTimeString();
                                  setTelemetryStates({
                                    ...telemetryStates,
                                    [m.id]: {
                                      ...state,
                                      activeMould: nextMould,
                                      mouldLogs: [
                                        { mould: nextMould, timestamp },
                                        ...state.mouldLogs.slice(0, 4)
                                      ]
                                    }
                                  });
                                  createManualActivityLog({
                                    event_type: "machine_telemetry",
                                    description: `Machine ${m.machine_number || m.name || m.id} mould swapped to ${nextMould}ml cup size`
                                  }).catch(err => console.error(err));
                                }}
                                className="h-9 w-full rounded border border-zinc-200 px-2 bg-white text-xs"
                              >
                                {[65, 100, 150, 210, 250].map((size) => (
                                  <option key={size} value={size}>{size}ml size</option>
                                ))}
                              </select>
                            </div>
                          </div>

                          {/* Right Column: Downtime logging & Audit logs */}
                          <div className="space-y-4 flex flex-col justify-between">
                            <div>
                              <h4 className="text-xs font-semibold uppercase text-zinc-500 tracking-wider mb-2">Simulate Operator Logs</h4>
                              {state.status === "Stopped" ? (
                                <div className="space-y-2">
                                  <p className="text-[11px] text-zinc-600">Select reason for machine halt:</p>
                                  <div className="flex flex-wrap gap-2">
                                    {["No paper blank", "Mechanical fault", "Maintenance", "Power failure"].map((reason) => (
                                      <button
                                        key={reason}
                                        onClick={() => {
                                          const timestamp = new Date().toLocaleTimeString();
                                          setTelemetryStates({
                                            ...telemetryStates,
                                            [m.id]: {
                                              ...state,
                                              downtimeReason: reason,
                                              downtimeLogs: [
                                                { reason, timestamp },
                                                ...state.downtimeLogs.slice(0, 4)
                                              ]
                                            }
                                          });
                                          createManualActivityLog({
                                            event_type: "machine_telemetry",
                                            description: `Machine ${m.machine_number || m.name || m.id} stopped: ${reason}`
                                          }).catch(err => console.error(err));
                                        }}
                                        className="px-2 py-1 bg-red-100 hover:bg-red-200 text-red-800 text-[10px] font-semibold rounded"
                                        type="button"
                                      >
                                        ⚠️ {reason}
                                      </button>
                                    ))}
                                  </div>
                                </div>
                              ) : (
                                <p className="text-xs text-zinc-600">Machine is running smoothly. Set status to "Stopped" to log downtime events.</p>
                              )}
                            </div>

                            {/* Chronological Audit Logs */}
                            <div className="bg-white/80 p-2.5 rounded border border-zinc-100 text-[11px] text-zinc-700 flex-1 overflow-y-auto max-h-[120px] mt-2 space-y-1">
                              <p className="font-semibold text-zinc-800 uppercase tracking-wider text-[9px] mb-1">Live Floor Audit Trail</p>
                              {state.mouldLogs.length === 0 && state.downtimeLogs.length === 0 && (
                                <p className="text-zinc-400 italic">No events logged yet for this shift.</p>
                              )}
                              {state.downtimeLogs.map((log, idx) => (
                                <div key={`down-${idx}`} className="text-red-700">
                                  [{log.timestamp}] Halt: {log.reason}
                                </div>
                              ))}
                              {state.mouldLogs.map((log, idx) => (
                                <div key={`mould-${idx}`} className="text-brand-700">
                                  [{log.timestamp}] Mould swapped to {log.mould}ml size
                                </div>
                              ))}
                            </div>
                          </div>
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </Panel>
      ) : null}

      {step === 3 ? (
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
                <TextInput label="Box Type" value={boxStock.box_type} onChange={(box_type) => setBoxStock({ ...boxStock, box_type })} />
                <NumberInput label="Box Quantity (Pieces)" value={boxStock.box_quantity} onChange={(box_quantity) => setBoxStock({ ...boxStock, box_quantity })} />
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

      {step === 4 ? (
        <Panel icon={PackageCheck} title="Final Product Stock (Finished Goods)">
          <div className="space-y-6">
            <div className="bg-zinc-50/50 p-5 rounded-xl border border-zinc-200 shadow-sm space-y-4">
              <p className="text-sm font-medium text-zinc-600">Manual Entry (Single Source of Truth for Opening Stock)</p>
              
              <div className="grid gap-4 md:grid-cols-3">
                <NumberInput
                  label="Product Size (ML)"
                  value={productSizeMl}
                  onChange={(val) => setProductSizeMl(val)}
                />
                
                <div>
                  <TextInput
                    label="Variety / Design"
                    value={varietyDesign}
                    onChange={(val) => setVarietyDesign(val)}
                  />
                  <p className="mt-1 text-[11px] text-zinc-400">e.g., Standard/White, Printed, Brown Kraft</p>
                </div>

                <div>
                  <TextInput
                    label="Packaging Size Name (Optional)"
                    value={packagingSizeName}
                    onChange={(val) => setPackagingSizeName(val)}
                  />
                  <p className="mt-1 text-[11px] text-zinc-400">If blank, auto-generates in backend</p>
                </div>
              </div>

              <div className="grid gap-4 md:grid-cols-3">
                <NumberInput
                  label="Pcs / Packet"
                  value={pcsPerPacket}
                  onChange={(val) => setPcsPerPacket(val)}
                />
                <NumberInput
                  label="Packets / Box"
                  value={packetsPerBox}
                  onChange={(val) => setPacketsPerBox(val)}
                />
                <NumberInput
                  label="Initial Stock Quantity (Boxes)"
                  value={initialQuantityBoxes}
                  onChange={(val) => setInitialQuantityBoxes(val)}
                />
              </div>
            </div>

            <div className="flex justify-end border-b border-zinc-100 pb-4">
              <SaveButton
                label="Add Finished Goods Stock"
                isSaving={isSaving}
                onClick={addFinalProductStock}
              />
            </div>

            {/* Premium rendered cards list for onboarded Finished Goods */}
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <h3 className="text-sm font-bold text-zinc-800 uppercase tracking-wider">Onboarded Finished Goods Registry</h3>
                <span className="bg-[#F3E8FF] text-[#4C1D95] text-xs px-2.5 py-0.5 rounded-full font-semibold">
                  {finalProducts.length} unique configs
                </span>
              </div>

              {finalProducts.length === 0 ? (
                <div className="rounded-lg border-2 border-dashed border-zinc-200 p-8 text-center bg-zinc-50">
                  <p className="text-zinc-500 text-sm">No finished goods opening stock onboarded yet. Fill details above to register.</p>
                </div>
              ) : (
                <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
                  {finalProducts.map((product) => {
                    const totalBoxes = product.total_boxes ?? product.current_quantity ?? 0;
                    return (
                      <div
                        key={product.id}
                        className="relative overflow-hidden rounded-xl border border-zinc-200 bg-white p-4 shadow-sm transition-all duration-200 hover:shadow-md hover:border-zinc-300 flex flex-col justify-between"
                      >
                        <div className="flex items-start justify-between">
                          <div className="space-y-1">
                            <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-semibold bg-zinc-100 text-zinc-800">
                              {product.product_size_ml} ml
                            </span>
                            <h4 className="text-sm font-bold text-zinc-950 mt-1">
                              {product.variety}
                            </h4>
                            <p className="text-[11px] text-zinc-500 line-clamp-1">
                              {product.packaging_size_name}
                            </p>
                          </div>
                          
                          <div className="flex flex-col items-end">
                            <span className="text-xs font-bold text-zinc-400">STOCK</span>
                            <span className="text-lg font-black text-[#6D28D9]">
                              {totalBoxes} <span className="text-xs font-semibold text-zinc-500">Boxes</span>
                            </span>
                          </div>
                        </div>

                        <div className="mt-4 pt-3 border-t border-zinc-100 flex items-center justify-between text-xs text-zinc-500">
                          <div>
                            <span className="font-semibold text-zinc-700">{product.pieces_per_packet}</span> pcs/pkt
                          </div>
                          <div>
                            <span className="font-semibold text-zinc-700">{product.packets_per_box_limit || product.packets_per_box}</span> pkts/box
                          </div>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          </div>
        </Panel>
      ) : null}
      
      {editingMachine ? (
        <EditMachineModal
          machine={editingMachine}
          onClose={() => setEditingMachine(null)}
          onSaved={async () => {
            setToast("Machine updated successfully");
            await loadSavedMachines();
            await loadMachineUsage();
          }}
        />
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

function TextInput({ label, placeholder, value, onChange }: { label: string; placeholder?: string; value: string; onChange: (value: string) => void }) {
  return (
    <label className="block text-sm">
      <span className="font-medium text-zinc-700">{label}</span>
      <input className="mt-1 h-10 w-full rounded-md border border-zinc-200 px-3 outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-100" placeholder={placeholder} value={value} onChange={(event) => onChange(event.target.value)} />
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
// React Form Data State Validation Hook
// apps/web/src/pages/Onboarding.tsx (or matching component setup)

import React, { useState } from 'react';

interface OnboardingFormData {
  company_name: string;
  bill_of_supply_start_seq: number;
  tax_invoice_start_seq: number;
  bill_of_supply_simple_start_seq: number;
}

export const OnboardingForm: React.FC = () => {
  const [formData, setFormData] = useState<OnboardingFormData>({
    company_name: '',
    bill_of_supply_start_seq: 1,        // Default Initialization 
    tax_invoice_start_seq: 1,           // Default Initialization
    bill_of_supply_simple_start_seq: 1,  // Default Initialization
  });

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const { name, value } = e.target;
    setFormData({
      ...formData,
      [name]: name.endsWith('_seq') ? Math.max(1, parseInt(value) || 1) : value
    });
  };

  return (
    <div className="space-y-6 max-w-2xl mx-auto p-6 bg-white rounded-lg shadow">
      <h2 className="text-xl font-bold text-gray-800">Configure Invoice Series Counters</h2>
      <p className="text-sm text-gray-500">Set starting tracking numbers for your distinct billing streams.</p>
      
      <hr className="border-gray-200" />

      {/* Input Container 1: Bill of Supply */}
      <div className="flex flex-col space-y-2">
        <label className="text-sm font-semibold text-gray-700">Starting Invoice Number for Bill of Supply</label>
        <input
          type="number"
          name="bill_of_supply_start_seq"
          min="1"
          value={formData.bill_of_supply_start_seq}
          onChange={handleInputChange}
          className="w-full p-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500"
        />
      </div>

      {/* Input Container 2: Tax Invoice (GST) */}
      <div className="flex flex-col space-y-2">
        <label className="text-sm font-semibold text-gray-700">Starting Invoice Number for Tax Invoice (GST)</label>
        <input
          type="number"
          name="tax_invoice_start_seq"
          min="1"
          value={formData.tax_invoice_start_seq}
          onChange={handleInputChange}
          className="w-full p-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500"
        />
      </div>

      {/* Input Container 3: Bill of Supply Simple */}
      <div className="flex flex-col space-y-2">
        <label className="text-sm font-semibold text-gray-700">Starting Invoice Number for Bill of Supply Simple</label>
        <input
          type="number"
          name="bill_of_supply_simple_start_seq"
          min="1"
          value={formData.bill_of_supply_simple_start_seq}
          onChange={handleInputChange}
          className="w-full p-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500"
        />
      </div>
    </div>
  );
};