import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { api, clearToken, getToken, setToken, ApiError } from "../api";
import type { User } from "../types";

interface AuthContextValue {
  token: string | null;
  user: User | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string, fullName: string) => Promise<void>;
  logout: () => Promise<void>;
  setUser: (user: User | null) => void;
  refreshUser: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setTok] = useState<string | null>(() => getToken());
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState<boolean>(() => !!getToken());

  const refreshUser = useCallback(async () => {
    if (!getToken()) {
      setUser(null);
      setLoading(false);
      return;
    }
    try {
      const me = await api<User>("/api/me");
      setUser(me);
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) {
        clearToken();
        setTok(null);
        setUser(null);
      }
      // other errors: leave user null but stay "logged in" — server may be down
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (token) void refreshUser();
    else setLoading(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    const res = await api<{ access_token: string; user: User }>(
      "/api/auth/login",
      { method: "POST", body: { email, password }, auth: false },
    );
    setToken(res.access_token);
    setTok(res.access_token);
    setUser(res.user);
  }, []);

  const register = useCallback(
    async (email: string, password: string, fullName: string) => {
      const res = await api<{ access_token: string; user: User }>(
        "/api/auth/register",
        { method: "POST", body: { email, password, full_name: fullName }, auth: false },
      );
      setToken(res.access_token);
      setTok(res.access_token);
      setUser(res.user);
    },
    [],
  );

  const logout = useCallback(async () => {
    try {
      await api("/api/auth/logout", { method: "POST" });
    } catch {
      // best effort — still clear locally
    }
    clearToken();
    setTok(null);
    setUser(null);
  }, []);

  return (
    <AuthContext.Provider
      value={{ token, user, loading, login, register, logout, setUser, refreshUser }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside <AuthProvider>");
  return ctx;
}
