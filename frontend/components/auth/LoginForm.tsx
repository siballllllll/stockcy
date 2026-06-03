"use client";
/**
 * 로그인 화면 (Phase 1b) — 미로그인 시 앱 전체 대신 표시된다.
 */
import { useState } from "react";
import { useAuth } from "@/lib/auth-context";

export function LoginForm() {
  const { login } = useAuth();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      await login(username.trim(), password);
    } catch (err) {
      setError(err instanceof Error ? err.message : "로그인에 실패했습니다.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div
      style={{
        minHeight: "100vh",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        background: "var(--color-bg)",
        padding: "1.5rem",
      }}
    >
      <form
        onSubmit={onSubmit}
        style={{
          width: "100%",
          maxWidth: "360px",
          background: "var(--color-card)",
          border: "1px solid var(--color-border)",
          borderRadius: "14px",
          padding: "2rem 1.75rem",
          boxShadow: "0 12px 40px rgba(0,0,0,0.35)",
          display: "flex",
          flexDirection: "column",
          gap: "1rem",
        }}
      >
        <div style={{ textAlign: "center", marginBottom: "0.25rem" }}>
          <div style={{ fontSize: "1.5rem", fontWeight: 800, color: "var(--color-accent)", letterSpacing: "-0.02em" }}>
            STOCKCY
          </div>
          <div style={{ fontSize: "0.78rem", color: "var(--color-muted)", marginTop: "0.25rem" }}>
            AI 트레이딩 대시보드 로그인
          </div>
        </div>

        <label style={{ display: "flex", flexDirection: "column", gap: "0.35rem", fontSize: "0.8rem", color: "var(--color-muted)", fontWeight: 600 }}>
          아이디
          <input
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            autoComplete="username"
            autoFocus
            required
            style={inputStyle}
          />
        </label>

        <label style={{ display: "flex", flexDirection: "column", gap: "0.35rem", fontSize: "0.8rem", color: "var(--color-muted)", fontWeight: 600 }}>
          비밀번호
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="current-password"
            required
            style={inputStyle}
          />
        </label>

        {error && (
          <div style={{ color: "var(--color-danger)", fontSize: "0.78rem", fontWeight: 600 }}>
            {error}
          </div>
        )}

        <button
          type="submit"
          disabled={busy}
          className="stockcy-btn stockcy-btn-primary"
          style={{ padding: "0.6rem", fontSize: "0.9rem", fontWeight: 700, marginTop: "0.25rem", opacity: busy ? 0.6 : 1 }}
        >
          {busy ? "로그인 중…" : "로그인"}
        </button>
      </form>
    </div>
  );
}

const inputStyle: React.CSSProperties = {
  padding: "0.55rem 0.7rem",
  borderRadius: "8px",
  border: "1px solid var(--color-border)",
  background: "var(--color-bg)",
  color: "var(--color-text)",
  fontSize: "0.9rem",
  outline: "none",
};
