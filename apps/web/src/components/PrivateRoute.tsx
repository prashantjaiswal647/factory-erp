import type { ReactNode } from "react";
import { Navigate, useLocation } from "react-router-dom";

import LoadingState from "./LoadingState";
import { useAuth } from "../context/AuthContext";

type UserRole = "Owner" | "Operator";

export default function PrivateRoute({
  allowedRoles,
  children
}: {
  allowedRoles?: UserRole[];
  children: ReactNode;
}) {
  const { user, isLoading } = useAuth();
  const location = useLocation();

  if (isLoading) {
    return <LoadingState label="Checking access..." />;
  }

  if (!user) {
    return <Navigate to="/login" replace state={{ from: location }} />;
  }

  if (allowedRoles && !allowedRoles.includes(user.role)) {
    return <Navigate to={user.role === "Operator" ? "/production" : "/"} replace />;
  }

  return <>{children}</>;
}
