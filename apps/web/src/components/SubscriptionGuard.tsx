import { useEffect, useState } from "react";
import type { ReactNode } from "react";
import { Navigate, useLocation } from "react-router-dom";

import { getBillingStatus } from "../lib/api";
import type { BillingStatus } from "../lib/api";
import LoadingState from "./LoadingState";
import { useAuth } from "../context/AuthContext";

export default function SubscriptionGuard({ children }: { children: ReactNode }) {
  const { user, updateUser } = useAuth();
  const location = useLocation();
  const [status, setStatus] = useState<BillingStatus | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    let isMounted = true;
    async function loadStatus() {
      try {
        const response = await getBillingStatus();
        if (!isMounted) return;
        setStatus(response.data);
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
      } finally {
        if (isMounted) setIsLoading(false);
      }
    }
    void loadStatus();
    return () => {
      isMounted = false;
    };
  }, [updateUser]);

  if (isLoading) {
    return <LoadingState label="Checking subscription..." />;
  }

  const hasAllowedStatus = status?.subscription_status === "active" || (status?.subscription_status === "trial_active" && status?.active_plan === "basic");

  if (!status || (status.is_access_allowed && hasAllowedStatus)) {
    return <>{children}</>;
  }

  if (location.pathname === "/billing" && user?.role === "Owner") {
    return <>{children}</>;
  }

  if (location.pathname === "/plans" && user?.role === "Owner") {
    return <>{children}</>;
  }

  if (location.pathname === "/subscription-expired") {
    return <>{children}</>;
  }

  return <Navigate to="/subscription-expired" replace />;
}
