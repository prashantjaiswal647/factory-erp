import { Plus, Save, Trash2 } from "lucide-react";
import { FormEvent, useEffect, useMemo, useState } from "react";

import { getMachineTemplate, submitMachineTemplate, type MachineOnboardingPayload, type MachineTemplateRecord, type TemplateStatus } from "../lib/api";

type MachineType = "Paper Cup" | "Paper Bag" | "Dona";
type FieldType = "text" | "number";

type BaseField = {
  key: string;
  label: string;
  type: FieldType;
  placeholder?: string;
};

type CustomFieldRow = {
  id: number;
  label: string;
  value: string;
};

const machineFields: Record<MachineType, BaseField[]> = {
  "Paper Cup": [
    { key: "cup_size_ml", label: "Cup Size (ml)", type: "number", placeholder: "250" },
    { key: "bottom_size_mm", label: "Bottom Size (mm)", type: "number", placeholder: "52" },
    { key: "speed_cups_per_minute", label: "Speed (cups/min)", type: "number", placeholder: "45" },
    { key: "mould_count", label: "Mould Count", type: "number", placeholder: "12" }
  ],
  "Paper Bag": [
    { key: "bag_width_mm", label: "Bag Width (mm)", type: "number", placeholder: "180" },
    { key: "bag_height_mm", label: "Bag Height (mm)", type: "number", placeholder: "300" },
    { key: "gsm_range", label: "GSM Range", type: "text", placeholder: "80-120" },
    { key: "speed_bags_per_minute", label: "Speed (bags/min)", type: "number", placeholder: "60" }
  ],
  Dona: [
    { key: "plate_size_inch", label: "Plate Size (inch)", type: "number", placeholder: "8" },
    { key: "die_size", label: "Die Size", type: "text", placeholder: "Standard 8 inch" },
    { key: "press_capacity_ton", label: "Press Capacity (ton)", type: "number", placeholder: "25" },
    { key: "speed_pieces_per_minute", label: "Speed (pieces/min)", type: "number", placeholder: "35" }
  ]
};

const machineTypes = Object.keys(machineFields) as MachineType[];

function normalizeKey(label: string) {
  return label.trim().toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_|_$/g, "");
}

function statusBadgeClass(statusValue: TemplateStatus) {
  if (statusValue === "approved") {
    return "border-[#16A34A]/30 bg-[#16A34A]/10 text-[#166534]";
  }
  if (statusValue === "processing") {
    return "border-[#6D28D9]/30 bg-[#F3E8FF] text-[#4C1D95]";
  }
  if (statusValue === "rejected") {
    return "border-[#DC2626]/30 bg-[#DC2626]/10 text-[#DC2626]";
  }
  return "border-[#F59E0B]/30 bg-[#F59E0B]/10 text-[#111827]";
}

function statusLabel(statusValue: TemplateStatus) {
  if (statusValue === "processing") return "Processing";
  if (statusValue === "approved") return "Approved";
  if (statusValue === "pending") return "Pending Review";
  return "Rejected";
}

export default function MachineOnboardingPage() {
  const [machineType, setMachineType] = useState<MachineType>("Paper Cup");
  const [baseConfig, setBaseConfig] = useState<Record<string, string>>({});
  const [customFields, setCustomFields] = useState<CustomFieldRow[]>([{ id: Date.now(), label: "", value: "" }]);
  const [status, setStatus] = useState<"idle" | "saving" | "saved" | "error">("idle");
  const [errorMessage, setErrorMessage] = useState("");
  const [submittedTemplate, setSubmittedTemplate] = useState<MachineTemplateRecord | null>(null);

  const selectedFields = useMemo(() => machineFields[machineType], [machineType]);

  useEffect(() => {
    if (!submittedTemplate || submittedTemplate.status !== "processing") {
      return undefined;
    }

    const intervalId = window.setInterval(async () => {
      try {
        const refreshedTemplate = await getMachineTemplate(submittedTemplate.id);
        setSubmittedTemplate(refreshedTemplate);
      } catch {
        window.clearInterval(intervalId);
      }
    }, 2500);

    return () => window.clearInterval(intervalId);
  }, [submittedTemplate]);

  function updateBaseConfig(key: string, value: string) {
    setBaseConfig((current) => ({ ...current, [key]: value }));
  }

  function addCustomField() {
    setCustomFields((current) => [...current, { id: Date.now(), label: "", value: "" }]);
  }

  function updateCustomField(id: number, patch: Partial<CustomFieldRow>) {
    setCustomFields((current) => current.map((field) => (field.id === id ? { ...field, ...patch } : field)));
  }

  function removeCustomField(id: number) {
    setCustomFields((current) => (current.length === 1 ? current : current.filter((field) => field.id !== id)));
  }

  function buildPayload(): MachineOnboardingPayload {
    const typedBaseConfig = selectedFields.reduce<Record<string, string | number | boolean>>((acc, field) => {
      const rawValue = baseConfig[field.key];
      if (rawValue === undefined || rawValue === "") {
        return acc;
      }
      acc[field.key] = field.type === "number" ? Number(rawValue) : rawValue;
      return acc;
    }, {});

    const normalizedCustomFields = customFields.reduce<Record<string, string>>((acc, field) => {
      const key = normalizeKey(field.label);
      if (key) {
        acc[key] = field.value;
      }
      return acc;
    }, {});

    return {
      machine_type: machineType,
      base_config: typedBaseConfig,
      custom_fields: normalizedCustomFields
    };
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setStatus("saving");
    setErrorMessage("");

    try {
      const template = await submitMachineTemplate(buildPayload());
      setSubmittedTemplate(template);
      setStatus("saved");
      setBaseConfig({});
      setCustomFields([{ id: Date.now(), label: "", value: "" }]);
    } catch (error) {
      setStatus("error");
      setErrorMessage(error instanceof Error ? error.message : "Unable to save machine configuration");
    }
  }

  return (
    <div className="mx-auto max-w-5xl space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-normal text-[#111827]">Template Studio</h1>
        <p className="mt-1 text-sm text-[#4B5563]">Create AI-verified machine templates for factory onboarding.</p>
      </div>

      {submittedTemplate ? (
        <div className="rounded-lg border border-[#E5E7EB] bg-white p-4 shadow-sm">
          <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
            <p className="text-sm font-medium text-[#111827]">Template #{submittedTemplate.id}</p>
            <span className={`inline-flex w-fit items-center rounded-full border px-3 py-1 text-xs font-semibold capitalize ${statusBadgeClass(submittedTemplate.status)}`}>
              {statusLabel(submittedTemplate.status)}
            </span>
          </div>
          {submittedTemplate.status === "processing" ? (
            <p className="mt-2 text-sm text-[#4C1D95]">AI is verifying format, duplicate risk, and machine logic.</p>
          ) : null}
          {submittedTemplate.status === "approved" ? (
            <p className="mt-2 text-sm text-[#166534]">Approved. This template is now globally active.</p>
          ) : null}
          {submittedTemplate.status === "pending" ? (
            <p className="mt-2 text-sm text-[#111827]">Your custom template is under admin review.</p>
          ) : null}
          {submittedTemplate.ai_confidence !== null && submittedTemplate.ai_confidence !== undefined ? (
            <p className="mt-2 text-xs text-[#4B5563]">AI confidence: {(submittedTemplate.ai_confidence * 100).toFixed(0)}%</p>
          ) : null}
        </div>
      ) : null}

      <form className="space-y-6" onSubmit={handleSubmit}>
        <section className="rounded-lg border border-[#E5E7EB] bg-white p-5 shadow-sm">
          <label className="block text-sm font-medium text-[#4B5563]" htmlFor="machine-type">
            Machine Type
          </label>
          <select
            id="machine-type"
            className="mt-2 h-11 w-full max-w-sm rounded-md border border-[#E5E7EB] bg-white px-3 text-sm outline-none transition focus:border-[#6D28D9] focus:ring-2 focus:ring-[#F3E8FF]"
            value={machineType}
            onChange={(event) => {
              setMachineType(event.target.value as MachineType);
              setBaseConfig({});
            }}
          >
            {machineTypes.map((type) => (
              <option key={type} value={type}>
                {type}
              </option>
            ))}
          </select>

          <div className="mt-5 grid gap-4 md:grid-cols-2">
            {selectedFields.map((field) => (
              <label key={field.key} className="block text-sm font-medium text-[#4B5563]">
                {field.label}
                <input
                  className="mt-2 h-11 w-full rounded-md border border-[#E5E7EB] px-3 text-sm outline-none transition placeholder:text-[#4B5563] focus:border-[#6D28D9] focus:ring-2 focus:ring-[#F3E8FF]"
                  type={field.type}
                  min={field.type === "number" ? 0 : undefined}
                  placeholder={field.placeholder}
                  value={baseConfig[field.key] ?? ""}
                  onChange={(event) => updateBaseConfig(field.key, event.target.value)}
                />
              </label>
            ))}
          </div>
        </section>

        <section className="rounded-lg border border-[#E5E7EB] bg-white p-5 shadow-sm">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <h2 className="text-base font-semibold text-[#111827]">Custom Fields</h2>
              <p className="mt-1 text-sm text-[#4B5563]">Add values that are unique to this machine or factory.</p>
            </div>
            <button
              className="inline-flex h-10 items-center justify-center gap-2 rounded-md border border-[#E5E7EB] bg-white px-3 text-sm font-medium text-[#4B5563] transition hover:bg-[#FFF7ED]"
              type="button"
              onClick={addCustomField}
            >
              <Plus className="h-4 w-4" />
              Add Field
            </button>
          </div>

          <div className="mt-5 space-y-3">
            {customFields.map((field) => (
              <div key={field.id} className="grid gap-3 md:grid-cols-[1fr_1fr_auto]">
                <input
                  className="h-11 rounded-md border border-[#E5E7EB] px-3 text-sm outline-none transition placeholder:text-[#4B5563] focus:border-[#6D28D9] focus:ring-2 focus:ring-[#F3E8FF]"
                  placeholder="Label, e.g. Voltage"
                  value={field.label}
                  onChange={(event) => updateCustomField(field.id, { label: event.target.value })}
                />
                <input
                  className="h-11 rounded-md border border-[#E5E7EB] px-3 text-sm outline-none transition placeholder:text-[#4B5563] focus:border-[#6D28D9] focus:ring-2 focus:ring-[#F3E8FF]"
                  placeholder="Value, e.g. 220v"
                  value={field.value}
                  onChange={(event) => updateCustomField(field.id, { value: event.target.value })}
                />
                <button
                  className="grid h-11 w-11 place-items-center rounded-md border border-[#E5E7EB] text-[#4B5563] transition hover:bg-[#DC2626]/10 hover:text-[#DC2626]"
                  type="button"
                  aria-label="Remove custom field"
                  title="Remove custom field"
                  onClick={() => removeCustomField(field.id)}
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
            {status === "saving" ? "Submitting" : "Submit Template"}
          </button>
          {status === "saved" ? <p className="text-sm font-medium text-[#4C1D95]">Machine template submitted for AI verification.</p> : null}
          {status === "error" ? <p className="text-sm font-medium text-[#DC2626]">{errorMessage}</p> : null}
        </div>
      </form>
    </div>
  );
}
