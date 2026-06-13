import axios from "axios";
import { AlertCircle, CheckCircle2, CloudUpload, Download, Loader2, TriangleAlert, X } from "lucide-react";
import { useRef, useState } from "react";
import type { ChangeEvent, ReactNode } from "react";

import {
  downloadMasterOnboardingTemplate,
  uploadMasterOnboardingSheet
} from "../lib/api";
import type { BulkValidationIssue, OnboardingBulkUploadResponse } from "../lib/api";

type BulkUploadSectionProps = {
  onUploaded?: () => Promise<void> | void;
  onToast?: (message: string) => void;
};

type UploadSummary = {
  message: string;
  status: string;
  rows: number;
  inserted: number;
  updated: number;
  unchanged: number;
  skipped: number;
  failed: number;
  warnings: number;
};

function issuesFromReport(report: unknown): BulkValidationIssue[] {
  if (!report || typeof report !== "object") return [];
  const value = report as {
    fatal_errors?: BulkValidationIssue[];
    warnings?: BulkValidationIssue[];
    info?: BulkValidationIssue[];
  };
  return [
    ...(Array.isArray(value.fatal_errors) ? value.fatal_errors : []),
    ...(Array.isArray(value.warnings) ? value.warnings : []),
    ...(Array.isArray(value.info) ? value.info : [])
  ];
}

function legacyRowsToIssues(rows: Array<Record<string, unknown>>): BulkValidationIssue[] {
  return rows.map((row) => ({
    row: typeof row.row === "number" ? row.row : null,
    field: typeof row.field === "string" ? row.field : "unknown",
    error: typeof row.error === "string" ? row.error : JSON.stringify(row),
    severity: "fatal",
    suggested_correction: typeof row.suggested_correction === "string" ? row.suggested_correction : null,
    sheet: typeof row.sheet === "string" ? row.sheet : "Workbook",
    section: typeof row.section === "string" ? row.section : null,
    raw_value: row.values ?? row.raw_value,
    action_type: typeof row.action_type === "string" ? row.action_type as BulkValidationIssue["action_type"] : "error"
  }));
}

function extractIssues(error: unknown): BulkValidationIssue[] {
  if (!axios.isAxiosError(error)) {
    return [{ row: null, field: "request", error: String(error), severity: "fatal", sheet: "Upload" }];
  }
  const detail = error.response?.data?.detail;
  if (detail && typeof detail === "object" && !Array.isArray(detail)) {
    const issues = issuesFromReport((detail as Record<string, unknown>).validation_report);
    if (issues.length > 0) return issues;
    const failedRows = (detail as Record<string, unknown>).failed_rows;
    if (Array.isArray(failedRows)) return legacyRowsToIssues(failedRows as Array<Record<string, unknown>>);
  }
  if (Array.isArray(detail)) return legacyRowsToIssues(detail as Array<Record<string, unknown>>);
  return [{ row: null, field: "request", error: String(detail || error.message || "Bulk upload failed"), severity: "fatal", sheet: "Upload" }];
}

function buildSummary(data: OnboardingBulkUploadResponse): UploadSummary {
  const operationCounts = data.operation_counts || {};
  const report = data.validation_report;
  return {
    message: data.message,
    status: data.overall_status || "success",
    rows: Number(data.rows_inserted || 0),
    inserted: Number(operationCounts.inserted || 0),
    updated: Number(operationCounts.updated || 0),
    unchanged: Number(operationCounts.unchanged || 0),
    skipped: Number(operationCounts.skipped || 0),
    failed: Number(operationCounts.failed ?? report?.fatal_count ?? 0),
    warnings: Number(operationCounts.warnings ?? report?.warning_count ?? 0)
  };
}

export default function BulkUploadSection({ onUploaded, onToast }: BulkUploadSectionProps) {
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const [isBusy, setIsBusy] = useState(false);
  const [issues, setIssues] = useState<BulkValidationIssue[]>([]);
  const [summary, setSummary] = useState<UploadSummary | null>(null);

  async function handleDownload() {
    setIsBusy(true);
    try {
      const response = await downloadMasterOnboardingTemplate();
      const blobUrl = URL.createObjectURL(response.data);
      const link = document.createElement("a");
      link.href = blobUrl;
      link.download = "Munshi_AI_Factory_Owner_Onboarding_Template.xlsx";
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(blobUrl);
    } catch (error) {
      setIssues(extractIssues(error));
    } finally {
      setIsBusy(false);
    }
  }

  async function handleFileChange(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    if (!window.confirm(
      "This will replace current onboarding master data with this Excel sheet. Items not present in the sheet will be removed or archived from active dashboard views."
    )) return;

    setIsBusy(true);
    setIssues([]);
    setSummary(null);
    try {
      const response = await uploadMasterOnboardingSheet(file);
      const nextSummary = buildSummary(response.data);
      setSummary(nextSummary);
      onToast?.(`Master data replace/update completed: ${nextSummary.rows} rows processed.`);
      await onUploaded?.();
    } catch (error) {
      setIssues(extractIssues(error));
    } finally {
      setIsBusy(false);
    }
  }

  return (
    <div className="mt-6 rounded-lg border border-zinc-200 bg-zinc-50 p-4">
      <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
        <div>
          <p className="text-sm font-semibold text-zinc-900">Replace / Update Master Data</p>
          <p className="mt-1 text-xs text-zinc-500">Enter business details only. Munshi AI generates technical IDs and validates machine, material, product, and packaging mappings.</p>
        </div>
        <div className="flex flex-col gap-2 sm:flex-row">
          <button
            type="button"
            className="inline-flex h-10 items-center justify-center gap-2 rounded-md bg-emerald-600 px-4 text-sm font-semibold text-white hover:bg-emerald-700 disabled:opacity-60"
            onClick={handleDownload}
            disabled={isBusy}
          >
            {isBusy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Download className="h-4 w-4" />}
            Download Master Onboarding Sheet
          </button>
          <button
            type="button"
            className="inline-flex h-10 items-center justify-center gap-2 rounded-md border border-zinc-300 bg-white px-4 text-sm font-semibold text-zinc-700 hover:bg-zinc-100 disabled:opacity-60"
            onClick={() => fileInputRef.current?.click()}
            disabled={isBusy}
          >
            {isBusy ? <Loader2 className="h-4 w-4 animate-spin" /> : <CloudUpload className="h-4 w-4" />}
            Replace / Update Master Data
          </button>
        </div>
      </div>
      <input
        ref={fileInputRef}
        type="file"
        accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        className="hidden"
        onChange={handleFileChange}
      />

      {summary ? (
        <div className="mt-4 grid gap-2 rounded-md border border-emerald-200 bg-emerald-50 p-3 text-xs text-emerald-900 sm:grid-cols-3 lg:grid-cols-7">
          <Metric label="Processed" value={summary.rows} />
          <Metric label="Created" value={summary.inserted} />
          <Metric label="Updated / Replaced" value={summary.updated} />
          <Metric label="Unchanged" value={summary.unchanged} />
          <Metric label="Archived / Removed" value={summary.skipped} />
          <Metric label="Warnings" value={summary.warnings} />
          <Metric label="Failed" value={summary.failed} />
        </div>
      ) : null}

      {issues.length > 0 ? (
        <div className="fixed inset-0 z-50 grid place-items-center bg-black/40 px-4">
          <div className="w-full max-w-5xl rounded-lg bg-white shadow-xl">
            <div className="flex items-center justify-between border-b border-zinc-200 px-5 py-4">
              <div>
                <h2 className="text-base font-semibold text-zinc-950">Bulk Upload Validation Report</h2>
                <p className="mt-1 text-xs text-zinc-500">Review sheet, section, row, current value, action, issue, and correction guidance.</p>
              </div>
              <button
                type="button"
                className="grid h-8 w-8 place-items-center rounded-md text-zinc-500 hover:bg-zinc-100"
                onClick={() => setIssues([])}
              >
                <X className="h-4 w-4" />
              </button>
            </div>
            <div className="max-h-[65vh] space-y-3 overflow-y-auto p-5">
              <IssueGroup title="Fatal Errors / जरूरी सुधार" severity="fatal" issues={issues} icon={<AlertCircle className="h-4 w-4" />} />
              <IssueGroup title="Warnings / चेतावनी" severity="warning" issues={issues} icon={<TriangleAlert className="h-4 w-4" />} />
              <IssueGroup title="Auto-fixed / अपने आप ठीक किया" severity="info" issues={issues} icon={<CheckCircle2 className="h-4 w-4" />} />
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}

function Metric({ label, value }: { label: string; value: number }) {
  return (
    <div>
      <p className="font-semibold uppercase tracking-wide text-emerald-700">{label}</p>
      <p className="mt-1 text-base font-black text-emerald-950">{value}</p>
    </div>
  );
}

function IssueGroup({ title, severity, issues, icon }: {
  title: string;
  severity: BulkValidationIssue["severity"];
  issues: BulkValidationIssue[];
  icon: ReactNode;
}) {
  const matching = issues.filter((issue) => issue.severity === severity);
  if (!matching.length) return null;
  const colors = severity === "fatal"
    ? "border-red-200 bg-red-50 text-red-800"
    : severity === "warning"
      ? "border-amber-200 bg-amber-50 text-amber-800"
      : "border-emerald-200 bg-emerald-50 text-emerald-800";
  return (
    <details open={severity === "fatal"} className={`rounded-lg border ${colors}`}>
      <summary className="flex cursor-pointer list-none items-center gap-2 px-4 py-3 text-sm font-bold">
        {icon}
        {title} ({matching.length})
      </summary>
      <div className="space-y-2 border-t border-current/10 p-3">
        {matching.map((issue, index) => (
          <div key={`${issue.sheet}-${issue.row}-${index}`} className="rounded-md bg-white/80 p-3 text-sm text-zinc-800">
            <p className="font-semibold">{issue.sheet || "Workbook"}{issue.row ? `, Row ${issue.row}` : ""}</p>
            <p className="mt-1">{issue.error}</p>
            {issue.suggested_correction ? (
              <p className="mt-2 text-xs font-medium text-zinc-600">Correction: {issue.suggested_correction}</p>
            ) : null}
          </div>
        ))}
      </div>
    </details>
  );
}
