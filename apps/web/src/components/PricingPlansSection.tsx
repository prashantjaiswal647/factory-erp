import { CheckCircle2, CreditCard, MessageCircle, ShieldCheck, Sparkles, X } from "lucide-react";
import { FormEvent, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { useNavigate } from "react-router-dom";

import PhoneNumberInput from "./PhoneNumberInput";
import { useAuth } from "../context/AuthContext";
import { useDataRefresh } from "../context/DataRefreshContext";
import {
  createBillingOrder,
  getCashfreeOrderStatus,
  getBillingStatus,
  getPricingPlans,
  startFreeTrial,
  submitCustomPlanEnquiry,
  submitDemoBooking,
} from "../lib/api";
import type { PricingPlan } from "../lib/api";
import { splitE164Phone, validateLocalPhone } from "../lib/phoneCountries";

declare global {
  interface Window {
    Cashfree?: (options: { mode: "sandbox" | "production" }) => {
      checkout: (options: { paymentSessionId: string; redirectTarget: "_self" | "_modal" }) => Promise<{ error?: { message?: string } }>;
    };
  }
}

type BillingCycle = "monthly" | "yearly";
type PricingSource = "landing" | "billing";

const fallbackPlans: PricingPlan[] = [
  {
    code: "basic",
    name: "Basic",
    machine_limit_label: "Up to 7 Machines",
    monthly_label: "\u20B9999 + GST / month",
    yearly_label: "\u20B99,999 + GST / year",
    features: ["Best for small factories", "Up to 7 Machines", "Production, inventory, finance", "E-invoicing", "AI reports"],
    price: { monthly: 99900, yearly_original: 1198800, yearly_discounted: 999900 },
    is_custom: false
  },
  {
    code: "growth",
    name: "Growth",
    machine_limit_label: "Up to 20 Machines",
    monthly_label: "\u20B91,999 + GST / month",
    yearly_label: "\u20B919,999 + GST / year",
    features: ["Best for growing factories", "Up to 20 Machines", "Advanced dashboards", "Payment reminders", "n8n automation"],
    price: { monthly: 199900, yearly_original: 2398800, yearly_discounted: 1999900 },
    is_custom: false
  },
  {
    code: "premium",
    name: "Premium",
    machine_limit_label: "20 to 50 Machines",
    monthly_label: "\u20B94,999 + GST / month",
    yearly_label: "\u20B949,999 + GST / year",
    features: ["Best for large factories", "20 to 50 Machines", "Priority AI workflows", "Advanced analytics", "Priority support"],
    price: { monthly: 499900, yearly_original: 5998800, yearly_discounted: 4999900 },
    is_custom: false
  },
  {
    code: "custom",
    name: "Custom",
    machine_limit_label: "50+ Machines",
    monthly_label: "Starting from \u20B91,00,000 + GST",
    features: ["50+ machines / special requirements", "Custom workflows", "Implementation support", "Dedicated success planning"],
    price: { monthly: 0, starts_from: 10000000 },
    is_custom: true
  }
];

const planCopy: Record<string, { subtitle: string; badges: string[]; cta: string; secondaryCta?: string; featured?: boolean }> = {
  basic: {
    subtitle: "Best for small factories",
    badges: ["\u2713 7 Days Free Trial Available"],
    cta: "Start 7 Days Free Trial",
    secondaryCta: "Choose Basic"
  },
  growth: {
    subtitle: "Best for growing factories",
    badges: ["No Free Trial", "Recommended for growing factories"],
    cta: "Buy Growth Plan",
    featured: true
  },
  premium: {
    subtitle: "Best for large factories",
    badges: ["No Free Trial", "Recommended for established factories"],
    cta: "Buy Premium Plan"
  },
  custom: {
    subtitle: "50+ machines / special requirements",
    badges: ["Contact Sales"],
    cta: "Contact Sales"
  }
};

type Props = {
  className?: string;
  source?: PricingSource;
};

export default function PricingPlansSection({ className = "", source = "billing" }: Props) {
  const navigate = useNavigate();
  const { updateUser, user } = useAuth();
  const { triggerDataRefresh } = useDataRefresh();
  const [plans, setPlans] = useState<PricingPlan[]>(fallbackPlans);
  const [billingCycle, setBillingCycle] = useState<BillingCycle>("monthly");
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoadingPlan, setIsLoadingPlan] = useState<string | null>(null);
  const [isCustomOpen, setIsCustomOpen] = useState(false);
  const [isDemoOpen, setIsDemoOpen] = useState(false);
  const [customForm, setCustomForm] = useState({
    owner_name: user?.full_name || "",
    factory_name: user?.factory_name || "",
    phone: user?.phone_number || "",
    email: user?.username?.includes("@") ? user.username : "",
    number_of_machines: 51,
    requirement_details: ""
  });
  const [demoForm, setDemoForm] = useState({
    owner_name: user?.full_name || "",
    factory_name: user?.factory_name || "",
    phone: user?.phone_number || "",
    email: user?.username?.includes("@") ? user.username : "",
    preferred_plan: "basic",
    message: ""
  });

  useEffect(() => {
    getPricingPlans()
      .then((response) => setPlans(mergePricingPlans(response.data)))
      .catch(() => setPlans(fallbackPlans));
  }, []);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const orderId = params.get("order_id");
    if (params.get("cashfree") !== "return" || !orderId || !user) return;
    const cashfreeOrderId = orderId;
    let active = true;
    let attempts = 0;
    async function poll() {
      try {
        const response = await getCashfreeOrderStatus(cashfreeOrderId);
        if (!active) return;
        if (response.data.subscription_active) {
          await refreshBillingStatus();
          triggerDataRefresh();
          setMessage("Payment verified. Your subscription is active.");
          window.history.replaceState({}, "", "/billing?payment=success");
          return;
        }
        if (["failed", "user_dropped"].includes(response.data.payment_status || "")) {
          setError("Payment was not completed. You can retry from the selected plan.");
          window.history.replaceState({}, "", "/billing?payment=failed");
          return;
        }
      } catch {
        if (active) setError("Unable to verify payment status yet.");
      }
      attempts += 1;
      if (active && attempts < 10) window.setTimeout(poll, 2000);
      else if (active) setMessage("Payment confirmation is pending. Refresh this page shortly.");
    }
    void poll();
    return () => {
      active = false;
    };
  }, [user]);

  const paidPlans = useMemo(() => plans.filter((plan) => !plan.is_custom), [plans]);
  const customPlan = plans.find((plan) => plan.is_custom) || fallbackPlans[3];
  const customPhone = splitE164Phone(customForm.phone);
  const demoPhone = splitE164Phone(demoForm.phone);

  async function refreshBillingStatus() {
    const response = await getBillingStatus();
    updateUser({
      subscription_status: response.data.subscription_status,
      trial_end_date: response.data.trial_end_date,
      trial_days_remaining: response.data.trial_days_remaining,
      active_plan: response.data.active_plan,
      billing_cycle: response.data.billing_cycle,
      subscription_start_date: response.data.subscription_start_date,
      subscription_end_date: response.data.subscription_end_date,
      payment_status: response.data.payment_status
    });
    return response.data;
  }

  async function loadCashfree() {
    if (window.Cashfree) return;
    await new Promise<void>((resolve, reject) => {
      const script = document.createElement("script");
      script.src = "https://sdk.cashfree.com/js/v3/cashfree.js";
      script.onload = () => resolve();
      script.onerror = () => reject(new Error("Cashfree checkout failed to load"));
      document.body.appendChild(script);
    });
  }

  function redirectToSignup(plan: PricingPlan) {
    navigate(`/login?tab=signup&plan=${encodeURIComponent(plan.code)}&billing=${billingCycle}`);
  }

  async function startBasicTrial(plan: PricingPlan) {
    if (!user) {
      redirectToSignup(plan);
      return;
    }
    setIsLoadingPlan(`${plan.code}-trial`);
    setMessage(null);
    setError(null);
    try {
      const response = await startFreeTrial({ plan_code: "basic" });
      updateUser(response.data);
      triggerDataRefresh();
      setMessage("Basic plan 7-day free trial started.");
    } catch (caught) {
      setError(getErrorMessage(caught, "Free trial start failed."));
    } finally {
      setIsLoadingPlan(null);
    }
  }

  async function startCheckout(plan: PricingPlan) {
    if (plan.is_custom) {
      setIsCustomOpen(true);
      return;
    }
    if (!user) {
      redirectToSignup(plan);
      return;
    }
    setIsLoadingPlan(plan.code);
    setMessage(null);
    setError(null);
    try {
      await loadCashfree();
      const order = await createBillingOrder({ plan_code: plan.code, billing_cycle: billingCycle });
      const Cashfree = window.Cashfree;
      if (!Cashfree) throw new Error("Cashfree checkout unavailable");
      const mode = (order.data.cashfree_mode || "sandbox") as "production" | "sandbox";
      const paymentSessionId = order.data.payment_session_id || "";
      const result = await Cashfree({ mode }).checkout({
        paymentSessionId,
        redirectTarget: "_self"
      });
      if (result?.error) throw new Error(result.error.message || "Cashfree checkout failed");
    } catch (caught) {
      setError(getErrorMessage(caught, "Payment start failed."));
    } finally {
      setIsLoadingPlan(null);
    }
  }

  async function submitCustom(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setMessage(null);
    if (!validateLocalPhone(customPhone.country.dialCode, customPhone.localNumber)) {
      setError("Please enter a valid phone number for the selected country.");
      return;
    }
    try {
      const response = await submitCustomPlanEnquiry({
        ...customForm,
        country_code: customPhone.country.dialCode,
        phone: customPhone.localNumber
      });
      setMessage(response.data.message);
      setIsCustomOpen(false);
    } catch (caught) {
      setError(getErrorMessage(caught, "Custom enquiry failed."));
    }
  }

  async function submitDemo(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setMessage(null);
    if (!validateLocalPhone(demoPhone.country.dialCode, demoPhone.localNumber)) {
      setError("Please enter a valid phone number for the selected country.");
      return;
    }
    try {
      const response = await submitDemoBooking({
        ...demoForm,
        country_code: demoPhone.country.dialCode,
        phone: demoPhone.localNumber
      });
      setMessage(response.data.message);
      setIsDemoOpen(false);
    } catch (caught) {
      setError(getErrorMessage(caught, "Demo booking failed."));
    }
  }

  return (
    <section id="pricing" className={`bg-[#FFF7ED] px-4 py-16 lg:px-8 ${className}`}>
      <div className="mx-auto max-w-7xl">
        <header className="rounded-3xl border border-[#E5E7EB] bg-white p-6 shadow-sm shadow-orange-100/70 md:p-8">
          <div className="flex flex-col gap-5 lg:flex-row lg:items-end lg:justify-between">
            <div>
              <p className="inline-flex items-center gap-2 rounded-full bg-[#F3E8FF] px-3 py-1 text-sm font-black uppercase tracking-wide text-[#6D28D9]">
                <Sparkles className="h-4 w-4" />
                Plans & Pricing
              </p>
              <h2 className="mt-4 text-3xl font-black tracking-tight text-[#111827] md:text-4xl">
                Machine count ke hisaab se Munshi AI plan choose karein.
              </h2>
              <p className="mt-3 max-w-3xl text-base leading-7 text-[#4B5563]">
                Basic plan par 7-day free trial available hai. Growth, Premium aur Custom plans activation ke liye purchase required hai.
              </p>
            </div>
            <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
              <button
                className="h-11 rounded-xl border border-[#6D28D9] bg-white px-5 text-sm font-bold text-[#6D28D9] transition hover:bg-[#F3E8FF]"
                type="button"
                onClick={() => setIsDemoOpen(true)}
              >
                Book Demo
              </button>
              <div className="grid w-full grid-cols-2 rounded-xl border border-[#E5E7EB] bg-[#FFF7ED] p-1 sm:w-72">
                {(["monthly", "yearly"] as BillingCycle[]).map((cycle) => (
                  <button
                    key={cycle}
                    className={`h-10 rounded-lg text-sm font-bold capitalize transition ${
                      billingCycle === cycle ? "bg-[#6D28D9] text-white shadow-sm" : "text-[#4B5563] hover:bg-white"
                    }`}
                    type="button"
                    onClick={() => setBillingCycle(cycle)}
                  >
                    {cycle === "yearly" ? "Yearly Save" : "Monthly"}
                  </button>
                ))}
              </div>
            </div>
          </div>
        </header>

        <Messages message={message} error={error} />

        <div className="mt-8 grid gap-5 lg:grid-cols-4">
          {paidPlans.map((plan) => (
            <PlanCard
              key={plan.code}
              billingCycle={billingCycle}
              isLoading={isLoadingPlan === plan.code || isLoadingPlan === `${plan.code}-trial`}
              onBuy={() => startCheckout(plan)}
              onTrial={plan.code === "basic" ? () => startBasicTrial(plan) : undefined}
              plan={plan}
            />
          ))}
          <CustomPlanCard customPlan={customPlan} onOpen={() => setIsCustomOpen(true)} />
        </div>

        <div className="mt-6 grid gap-3 rounded-2xl border border-[#E5E7EB] bg-white p-5 text-sm font-semibold text-[#4B5563] shadow-sm md:grid-cols-3">
          <p>GST extra as applicable.</p>
          <p>7-day free trial available only on Basic Plan.</p>
          <p>Growth, Premium and Custom plans require activation through purchase.</p>
        </div>

        {source === "landing" ? (
          <div className="mt-8 rounded-3xl bg-[#4C1D95] p-6 text-white shadow-2xl shadow-purple-200 md:p-8">
            <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
              <div>
                <p className="text-sm font-bold uppercase tracking-wide text-purple-200">Factory Audit</p>
                <h3 className="mt-2 text-2xl font-black">Start free. Apne factory workflow ka smart audit karein.</h3>
              </div>
              <button
                className="inline-flex h-12 items-center justify-center rounded-lg bg-white px-6 font-bold text-[#4C1D95]"
                type="button"
                onClick={() => {
                  const basic = plans.find((plan) => plan.code === "basic") || fallbackPlans[0];
                  void startBasicTrial(basic);
                }}
              >
                Start 7 Days Free Trial
              </button>
            </div>
          </div>
        ) : null}
      </div>

      {isCustomOpen ? (
        <Modal title="Custom plan enquiry" description="50+ machines, multi-factory setup ya special workflow ke liye details bhejein." onClose={() => setIsCustomOpen(false)}>
          <form onSubmit={submitCustom}>
            <div className="grid gap-3 sm:grid-cols-2">
              <FormInput label="Owner Name" value={customForm.owner_name} onChange={(owner_name) => setCustomForm({ ...customForm, owner_name })} />
              <FormInput label="Factory Name" value={customForm.factory_name} onChange={(factory_name) => setCustomForm({ ...customForm, factory_name })} />
              <PhoneNumberInput
                countryCode={customPhone.country.dialCode}
                localNumber={customPhone.localNumber}
                onCountryCodeChange={(country_code) => setCustomForm({ ...customForm, phone: `${country_code}${customPhone.localNumber}` })}
                onLocalNumberChange={(phone) => setCustomForm({ ...customForm, phone: `${customPhone.country.dialCode}${phone}` })}
              />
              <FormInput label="Email" type="email" value={customForm.email} onChange={(email) => setCustomForm({ ...customForm, email })} />
              <FormInput
                label="Number of Machines"
                type="number"
                value={String(customForm.number_of_machines)}
                onChange={(number_of_machines) => setCustomForm({ ...customForm, number_of_machines: Number(number_of_machines) })}
              />
              <TextArea label="Requirement Details" value={customForm.requirement_details} onChange={(requirement_details) => setCustomForm({ ...customForm, requirement_details })} />
            </div>
            <button className="mt-5 h-11 w-full rounded-lg bg-[#6D28D9] px-4 text-sm font-bold text-white hover:bg-[#4C1D95]" type="submit">
              Submit Enquiry
            </button>
          </form>
        </Modal>
      ) : null}

      {isDemoOpen ? (
        <Modal title="Book a Munshi AI demo" description="Team aapke factory workflow aur suitable plan par call karegi." onClose={() => setIsDemoOpen(false)}>
          <form onSubmit={submitDemo}>
            <div className="grid gap-3 sm:grid-cols-2">
              <FormInput label="Owner Name" value={demoForm.owner_name} onChange={(owner_name) => setDemoForm({ ...demoForm, owner_name })} />
              <FormInput label="Factory Name" value={demoForm.factory_name} onChange={(factory_name) => setDemoForm({ ...demoForm, factory_name })} />
              <PhoneNumberInput
                countryCode={demoPhone.country.dialCode}
                localNumber={demoPhone.localNumber}
                onCountryCodeChange={(country_code) => setDemoForm({ ...demoForm, phone: `${country_code}${demoPhone.localNumber}` })}
                onLocalNumberChange={(phone) => setDemoForm({ ...demoForm, phone: `${demoPhone.country.dialCode}${phone}` })}
              />
              <FormInput label="Email" type="email" value={demoForm.email} onChange={(email) => setDemoForm({ ...demoForm, email })} />
              <label className="block text-sm sm:col-span-2">
                <span className="font-semibold text-[#111827]">Preferred Plan</span>
                <select
                  className="mt-1 h-11 w-full rounded-lg border border-[#E5E7EB] bg-white px-3 text-sm outline-none focus:border-[#6D28D9] focus:ring-2 focus:ring-[#F3E8FF]"
                  value={demoForm.preferred_plan}
                  onChange={(event) => setDemoForm({ ...demoForm, preferred_plan: event.target.value })}
                >
                  {plans.map((plan) => (
                    <option key={plan.code} value={plan.code}>
                      {plan.name}
                    </option>
                  ))}
                </select>
              </label>
              <TextArea label="Message" value={demoForm.message} onChange={(messageValue) => setDemoForm({ ...demoForm, message: messageValue })} required={false} />
            </div>
            <button className="mt-5 h-11 w-full rounded-lg bg-[#6D28D9] px-4 text-sm font-bold text-white hover:bg-[#4C1D95]" type="submit">
              Submit Demo Request
            </button>
          </form>
        </Modal>
      ) : null}
    </section>
  );
}

function PlanCard({
  billingCycle,
  isLoading,
  onBuy,
  onTrial,
  plan
}: {
  billingCycle: BillingCycle;
  isLoading: boolean;
  onBuy: () => void;
  onTrial?: () => void;
  plan: PricingPlan;
}) {
  const yearly = billingCycle === "yearly";
  const copy = planCopy[plan.code] || planCopy.basic;
  const original = plan.price.yearly_original ? formatRupees(plan.price.yearly_original) : null;
  const discounted = plan.price.yearly_discounted ? formatRupees(plan.price.yearly_discounted) : null;
  const saving = plan.price.yearly_original && plan.price.yearly_discounted ? formatRupees(plan.price.yearly_original - plan.price.yearly_discounted) : null;

  return (
    <article className={`relative rounded-3xl border bg-white p-6 shadow-sm transition hover:-translate-y-1 hover:shadow-xl ${copy.featured ? "border-[#6D28D9] shadow-purple-100" : "border-[#E5E7EB] shadow-orange-100/70"}`}>
      {copy.featured ? <p className="absolute right-5 top-5 rounded-full bg-[#6D28D9] px-3 py-1 text-xs font-black text-white">Popular</p> : null}
      <p className="text-sm font-bold uppercase tracking-wide text-[#6D28D9]">{plan.machine_limit_label}</p>
      <h3 className="mt-3 text-2xl font-black text-[#111827]">{plan.name} Plan</h3>
      <p className="mt-2 text-sm font-semibold text-[#4B5563]">{copy.subtitle}</p>

      <div className="mt-5 min-h-[72px]">
        {yearly ? (
          <>
            {original ? <p className="text-sm font-semibold text-[#4B5563] line-through">{original} + GST</p> : null}
            <p className="text-3xl font-black text-[#111827]">{discounted} + GST</p>
            {saving ? <p className="mt-1 inline-flex rounded-full bg-[#F3E8FF] px-3 py-1 text-xs font-bold text-[#4C1D95]">Save {saving} yearly</p> : null}
          </>
        ) : (
          <p className="text-3xl font-black text-[#111827]">
            {formatRupees(plan.price.monthly)} <span className="text-base font-bold text-[#4B5563]">+ GST / month</span>
          </p>
        )}
      </div>

      <div className="mt-4 flex flex-wrap gap-2">
        {copy.badges.map((badge) => (
          <span key={badge} className="rounded-full bg-[#F3E8FF] px-3 py-1 text-xs font-bold text-[#4C1D95]">
            {badge}
          </span>
        ))}
      </div>

      <ul className="mt-5 space-y-3">
        {plan.features.map((feature) => (
          <li key={feature} className="flex gap-2 text-sm text-[#4B5563]">
            <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-[#16A34A]" />
            {feature}
          </li>
        ))}
      </ul>

      <div className="mt-6 space-y-3">
        {onTrial ? (
          <button
            className="inline-flex h-11 w-full items-center justify-center gap-2 rounded-lg bg-[#6D28D9] px-4 text-sm font-bold text-white hover:bg-[#4C1D95] disabled:bg-[#9CA3AF]"
            disabled={isLoading}
            type="button"
            onClick={onTrial}
          >
            <ShieldCheck className="h-4 w-4" />
            {isLoading ? "Starting..." : copy.cta}
          </button>
        ) : (
          <button
            className="inline-flex h-11 w-full items-center justify-center gap-2 rounded-lg bg-[#6D28D9] px-4 text-sm font-bold text-white hover:bg-[#4C1D95] disabled:bg-[#9CA3AF]"
            disabled={isLoading}
            type="button"
            onClick={onBuy}
          >
            <CreditCard className="h-4 w-4" />
            {isLoading ? "Starting..." : copy.cta}
          </button>
        )}
        {copy.secondaryCta ? (
          <button
            className="h-11 w-full rounded-lg border border-[#6D28D9] bg-white px-4 text-sm font-bold text-[#6D28D9] hover:bg-[#F3E8FF]"
            type="button"
            onClick={onBuy}
          >
            {copy.secondaryCta}
          </button>
        ) : null}
      </div>
    </article>
  );
}

function CustomPlanCard({ customPlan, onOpen }: { customPlan: PricingPlan; onOpen: () => void }) {
  return (
    <article className="rounded-3xl border border-[#E5E7EB] bg-white p-6 shadow-sm shadow-orange-100/70 transition hover:-translate-y-1 hover:shadow-xl">
      <div className="rounded-xl bg-[#F3E8FF] p-3 text-[#6D28D9]">
        <MessageCircle className="h-6 w-6" />
      </div>
      <h3 className="mt-5 text-2xl font-black text-[#111827]">Custom Plan</h3>
      <p className="mt-2 text-sm font-semibold text-[#4B5563]">{customPlan.machine_limit_label}</p>
      <p className="mt-5 text-3xl font-black text-[#111827]">Starting from {formatRupees(customPlan.price.starts_from || 10000000)} + GST</p>
      <span className="mt-4 inline-flex rounded-full bg-[#F3E8FF] px-3 py-1 text-xs font-bold text-[#4C1D95]">Contact Sales</span>
      <ul className="mt-5 space-y-3">
        {customPlan.features.map((feature) => (
          <li key={feature} className="flex gap-2 text-sm text-[#4B5563]">
            <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-[#16A34A]" />
            {feature}
          </li>
        ))}
      </ul>
      <button className="mt-6 h-11 w-full rounded-lg border border-[#6D28D9] bg-white px-4 text-sm font-bold text-[#6D28D9] hover:bg-[#F3E8FF]" type="button" onClick={onOpen}>
        Contact Sales
      </button>
    </article>
  );
}

function Modal({ children, description, onClose, title }: { children: ReactNode; description: string; onClose: () => void; title: string }) {
  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-[#111827]/55 px-4 py-6">
      <div className="max-h-[92vh] w-full max-w-xl overflow-y-auto rounded-2xl border border-[#E5E7EB] bg-white p-6 shadow-2xl">
        <div className="mb-5 flex items-start justify-between gap-4">
          <div>
            <h2 className="text-xl font-black text-[#111827]">{title}</h2>
            <p className="mt-1 text-sm leading-6 text-[#4B5563]">{description}</p>
          </div>
          <button className="grid h-9 w-9 shrink-0 place-items-center rounded-lg border border-[#E5E7EB] text-[#4B5563] hover:bg-[#FFF7ED]" type="button" onClick={onClose}>
            <X className="h-4 w-4" />
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}

function FormInput({ label, value, onChange, type = "text" }: { label: string; value: string; onChange: (value: string) => void; type?: string }) {
  return (
    <label className="block text-sm">
      <span className="font-semibold text-[#111827]">{label}</span>
      <input
        className="mt-1 h-11 w-full rounded-lg border border-[#E5E7EB] bg-white px-3 text-sm text-[#111827] outline-none focus:border-[#6D28D9] focus:ring-2 focus:ring-[#F3E8FF]"
        type={type}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        required
      />
    </label>
  );
}

function TextArea({ label, onChange, required = true, value }: { label: string; onChange: (value: string) => void; required?: boolean; value: string }) {
  return (
    <label className="block text-sm sm:col-span-2">
      <span className="font-semibold text-[#111827]">{label}</span>
      <textarea
        className="mt-1 min-h-24 w-full rounded-lg border border-[#E5E7EB] bg-white px-3 py-2 text-sm text-[#111827] outline-none focus:border-[#6D28D9] focus:ring-2 focus:ring-[#F3E8FF]"
        value={value}
        onChange={(event) => onChange(event.target.value)}
        required={required}
      />
    </label>
  );
}

function Messages({ error, message }: { error: string | null; message: string | null }) {
  if (!error && !message) return null;
  return (
    <div
      className={`mt-5 flex items-center gap-2 rounded-xl border px-4 py-3 text-sm font-semibold ${
        error ? "border-[#DC2626]/30 bg-[#DC2626]/10 text-[#DC2626]" : "border-[#16A34A]/30 bg-[#16A34A]/10 text-[#166534]"
      }`}
    >
      <ShieldCheck className="h-4 w-4" />
      {error || message}
    </div>
  );
}

function formatRupees(amountPaise: number) {
  return `\u20B9${Math.round(amountPaise / 100).toLocaleString("en-IN")}`;
}

function mergePricingPlans(serverPlans: PricingPlan[]) {
  const cleanServerPlans = Array.isArray(serverPlans) ? serverPlans : [];
  return fallbackPlans.map((fallback) => {
    const serverPlan = cleanServerPlans.find((plan) => plan.code === fallback.code);
    return serverPlan ? { ...fallback, ...serverPlan, features: serverPlan.features?.length ? serverPlan.features : fallback.features } : fallback;
  });
}

function getErrorMessage(caught: unknown, fallback: string) {
  if (typeof caught === "object" && caught && "response" in caught) {
    const response = (caught as { response?: { data?: { detail?: unknown } } }).response;
    const detail = response?.data?.detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail)) {
      return detail
        .map((item) => {
          if (typeof item === "object" && item && "msg" in item && typeof item.msg === "string") return item.msg;
          return typeof item === "string" ? item : "";
        })
        .filter(Boolean)
        .join(" ");
    }
  }
  return caught instanceof Error ? caught.message : fallback;
}
