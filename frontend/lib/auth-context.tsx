"use client";
/**
 * 인증 컨텍스트 (Phase 1b)
 * - 토큰을 localStorage 에 저장하고, 백엔드(FastAPI) /api/auth/* 와 통신한다.
 * - 실제 권한 강제는 백엔드(Phase 1c)가 담당하며, 여기서는 로그인 상태/사용자 정보를
 *   클라이언트에 노출하는 역할만 한다.
 */
import {
  createContext, useContext, useState, useEffect, useCallback, type ReactNode,
} from "react";

const TOKEN_KEY = "stockcy_token";

export type AuthUser = {
  username: string;
  role: "admin" | "user";
  ai_credits: number;
};

type AuthCtx = {
  user: AuthUser | null;
  loading: boolean;
  login: (username: string, password: string) => Promise<void>;
  logout: () => void;
  refresh: () => Promise<void>;
  requestAiAccess: (reason?: string) => Promise<string>;
};

const AuthContext = createContext<AuthCtx>({
  user: null,
  loading: true,
  login: async () => {},
  logout: () => {},
  refresh: async () => {},
  requestAiAccess: async () => "",
});

/** fetch 몽키패치 등에서 동기적으로 토큰을 읽기 위한 헬퍼. */
export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(TOKEN_KEY);
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    const token = getToken();
    if (!token) {
      setUser(null);
      setLoading(false);
      return;
    }
    try {
      const res = await fetch("/backend/api/auth/me", {
        headers: {
          Authorization: `Bearer ${token}`,
          "ngrok-skip-browser-warning": "69420",
        },
        cache: "no-store",
      });
      if (res.ok) {
        const d = await res.json();
        setUser({ username: d.username, role: d.role, ai_credits: d.ai_credits });
      } else {
        localStorage.removeItem(TOKEN_KEY);
        setUser(null);
      }
    } catch {
      setUser(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const login = useCallback(async (username: string, password: string) => {
    const res = await fetch("/backend/api/auth/login", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "ngrok-skip-browser-warning": "69420",
      },
      body: JSON.stringify({ username, password }),
    });
    if (!res.ok) {
      let msg = "로그인에 실패했습니다.";
      try {
        const e = await res.json();
        if (e?.detail) msg = e.detail;
      } catch {
        /* noop */
      }
      throw new Error(msg);
    }
    const d = await res.json();
    localStorage.setItem(TOKEN_KEY, d.token);
    setUser({ username: d.username, role: d.role, ai_credits: d.ai_credits });
  }, []);

  const logout = useCallback(() => {
    const token = getToken();
    localStorage.removeItem(TOKEN_KEY);
    setUser(null);
    // 서버 쿠키도 best-effort 로 제거
    fetch("/backend/api/auth/logout", {
      method: "POST",
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    }).catch(() => {});
  }, []);

  const requestAiAccess = useCallback(async (reason = "") => {
    const res = await fetch("/backend/api/auth/ai-request", {
      method: "POST",
      headers: { "Content-Type": "application/json", "ngrok-skip-browser-warning": "69420" },
      body: JSON.stringify({ reason }),
    });
    const d = await res.json().catch(() => ({}));
    return d?.message || (res.ok ? "신청이 접수되었습니다." : "신청에 실패했습니다.");
  }, []);

  return (
    <AuthContext.Provider value={{ user, loading, login, logout, refresh, requestAiAccess }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}
