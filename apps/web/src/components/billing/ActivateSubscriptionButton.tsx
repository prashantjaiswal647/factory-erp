import { useState } from "react";
import { Copy, ExternalLink } from "lucide-react";

import { createCashfreeSubscription } from "../../api/billing";
import type { PlanCode } from "../../types/billing";

export default function ActivateSubscriptionButton({ factoryId }: { factoryId: number }) {
  const [open, setOpen] = useState(false);
  const [planCode, setPlanCode] = useState<PlanCode>("monthly");
  const [url, setUrl] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function activate() {
    setLoading(true);
    setError("");
    try {
      const result = await createCashfreeSubscription(factoryId, planCode);
      setUrl(result.hosted_payment_url);
    } catch {
      setError("Cashfree activation failed.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <>
      <button className="rounded-md bg-emerald-700 px-3 py-2 text-sm font-bold text-white" type="button" onClick={() => setOpen(true)}>
        Activate Cashfree
      </button>
      {open ? (
        <div className="fixed inset-0 z-[60] grid place-items-center bg-black/40 p-4">
          <div className="w-full max-w-md rounded-lg bg-white p-5 shadow-xl">
            <h3 className="text-lg font-black">Activate Cashfree subscription</h3>
            <select className="mt-4 h-10 w-full border border-zinc-300 px-3" value={planCode} onChange={(event) => setPlanCode(event.target.value as PlanCode)}>
              <option value="monthly">Monthly</option>
              <option value="quarterly">Quarterly</option>
              <option value="yearly">Yearly</option>
            </select>
            {error ? <p className="mt-3 text-sm text-red-700">{error}</p> : null}
            {url ? (
              <div className="mt-4 flex gap-2">
                <a className="inline-flex items-center gap-2 text-sm font-bold text-indigo-700" href={url} target="_blank" rel="noreferrer">
                  Open authorization <ExternalLink size={16} />
                </a>
                <button title="Copy authorization URL" type="button" onClick={() => void navigator.clipboard.writeText(url)}>
                  <Copy size={16} />
                </button>
              </div>
            ) : null}
            <div className="mt-5 flex justify-end gap-2">
              <button className="border px-3 py-2 text-sm font-bold" type="button" onClick={() => setOpen(false)}>Close</button>
              <button className="bg-emerald-700 px-3 py-2 text-sm font-bold text-white disabled:opacity-50" type="button" disabled={loading} onClick={activate}>
                {loading ? "Creating..." : "Create subscription"}
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </>
  );
}
