import PricingPlansSection from "../components/PricingPlansSection";
import SubscriptionStatusWidget from "../components/billing/SubscriptionStatusWidget";

export default function BillingPage() {
  return (
    <div className="space-y-5">
      <SubscriptionStatusWidget />
      <PricingPlansSection source="billing" />
    </div>
  );
}
