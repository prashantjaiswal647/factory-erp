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
          trial_days_remaining: response.data.trial_days_remaining
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

  if (!status || status.is_access_allowed) {
    return <>{children}</>;
  }

  if (location.pathname === "/billing" && user?.role === "Owner") {
    return <>{children}</>;
  }

  if (location.pathname === "/subscription-expired") {
    return <>{children}</>;
  }

  if (user?.role === "Owner") {
    return <Navigate to="/billing" replace />;
  }

  return <Navigate to="/subscription-expired" replace />;
}
