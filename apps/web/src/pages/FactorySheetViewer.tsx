import { ArrowLeft, ExternalLink } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { superAdminApi } from "../lib/api";

type FactorySheetOverview = {
  factory_id: number;
  factory_name: string;
  registered_owner_email?: string | null;
  phone_number?: string | null;
  google_spreadsheet_id?: string | null;
  created_at?: string | null;
};

export default function FactorySheetViewer() {
  const { factoryId } = useParams();
  const [factories, setFactories] = useState<FactorySheetOverview[]>([]);
  const [error, setError] = useState("");
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    let isMounted = true;

    async function loadFactorySheet() {
      setIsLoading(true);
      setError("");
      try {
        const response = await superAdminApi.get<FactorySheetOverview[]>("/api/admin/overview");
        if (isMounted) setFactories(response.data);
      } catch (caught) {
        if (!isMounted) return;
        setError(caught instanceof Error ? caught.message : "Factory sheet metadata load failed");
      } finally {
        if (isMounted) setIsLoading(false);
      }
    }

    void loadFactorySheet();
    return () => {
      isMounted = false;
    };
  }, []);

  const selectedFactory = useMemo(
    () => factories.find((factory) => String(factory.factory_id) === String(factoryId)) || null,
    [factories, factoryId],
  );
  const spreadsheetId = selectedFactory?.google_spreadsheet_id || "";
  const spreadsheetSrc = spreadsheetId ? `https://docs.google.com/spreadsheets/d/${spreadsheetId}/edit?usp=sharing` : "";

  return (
    <div className="min-h-[calc(100vh-96px)] bg-slate-900 text-white">
      <div className="border-b border-gray-700 bg-slate-950 px-4 py-4 sm:px-6">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
          <div>
            <Link
              to="/munshi-control-room/dashboard"
              className="inline-flex items-center gap-2 rounded-md border border-gray-700 px-3 py-2 text-sm font-bold text-slate-200 hover:bg-slate-800"
            >
              <ArrowLeft className="h-4 w-4" />
              Back to Control Room Overview
            </Link>
            <h1 className="mt-4 text-2xl font-black sm:text-3xl">Live Google Sheet Auditor - Factory ID: {factoryId || "-"}</h1>
          </div>
          <div className="rounded-lg border border-gray-700 bg-slate-900 px-4 py-3 text-sm text-slate-300">
            <p className="font-bold text-white">{selectedFactory?.factory_name || "Factory sheet context"}</p>
            <p>{selectedFactory?.registered_owner_email || "Owner email unavailable"}</p>
          </div>
        </div>
      </div>

      <main className="p-4 sm:p-6">
        {isLoading ? (
          <div className="flex h-[calc(100vh-180px)] items-center justify-center rounded-xl border border-gray-700 bg-slate-950 text-sm font-bold text-slate-300">
            Loading live spreadsheet...
          </div>
        ) : error ? (
          <div className="rounded-xl border border-red-800 bg-red-950/60 p-5 text-sm font-semibold text-red-100">{error}</div>
        ) : spreadsheetSrc ? (
          <section className="overflow-hidden rounded-xl border border-gray-700 bg-slate-950 shadow-2xl">
            <div className="flex flex-col gap-2 border-b border-gray-700 px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
              <div>
                <p className="text-sm font-black">{selectedFactory?.factory_name}</p>
                <p className="font-mono text-xs text-slate-400">{spreadsheetId}</p>
              </div>
              <a className="inline-flex items-center gap-2 text-sm font-bold text-indigo-300 hover:text-indigo-200" href={spreadsheetSrc} target="_blank" rel="noreferrer">
                Open in Google Sheets
                <ExternalLink className="h-4 w-4" />
              </a>
            </div>
            <iframe
              src={spreadsheetSrc}
              className="w-full h-[calc(100vh-120px)] border-0 rounded-b-xl"
              allowFullScreen
              title={`Google Sheet Factory ${factoryId}`}
            />
          </section>
        ) : (
          <div className="flex h-[calc(100vh-180px)] items-center justify-center rounded-xl border border-gray-700 bg-slate-950 p-6 text-center">
            <div>
              <p className="text-lg font-black">Google Spreadsheet ID not configured.</p>
              <p className="mt-2 text-sm text-slate-400">Factory ID {factoryId || "-"} exists without live sheet metadata in `/api/admin/overview`.</p>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
