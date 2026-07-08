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
                  color: p.win_rate == null ? "var(--color-muted)" : p.win_rate >= 50 ? "var(--color-danger)" : "var(--color-primary)" }}>
                  {p.win_rate == null ? "—" : `${p.win_rate}%`}
                </td>
                <td style={{ padding: "6px 8px", textAlign: "right",
                  color: (p.avg_pct ?? 0) >= 0 ? "var(--color-danger)" : "var(--color-primary)" }}>
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
      {/* 리그 큐레이터 — 섀도우 총괄 어시스턴트의 일일 코멘트 (매일 16:20 자동 생성) */}
      {data.curator?.commentary && (
        <div style={{ marginTop: "12px", padding: "10px 12px", background: "rgba(52,211,153,0.06)", border: "1px solid rgba(52,211,153,0.22)", borderRadius: "8px" }}>
          <div style={{ fontWeight: 800, fontSize: "0.85rem", marginBottom: "5px" }}>🧠 리그 큐레이터 <span style={{ fontSize: "0.68rem", fontWeight: 600, color: "var(--color-muted)" }}>— 총괄 어시스턴트 일일 분석 ({data.curator.date})</span></div>
          <div style={{ fontSize: "0.8rem", color: "var(--color-text)", lineHeight: 1.6, whiteSpace: "pre-wrap" }}>{data.curator.commentary}</div>
        </div>
      )}
      {/* 전략×상황 매트릭스 — 리그의 최종 목적(상황별 최적 기법 합성). 표본 5건+ 셀부터 자동 표시 */}
      {(data.synthesis?.cells?.length ?? 0) > 0 && (
        <div style={{ marginTop: "12px", padding: "10px 12px", background: "rgba(99,102,241,0.06)", border: "1px solid rgba(99,102,241,0.2)", borderRadius: "8px" }}>
          <div style={{ fontWeight: 800, fontSize: "0.85rem", marginBottom: "6px" }}>🧩 전략×상황 매트릭스 <span style={{ fontSize: "0.68rem", fontWeight: 600, color: "var(--color-muted)" }}>— 상황별 최적 기법 합성용 (표본 5건+ 셀만)</span></div>
          <div style={{ display: "flex", flexDirection: "column", gap: "3px" }}>
            {data.synthesis.cells.slice(0, 12).map((c: any, i: number) => (
              <div key={i} style={{ display: "flex", justifyContent: "space-between", gap: "8px", fontSize: "0.78rem" }}>
                <span><b>{String(c.strategy).replace("SHADOW_", "섀도우 ")}</b> × {c.situation} <span style={{ color: "var(--color-muted)" }}>({c.n}건)</span></span>
                <span style={{ fontWeight: 700, color: c.win_rate >= 50 ? "var(--color-danger)" : "var(--color-primary)" }}>
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

// ── 섀도우 개별 상세 — 메인 에이전트 대시보드와 동일한 문법(요약 카드 + 표) ──
function ShadowDetail({ owner }: { owner: string }) {
  const { data } = useSWR(`${B}/api/ai/shadow-league/detail?owner=${owner}`, fetcher, { refreshInterval: 60000 });
  if (!data) return <div style={{ fontSize: "0.8rem", color: "var(--color-muted)", padding: "12px" }}>불러오는 중…</div>;
  const holdings: any[] = data.holdings ?? [];
  const trades: any[] = data.trades ?? [];
  const isUs = (tk: string) => /[A-Za-z]/.test(String(tk || ""));
  const sym = (tk: string) => (isUs(tk) ? "$" : "₩");
  const num = (v: any, tk?: string) => {
    const n = Number(v ?? 0);
    return tk && isUs(tk) ? n.toLocaleString(undefined, { maximumFractionDigits: 2 }) : Math.round(n).toLocaleString();
  };
  const dt = (s: any) => String(s || "").slice(5, 16);
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
    if (ctx.issue) bits.push("이슈");
    if (ctx.supply) bits.push("수급");
    if (ctx.bb != null) bits.push(`bb ${ctx.bb}`);
    if (ctx.m5 != null) bits.push(`5일 ${ctx.m5 > 0 ? "+" : ""}${ctx.m5}%`);
    if (ctx.ml7 != null) bits.push(`ML ${ctx.ml7}%`);
    if (!bits.length) return null;
    return (
      <div style={{ display: "flex", gap: "3px", flexWrap: "wrap", marginTop: "3px" }}>
        {bits.map((b, i) => (
          <span key={i} style={{ fontSize: "0.62rem", padding: "0 6px", borderRadius: "8px",
            background: "rgba(255,255,255,0.05)", border: "1px solid var(--color-border)", color: "var(--color-muted)" }}>{b}</span>
        ))}
      </div>
    );
  };
  // 요약 집계 — 평가손익(보유)·실현손익(거래), 통화별 분리
  const evalKr = holdings.filter(h => !isUs(h.ticker) && h.current_price != null)
    .reduce((a, h) => a + (h.current_price - h.buy_price) * h.quantity, 0);
  const evalUs = holdings.filter(h => isUs(h.ticker) && h.current_price != null)
    .reduce((a, h) => a + (h.current_price - h.buy_price) * h.quantity, 0);
  const realKr = trades.filter(t => !isUs(t.ticker)).reduce((a, t) => a + Number(t.profit ?? 0), 0);
  const realUs = trades.filter(t => isUs(t.ticker)).reduce((a, t) => a + Number(t.profit ?? 0), 0);
  const wins = trades.filter(t => Number(t.profit_pct ?? 0) > 0).length;
  const winRate = trades.length ? Math.round(wins / trades.length * 1000) / 10 : null;
  const moneyPair = (kr: number, us: number) => {
    const parts: string[] = [];
    if (kr !== 0 || us === 0) parts.push(`${kr >= 0 ? "+" : "-"}₩${Math.abs(Math.round(kr)).toLocaleString()}`);
    if (us !== 0) parts.push(`${us >= 0 ? "+" : "-"}$${Math.abs(us).toLocaleString(undefined, { maximumFractionDigits: 2 })}`);
    return parts.join(" · ");
  };
  const cardSt = { background: "var(--color-card)", border: "1px solid var(--color-border)", borderRadius: "12px", padding: "0.9rem 1.1rem" } as const;
  const cUp = "var(--color-danger)", cDn = "var(--color-primary)";
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "14px" }}>
      {/* 요약 카드 — 메인 에이전트 대시보드와 동일 문법 */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))", gap: "10px" }}>
        <div style={cardSt}>
          <div style={{ color: "var(--color-muted)", fontSize: "0.76rem", marginBottom: "4px" }}>보유 종목 · 평가손익</div>
          <div style={{ fontSize: "1.4rem", fontWeight: 800 }}>{holdings.length}건</div>
          <div style={{ fontSize: "0.85rem", fontWeight: 800, color: (evalKr + evalUs) >= 0 ? cUp : cDn }}>{moneyPair(evalKr, evalUs)}</div>
        </div>
        <div style={cardSt}>
          <div style={{ color: "var(--color-muted)", fontSize: "0.76rem", marginBottom: "4px" }}>실현 거래 · 승률</div>
          <div style={{ fontSize: "1.4rem", fontWeight: 800 }}>{trades.length}건</div>
          <div style={{ fontSize: "0.85rem", fontWeight: 800, color: winRate == null ? "var(--color-muted)" : winRate >= 50 ? cUp : cDn }}>
            {winRate == null ? "—" : `승률 ${winRate}%`}
          </div>
        </div>
        <div style={cardSt}>
          <div style={{ color: "var(--color-muted)", fontSize: "0.76rem", marginBottom: "4px" }}>누적 실현 손익</div>
          <div style={{ fontSize: "1.25rem", fontWeight: 800, color: (realKr + realUs) >= 0 ? cUp : cDn }}>
            {trades.length ? moneyPair(realKr, realUs) : "—"}
          </div>
        </div>
      </div>

      {/* 보유 종목 표 */}
      <div>
        <div style={{ fontWeight: 800, fontSize: "0.9rem", marginBottom: "6px" }}>📦 보유 종목</div>
        {!holdings.length ? <div style={{ fontSize: "0.78rem", color: "var(--color-muted)" }}>보유 없음</div> : (
          <div style={{ overflowX: "auto" }}>
            <table className="stockcy-table" style={{ fontSize: "0.8rem" }}>
              <thead>
                <tr>
                  <th>종목</th>
                  <th style={{ textAlign: "right" }}>수량</th>
                  <th style={{ textAlign: "right" }}>매수가</th>
                  <th style={{ textAlign: "right" }}>현재가</th>
                  <th style={{ textAlign: "right" }}>평가손익</th>
                  <th style={{ textAlign: "right" }}>수익률</th>
                  <th>매수 근거</th>
                  <th>매수일</th>
                </tr>
              </thead>
              <tbody>
                {holdings.map((h: any) => {
                  const hasPx = h.current_price != null;
                  const diff = hasPx ? (h.current_price - h.buy_price) * h.quantity : null;
                  const color = (h.eval_pct ?? 0) >= 0 ? cUp : cDn;
                  return (
                    <tr key={h.ticker}>
                      <td><strong>{h.name}</strong><div style={{ fontSize: "0.68rem", color: "var(--color-muted)" }}>{h.ticker}</div></td>
                      <td style={{ textAlign: "right" }}>{Number(h.quantity).toLocaleString()}주</td>
                      <td style={{ textAlign: "right" }}>{sym(h.ticker)}{num(h.buy_price, h.ticker)}</td>
                      <td style={{ textAlign: "right" }}>{hasPx ? `${sym(h.ticker)}${num(h.current_price, h.ticker)}` : "—"}</td>
                      <td style={{ textAlign: "right", color: hasPx ? color : "var(--color-muted)", fontWeight: 700 }}>
                        {hasPx ? `${diff! >= 0 ? "+" : "-"}${sym(h.ticker)}${num(Math.abs(diff!), h.ticker)}` : "—"}
                      </td>
                      <td style={{ textAlign: "right", color: hasPx ? color : "var(--color-muted)", fontWeight: 700 }}>
                        {h.eval_pct != null ? `${h.eval_pct >= 0 ? "+" : ""}${Number(h.eval_pct).toFixed(2)}%` : "—"}
                      </td>
                      <td style={{ maxWidth: "220px" }}>
                        <div style={{ fontSize: "0.76rem", whiteSpace: "pre-wrap", lineHeight: 1.4 }}>
                          {h.ctx?.note || <span style={{ color: "var(--color-subtle)" }}>기록 이전 매수</span>}
                        </div>
                        {ctxChips(h.ctx)}
                      </td>
                      <td style={{ fontSize: "0.72rem", color: "var(--color-muted)", whiteSpace: "nowrap" }}>
                        {dt(h.buy_date)}<br />보유 {heldFor(h.buy_date)}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* 거래 내역 표 */}
      <div>
        <div style={{ fontWeight: 800, fontSize: "0.9rem", marginBottom: "6px" }}>📜 거래 내역</div>
        {!trades.length ? (
          <div style={{ fontSize: "0.78rem", color: "var(--color-muted)" }}>아직 실현 거래 없음 — 7거래일 기간만료(또는 재난 -20%) 청산 시 쌓입니다.</div>
        ) : (
          <div style={{ overflowX: "auto" }}>
            <table className="stockcy-table" style={{ fontSize: "0.8rem" }}>
              <thead>
                <tr>
                  <th>종목</th>
                  <th style={{ textAlign: "right" }}>수량</th>
                  <th style={{ textAlign: "right" }}>매수가</th>
                  <th style={{ textAlign: "right" }}>매도가</th>
                  <th style={{ textAlign: "right" }}>수익금</th>
                  <th style={{ textAlign: "right" }}>수익률</th>
                  <th>매수 근거</th>
                  <th>매도 사유</th>
                  <th>기간</th>
                </tr>
              </thead>
              <tbody>
                {trades.map((t: any, idx: number) => {
                  const pct = Number(t.profit_pct ?? 0);
                  const color = pct >= 0 ? cUp : cDn;
                  const profit = Number(t.profit ?? 0);
                  return (
                    <tr key={idx}>
                      <td><strong>{t.name}</strong><div style={{ fontSize: "0.68rem", color: "var(--color-muted)" }}>{t.ticker}</div></td>
                      <td style={{ textAlign: "right" }}>{Number(t.quantity).toLocaleString()}주</td>
                      <td style={{ textAlign: "right" }}>{sym(t.ticker)}{num(t.buy_price, t.ticker)}</td>
                      <td style={{ textAlign: "right" }}>{sym(t.ticker)}{num(t.sell_price, t.ticker)}</td>
                      <td style={{ textAlign: "right", color, fontWeight: 700 }}>
                        {profit >= 0 ? "+" : "-"}{sym(t.ticker)}{num(Math.abs(profit), t.ticker)}
                      </td>
                      <td style={{ textAlign: "right", color, fontWeight: 700 }}>{pct >= 0 ? "+" : ""}{pct.toFixed(2)}%</td>
                      <td style={{ maxWidth: "200px" }}>
                        <div style={{ fontSize: "0.76rem", whiteSpace: "pre-wrap", lineHeight: 1.4 }}>
                          {t.ctx?.note || <span style={{ color: "var(--color-subtle)" }}>기록 이전 매수</span>}
                        </div>
                        {ctxChips(t.ctx)}
                      </td>
                      <td style={{ maxWidth: "180px", fontSize: "0.76rem" }}>{t.learning_point || "—"}</td>
                      <td style={{ fontSize: "0.72rem", color: "var(--color-muted)", whiteSpace: "nowrap" }}>
                        {dt(t.buy_date)}<br />→ {dt(t.sell_date)}<br />({heldFor(t.buy_date, t.sell_date)})
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
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
        <div style={{ flex: "1.4 1 640px", minWidth: "420px", maxWidth: "1100px", position: "sticky", top: "12px", maxHeight: "calc(100vh - 24px)", overflowY: "auto" }}>
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
