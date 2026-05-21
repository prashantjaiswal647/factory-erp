import { Headphones, LockKeyhole, WalletCards } from "lucide-react";
import { Link } from "react-router-dom";

import { useAuth } from "../context/AuthContext";

export default function SubscriptionExpiredPage() {
  const { user } = useAuth();

  return (
    <div className="mx-auto max-w-3xl rounded-2xl border border-[#E5E7EB] bg-white p-8 shadow-sm">
      <div className="mx-auto grid h-16 w-16 place-items-center rounded-2xl bg-[#F3E8FF] text-[#6D28D9]">
        <LockKeyhole className="h-8 w-8" />
      </div>
      <div className="mt-5 text-center">
        <p className="text-sm font-bold uppercase tracking-wide text-[#6D28D9]">Payment Required</p>
        <h1 className="mt-2 text-3xl font-black text-[#111827]">Munshi AI access is paused</h1>
        <p className="mx-auto mt-3 max-w-xl text-sm leading-6 text-[#4B5563]">
          Trial ya subscription expire ho gaya hai. ERP modules unlock karne ke liye plan renew karein.
        </p>
      </div>

      <div className="mt-8 grid gap-4 rounded-2xl border border-[#E5E7EB] bg-[#FFF7ED] p-5 sm:grid-cols-3">
        <PlanDetail label="Current Status" value={user?.subscription_status || "payment_pending"} />
        <PlanDetail label="Active Plan" value={user?.active_plan || "Not selected"} />
        <PlanDetail label="Billing Cycle" value={user?.billing_cycle || "Not active"} />
        <PlanDetail label="Payment Status" value={user?.payment_status || "payment_pending"} />
        <PlanDetail label="Trial Ends" value={formatDate(user?.trial_end_date)} />
        <PlanDetail label="Subscription Ends" value={formatDate(user?.subscription_end_date)} />
      </div>

      <div className="mt-8 grid gap-3 sm:grid-cols-3">
        <Link className="inline-flex h-12 items-center justify-center gap-2 rounded-lg bg-[#6D28D9] px-4 text-sm font-bold text-white hover:bg-[#4C1D95]" to="/billing">
          <WalletCards className="h-4 w-4" />
          Pay Now
        </Link>
        <Link className="inline-flex h-12 items-center justify-center rounded-lg border border-[#6D28D9] bg-white px-4 text-sm font-bold text-[#6D28D9] hover:bg-[#F3E8FF]" to="/plans">
          Upgrade Plan
        </Link>
        <a className="inline-flex h-12 items-center justify-center gap-2 rounded-lg border border-[#E5E7EB] bg-white px-4 text-sm font-bold text-[#111827] hover:bg-[#FFF7ED]" href="mailto:support@munshiai.co.in">
          <Headphones className="h-4 w-4 text-[#6D28D9]" />
          Contact Support
        </a>
      </div>
    </div>
  );
}

function formatDate(value?: string | null) {
  if (!value) return "-";
  return new Date(value).toLocaleDateString("en-IN");
}

function PlanDetail({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-xs font-bold uppercase tracking-wide text-[#6D28D9]">{label}</p>
      <p className="mt-1 text-sm font-semibold text-[#111827]">{value}</p>
    </div>
  );
}
