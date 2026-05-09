import { createContext, useContext, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";

import { api } from "../lib/api";

type UserRole = "Owner" | "Operator";

type AuthUser = {
  username: string;
  role: UserRole;
};

type AuthContextValue = {
  user: AuthUser | null;
  isLoading: boolean;
  login: (username: string, password: string) => Promise<AuthUser>;
  logout: () => void;
};

type TokenResponse = {
  access_token: string;
  token_type: string;
  username: string;
  role: UserRole;
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

  async function login(username: string, password: string) {
    const formData = new URLSearchParams();
    formData.set("username", username);
    formData.set("password", password);

    const response = await api.post<TokenResponse>("/token", formData, {
      headers: {
        "Content-Type": "application/x-www-form-urlencoded"
      }
    });

    const nextUser = {
      username: response.data.username,
      role: response.data.role
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

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used inside AuthProvider");
  }
  return context;
}
