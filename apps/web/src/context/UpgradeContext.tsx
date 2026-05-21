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
              toast.tone === "warning" ? "border-[#F59E0B]/30 bg-[#F59E0B]/10 text-[#111827]" : "",
              toast.tone === "success" ? "border-[#16A34A]/30 bg-[#16A34A]/10 text-[#166534]" : "",
              toast.tone === "info" ? "border-[#E5E7EB] bg-white text-[#111827]" : ""
            ].join(" ")}
          >
            {toast.message}
          </div>
        ))}
      </div>
      {upgradeDetail ? (
        <div className="fixed inset-0 z-50 grid place-items-center bg-[#111827]/50 px-4">
          <div className="w-full max-w-lg rounded-lg border border-[#E5E7EB] bg-white p-6 shadow-xl">
            <div className="flex items-start justify-between gap-4">
              <div>
                <h2 className="text-lg font-semibold text-[#111827]">Upgrade Required</h2>
                <p className="mt-2 text-sm text-[#4B5563]">{upgradeDetail.message}</p>
              </div>
              <button className="text-sm font-semibold text-[#4B5563] hover:text-[#6D28D9]" type="button" onClick={() => setUpgradeDetail(null)}>
                Close
              </button>
            </div>

            <div className="mt-5 rounded-lg border border-[#E5E7EB]">
              {[
                ["Current plan", `${upgradeDetail.used}/${upgradeDetail.limit} machines used`],
                ["Next plan", "Higher machine capacity"],
                ["Includes", "More factories, staff roles, AI automation, and priority scaling"]
              ].map(([label, value]) => (
                <div key={label} className="grid grid-cols-[130px_1fr] border-b border-[#E5E7EB] px-4 py-3 last:border-b-0">
                  <span className="text-sm font-semibold text-[#111827]">{label}</span>
                  <span className="text-sm text-[#4B5563]">{value}</span>
                </div>
              ))}
            </div>

            <div className="mt-6 flex justify-end gap-3">
              <button className="h-10 rounded-md border border-[#E5E7EB] px-4 text-sm font-semibold text-[#4B5563] hover:bg-[#FFF7ED]" type="button" onClick={() => setUpgradeDetail(null)}>
                Not now
              </button>
              <button
                className="h-10 rounded-md bg-[#6D28D9] px-4 text-sm font-semibold text-white hover:bg-[#4C1D95]"
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
