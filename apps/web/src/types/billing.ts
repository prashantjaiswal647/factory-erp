export type SubscriptionStatus =
  | "trialing"
  | "trial_active"
  | "active"
  | "past_due"
  | "cancelled"
  | "pending"
  | null;

export type PlanCode = "monthly" | "quarterly" | "yearly";

export type BillingMeResponse = {
  subscription_status: SubscriptionStatus;
  trial_end: string | null;
  current_period_start: string | null;
  current_period_end: string | null;
  next_billing_at: string | null;
  cancelled_at: string | null;
  plan_code: string | null;
  is_payable: boolean;
  hosted_payment_url: string | null;
};

export type CashfreeCreateSubscriptionRequest = {
  factory_id: number;
  plan_code: PlanCode;
};

export type CashfreeCreateSubscriptionResponse = {
  cashfree_customer_id: string;
  cashfree_subscription_id: string;
  hosted_payment_url: string;
  subscription_status: string;
};
