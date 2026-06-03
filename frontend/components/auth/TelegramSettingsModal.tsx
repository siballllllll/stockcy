"use client";
/**
 * 텔레그램 알림 설정 모달 (Phase 5) — 공유 봇 + 본인 chat_id.
 * 유저가 자기 chat_id 를 등록하면 본인 가격 알림이 그 채팅으로 발송된다.
 */
import { useEffect, useState } from "react";

export function TelegramSettingsModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [chatId, setChatId] = useState("");
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!open) return;
    setMsg("");
    fetch("/backend/api/auth/me", { cache: "no-store" })
      .then((r) => r.json())
      .then((d) => setChatId(d.telegram_chat_id || ""))
      .catch(() => {});
  }, [open]);

  if (!open) return null;

  async function save() {
    setBusy(true);
    setMsg("");
    try {
      const r = await fetch("/backend/api/auth/telegram/chat-id", {
        method: "POST",
        headers: { "Content-Type": "application/json", "ngrok-skip-browser-warning": "69420" },
        body: JSON.stringify({ chat_id: chatId.trim() }),
      });
      const d = await r.json().catch(() => ({}));
      setMsg(d?.message || (r.ok ? "저장됨" : "저장 실패"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div onClick={onClose} style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.55)", zIndex: 1000, display: "flex", alignItems: "center", justifyContent: "center", padding: "1rem" }}>
      <div onClick={(e) => e.stopPropagation()} style={{ width: "100%", maxWidth: "420px", background: "var(--color-card)", border: "1px solid var(--color-border)", borderRadius: "14px", padding: "1.5rem", display: "flex", flexDirection: "column", gap: "0.9rem" }}>
        <div style={{ fontSize: "1.05rem", fontWeight: 800 }}>🔔 텔레그램 알림 설정</div>
        <div style={{ fontSize: "0.82rem", color: "var(--color-muted)", lineHeight: 1.6 }}>
          내가 설정한 가격 알림을 텔레그램으로 받습니다.
          <br />① 안내받은 스톡시 봇에게 <b>/start</b> 를 보내고
          <br />② 본인 <b>chat ID</b>를 아래에 입력하세요. (예: @userinfobot 으로 확인)
        </div>
        <input
          value={chatId}
          onChange={(e) => setChatId(e.target.value)}
          placeholder="텔레그램 chat ID (숫자)"
          style={{ padding: "0.55rem 0.7rem", borderRadius: "8px", border: "1px solid var(--color-border)", background: "var(--color-bg)", color: "var(--color-text)", fontSize: "0.9rem" }}
        />
        {msg && <div style={{ fontSize: "0.8rem", color: "var(--color-text)", fontWeight: 600 }}>{msg}</div>}
        <div style={{ display: "flex", gap: "0.5rem", justifyContent: "flex-end" }}>
          <button onClick={onClose} style={{ padding: "0.5rem 0.9rem", borderRadius: "8px", border: "1px solid var(--color-border)", background: "var(--color-surface)", color: "var(--color-muted)", cursor: "pointer", fontSize: "0.85rem" }}>닫기</button>
          <button onClick={save} disabled={busy} className="stockcy-btn stockcy-btn-primary" style={{ padding: "0.5rem 0.9rem", fontSize: "0.85rem", fontWeight: 700, opacity: busy ? 0.5 : 1 }}>
            {busy ? "저장 중…" : "저장 + 테스트"}
          </button>
        </div>
      </div>
    </div>
  );
}
