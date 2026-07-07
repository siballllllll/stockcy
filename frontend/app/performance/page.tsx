"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import dynamic from "next/dynamic";
import useSWR from "swr";
import { MarkdownLite } from "@/components/ui/MarkdownLite";
import { ScenarioTrackingPanel } from "@/app/scenarios/page";
import { useAuth } from "@/lib/auth-context";

// AI 에이전트 대시보드(구 상단 탭)를 리그 우측 패널로 임베드 — 무거워서 지연 로드
const AgentDashboard = dynamic(() => import("@/app/agent/page"), { ssr: false });

const B = "/backend";
const fetcher = (url: string) => fetch(url).then((r) => (r.ok ? r.json() : null));

const wrColor = (v: number | null | undefined) =>
  v == null ? "var(--color-muted)" : v >= 60 ? "#34d399" : v >= 45 ? "#fbbf24" : "#f87171";
const pct = (v: number | null | undefined) => (v == null ? "—" : `${v}%`);
const ret = (v: number | null | undefined) => (v == null ? "—" : `${v >= 0 ? "+" : ""}${v}%`);

// ── 엔진별 성과 + AI추천 적중률 ─────────────────────────────────────────────────
function EngineScoreboard() {
  const router = useRouter();
  const { data: rec } = useSWR(`${B}/api/ai/recommendation-stats`, fetcher);
  const { data: scn } = useSWR(`${B}/api/ai/scenario-tracking/stats`, fetcher);
  const { data: scr } = useSWR(`${B}/api/ai/screener-backtest/stats`, fetcher);
  const { data: agent } = useSWR(`${B}/api/ai/agent-performance`, fetcher);
  const { data: bench } = useSWR(`${B}/api/ai/benchmark-returns?days=7,30,90`, fetcher, { refreshInterval: 600000 });

  // 엔진별 d7 헤드라인 산출
  const recH = (rec?.horizons ?? []).find((h: any) => h.horizon === "7일");
  // 시나리오: by_scenario 가중 평균
  const bs: any[] = scn?.by_scenario ?? [];
  const scnN = bs.reduce((a, b) => a + (b.count || 0), 0);
  const scnWin = scnN > 0 ? Math.round(bs.reduce((a, b) => a + (b.win_rate_d7 || 0) * (b.count || 0), 0) / scnN * 10) / 10 : null;
  const scnAvg = scnN > 0 ? Math.round(bs.reduce((a, b) => a + (b.avg_d7_return || 0) * (b.count || 0), 0) / scnN * 100) / 100 : null;
  const scrO = scr?.overall ?? {};

  const engines = [
    { name: "🤖 AI추천", n: rec?.measured ?? 0, win: recH?.win_rate ?? null, avg: recH?.avg_return ?? null, note: "단타발굴·종목분석 추천의 7일 후 성과", href: "" },
    { name: "📈 시나리오", n: scnN, win: scnWin, avg: scnAvg, note: "시나리오 등장 종목 7일 후 (방향 적중) — 아래 상세", href: "" },
    { name: "🔍 복합스크리너", n: scr?.total_picks_backtested ?? 0, win: scrO.win_rate_d7 ?? null, avg: scrO.avg_d7_return ?? null, note: "패턴 스크리너 픽 7일 후 백테스트", href: "" },
    { name: "🦾 AI에이전트", n: agent?.n ?? 0, win: agent?.win_rate ?? null, avg: agent?.avg_return ?? null, note: "에이전트 모의매매 '확정 거래'의 실현 승률·수익률", href: "/agent" },
  ];

  // 벤치마크(시장) 기준선 — 엔진 평균수익률을 '시장 대비'로 가늠
  const bk7 = bench?.["KOSPI"]?.["7"]; const bs7 = bench?.["S&P500"]?.["7"];

  return (
    <div className="stockcy-card" style={{ padding: "1rem 1.2rem" }}>
      <div style={{ fontWeight: 800, fontSize: "1rem", marginBottom: "4px" }}>📊 엔진별 성과 (7일 기준)</div>
      <div style={{ fontSize: "0.74rem", color: "var(--color-muted)", marginBottom: "12px" }}>각 AI 엔진이 추천한 종목이 실제로 며칠 뒤 맞았나 — 표본이 쌓일수록 정확해집니다.</div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: "10px" }}>
        {engines.map((e, i) => (
          <div key={i} onClick={e.href ? () => router.push(e.href) : undefined}
            style={{ background: "rgba(255,255,255,0.03)", border: "1px solid var(--color-border)", borderRadius: "10px", padding: "12px 14px", cursor: e.href ? "pointer" : "default", transition: "border-color 0.15s" }}
            onMouseEnter={e.href ? (ev) => { ev.currentTarget.style.borderColor = "var(--color-accent)"; } : undefined}
            onMouseLeave={e.href ? (ev) => { ev.currentTarget.style.borderColor = "var(--color-border)"; } : undefined}>
            <div style={{ fontWeight: 800, fontSize: "0.9rem", marginBottom: "6px", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <span>{e.name}</span>
              {e.href && <span style={{ fontSize: "0.68rem", color: "var(--color-accent)", fontWeight: 600 }}>상세 →</span>}
            </div>
            <div style={{ display: "flex", alignItems: "baseline", gap: "8px" }}>
              <span style={{ fontSize: "1.5rem", fontWeight: 900, color: wrColor(e.win) }}>{pct(e.win)}</span>
              <span style={{ fontSize: "0.78rem", color: "var(--color-muted)" }}>승률</span>
            </div>
            <div style={{ fontSize: "0.8rem", color: "var(--color-subtle)" }}>평균 {ret(e.avg)} · 표본 {e.n}건</div>
            <div style={{ fontSize: "0.68rem", color: "var(--color-muted)", marginTop: "4px", lineHeight: 1.4 }}>{e.note}</div>
          </div>
        ))}
      </div>
      {/* 벤치마크(시장) 기준선 — 엔진 평균수익률 vs 시장 */}
      {(bk7 != null || bs7 != null) && (
        <div style={{ marginTop: "12px", display: "flex", alignItems: "center", gap: "10px", flexWrap: "wrap", fontSize: "0.78rem", background: "rgba(255,255,255,0.03)", border: "1px dashed var(--color-border)", borderRadius: "8px", padding: "8px 12px" }}>
          <span style={{ fontWeight: 700, color: "var(--color-muted)" }}>📐 시장 기준선 (7일)</span>
          {bk7 != null && <span>KOSPI <b style={{ color: bk7 >= 0 ? "#34d399" : "#f87171" }}>{ret(bk7)}</b></span>}
          {bs7 != null && <span>S&amp;P500 <b style={{ color: bs7 >= 0 ? "#34d399" : "#f87171" }}>{ret(bs7)}</b></span>}
          <span style={{ color: "var(--color-subtle)", fontSize: "0.72rem" }}>— 엔진 평균수익률이 이보다 높아야 '시장 초과(실력)'</span>
        </div>
      )}

      {/* AI추천 1/3/7일 분해 */}
      {(rec?.horizons ?? []).length > 0 && (
        <div style={{ marginTop: "12px", borderTop: "1px solid var(--color-border)", paddingTop: "10px" }}>
          <div style={{ fontSize: "0.78rem", fontWeight: 700, color: "var(--color-muted)", marginBottom: "6px" }}>🤖 AI추천 기간별 적중률</div>
          <div style={{ display: "flex", gap: "10px", flexWrap: "wrap" }}>
            {rec.horizons.map((h: any, i: number) => (
              <div key={i} style={{ background: "rgba(0,0,0,0.15)", borderRadius: "6px", padding: "6px 12px", fontSize: "0.8rem" }}>
                {h.horizon} <b style={{ color: wrColor(h.win_rate) }}>{pct(h.win_rate)}</b> <span style={{ color: "var(--color-muted)" }}>(평균 {ret(h.avg_return)}, {h.n}건)</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// ── 자산 추이 ────────────────────────────────────────────────────────────────────
function EquityCurve() {
  const { data } = useSWR(`${B}/api/ai/portfolio-series?days=90`, fetcher);
  const series: any[] = data?.series ?? [];
  if (series.length === 0) {
    return (
      <div className="stockcy-card" style={{ padding: "1rem 1.2rem" }}>
        <div style={{ fontWeight: 800, fontSize: "1rem", marginBottom: "4px" }}>💰 자산 추이</div>
        <div style={{ fontSize: "0.8rem", color: "var(--color-muted)" }}>매일 새벽 보유 스냅샷이 쌓이면 평가손익 추이가 표시됩니다. (오늘부터 누적)</div>
      </div>
    );
  }
  const pcts = series.map((s) => s.eval_pct).filter((v) => v != null) as number[];
  const lo = Math.min(0, ...pcts), hi = Math.max(0, ...pcts);
  const span = hi - lo || 1;
  return (
    <div className="stockcy-card" style={{ padding: "1rem 1.2rem" }}>
      <div style={{ fontWeight: 800, fontSize: "1rem", marginBottom: "10px" }}>💰 자산 추이 <span style={{ fontSize: "0.72rem", fontWeight: 600, color: "var(--color-muted)" }}>— 일별 평가손익률 (KR 보유 기준)</span></div>
      <div style={{ display: "flex", alignItems: "flex-end", gap: "3px", height: "90px", marginBottom: "8px" }}>
        {series.map((s, i) => {
          const v = s.eval_pct ?? 0;
          const h = Math.max(3, ((v - lo) / span) * 86);
          return <div key={i} title={`${s.date}: ${ret(s.eval_pct)}`} style={{ flex: 1, minWidth: "2px", height: `${h}px`, background: v >= 0 ? "#34d399" : "#f87171", borderRadius: "2px 2px 0 0", opacity: 0.85 }} />;
        })}
      </div>
      <div style={{ display: "flex", justifyContent: "space-between", fontSize: "0.74rem", color: "var(--color-subtle)" }}>
        <span>{series[0].date} · {ret(series[0].eval_pct)}</span>
        <span style={{ fontWeight: 800, color: wrColor((series[series.length - 1].eval_pct ?? 0) >= 0 ? 60 : 0) }}>최신 {ret(series[series.length - 1].eval_pct)}</span>
      </div>
    </div>
  );
}

// ── 시장 기록 다시보기 ──────────────────────────────────────────────────────────
function MarketLogArchive() {
  const { data } = useSWR(`${B}/api/ai/market-log/dates?limit=60`, fetcher);
  const items: any[] = data?.items ?? [];
  const [sel, setSel] = useState<{ date: string; kind: string } | null>(null);
  const { data: detail } = useSWR(
    sel ? `${B}/api/ai/market-log?date=${sel.date}&kind=${sel.kind}` : null,
    fetcher
  );

  const kindLabel = (k: string) => (k === "commentary" ? "🧭 시장 인사이트" : "📈 시나리오");

  return (
    <div className="stockcy-card" style={{ padding: "1rem 1.2rem" }}>
      <div style={{ fontWeight: 800, fontSize: "1rem", marginBottom: "4px" }}>🗂️ 시장 기록 다시보기</div>
      <div style={{ fontSize: "0.74rem", color: "var(--color-muted)", marginBottom: "10px" }}>그날의 시장 인사이트·시나리오를 날짜별로 보관합니다. (오늘부터 누적)</div>
      {items.length === 0 ? (
        <div style={{ fontSize: "0.8rem", color: "var(--color-muted)" }}>아직 보관된 기록이 없습니다. 시장 인사이트/시나리오가 생성되면 쌓입니다.</div>
      ) : (
        <div style={{ display: "grid", gridTemplateColumns: "minmax(180px, 240px) 1fr", gap: "14px" }}>
          <div style={{ display: "flex", flexDirection: "column", gap: "4px", maxHeight: "360px", overflowY: "auto" }}>
            {items.map((it, i) => {
              const active = sel?.date === it.log_date && sel?.kind === it.kind;
              return (
                <button key={i} onClick={() => setSel({ date: it.log_date, kind: it.kind })}
                  style={{ textAlign: "left", padding: "6px 10px", borderRadius: "6px", cursor: "pointer", fontSize: "0.78rem",
                    border: `1px solid ${active ? "var(--color-accent)" : "var(--color-border)"}`,
                    background: active ? "rgba(99,102,241,0.15)" : "transparent", color: "var(--color-text)" }}>
                  <div style={{ fontWeight: 700 }}>{it.log_date}</div>
                  <div style={{ fontSize: "0.7rem", color: "var(--color-muted)" }}>{kindLabel(it.kind)}</div>
                </button>
              );
            })}
          </div>
          <div style={{ minWidth: 0 }}>
            {!sel ? (
              <div style={{ fontSize: "0.8rem", color: "var(--color-muted)", padding: "1rem" }}>왼쪽에서 날짜를 선택하세요.</div>
            ) : !detail?.data ? (
              <div style={{ fontSize: "0.8rem", color: "var(--color-muted)", padding: "1rem" }}>불러오는 중...</div>
            ) : sel.kind === "commentary" ? (
              <div>
                <div style={{ fontWeight: 800, fontSize: "0.95rem", marginBottom: "6px" }}>{detail.data.title}</div>
                <MarkdownLite text={detail.data.commentary} style={{ fontSize: "0.84rem", color: "var(--color-subtle)", lineHeight: 1.7 }} />
              </div>
            ) : (
              <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
                {(detail.data.issues ?? []).map((iss: any, i: number) => (
                  <div key={i} style={{ background: "rgba(0,0,0,0.18)", borderRadius: "6px", padding: "8px 12px" }}>
                    <div style={{ fontWeight: 700, fontSize: "0.85rem" }}>{iss.title}</div>
                    <div style={{ fontSize: "0.76rem", color: "var(--color-subtle)", marginTop: "2px" }}>{iss.summary}</div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

// ── 섀도우 리그 — 메인 vs 대조군 전략 실측 비교 (관리자 전용) ─────────
// 행 클릭 → 우측 상세 패널 토글 (메인=에이전트 대시보드 임베드, 섀도우=보유·거래 상세)
function ShadowLeaguePanel({ selected, onSelect }: { selected: string | null; onSelect: (owner: string) => void }) {
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";
  const { data } = useSWR(isAdmin ? `${B}/api/ai/shadow-league` : null, fetcher, { refreshInterval: 0 });
  if (!isAdmin || !data?.players?.length) return null;
  return (
    <div className="stockcy-card" style={{ padding: "1rem 1.2rem" }}>
      <div style={{ fontWeight: 800, fontSize: "1rem", marginBottom: "4px" }}>
        🥊 섀도우 리그 <span style={{ fontSize: "0.72rem", fontWeight: 600, color: "var(--color-muted)" }}>— 같은 시장에서 다른 전략으로 경쟁 중 (대조군 실측)</span>
      </div>
      <div style={{ fontSize: "0.74rem", color: "var(--color-muted)", marginBottom: "10px" }}>
        [상세] 버튼을 누르면 오른쪽에 해당 전략의 창(보유·거래)이 열리고, 다시 누르면 닫힙니다. 목적은 승자 선발이 아니라 전략×상황 매트릭스로 우리만의 통합 패턴을 합성하는 것.
      </div>
      <div style={{ overflowX: "auto" }}>
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.82rem" }}>
          <thead>
            <tr style={{ color: "var(--color-muted)", fontSize: "0.72rem" }}>
              <th style={{ textAlign: "left", padding: "4px 8px" }}>전략</th>
              <th style={{ textAlign: "right", padding: "4px 8px" }}>실현 거래</th>
              <th style={{ textAlign: "right", padding: "4px 8px" }}>승률</th>
              <th style={{ textAlign: "right", padding: "4px 8px" }}>평균 수익률</th>
              <th style={{ textAlign: "right", padding: "4px 8px" }}>보유 중</th>
              <th style={{ textAlign: "right", padding: "4px 8px" }}>현금</th>
              <th style={{ textAlign: "center", padding: "4px 8px" }}></th>
            </tr>
          </thead>
          <tbody>
            {data.players.map((p: any) => (
              <tr key={p.owner}
                style={{ borderTop: "1px solid var(--color-border)",
                  background: selected === p.owner ? "rgba(99,102,241,0.12)" : "transparent" }}>
                <td style={{ padding: "6px 8px", fontWeight: 700 }}>{p.label}</td>
                <td style={{ padding: "6px 8px", textAlign: "right" }}>{p.realized_trades}건</td>
                <td style={{ padding: "6px 8px", textAlign: "right", fontWeight: 700,
                  color: p.win_rate == null ? "var(--color-muted)" : p.win_rate >= 50 ? "#34d399" : "var(--color-danger)" }}>
                  {p.win_rate == null ? "—" : `${p.win_rate}%`}
                </td>
                <td style={{ padding: "6px 8px", textAlign: "right",
                  color: (p.avg_pct ?? 0) >= 0 ? "#34d399" : "var(--color-danger)" }}>
                  {p.avg_pct == null ? "—" : `${p.avg_pct > 0 ? "+" : ""}${p.avg_pct}%`}
                </td>
                <td style={{ padding: "6px 8px", textAlign: "right" }}>{p.open_positions}종목</td>
                <td style={{ padding: "6px 8px", textAlign: "right", color: "var(--color-muted)" }}>
                  {p.cash == null ? "—" : `${Number(p.cash).toLocaleString()}원`}
                </td>
                <td style={{ padding: "6px 8px", textAlign: "center" }}>
                  <button onClick={() => onSelect(p.owner)}
                    style={{ fontSize: "0.72rem", fontWeight: 700, padding: "3px 10px", borderRadius: "7px",
                      cursor: "pointer", whiteSpace: "nowrap",
                      border: `1px solid ${selected === p.owner ? "var(--color-accent)" : "var(--color-border)"}`,
                      background: selected === p.owner ? "rgba(99,102,241,0.18)" : "rgba(255,255,255,0.04)",
                      color: selected === p.owner ? "var(--color-text)" : "var(--color-muted)" }}>
                    {selected === p.owner ? "▼ 닫기" : "상세 ▶"}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {/* 전략×상황 매트릭스 — 리그의 최종 목적(상황별 최적 기법 합성). 표본 5건+ 셀부터 자동 표시 */}
      {(data.synthesis?.cells?.length ?? 0) > 0 && (
        <div style={{ marginTop: "12px", padding: "10px 12px", background: "rgba(99,102,241,0.06)", border: "1px solid rgba(99,102,241,0.2)", borderRadius: "8px" }}>
          <div style={{ fontWeight: 800, fontSize: "0.85rem", marginBottom: "6px" }}>🧩 전략×상황 매트릭스 <span style={{ fontSize: "0.68rem", fontWeight: 600, color: "var(--color-muted)" }}>— 상황별 최적 기법 합성용 (표본 5건+ 셀만)</span></div>
          <div style={{ display: "flex", flexDirection: "column", gap: "3px" }}>
            {data.synthesis.cells.slice(0, 12).map((c: any, i: number) => (
              <div key={i} style={{ display: "flex", justifyContent: "space-between", gap: "8px", fontSize: "0.78rem" }}>
                <span><b>{String(c.strategy).replace("SHADOW_", "섀도우 ")}</b> × {c.situation} <span style={{ color: "var(--color-muted)" }}>({c.n}건)</span></span>
                <span style={{ fontWeight: 700, color: c.win_rate >= 50 ? "#34d399" : "var(--color-danger)" }}>
                  승률 {c.win_rate}% · 평균 {c.avg_pct > 0 ? "+" : ""}{c.avg_pct}%
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// ── 자체 ML 모델 현황 ────────────────────────────────────────────────────────────
function MlStatusPanel() {
  const { data, mutate } = useSWR(`${B}/api/ai/ml-status`, fetcher, { refreshInterval: 0 });
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";
  const [training, setTraining] = useState(false);
  const [msg, setMsg] = useState("");
  const H = data?.horizons ?? {};
  const min = data?.min_required ?? 80;
  const ROWS = [
    { key: "d3",  label: "단타", desc: "3거래일" },
    { key: "d7",  label: "스윙", desc: "7거래일" },
    { key: "d20", label: "중장기", desc: "약 1개월" },
  ];

  const handleTrain = async () => {
    setTraining(true); setMsg("");
    try {
      const r = await fetch(`${B}/api/ai/ml-train`, { method: "POST" }).then((x) => x.json());
      setMsg(r?.success ? "학습 완료" : (r?.message || "학습 실패"));
      mutate();
    } catch { setMsg("학습 오류"); }
    finally { setTraining(false); }
  };

  return (
    <div className="stockcy-card" style={{ padding: "1rem 1.2rem" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: "8px", flexWrap: "wrap", marginBottom: "4px" }}>
        <div style={{ fontWeight: 800, fontSize: "1rem" }}>🤖 자체 ML 모델 현황 <span style={{ fontSize: "0.72rem", fontWeight: 600, color: "var(--color-muted)" }}>— 우리 데이터로 학습하는 예측 모델</span></div>
        {isAdmin && (
          <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
            {msg && <span style={{ fontSize: "0.72rem", color: "var(--color-muted)" }}>{msg}</span>}
            <button onClick={handleTrain} disabled={training}
              style={{ fontSize: "0.74rem", fontWeight: 700, padding: "5px 12px", borderRadius: "7px",
                border: "1px solid var(--color-accent)", background: "rgba(99,102,241,0.12)",
                color: "var(--color-text)", cursor: training ? "default" : "pointer", opacity: training ? 0.6 : 1 }}>
              {training ? "학습 중…" : "지금 학습"}
            </button>
          </div>
        )}
      </div>
      <div style={{ fontSize: "0.74rem", color: "var(--color-muted)", marginBottom: "10px" }}>추천을 쓸수록 자동으로 데이터가 쌓이고, 매일 아침 결과 갱신 후 자동 재학습됩니다. {min}건 넘으면 학습됩니다.</div>
      <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
        {ROWS.map((r) => {
          const info = H[r.key] ?? {};
          const n = info.samples ?? 0;
          const ready = info.ready_to_train;
          const active = info.model_exists;
          const auc = info.cv_auc;
          const trainedAt = info.trained_at ? String(info.trained_at).slice(0, 10) : null;
          const pctv = Math.min(100, Math.round((n / min) * 100));
          const c = active ? "#34d399" : ready ? "#34d399" : "#60a5fa";
          // AUC 0.5≈무작위. 0.55+ 부터 의미. 솔직하게 품질 라벨.
          const aucLabel = auc == null ? "" : auc >= 0.6 ? `AUC ${auc} (양호)` : auc >= 0.55 ? `AUC ${auc} (보통)` : `AUC ${auc} (예측력 낮음·학습중)`;
          return (
            <div key={r.key}>
              <div style={{ display: "flex", justifyContent: "space-between", fontSize: "0.82rem", marginBottom: "3px" }}>
                <span><b>{r.label}</b> <span style={{ fontSize: "0.7rem", color: "var(--color-muted)" }}>({r.desc})</span></span>
                <span style={{ color: "var(--color-subtle)" }}>
                  <b style={{ color: c }}>{n}</b> / {min}건
                  {active ? <span style={{ color: "#34d399", marginLeft: 6 }}>● 모델 활성</span>
                    : ready ? <span style={{ color: "#34d399", marginLeft: 6 }}>학습 가능</span>
                    : <span style={{ color: "var(--color-muted)", marginLeft: 6 }}>수집 중</span>}
                </span>
              </div>
              <div style={{ height: "7px", background: "rgba(255,255,255,0.06)", borderRadius: "99px", overflow: "hidden" }}>
                <div style={{ width: `${pctv}%`, height: "100%", background: c, borderRadius: "99px", transition: "width 0.3s" }} />
              </div>
              {active && (
                <div style={{ fontSize: "0.66rem", color: "var(--color-muted)", marginTop: "2px" }}>
                  학습 {trainedAt}{aucLabel ? ` · ${aucLabel}` : ""}
                </div>
              )}
            </div>
          );
        })}
      </div>
      {/* 예측 사후검증 — 추천 시점 예측확률 vs 실제 결과 (라이브 성적표) */}
      {(() => {
        const ver = data?.verification;
        if (!ver) return null;
        if (!ver.available) return (
          <div style={{ fontSize: "0.68rem", color: "var(--color-muted)", marginTop: "10px", padding: "8px 10px", background: "rgba(255,255,255,0.03)", borderRadius: "8px", lineHeight: 1.5 }}>
            🔬 <b>예측 사후검증</b>: {ver.reason || "예측 기록 수집 중"}
            <div style={{ color: "#a5b4fc", marginTop: "3px" }}>🏁 <b>v4.0 승격 게이트</b> (확정): 검증표본 100건+ · 실전 AUC 0.6+ · '55%+ 예측' 구간 실제 승률 50%+</div>
          </div>
        );
        const HL: Record<string, string> = { d3: "단타(3일)", d7: "스윙(7일)", d20: "중장기(20일)" };
        return (
          <div style={{ marginTop: "10px", padding: "10px 12px", background: "rgba(99,102,241,0.06)", border: "1px solid rgba(99,102,241,0.2)", borderRadius: "8px" }}>
            <div style={{ fontSize: "0.78rem", fontWeight: 800, marginBottom: "6px" }}>🔬 예측 사후검증 <span style={{ fontSize: "0.66rem", fontWeight: 600, color: "var(--color-muted)" }}>— 추천 시점 예측 vs 실제 결과 (실전 성적표)</span></div>
            {Object.entries(ver.horizons || {}).filter(([, v]: any) => v.n > 0).map(([h, v]: any) => (
              <div key={h} style={{ marginBottom: "6px" }}>
                <div style={{ fontSize: "0.72rem", color: "var(--color-subtle)" }}>
                  <b>{HL[h] ?? h}</b> — 검증표본 {v.n}건{v.live_auc != null && <> · 실전 AUC <b style={{ color: v.live_auc >= 0.6 ? "#34d399" : v.live_auc >= 0.55 ? "#a5b4fc" : "#f87171" }}>{v.live_auc}</b></>}
                </div>
                {v.buckets?.length > 0 && (
                  <div style={{ display: "flex", flexWrap: "wrap", gap: "4px", marginTop: "3px" }}>
                    {v.buckets.map((b: any, i: number) => (
                      <span key={i} style={{ fontSize: "0.66rem", padding: "2px 7px", borderRadius: "5px", background: "rgba(255,255,255,0.04)", border: "1px solid var(--color-border)", color: "var(--color-subtle)" }} title={`평균수익 ${b.avg_return}%`}>
                        예측 {b.label} → 실제 승률 <b style={{ color: "var(--color-text)" }}>{b.actual_win_rate}%</b> ({b.n}건)
                      </span>
                    ))}
                  </div>
                )}
              </div>
            ))}
            <div style={{ fontSize: "0.62rem", color: "var(--color-muted)", marginTop: "4px" }}>※ 보정이 잘 됐다면 각 구간의 실제 승률이 예측 구간과 비슷해야 합니다 (예: '55% 이상' 구간 → 실제 승률 ≈ 55%+).</div>
            <div style={{ fontSize: "0.64rem", color: "#a5b4fc", marginTop: "5px", padding: "5px 8px", background: "rgba(99,102,241,0.08)", borderRadius: "6px", lineHeight: 1.5 }}>
              🏁 <b>v4.0 승격 게이트</b> (확정): 검증표본 <b>100건+</b> · 실전 AUC <b>0.6+</b> · '55%+ 예측' 구간 실제 승률 <b>50%+</b> — 셋 다 충족되면 스톡시 4.0(자체 학습 두뇌) 선언
            </div>
          </div>
        );
      })()}
      <div style={{ fontSize: "0.68rem", color: "var(--color-muted)", marginTop: "8px", lineHeight: 1.5 }}>
        ※ v3.108+: ML 확률이 패턴 스크리너 점수(±12점)·매도타이밍·종목리포트에 실전 반영 중. 시계열 교차검증 + 확률보정 + 최근성 가중 적용, 매일 아침 자동 재학습.
      </div>
    </div>
  );
}

// ── 섀도우 개별 상세 — 보유 종목 + 최근 거래 (매수시각·수량·금액·근거·매도사유) ──
function ShadowDetail({ owner }: { owner: string }) {
  const { data } = useSWR(`${B}/api/ai/shadow-league/detail?owner=${owner}`, fetcher, { refreshInterval: 60000 });
  if (!data) return <div style={{ fontSize: "0.8rem", color: "var(--color-muted)", padding: "12px" }}>불러오는 중…</div>;
  const isUs = (tk: string) => /[A-Za-z]/.test(String(tk || ""));
  const money = (v: number, tk: string) => isUs(tk) ? `$${Number(v).toLocaleString(undefined, { maximumFractionDigits: 2 })}` : `${Number(v).toLocaleString()}원`;
  const dt = (s: any) => String(s || "").slice(5, 16);   // "MM-DD HH:MM"
  const heldFor = (buy: any, sell?: any) => {
    try {
      const a = new Date(String(buy).replace(" ", "T"));
      const b = sell ? new Date(String(sell).replace(" ", "T")) : new Date();
      const h = Math.max(0, (b.getTime() - a.getTime()) / 3600000);
      return h < 24 ? `${h.toFixed(1)}시간` : `${Math.floor(h / 24)}일`;
    } catch { return ""; }
  };
  const ctxChips = (ctx: any) => {
    if (!ctx) return null;
    const bits: string[] = [];
    if (ctx.regime && ctx.regime !== "?") bits.push(`레짐:${ctx.regime}`);
    if (ctx.issue) bits.push("이슈연관");
    if (ctx.supply) bits.push("수급상위");
    if (ctx.bb != null) bits.push(`볼린저 ${ctx.bb}`);
    if (ctx.m5 != null) bits.push(`5일 ${ctx.m5 > 0 ? "+" : ""}${ctx.m5}%`);
    if (ctx.rsi != null) bits.push(`RSI ${ctx.rsi}`);
    if (ctx.ml7 != null) bits.push(`ML ${ctx.ml7}%`);
    if (!bits.length) return null;
    return (
      <div style={{ display: "flex", gap: "4px", flexWrap: "wrap", marginTop: "4px" }}>
        {bits.map((b, i) => (
          <span key={i} style={{ fontSize: "0.64rem", padding: "1px 7px", borderRadius: "9px",
            background: "rgba(255,255,255,0.05)", border: "1px solid var(--color-border)", color: "var(--color-muted)" }}>{b}</span>
        ))}
      </div>
    );
  };
  const reasonLine = (label: string, text: any, color: string) => text ? (
    <div style={{ fontSize: "0.74rem", marginTop: "3px", lineHeight: 1.45 }}>
      <span style={{ fontWeight: 800, color, fontSize: "0.68rem" }}>{label}</span>{" "}
      <span style={{ color: "var(--color-text)" }}>{String(text)}</span>
    </div>
  ) : (
    <div style={{ fontSize: "0.7rem", marginTop: "3px", color: "var(--color-muted)" }}>
      <span style={{ fontWeight: 800, fontSize: "0.68rem" }}>{label}</span> 기록 없음 (컨텍스트 기록 이전 거래)
    </div>
  );
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "14px" }}>
      <div>
        <div style={{ fontWeight: 800, fontSize: "0.88rem", marginBottom: "6px" }}>📦 보유 중 ({data.holdings?.length ?? 0}종목)</div>
        {!data.holdings?.length && <div style={{ fontSize: "0.78rem", color: "var(--color-muted)" }}>보유 없음</div>}
        {(data.holdings ?? []).map((h: any) => (
          <div key={h.ticker} style={{ padding: "9px 10px", borderTop: "1px solid var(--color-border)", fontSize: "0.8rem" }}>
            <div style={{ display: "flex", justifyContent: "space-between", gap: "8px" }}>
              <b>{h.name} <span style={{ color: "var(--color-muted)", fontWeight: 500 }}>({h.ticker})</span></b>
              <span style={{ fontSize: "0.7rem", color: "var(--color-muted)" }}>보유 {heldFor(h.buy_date)}</span>
            </div>
            <div style={{ fontSize: "0.76rem", color: "var(--color-subtle)", marginTop: "2px" }}>
              매수 <b>{dt(h.buy_date)}</b> · {Number(h.quantity).toLocaleString()}주 × {money(h.buy_price, h.ticker)}
              {" = "}<b>{money(h.quantity * h.buy_price, h.ticker)}</b>
            </div>
            {reasonLine("매수 근거", h.ctx?.note, "#34d399")}
            {ctxChips(h.ctx)}
          </div>
        ))}
      </div>
      <div>
        <div style={{ fontWeight: 800, fontSize: "0.88rem", marginBottom: "6px" }}>📜 최근 거래 ({data.trades?.length ?? 0}건)</div>
        {!data.trades?.length && <div style={{ fontSize: "0.78rem", color: "var(--color-muted)" }}>아직 실현 거래 없음 — 청산(-5%/+8%/10일)이 발생하면 여기 쌓입니다.</div>}
        {(data.trades ?? []).map((t: any, i: number) => (
          <div key={i} style={{ padding: "9px 10px", borderTop: "1px solid var(--color-border)", fontSize: "0.8rem" }}>
            <div style={{ display: "flex", justifyContent: "space-between", gap: "8px" }}>
              <b>{t.name} <span style={{ color: "var(--color-muted)", fontWeight: 500 }}>({t.ticker})</span></b>
              <b style={{ color: (t.profit_pct ?? 0) >= 0 ? "#34d399" : "var(--color-danger)" }}>
                {(t.profit_pct ?? 0) >= 0 ? "+" : ""}{Number(t.profit_pct ?? 0).toFixed(2)}%
                {t.profit != null && <span style={{ fontWeight: 600, fontSize: "0.7rem" }}> ({(t.profit >= 0 ? "+" : "") + money(Math.round(t.profit), t.ticker)})</span>}
              </b>
            </div>
            <div style={{ fontSize: "0.76rem", color: "var(--color-subtle)", marginTop: "2px" }}>
              매수 <b>{dt(t.buy_date)}</b> → 매도 <b>{dt(t.sell_date)}</b>
              <span style={{ color: "var(--color-muted)" }}> (보유 {heldFor(t.buy_date, t.sell_date)})</span>
            </div>
            <div style={{ fontSize: "0.76rem", color: "var(--color-subtle)", marginTop: "1px" }}>
              {Number(t.quantity).toLocaleString()}주 × {money(t.buy_price, t.ticker)} → {money(t.sell_price, t.ticker)}
            </div>
            {reasonLine("매수 근거", t.ctx?.note, "#34d399")}
            {reasonLine("매도 사유", t.learning_point, "#f87171")}
            {ctxChips(t.ctx)}
          </div>
        ))}
      </div>
    </div>
  );
}

const OWNER_LABEL: Record<string, string> = {
  AI_AGENT: "🤖 메인 에이전트 (Gemini 하이브리드)",
  SHADOW_A: "🥷 섀도우 A — 순수 눌림목",
  SHADOW_B: "🥷 섀도우 B — ML 순종",
  SHADOW_C: "🥷 섀도우 C — 이슈×구간",
  SHADOW_D: "🥷 섀도우 D — 수급 추종",
  SHADOW_E: "🎲 섀도우 E — 랜덤 대조군",
  SHADOW_F: "🔥 섀도우 F — 모멘텀 추격",
};

export default function PerformancePage() {
  // 리그 행 클릭 → 우측 상세 패널 토글 (같은 행 재클릭 시 닫힘)
  const [selOwner, setSelOwner] = useState<string | null>(null);
  const toggleOwner = (o: string) => setSelOwner((cur) => (cur === o ? null : o));
  return (
    <div style={{ display: "flex", gap: "16px", alignItems: "flex-start", flexWrap: "wrap" }}>
      <div style={{ display: "flex", flexDirection: "column", gap: "16px", maxWidth: "1100px", flex: "1 1 620px", minWidth: 0 }}>
        <h1 style={{ fontSize: "1.5rem", fontWeight: 800, margin: 0 }}>📊 성과 · 기록</h1>
        <div style={{ fontSize: "0.82rem", color: "var(--color-muted)", marginTop: "-8px" }}>이 시스템이 실제로 맞고 있는지, 그때 시장을 어떻게 봤는지, 내 자산이 어떻게 변했는지를 한 곳에서.</div>
        <EngineScoreboard />
        <MlStatusPanel />
        <ShadowLeaguePanel selected={selOwner} onSelect={toggleOwner} />
        {/* 시나리오 적중률·추적 종목 상세 (시나리오 페이지에서 이동) */}
        <ScenarioTrackingPanel />
        <EquityCurve />
        <MarketLogArchive />
      </div>
      {selOwner && (
        <div style={{ flex: "1 1 480px", minWidth: "360px", maxWidth: "820px", position: "sticky", top: "12px", maxHeight: "calc(100vh - 24px)", overflowY: "auto" }}>
          <div className="stockcy-card" style={{ padding: "0.9rem 1.1rem" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: "8px", marginBottom: "10px" }}>
              <div style={{ fontWeight: 800, fontSize: "0.95rem" }}>{OWNER_LABEL[selOwner] ?? selOwner}</div>
              <button onClick={() => setSelOwner(null)}
                style={{ border: "1px solid var(--color-border)", background: "transparent", color: "var(--color-muted)",
                  borderRadius: "7px", padding: "3px 10px", fontSize: "0.74rem", cursor: "pointer" }}>
                ✕ 닫기
              </button>
            </div>
            {selOwner === "AI_AGENT" ? <AgentDashboard /> : <ShadowDetail owner={selOwner} />}
          </div>
        </div>
      )}
    </div>
  );
}
