import { Plus, Save, Trash2 } from "lucide-react";
import { FormEvent, useEffect, useState } from "react";

import { listActiveMachines, setupDynamicMachine, type DynamicMachineSetupRecord } from "../lib/api";

const emptyMachine = {
  machine_name: "",
  default_speed: 0,
  target_output_per_shift: 0,
  raw_materials_mapped: [""],
  is_active: true
};

export default function MachineOnboardingPage() {
  const [machine, setMachine] = useState(emptyMachine);
  const [savedMachines, setSavedMachines] = useState<DynamicMachineSetupRecord[]>([]);
  const [status, setStatus] = useState<"idle" | "saving" | "saved" | "error">("idle");
  const [errorMessage, setErrorMessage] = useState("");

  useEffect(() => {
    void loadMachines();
  }, []);

  async function loadMachines() {
    try {
      setSavedMachines(await listActiveMachines());
    } catch (error) {
      console.error("Failed to load active machines:", error);
      setSavedMachines([]);
    }
  }

  function updateMaterial(index: number, value: string) {
    setMachine((current) => ({
      ...current,
      raw_materials_mapped: current.raw_materials_mapped.map((item, itemIndex) => itemIndex === index ? value : item)
    }));
  }

  function addMaterial() {
    setMachine((current) => ({ ...current, raw_materials_mapped: [...current.raw_materials_mapped, ""] }));
  }

  function removeMaterial(index: number) {
    setMachine((current) => {
      const nextMaterials = current.raw_materials_mapped.filter((_, itemIndex) => itemIndex !== index);
      return { ...current, raw_materials_mapped: nextMaterials.length ? nextMaterials : [""] };
    });
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!machine.machine_name.trim()) return;

    setStatus("saving");
    setErrorMessage("");
    try {
      await setupDynamicMachine({
        machine_name: machine.machine_name.trim(),
        default_speed: Number(machine.default_speed || 0),
        target_output_per_shift: Number(machine.target_output_per_shift || 0),
        raw_materials_mapped: machine.raw_materials_mapped.map((item) => item.trim()).filter(Boolean),
        is_active: machine.is_active
      });
      setMachine(emptyMachine);
      setStatus("saved");
      await loadMachines();
    } catch (error) {
      setStatus("error");
      setErrorMessage(error instanceof Error ? error.message : "Unable to save machine setup");
    }
  }

  return (
    <div className="mx-auto max-w-5xl space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-normal text-[#111827]">Machine Setup</h1>
        <p className="mt-1 text-sm text-[#4B5563]">Create open-ended machine profiles for production planning.</p>
      </div>

      <form className="space-y-6 rounded-lg border border-[#E5E7EB] bg-white p-5 shadow-sm" onSubmit={handleSubmit}>
        <div className="grid gap-4 md:grid-cols-3">
          <label className="block text-sm font-medium text-[#4B5563] md:col-span-3">
            Machine Name / Custom Type
            <input
              className="mt-2 h-11 w-full rounded-md border border-[#E5E7EB] px-3 text-sm outline-none transition placeholder:text-[#4B5563] focus:border-[#6D28D9] focus:ring-2 focus:ring-[#F3E8FF]"
              placeholder="e.g., Hi-Speed Cup Machine X, Hydraulic Plate Press"
              value={machine.machine_name}
              onChange={(event) => setMachine({ ...machine, machine_name: event.target.value })}
            />
          </label>
          <label className="block text-sm font-medium text-[#4B5563]">
            Default Operating Speed
            <input
              className="mt-2 h-11 w-full rounded-md border border-[#E5E7EB] px-3 text-sm outline-none transition focus:border-[#6D28D9] focus:ring-2 focus:ring-[#F3E8FF]"
              min={0}
              type="number"
              value={machine.default_speed || ""}
              onChange={(event) => setMachine({ ...machine, default_speed: event.target.value === "" ? 0 : Number(event.target.value) })}
            />
          </label>
          <label className="block text-sm font-medium text-[#4B5563]">
            Expected Target Output / Shift
            <input
              className="mt-2 h-11 w-full rounded-md border border-[#E5E7EB] px-3 text-sm outline-none transition focus:border-[#6D28D9] focus:ring-2 focus:ring-[#F3E8FF]"
              min={0}
              type="number"
              value={machine.target_output_per_shift || ""}
              onChange={(event) => setMachine({ ...machine, target_output_per_shift: event.target.value === "" ? 0 : Number(event.target.value) })}
            />
          </label>
          <label className="flex h-11 items-center gap-2 self-end rounded-md border border-[#E5E7EB] px-3 text-sm font-medium text-[#4B5563]">
            <input
              checked={machine.is_active}
              className="h-4 w-4 accent-[#6D28D9]"
              type="checkbox"
              onChange={(event) => setMachine({ ...machine, is_active: event.target.checked })}
            />
            Active for production
          </label>
        </div>

        <section className="rounded-lg border border-[#E5E7EB] bg-[#F9FAFB] p-4">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <h2 className="text-base font-semibold text-[#111827]">Raw Materials Mapped</h2>
              <p className="mt-1 text-sm text-[#4B5563]">Map every input material this machine consumes.</p>
            </div>
            <button
              className="inline-flex h-10 items-center justify-center gap-2 rounded-md border border-[#E5E7EB] bg-white px-3 text-sm font-medium text-[#4B5563] transition hover:bg-[#FFF7ED]"
              type="button"
              onClick={addMaterial}
            >
              <Plus className="h-4 w-4" />
              Add Raw Material
            </button>
          </div>

          <div className="mt-4 grid gap-3 md:grid-cols-2">
            {machine.raw_materials_mapped.map((material, index) => (
              <div key={index} className="grid grid-cols-[1fr_auto] gap-2">
                <input
                  className="h-11 rounded-md border border-[#E5E7EB] bg-white px-3 text-sm outline-none transition placeholder:text-[#4B5563] focus:border-[#6D28D9] focus:ring-2 focus:ring-[#F3E8FF]"
                  placeholder="e.g., Bottom Reel, PE Paper Blank"
                  value={material}
                  onChange={(event) => updateMaterial(index, event.target.value)}
                />
                <button
                  className="grid h-11 w-11 place-items-center rounded-md border border-[#E5E7EB] bg-white text-[#4B5563] transition hover:bg-[#DC2626]/10 hover:text-[#DC2626]"
                  type="button"
                  aria-label="Remove raw material"
                  title="Remove raw material"
                  onClick={() => removeMaterial(index)}
                >
                  <Trash2 className="h-4 w-4" />
                </button>
              </div>
            ))}
          </div>
        </section>

        <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
          <button
            className="inline-flex h-11 items-center justify-center gap-2 rounded-md bg-[#6D28D9] px-4 text-sm font-semibold text-white transition hover:bg-[#4C1D95] disabled:cursor-not-allowed disabled:opacity-70"
            type="submit"
            disabled={status === "saving"}
          >
            <Save className="h-4 w-4" />
            {status === "saving" ? "Saving" : "Save & Onboard Machine"}
          </button>
          {status === "saved" ? <p className="text-sm font-medium text-[#4C1D95]">Machine setup saved.</p> : null}
          {status === "error" ? <p className="text-sm font-medium text-[#DC2626]">{errorMessage}</p> : null}
        </div>
      </form>

      {savedMachines.length > 0 ? (
        <section className="rounded-lg border border-[#E5E7EB] bg-white p-5 shadow-sm">
          <h2 className="text-base font-semibold text-[#111827]">Active Machines</h2>
          <div className="mt-4 divide-y divide-[#E5E7EB]">
            {savedMachines.map((item) => (
              <div key={item.id} className="py-3 text-sm">
                <div className="flex flex-col gap-1 sm:flex-row sm:items-center sm:justify-between">
                  <p className="font-semibold text-[#111827]">{item.machine_name}</p>
                  <p className="text-[#4B5563]">Speed {item.default_speed} | Target {item.target_output_per_shift}</p>
                </div>
                <p className="mt-1 text-xs text-[#4B5563]">{item.raw_materials_mapped.length ? item.raw_materials_mapped.join(", ") : "No raw materials mapped"}</p>
              </div>
            ))}
          </div>
        </section>
      ) : null}
    </div>
  );
}
