"use client";
/**
 * 관리자 콘솔 (Phase 4b) — AI 사용 신청 승인 + 유저별 크레딧/사용량/계정 on·off.
 * + AI 엔진 대시보드 (프로바이더 전환, 사용량 통계, 벤치마크)
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

      {/* AI 엔진 대시보드 */}
      <AiEngineDashboard />
    </div>
  );
}

/* ── AI 엔진 대시보드 컴포넌트 ─────────────────────────────────────────────── */
function AiEngineDashboard() {
  const fetcher = (u: string) => fetch(u, { cache: "no-store", headers: { "ngrok-skip-browser-warning": "69420" } }).then(r => r.json());

  const { data: stats, mutate: mutateStats } = useSWR("/backend/api/admin/ai-stats?days=7", fetcher, { refreshInterval: 30000 });
  const { data: providerInfo, mutate: mutateProvider } = useSWR("/backend/api/admin/ai-provider", fetcher, { refreshInterval: 10000 });

  const [switching, setSwitching] = useState(false);
  const [switchMsg, setSwitchMsg] = useState<string | null>(null);
  const [selectedProvider, setSelectedProvider] = useState("openai");
  const [selectedModel, setSelectedModel] = useState("gpt-4o-mini");
  const [benchRunning, setBenchRunning] = useState(false);
  const [benchResult, setBenchResult] = useState<any>(null);

  async function switchProvider() {
    setSwitching(true);
    setSwitchMsg(null);
    const res = await fetch("/backend/api/admin/ai-provider/switch", {
      method: "POST",
      headers: { "Content-Type": "application/json", "ngrok-skip-browser-warning": "69420" },
      body: JSON.stringify({ provider: selectedProvider, openai_model: selectedModel }),
    }).then(r => r.json());
    setSwitching(false);
    if (res?.success) {
      setSwitchMsg(`✅ ${res.message}`);
      mutateProvider();
      mutateStats();
    } else {
      setSwitchMsg(`❌ ${res?.error || "전환 실패"}`);
    }
  }

  async function runBenchmark() {
    setBenchRunning(true);
    setBenchResult(null);
    const res = await fetch("/backend/api/admin/ai-benchmark/run", {
      method: "POST",
      headers: { "ngrok-skip-browser-warning": "69420" },
    }).then(r => r.json());
    setBenchRunning(false);
    setBenchResult(res);
    mutateStats();
  }

  const providerColor: Record<string, string> = {
    openai: "#10a37f",
    gemini: "#4285f4",
    benchmark: "#f59e0b",
  };

  const s = stats?.stats ?? {};

  return (
    <section style={{ background: "var(--color-card)", border: "1px solid var(--color-border)", borderRadius: "12px", padding: "1.2rem", display: "flex", flexDirection: "column", gap: "1rem" }}>
      <h2 style={{ fontSize: "1rem", fontWeight: 700 }}>🤖 AI 엔진 대시보드</h2>

      {/* 현재 상태 */}
      <div style={{ display: "flex", gap: "0.8rem", flexWrap: "wrap" }}>
        <div style={{ background: "var(--color-surface)", borderRadius: "8px", padding: "0.7rem 1rem", display: "flex", flexDirection: "column", gap: "2px" }}>
          <span style={{ fontSize: "0.7rem", color: "var(--color-muted)" }}>현재 프로바이더</span>
          <span style={{ fontWeight: 800, fontSize: "1.1rem", color: providerColor[providerInfo?.provider] ?? "#fff" }}>
            {providerInfo?.provider?.toUpperCase() ?? "—"}
          </span>
        </div>
        <div style={{ background: "var(--color-surface)", borderRadius: "8px", padding: "0.7rem 1rem", display: "flex", flexDirection: "column", gap: "2px" }}>
          <span style={{ fontSize: "0.7rem", color: "var(--color-muted)" }}>OpenAI 모델</span>
          <span style={{ fontWeight: 700, fontSize: "0.9rem" }}>{providerInfo?.openai_model ?? "—"}</span>
        </div>
        <div style={{ background: "var(--color-surface)", borderRadius: "8px", padding: "0.7rem 1rem", display: "flex", flexDirection: "column", gap: "2px" }}>
          <span style={{ fontSize: "0.7rem", color: "var(--color-muted)" }}>Gemini Key</span>
          <span style={{ fontWeight: 700, color: providerInfo?.gemini_key_set ? "#34d399" : "var(--color-danger)" }}>{providerInfo?.gemini_key_set ? "✅ 설정됨" : "❌ 없음"}</span>
        </div>
        <div style={{ background: "var(--color-surface)", borderRadius: "8px", padding: "0.7rem 1rem", display: "flex", flexDirection: "column", gap: "2px" }}>
          <span style={{ fontSize: "0.7rem", color: "var(--color-muted)" }}>OpenAI Key</span>
          <span style={{ fontWeight: 700, color: providerInfo?.openai_key_set ? "#34d399" : "var(--color-danger)" }}>{providerInfo?.openai_key_set ? "✅ 설정됨" : "❌ 없음"}</span>
        </div>
      </div>

      {/* 사용량 통계 (최근 7일) */}
      {Object.keys(s).length > 0 && (
        <div>
          <div style={{ fontSize: "0.78rem", color: "var(--color-muted)", marginBottom: "0.5rem" }}>📊 최근 7일 사용량</div>
          <div style={{ display: "flex", gap: "0.8rem", flexWrap: "wrap" }}>
            {Object.entries(s).map(([provider, d]: [string, any]) => (
              <div key={provider} style={{ background: "var(--color-surface)", borderRadius: "8px", padding: "0.8rem 1rem", minWidth: "180px", borderTop: `3px solid ${providerColor[provider] ?? "#888"}` }}>
                <div style={{ fontWeight: 800, fontSize: "0.9rem", marginBottom: "0.4rem", color: providerColor[provider] ?? "#fff" }}>
                  {provider === "openai" ? "🟢 OpenAI" : provider === "gemini" ? "🔵 Gemini" : "🟡 Benchmark"}
                </div>
                <div style={{ fontSize: "0.78rem", display: "flex", flexDirection: "column", gap: "2px", color: "var(--color-muted)" }}>
                  <span>호출 수: <b style={{ color: "var(--color-text)" }}>{d.calls.toLocaleString()}회</b></span>
                  <span>총 토큰: <b style={{ color: "var(--color-text)" }}>{d.total_tokens.toLocaleString()}</b></span>
                  <span>총 비용: <b style={{ color: "#fbbf24" }}>${d.cost_usd_total.toFixed(4)} (₩{d.cost_krw_total.toFixed(1)})</b></span>
                  <span>평균 응답: <b style={{ color: "var(--color-text)" }}>{d.avg_latency_sec != null ? `${d.avg_latency_sec}초` : "—"}</b></span>
                  <span>검색 포함: <b style={{ color: "var(--color-text)" }}>{d.search_calls}회</b></span>
                  {Object.entries(d.models).map(([m, cnt]: [string, any]) => (
                    <span key={m} style={{ fontSize: "0.7rem" }}>└ {m}: {cnt}회</span>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 프로바이더 전환 */}
      <div style={{ display: "flex", flexWrap: "wrap", alignItems: "flex-end", gap: "0.6rem" }}>
        <label style={{ display: "flex", flexDirection: "column", gap: "3px", fontSize: "0.72rem", color: "var(--color-muted)" }}>
          프로바이더
          <select value={selectedProvider} onChange={e => setSelectedProvider(e.target.value)}
            style={{ padding: "6px 8px", borderRadius: "6px", border: "1px solid var(--color-border)", background: "var(--color-bg)", color: "var(--color-text)", fontSize: "0.85rem" }}>
            <option value="openai">OpenAI</option>
            <option value="gemini">Gemini</option>
            <option value="benchmark">Benchmark (둘 다)</option>
          </select>
        </label>
        {(selectedProvider === "openai" || selectedProvider === "benchmark") && (
          <label style={{ display: "flex", flexDirection: "column", gap: "3px", fontSize: "0.72rem", color: "var(--color-muted)" }}>
            OpenAI 모델
            <select value={selectedModel} onChange={e => setSelectedModel(e.target.value)}
              style={{ padding: "6px 8px", borderRadius: "6px", border: "1px solid var(--color-border)", background: "var(--color-bg)", color: "var(--color-text)", fontSize: "0.85rem" }}>
              <option value="gpt-4o-mini">gpt-4o-mini (저비용)</option>
              <option value="gpt-4o">gpt-4o (고성능)</option>
              <option value="gpt-4.1-mini">gpt-4.1-mini</option>
            </select>
          </label>
        )}
        <button onClick={switchProvider} disabled={switching} className="stockcy-btn stockcy-btn-primary" style={{ padding: "7px 16px", fontSize: "0.85rem", opacity: switching ? 0.6 : 1 }}>
          {switching ? "전환 중…" : "⚡ 즉시 전환"}
        </button>
        {switchMsg && <span style={{ fontSize: "0.8rem", fontWeight: 600 }}>{switchMsg}</span>}
      </div>

      {/* 벤치마크 */}
      <div>
        <button onClick={runBenchmark} disabled={benchRunning}
          style={{ padding: "7px 18px", fontSize: "0.85rem", borderRadius: "8px", border: "1px solid #f59e0b", background: "transparent", color: "#f59e0b", cursor: benchRunning ? "not-allowed" : "pointer", fontWeight: 700, opacity: benchRunning ? 0.6 : 1 }}>
          {benchRunning ? "⏳ 벤치마크 실행 중 (10~15초)…" : "🏁 OpenAI vs Gemini 벤치마크 실행"}
        </button>
        {benchResult && (
          <div style={{ marginTop: "0.7rem", display: "flex", gap: "0.8rem", flexWrap: "wrap" }}>
            {Object.entries(benchResult.results ?? {}).map(([prov, r]: [string, any]) => (
              <div key={prov} style={{ background: "var(--color-surface)", borderRadius: "8px", padding: "0.7rem 1rem", minWidth: "200px", borderTop: `3px solid ${providerColor[prov] ?? "#888"}` }}>
                <div style={{ fontWeight: 700, marginBottom: "0.3rem", color: providerColor[prov] ?? "#fff" }}>{prov.toUpperCase()}</div>
                {r.status === "ok" ? (
                  <div style={{ fontSize: "0.78rem", display: "flex", flexDirection: "column", gap: "2px" }}>
                    <span>⏱ {r.latency_sec}초</span>
                    <span>추천가: <b>{r.result?.recommended_price?.toLocaleString()}</b></span>
                    <span style={{ color: "var(--color-muted)", fontSize: "0.7rem" }}>{r.result?.reason?.slice(0, 60)}…</span>
                  </div>
                ) : (
                  <div style={{ color: "var(--color-danger)", fontSize: "0.78rem" }}>❌ {r.error}</div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </section>
  );
}
