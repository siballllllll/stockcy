"use client";
import { MarketProvider } from "@/lib/market-context";
import { AnalysisReadyProvider } from "@/lib/analysis-ready-context";
import { AuthProvider, useAuth, getToken } from "@/lib/auth-context";
import { LoginForm } from "@/components/auth/LoginForm";
import { AiCreditModal } from "@/components/auth/AiCreditModal";
import type { ReactNode } from "react";

// ngrok 우회 헤더 + 백엔드 요청 인증 토큰을 모든 fetch 에 자동 주입 (몽키 패치).
// Authorization 은 "우리 백엔드로 가는 요청"에만 붙여 제3자 URL 로의 토큰 유출을 막는다.
if (typeof window !== "undefined") {
  const originalFetch = window.fetch;
  const apiBase = process.env.NEXT_PUBLIC_API_URL;
  window.fetch = async function (input, init) {
    const headers = new Headers(init?.headers);
    headers.set("ngrok-skip-browser-warning", "69420");
    try {
      const url =
        typeof input === "string"
          ? input
          : input instanceof Request
            ? input.url
            : String(input);
      const isBackend =
        url.startsWith("/backend") ||
        url.includes("127.0.0.1:8000") ||
        url.includes("localhost:8000") ||
        (!!apiBase && url.startsWith(apiBase));
      const token = getToken();
      if (isBackend && token && !headers.has("Authorization")) {
        headers.set("Authorization", `Bearer ${token}`);
      }
    } catch {
      /* noop */
    }
    const _res = await originalFetch(input, { ...init, headers });
    // AI 크레딧 부족(403 NEED_AI_CREDIT) → 전역 이벤트 → AiCreditModal 표시
    if (_res.status === 403) {
      _res.clone().text().then((t) => {
        if (t.includes("NEED_AI_CREDIT")) {
          window.dispatchEvent(new CustomEvent("stockcy:need-ai-credit"));
        }
      }).catch(() => { /* noop */ });
    }
    return _res;
  };
}

function FullScreenMessage({ text }: { text: string }) {
  return (
    <div
      style={{
        minHeight: "100vh",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        color: "var(--color-muted)",
        fontSize: "0.9rem",
        background: "var(--color-bg)",
      }}
    >
      {text}
    </div>
  );
}

function AuthGate({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth();
  if (loading) return <FullScreenMessage text="불러오는 중…" />;
  if (!user) return <LoginForm />;
  return (
    <>
      {children}
      <AiCreditModal />
    </>
  );
}

export function Providers({ children }: { children: ReactNode }) {
  return (
    <AuthProvider>
      <AnalysisReadyProvider>
        <MarketProvider>
          <AuthGate>{children}</AuthGate>
        </MarketProvider>
      </AnalysisReadyProvider>
    </AuthProvider>
  );
}
