import axios from "axios";
import { CloudUpload, Download, Loader2, X } from "lucide-react";
import { useRef, useState } from "react";
import type { ChangeEvent } from "react";

import {
  downloadMasterOnboardingTemplate,
  uploadMasterOnboardingSheet
} from "../lib/api";

type BulkUploadSectionProps = {
  onUploaded?: () => Promise<void> | void;
  onToast?: (message: string) => void;
};

function extractErrors(error: unknown): Array<Record<string, unknown>> {
  if (!axios.isAxiosError(error)) return [{ error: String(error) }];
  const detail = error.response?.data?.detail;
  if (Array.isArray(detail)) return detail;
  if (detail && typeof detail === "object") return [detail as Record<string, unknown>];
  return [{ error: detail || error.message || "Bulk upload failed" }];
}

export default function BulkUploadSection({ onUploaded, onToast }: BulkUploadSectionProps) {
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const [isBusy, setIsBusy] = useState(false);
  const [errorRows, setErrorRows] = useState<Array<Record<string, unknown>>>([]);

  async function handleDownload() {
    setIsBusy(true);
    try {
      const response = await downloadMasterOnboardingTemplate();
      const blobUrl = URL.createObjectURL(response.data);
      const link = document.createElement("a");
      link.href = blobUrl;
      link.download = "master_onboarding_bulk_upload.xlsx";
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(blobUrl);
    } catch (error) {
      setErrorRows(extractErrors(error));
    } finally {
      setIsBusy(false);
    }
  }

  async function handleFileChange(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;

    setIsBusy(true);
    setErrorRows([]);
    try {
      const response = await uploadMasterOnboardingSheet(file);
      onToast?.(`Master onboarding upload completed: ${response.data.rows_inserted} rows imported.`);
      await onUploaded?.();
    } catch (error) {
      setErrorRows(extractErrors(error));
    } finally {
      setIsBusy(false);
    }
  }

  return (
    <div className="mt-6 rounded-lg border border-zinc-200 bg-zinc-50 p-4">
      <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
        <div>
          <p className="text-sm font-semibold text-zinc-900">Master Onboarding Bulk Upload</p>
          <p className="mt-1 text-xs text-zinc-500">One workbook covers Factory Profile, Workers, Machines, Raw Materials, and Packaging Materials.</p>
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
            Upload Completed Master Sheet
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

      {errorRows.length > 0 ? (
        <div className="fixed inset-0 z-50 grid place-items-center bg-black/40 px-4">
          <div className="w-full max-w-2xl rounded-lg bg-white shadow-xl">
            <div className="flex items-center justify-between border-b border-zinc-200 px-5 py-4">
              <div>
                <h2 className="text-base font-semibold text-zinc-950">Bulk Upload Errors</h2>
                <p className="mt-1 text-xs text-zinc-500">Fix these Excel cells and upload again.</p>
              </div>
              <button
                type="button"
                className="grid h-8 w-8 place-items-center rounded-md text-zinc-500 hover:bg-zinc-100"
                onClick={() => setErrorRows([])}
              >
                <X className="h-4 w-4" />
              </button>
            </div>
            <div className="max-h-[420px] overflow-auto p-5">
              <pre className="whitespace-pre-wrap rounded-md bg-zinc-950 p-4 text-xs text-zinc-50">
                {JSON.stringify(errorRows, null, 2)}
              </pre>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
