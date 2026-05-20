import { createContext, useContext, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { useNavigate } from "react-router-dom";

import type { UpgradeRequiredDetail } from "../lib/api";

type ToastTone = "info" | "warning" | "success";

type ToastMessage = {
  id: number;
  message: string;
  tone: ToastTone;
};

type UpgradeContextValue = {
  showToast: (message: string, tone?: ToastTone) => void;
  showUpgradeModal: (detail: UpgradeRequiredDetail) => void;
};

const UpgradeContext = createContext<UpgradeContextValue | undefined>(undefined);

export function UpgradeProvider({ children }: { children: ReactNode }) {
  const [upgradeDetail, setUpgradeDetail] = useState<UpgradeRequiredDetail | null>(null);
  const [toasts, setToasts] = useState<ToastMessage[]>([]);
  const navigate = useNavigate();

  function showToast(message: string, tone: ToastTone = "info") {
    const id = Date.now();
    setToasts((current) => [...current, { id, message, tone }]);
    window.setTimeout(() => {
      setToasts((current) => current.filter((toast) => toast.id !== id));
    }, 3500);
  }

  function showUpgradeModal(detail: UpgradeRequiredDetail) {
    setUpgradeDetail(detail);
  }

  useEffect(() => {
    function handleUpgradeRequired(event: Event) {
      const detail = (event as CustomEvent<UpgradeRequiredDetail>).detail;
      if (detail?.code === "UPGRADE_REQUIRED") {
        setUpgradeDetail(detail);
      }
    }

    window.addEventListener("upgrade-required", handleUpgradeRequired);
    return () => window.removeEventListener("upgrade-required", handleUpgradeRequired);
  }, []);

  const value = useMemo(() => ({ showToast, showUpgradeModal }), []);

  return (
    <UpgradeContext.Provider value={value}>
      {children}
      <div className="fixed right-4 top-4 z-50 space-y-2">
        {toasts.map((toast) => (
          <div
            key={toast.id}
            className={[
              "w-80 rounded-lg border px-4 py-3 text-sm font-medium shadow-lg",
              toast.tone === "warning" ? "border-amber-200 bg-amber-50 text-amber-900" : "",
              toast.tone === "success" ? "border-emerald-200 bg-emerald-50 text-emerald-800" : "",
              toast.tone === "info" ? "border-zinc-200 bg-white text-zinc-800" : ""
            ].join(" ")}
          >
            {toast.message}
          </div>
        ))}
      </div>
      {upgradeDetail ? (
        <div className="fixed inset-0 z-50 grid place-items-center bg-zinc-950/50 px-4">
          <div className="w-full max-w-lg rounded-lg bg-white p-6 shadow-xl">
            <div className="flex items-start justify-between gap-4">
              <div>
                <h2 className="text-lg font-semibold text-zinc-950">Upgrade Required</h2>
                <p className="mt-2 text-sm text-zinc-600">{upgradeDetail.message}</p>
              </div>
              <button className="text-sm font-semibold text-zinc-500" type="button" onClick={() => setUpgradeDetail(null)}>
                Close
              </button>
            </div>

            <div className="mt-5 rounded-lg border border-zinc-200">
              {[
                ["Current plan", `${upgradeDetail.used}/${upgradeDetail.limit} machines used`],
                ["Next plan", "Higher machine capacity"],
                ["Includes", "More factories, staff roles, AI automation, and priority scaling"]
              ].map(([label, value]) => (
                <div key={label} className="grid grid-cols-[130px_1fr] border-b border-zinc-200 px-4 py-3 last:border-b-0">
                  <span className="text-sm font-semibold text-zinc-700">{label}</span>
                  <span className="text-sm text-zinc-600">{value}</span>
                </div>
              ))}
            </div>

            <div className="mt-6 flex justify-end gap-3">
              <button className="h-10 rounded-md border border-zinc-300 px-4 text-sm font-semibold text-zinc-700" type="button" onClick={() => setUpgradeDetail(null)}>
                Not now
              </button>
              <button
                className="h-10 rounded-md bg-brand-600 px-4 text-sm font-semibold text-white hover:bg-brand-700"
                type="button"
                onClick={() => {
                  setUpgradeDetail(null);
                  navigate("/billing");
                }}
              >
                Upgrade Now
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </UpgradeContext.Provider>
  );
}

export function useUpgrade() {
  const context = useContext(UpgradeContext);
  if (!context) {
    throw new Error("useUpgrade must be used inside UpgradeProvider");
  }
  return context;
}
