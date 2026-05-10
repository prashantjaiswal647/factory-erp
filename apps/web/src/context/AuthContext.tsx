import { createContext, useContext, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";

import { api } from "../lib/api";

export type UserRole = "Owner" | "Supervisor" | "Operator";

type AuthUser = {
  id?: number;
  user_id?: string | null;
  username: string;
  phone_number?: string | null;
  full_name?: string | null;
  role: UserRole;
  factory_id?: number;
};

type AuthContextValue = {
  user: AuthUser | null;
  isLoading: boolean;
  login: (username: string, password: string, factoryId?: number) => Promise<AuthUser>;
  logout: () => void;
};

type TokenResponse = {
  access_token: string;
  token_type: string;
  user: {
    id: number;
    user_id?: string | null;
    factory_id: number;
    username: string;
    phone_number?: string | null;
    full_name?: string | null;
    role: string;
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

  async function login(username: string, password: string, factoryId?: number) {
    const response = await api.post<TokenResponse>("/api/auth/login", {
      factory_id: factoryId,
      username,
      password
    });

    const role = normalizeRole(response.data.user.role);
    const nextUser = {
      id: response.data.user.id,
      user_id: response.data.user.user_id,
      username: response.data.user.username,
      phone_number: response.data.user.phone_number,
      full_name: response.data.user.full_name,
      role,
      factory_id: response.data.user.factory_id
    };

    localStorage.setItem(tokenKey, response.data.access_token);
    localStorage.setItem(userKey, JSON.stringify(nextUser));
    setUser(nextUser);
    return nextUser;
  }

  function logout() {
    localStorage.removeItem(tokenKey);
    localStorage.removeItem(userKey);
    setUser(null);
  }

  const value = useMemo(
    () => ({
      user,
      isLoading,
      login,
      logout
    }),
    [isLoading, user]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

function normalizeRole(role: string): UserRole {
  const value = role.trim().toUpperCase();
  if (value === "OWNER") return "Owner";
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
