"use client";
/**
 * 관리자 콘솔 (Phase 4b) — AI 사용 신청 승인 + 유저별 크레딧/사용량/계정 on·off.
 * 관리자만 접근 가능 (백엔드도 require_admin 으로 이중 보호).
 */
import { useState } from "react";
import useSWR from "swr";
import { useAuth } from "@/lib/auth-context";

const fetcher = (u: string) => fetch(u, { cache: "no-store" }).then((r) => r.json());

async function post(url: string, body?: object) {
  const r = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json", "ngrok-skip-browser-warning": "69420" },
    body: body ? JSON.stringify(body) : undefined,
  });
  return r.json().catch(() => ({}));
}

export default function AdminPage() {
  const { user, loading } = useAuth();

  const { data: reqData, mutate: mutateReqs } = useSWR("/backend/api/auth/admin/ai-requests?status=pending", fetcher, { refreshInterval: 15000 });
  const { data: userData, mutate: mutateUsers } = useSWR("/backend/api/auth/admin/users-usage", fetcher, { refreshInterval: 15000 });
  const [grantCounts, setGrantCounts] = useState<Record<number, number>>({});

  // 새 유저 생성 폼
  const [newUser, setNewUser] = useState({ username: "", password: "", role: "user", ai_credits: 0 });
  const [creating, setCreating] = useState(false);
  const [createMsg, setCreateMsg] = useState<{ ok: boolean; text: string } | null>(null);

  if (loading) return <div style={{ color: "var(--color-muted)" }}>불러오는 중…</div>;
  if (!user || user.role !== "admin") {
    return <div style={{ color: "var(--color-danger)", fontWeight: 700, padding: "2rem" }}>관리자만 접근할 수 있습니다.</div>;
  }

  const requests = reqData?.requests ?? [];
  const users = userData?.users ?? [];

  async function decide(id: number, approve: boolean) {
    const count = approve ? (grantCounts[id] ?? 5) : 0;
    await post(`/backend/api/auth/admin/ai-requests/${id}/decide`, { approve, count });
    mutateReqs(); mutateUsers();
  }
  async function adjust(username: string, delta: number) {
    await post(`/backend/api/auth/users/${username}/credits`, { delta });
    mutateUsers();
  }
  async function toggle(username: string, isActive: boolean) {
    await post(`/backend/api/auth/users/${username}/toggle`, { is_active: isActive });
    mutateUsers();
  }
  async function createUser() {
    if (!newUser.username.trim() || !newUser.password) {
      setCreateMsg({ ok: false, text: "아이디와 비밀번호를 입력하세요." });
      return;
    }
    setCreating(true);
    setCreateMsg(null);
    const res = await post("/backend/api/auth/users", newUser);
    setCreating(false);
    if (res?.success) {
      setCreateMsg({ ok: true, text: res.message || "계정 생성 완료" });
      setNewUser({ username: "", password: "", role: "user", ai_credits: 0 });
      mutateUsers();
    } else {
      setCreateMsg({ ok: false, text: res?.detail || res?.message || "생성 실패" });
    }
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "1.5rem", maxWidth: "960px" }}>
      <h1 style={{ fontSize: "1.3rem", fontWeight: 800 }}>⚙ 관리자 콘솔</h1>

      {/* 대기 중 AI 사용 신청 */}
      <section style={{ background: "var(--color-card)", border: "1px solid var(--color-border)", borderRadius: "12px", padding: "1.2rem" }}>
        <h2 style={{ fontSize: "1rem", fontWeight: 700, marginBottom: "0.8rem" }}>⏳ AI 사용 신청 대기 ({requests.length})</h2>
        {requests.length === 0 ? (
          <div style={{ color: "var(--color-muted)", fontSize: "0.85rem" }}>대기 중인 신청이 없습니다.</div>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: "0.6rem" }}>
            {requests.map((r: any) => (
              <div key={r.id} style={{ display: "flex", alignItems: "center", gap: "0.6rem", flexWrap: "wrap", padding: "0.6rem 0.8rem", background: "var(--color-surface)", borderRadius: "8px" }}>
                <span style={{ fontWeight: 700 }}>{r.username}</span>
                <span style={{ fontSize: "0.78rem", color: "var(--color-muted)" }}>{r.requested_at}</span>
                {r.reason && <span style={{ fontSize: "0.78rem", color: "var(--color-muted)" }}>“{r.reason}”</span>}
                <div style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: "0.4rem" }}>
                  <input
                    type="number" min={1}
                    value={grantCounts[r.id] ?? 5}
                    onChange={(e) => setGrantCounts((g) => ({ ...g, [r.id]: parseInt(e.target.value) || 0 }))}
                    style={{ width: "56px", padding: "3px 6px", borderRadius: "6px", border: "1px solid var(--color-border)", background: "var(--color-bg)", color: "var(--color-text)" }}
                  />
                  <span style={{ fontSize: "0.75rem", color: "var(--color-muted)" }}>회</span>
                  <button onClick={() => decide(r.id, true)} className="stockcy-btn stockcy-btn-primary" style={{ padding: "4px 12px", fontSize: "0.8rem" }}>승인</button>
                  <button onClick={() => decide(r.id, false)} style={{ padding: "4px 12px", fontSize: "0.8rem", borderRadius: "6px", border: "1px solid var(--color-border)", background: "var(--color-surface)", color: "var(--color-danger)", cursor: "pointer" }}>거부</button>
                </div>
              </div>
            ))}
          </div>
        )}
      </section>

      {/* 유저 추가 */}
      <section style={{ background: "var(--color-card)", border: "1px solid var(--color-border)", borderRadius: "12px", padding: "1.2rem" }}>
        <h2 style={{ fontSize: "1rem", fontWeight: 700, marginBottom: "0.8rem" }}>➕ 유저 추가</h2>
        <div style={{ display: "flex", flexWrap: "wrap", alignItems: "flex-end", gap: "0.6rem" }}>
          <label style={{ display: "flex", flexDirection: "column", gap: "3px", fontSize: "0.72rem", color: "var(--color-muted)" }}>
            아이디
            <input
              value={newUser.username}
              onChange={(e) => setNewUser((u) => ({ ...u, username: e.target.value }))}
              placeholder="새 유저 아이디"
              style={{ width: "150px", padding: "6px 8px", borderRadius: "6px", border: "1px solid var(--color-border)", background: "var(--color-bg)", color: "var(--color-text)", fontSize: "0.85rem" }}
            />
          </label>
          <label style={{ display: "flex", flexDirection: "column", gap: "3px", fontSize: "0.72rem", color: "var(--color-muted)" }}>
            임시 비밀번호
            <input
              type="text"
              value={newUser.password}
              onChange={(e) => setNewUser((u) => ({ ...u, password: e.target.value }))}
              placeholder="로그인 후 변경 권장"
              style={{ width: "160px", padding: "6px 8px", borderRadius: "6px", border: "1px solid var(--color-border)", background: "var(--color-bg)", color: "var(--color-text)", fontSize: "0.85rem" }}
            />
          </label>
          <label style={{ display: "flex", flexDirection: "column", gap: "3px", fontSize: "0.72rem", color: "var(--color-muted)" }}>
            역할
            <select
              value={newUser.role}
              onChange={(e) => setNewUser((u) => ({ ...u, role: e.target.value }))}
              style={{ padding: "6px 8px", borderRadius: "6px", border: "1px solid var(--color-border)", background: "var(--color-bg)", color: "var(--color-text)", fontSize: "0.85rem" }}
            >
              <option value="user">유저</option>
              <option value="admin">관리자</option>
            </select>
          </label>
          <label style={{ display: "flex", flexDirection: "column", gap: "3px", fontSize: "0.72rem", color: "var(--color-muted)" }}>
            초기 AI 횟수
            <input
              type="number" min={0}
              value={newUser.ai_credits}
              onChange={(e) => setNewUser((u) => ({ ...u, ai_credits: parseInt(e.target.value) || 0 }))}
              style={{ width: "90px", padding: "6px 8px", borderRadius: "6px", border: "1px solid var(--color-border)", background: "var(--color-bg)", color: "var(--color-text)", fontSize: "0.85rem" }}
            />
          </label>
          <button onClick={createUser} disabled={creating} className="stockcy-btn stockcy-btn-primary" style={{ padding: "7px 16px", fontSize: "0.85rem", opacity: creating ? 0.6 : 1 }}>
            {creating ? "생성 중…" : "계정 생성"}
          </button>
        </div>
        {createMsg && (
          <div style={{ marginTop: "0.6rem", fontSize: "0.8rem", fontWeight: 600, color: createMsg.ok ? "#34d399" : "var(--color-danger)" }}>
            {createMsg.text}
          </div>
        )}
      </section>

      {/* 유저 관리 */}
      <section style={{ background: "var(--color-card)", border: "1px solid var(--color-border)", borderRadius: "12px", padding: "1.2rem" }}>
        <h2 style={{ fontSize: "1rem", fontWeight: 700, marginBottom: "0.8rem" }}>👥 유저 ({users.length})</h2>
        <div style={{ overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.82rem" }}>
            <thead>
              <tr style={{ color: "var(--color-muted)", textAlign: "left", borderBottom: "1px solid var(--color-border)" }}>
                <th style={{ padding: "6px 8px" }}>유저</th>
                <th style={{ padding: "6px 8px" }}>역할</th>
                <th style={{ padding: "6px 8px" }}>상태</th>
                <th style={{ padding: "6px 8px" }}>AI 잔여</th>
                <th style={{ padding: "6px 8px" }}>오늘/누적 사용</th>
                <th style={{ padding: "6px 8px" }}>크레딧 조정</th>
              </tr>
            </thead>
            <tbody>
              {users.map((u: any) => (
                <tr key={u.username} style={{ borderBottom: "1px solid var(--color-border)" }}>
                  <td style={{ padding: "8px", fontWeight: 700 }}>{u.username}{u.has_pending && <span style={{ marginLeft: 6, fontSize: "0.62rem", color: "#fbbf24" }}>● 신청</span>}</td>
                  <td style={{ padding: "8px" }}>{u.role === "admin" ? "관리자" : "유저"}</td>
                  <td style={{ padding: "8px" }}>
                    {u.role === "admin" ? (
                      <span style={{ color: "var(--color-muted)" }}>—</span>
                    ) : (
                      <button onClick={() => toggle(u.username, !u.is_active)} style={{ fontSize: "0.72rem", fontWeight: 700, cursor: "pointer", borderRadius: "20px", padding: "2px 10px", border: "1px solid", borderColor: u.is_active ? "#34d399" : "var(--color-danger)", color: u.is_active ? "#34d399" : "var(--color-danger)", background: "transparent" }}>
                        {u.is_active ? "활성" : "차단됨"}
                      </button>
                    )}
                  </td>
                  <td style={{ padding: "8px", fontWeight: 700 }}>{u.role === "admin" ? "∞" : u.ai_credits}</td>
                  <td style={{ padding: "8px", color: "var(--color-muted)" }}>{u.usage_today} / {u.usage_total}</td>
                  <td style={{ padding: "8px" }}>
                    {u.role !== "admin" && (
                      <span style={{ display: "inline-flex", gap: "4px" }}>
                        {[1, 5, 10].map((n) => (
                          <button key={n} onClick={() => adjust(u.username, n)} style={{ fontSize: "0.72rem", cursor: "pointer", borderRadius: "5px", border: "1px solid var(--color-border)", background: "var(--color-surface)", color: "#34d399", padding: "2px 7px" }}>+{n}</button>
                        ))}
                        <button onClick={() => adjust(u.username, -u.ai_credits)} style={{ fontSize: "0.72rem", cursor: "pointer", borderRadius: "5px", border: "1px solid var(--color-border)", background: "var(--color-surface)", color: "var(--color-danger)", padding: "2px 7px" }}>0</button>
                      </span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
