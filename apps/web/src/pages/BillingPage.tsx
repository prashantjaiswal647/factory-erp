import { CheckCircle2, CreditCard, IndianRupee, ShieldCheck } from "lucide-react";
import { useState } from "react";

import { createBillingOrder, verifyBillingPayment } from "../lib/api";
import { useAuth } from "../context/AuthContext";

declare global {
  interface Window {
    Razorpay?: new (options: Record<string, unknown>) => { open: () => void };
  }
}

export default function BillingPage() {
  const { updateUser } = useAuth();
  const [message, setMessage] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  async function loadRazorpay() {
    if (window.Razorpay) return;
    await new Promise<void>((resolve, reject) => {
      const script = document.createElement("script");
      script.src = "https://checkout.razorpay.com/v1/checkout.js";
      script.onload = () => resolve();
      script.onerror = () => reject(new Error("Razorpay checkout failed to load"));
      document.body.appendChild(script);
    });
  }

  async function startCheckout() {
    setIsLoading(true);
    setMessage(null);
    try {
      await loadRazorpay();
      const order = await createBillingOrder();
      const Razorpay = window.Razorpay;
      if (!Razorpay) throw new Error("Razorpay checkout unavailable");

      new Razorpay({
        key: order.data.key_id,
        amount: order.data.amount,
        currency: order.data.currency,
        name: "Munshi AI",
        description: "Monthly Factory ERP subscription",
        order_id: order.data.order_id,
        handler: async (response: Record<string, string>) => {
          const verified = await verifyBillingPayment({
            razorpay_order_id: response.razorpay_order_id,
            razorpay_payment_id: response.razorpay_payment_id,
            razorpay_signature: response.razorpay_signature
          });
          updateUser({
            subscription_status: verified.data.subscription_status,
            trial_end_date: verified.data.trial_end_date,
            trial_days_remaining: verified.data.trial_days_remaining
          });
          setMessage("Payment verified. Subscription active for 30 days.");
        },
        theme: { color: "#004D40" }
      }).open();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Payment start failed");
    } finally {
      setIsLoading(false);
    }
  }

  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <header>
        <p className="text-sm font-semibold uppercase tracking-wide text-brand-700">Subscription</p>
        <h1 className="mt-2 text-3xl font-semibold text-zinc-950">Keep Munshi AI Active</h1>
        <p className="mt-2 text-sm text-zinc-500">Expired factories are locked until the owner renews the plan.</p>
      </header>

      <section className="grid gap-5 rounded-lg border border-zinc-200 bg-white p-6 shadow-sm md:grid-cols-[1fr_auto]">
        <div>
          <div className="flex items-center gap-3">
            <div className="grid h-12 w-12 place-items-center rounded-md bg-[#004D40] text-[#B2FF59]">
              <IndianRupee className="h-6 w-6" />
            </div>
            <div>
              <h2 className="text-xl font-semibold text-zinc-950">Munshi AI Monthly</h2>
              <p className="text-sm text-zinc-500">Production, sales, collection, AI insights, and WhatsApp automation.</p>
            </div>
          </div>
          <ul className="mt-6 grid gap-3 text-sm text-zinc-700 sm:grid-cols-2">
            {["Factory-level data isolation", "RBAC for owner and staff", "AI dashboard insights", "Razorpay-secured renewal"].map((item) => (
              <li key={item} className="flex items-center gap-2">
                <CheckCircle2 className="h-4 w-4 text-emerald-600" />
                {item}
              </li>
            ))}
          </ul>
        </div>

        <div className="rounded-lg border border-zinc-200 bg-zinc-50 p-5 text-center">
          <p className="text-sm text-zinc-500">Monthly plan</p>
          <p className="mt-2 text-4xl font-semibold text-zinc-950">₹999</p>
          <button
            className="mt-5 inline-flex h-11 items-center justify-center gap-2 rounded-md bg-[#004D40] px-5 text-sm font-semibold text-white hover:bg-[#00695C] disabled:cursor-not-allowed disabled:bg-zinc-400"
            disabled={isLoading}
            onClick={startCheckout}
            type="button"
          >
            <CreditCard className="h-4 w-4" />
            {isLoading ? "Starting..." : "Upgrade Now"}
          </button>
        </div>
      </section>

      {message ? (
        <div className="flex items-center gap-2 rounded-md border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm font-medium text-emerald-800">
          <ShieldCheck className="h-4 w-4" />
          {message}
        </div>
      ) : null}
    </div>
  );
}
