import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";

import { api } from "../lib/api";

export type UserRole = "Owner" | "Sub-Owner" | "Supervisor" | "Operator";

type AuthUser = {
  id?: number;
  user_id?: string | null;
  username: string;
  phone_number?: string | null;
  full_name?: string | null;
  role: UserRole;
  factory_id?: number;
  factory_name?: string | null;
  subscription_status?: "trial" | "active" | "expired" | null;
  trial_end_date?: string | null;
  trial_days_remaining?: number;
};

type AuthContextValue = {
  user: AuthUser | null;
  isLoading: boolean;
  login: (identifier: string, password: string) => Promise<AuthUser>;
  loginWithGoogle: (credential: string) => Promise<AuthUser>;
  updateUser: (patch: Partial<AuthUser>) => void;
  logout: () => void;
};

type TokenResponse = {
  access_token: string;
  token_type: string;
  user: {
    id: number;
    user_id?: string | null;
    factory_id: number;
    factory_name?: string | null;
    username: string;
    phone_number?: string | null;
    full_name?: string | null;
    role: string;
    subscription_status?: "trial" | "active" | "expired" | null;
    trial_end_date?: string | null;
    trial_days_remaining?: number;
  };
};

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

const tokenKey = "ai_erp_token";
const userKey = "ai_erp_user";

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    const savedToken = localStorage.getItem(tokenKey);
    const savedUser = localStorage.getItem(userKey);

    if (!savedToken || !savedUser) {
      setIsLoading(false);
      return;
    }

    try {
      setUser(JSON.parse(savedUser) as AuthUser);
    } catch {
      localStorage.removeItem(tokenKey);
      localStorage.removeItem(userKey);
    } finally {
      setIsLoading(false);
    }
  }, []);

  async function login(identifier: string, password: string) {
    const response = await api.post<TokenResponse>("/api/auth/login", {
      identifier,
      password
    });

    return persistAuth(response.data);
  }

  async function loginWithGoogle(credential: string) {
    const response = await api.post<TokenResponse>("/api/auth/google", { credential });
    return persistAuth(response.data);
  }

  function persistAuth(data: TokenResponse) {
    const role = normalizeRole(data.user.role);
    const nextUser: AuthUser = {
      id: data.user.id,
      user_id: data.user.user_id,
      username: data.user.username,
      phone_number: data.user.phone_number,
      full_name: data.user.full_name,
      role,
      factory_id: data.user.factory_id,
      factory_name: data.user.factory_name,
      subscription_status: data.user.subscription_status,
      trial_end_date: data.user.trial_end_date,
      trial_days_remaining: data.user.trial_days_remaining
    };

    localStorage.setItem(tokenKey, data.access_token);
    localStorage.setItem("token", data.access_token);
    localStorage.setItem("factory_id", String(nextUser.factory_id ?? ""));
    localStorage.setItem(userKey, JSON.stringify(nextUser));
    setUser(nextUser);
    return nextUser;
  }

  const updateUser = useCallback(function updateUser(patch: Partial<AuthUser>) {
    setUser((current) => {
      if (!current) return current;
      const nextUser = { ...current, ...patch };
      localStorage.setItem(userKey, JSON.stringify(nextUser));
      return nextUser;
    });
  }, []);

  function logout() {
    localStorage.removeItem("token");
    localStorage.removeItem("factory_id");
    localStorage.removeItem(tokenKey);
    localStorage.removeItem(userKey);
    setUser(null);
  }

  const value = useMemo(
    () => ({
      user,
      isLoading,
      login,
      loginWithGoogle,
      updateUser,
      logout
    }),
    [isLoading, updateUser, user]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

function normalizeRole(role: string): UserRole {
  const value = role.trim().toUpperCase();
  if (value === "OWNER") return "Owner";
  if (value === "SUB-OWNER" || value === "SUB_OWNER") return "Sub-Owner";
  if (value === "SUPERVISOR") return "Supervisor";
  return "Operator";
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used inside AuthProvider");
  }
  return context;
}
