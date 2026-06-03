"use client";
/**
 * AI 사용 권한 모달 (Phase 4b)
 * - 비용 AI 호출이 403(NEED_AI_CREDIT)을 반환하면 Providers의 fetch 패치가
 *   `stockcy:need-ai-credit` 이벤트를 쏘고, 이 모달이 떠서 사용 신청을 유도한다.
 */
import { useEffect, useState } from "react";
import { useAuth } from "@/lib/auth-context";

export function AiCreditModal() {
  const { requestAiAccess } = useAuth();
  const [open, setOpen] = useState(false);
  const [pending, setPending] = useState(false);
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    const handler = () => {
      setMsg("");
      setOpen(true);
      // 현재 신청 상태 확인
      fetch("/backend/api/auth/ai-status", { cache: "no-store" })
        .then((r) => r.json())
        .then((d) => setPending(!!d.pending))
        .catch(() => {});
    };
    window.addEventListener("stockcy:need-ai-credit", handler);
    return () => window.removeEventListener("stockcy:need-ai-credit", handler);
  }, []);

  if (!open) return null;

  async function submit() {
    setBusy(true);
    try {
      const m = await requestAiAccess("");
      setMsg(m);
      setPending(true);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div
      onClick={() => setOpen(false)}
      style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.55)", zIndex: 1000, display: "flex", alignItems: "center", justifyContent: "center", padding: "1rem" }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{ width: "100%", maxWidth: "380px", background: "var(--color-card)", border: "1px solid var(--color-border)", borderRadius: "14px", padding: "1.5rem", display: "flex", flexDirection: "column", gap: "0.9rem" }}
      >
        <div style={{ fontSize: "1.05rem", fontWeight: 800, color: "var(--color-text)" }}>🎟️ AI 사용 권한 필요</div>
        <div style={{ fontSize: "0.85rem", color: "var(--color-muted)", lineHeight: 1.6 }}>
          AI 분석 기능은 관리자 승인 후 사용할 수 있어요. 사용 횟수가 모두 소진되었거나 아직 권한이 없습니다.
        </div>

        {msg && (
          <div style={{ fontSize: "0.82rem", color: "var(--color-up, #34d399)", fontWeight: 600 }}>{msg}</div>
        )}
        {pending && !msg && (
          <div style={{ fontSize: "0.82rem", color: "#fbbf24", fontWeight: 600 }}>이미 승인 대기 중입니다. 관리자 승인을 기다려 주세요.</div>
        )}

        <div style={{ display: "flex", gap: "0.5rem", justifyContent: "flex-end" }}>
          <button
            onClick={() => setOpen(false)}
            style={{ padding: "0.5rem 0.9rem", borderRadius: "8px", border: "1px solid var(--color-border)", background: "var(--color-surface)", color: "var(--color-muted)", cursor: "pointer", fontSize: "0.85rem" }}
          >
            닫기
          </button>
          <button
            onClick={submit}
            disabled={busy || pending}
            className="stockcy-btn stockcy-btn-primary"
            style={{ padding: "0.5rem 0.9rem", fontSize: "0.85rem", fontWeight: 700, opacity: busy || pending ? 0.5 : 1 }}
          >
            {pending ? "신청됨" : busy ? "신청 중…" : "사용 신청"}
          </button>
        </div>
      </div>
    </div>
  );
}
