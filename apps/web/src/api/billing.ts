import { api, superAdminApi } from "../lib/api";
import type {
  BillingMeResponse,
  CashfreeCreateSubscriptionResponse,
  PlanCode,
} from "../types/billing";

export async function getBillingMe(): Promise<BillingMeResponse> {
  const response = await api.get<BillingMeResponse>("/api/v1/billing/me");
  return response.data;
}

export async function createCashfreeSubscription(
  factoryId: number,
  planCode: PlanCode,
): Promise<CashfreeCreateSubscriptionResponse> {
  const response = await superAdminApi.post<CashfreeCreateSubscriptionResponse>(
    "/api/super-admin/billing/cashfree/create-subscription",
    { factory_id: factoryId, plan_code: planCode },
  );
  return response.data;
}
