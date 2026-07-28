"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import {
  loginAccount,
  logoutAccount,
  refreshSession,
  registerAccount,
} from "@/lib/auth-api";
import type { LoginInput, RegisterInput, User } from "@/lib/types";

type AuthStatus = "loading" | "authenticated" | "unauthenticated";

type AuthContextValue = {
  user: User | null;
  status: AuthStatus;
  login: (input: LoginInput) => Promise<void>;
  register: (input: RegisterInput) => Promise<void>;
  logout: () => Promise<void>;
};

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [status, setStatus] = useState<AuthStatus>("loading");

  useEffect(() => {
    let active = true;

    refreshSession()
      .then((response) => {
        if (!active) return;
        setUser(response.user);
        setStatus("authenticated");
      })
      .catch((error: unknown) => {
        if (error instanceof Error && error.name === "AbortError") {
          console.error("Session restore timed out. Check the /api proxy.");
        }
        if (!active) return;
        setUser(null);
        setStatus("unauthenticated");
      });

    return () => {
      active = false;
    };
  }, []);

  const login = useCallback(async (input: LoginInput) => {
    const response = await loginAccount(input);
    setUser(response.user);
    setStatus("authenticated");
  }, []);

  const register = useCallback(
    async (input: RegisterInput) => {
      await registerAccount(input);
      await login({ email: input.email, password: input.password });
    },
    [login],
  );

  const logout = useCallback(async () => {
    await logoutAccount();
    setUser(null);
    setStatus("unauthenticated");
  }, []);

  const value = useMemo(
    () => ({ user, status, login, register, logout }),
    [user, status, login, register, logout],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);

  if (!context) {
    throw new Error("useAuth must be used inside AuthProvider");
  }

  return context;
}
