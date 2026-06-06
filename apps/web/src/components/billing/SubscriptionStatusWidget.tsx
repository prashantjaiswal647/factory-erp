import { useCallback, useEffect, useState } from "react";

import { getBillingMe } from "../../api/billing";
import type { BillingMeResponse } from "../../types/billing";

const badgeClass: Record<string, string> = {
  active: "bg-emerald-100 text-emerald-800",
  cancelled: "bg-red-100 text-red-800",
  past_due: "bg-red-100 text-red-800",
  pending: "bg-amber-100 text-amber-800",
  trialing: "bg-zinc-100 text-zinc-700",
  trial_active: "bg-zinc-100 text-zinc-700",
};

export default function SubscriptionStatusWidget() {
  const [billing, setBilling] = useState<BillingMeResponse | null>(null);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    try {
      setBilling(await getBillingMe());
      setError("");
    } catch {
      setError("Unable to load subscription status.");
    }
  }, []);

  useEffect(() => {
    void load();
    const onFocus = () => void load();
    window.addEventListener("focus", onFocus);
    return () => window.removeEventListener("focus", onFocus);
  }, [load]);

  if (error) return <p className="text-sm text-red-700">{error}</p>;
  if (!billing) return <p className="text-sm text-zinc-500">Loading subscription...</p>;
  const status = billing.subscription_status || "not active";
  return (
    <section className="border-y border-zinc-200 py-4" data-testid="subscription-status-widget">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-base font-bold text-zinc-950">Cashfree subscription</h2>
          <p className="mt-1 text-sm text-zinc-600">
            {billing.current_period_end
              ? `Current period ends ${new Date(billing.current_period_end).toLocaleDateString()}`
              : "No paid billing period is active."}
          </p>
        </div>
        <span className={`px-2.5 py-1 text-xs font-bold uppercase ${badgeClass[status] || "bg-zinc-100 text-zinc-700"}`}>
          {status.replace("_", " ")}
        </span>
      </div>
    </section>
  );
}
