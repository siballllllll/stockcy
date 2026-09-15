"use client";
import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import dynamic from "next/dynamic";
import useSWR from "swr";
import { MarkdownLite } from "@/components/ui/MarkdownLite";
import { ScenarioTrackingPanel } from "@/app/scenarios/page";
import { useAuth } from "@/lib/auth-context";
import { api } from "@/lib/api";

// AI 에이전트 대시보드(구 상단 탭)를 리그 우측 패널로 임베드 — 무거워서 지연 로드
const AgentDashboard = dynamic(() => import("@/app/agent/page"), { ssr: false });

const B = "/backend";
const fetcher = (url: string) => fetch(url).then((r) => (r.ok ? r.json() : null));

const wrColor = (v: number | null | undefined) =>
  v == null ? "var(--color-muted)" : v >= 60 ? "#34d399" : v >= 45 ? "#fbbf24" : "#f87171";
const pct = (v: number | null | undefined) => (v == null ? "—" : `${v}%`);
const ret = (v: number | null | undefined) => (v == null ? "—" : `${v >= 0 ? "+" : ""}${v}%`);

// ── 내가 분석한 종목 (v3.182.0) ────────────────────────────────────────────
// [왜] 이력은 analysis_history에 쌓이는데 종목별 조회밖에 없어서, "내가 뭘 분석했었지"를
// 보려면 종목을 하나씩 검색해봐야 했다. 사후 수익률(d1/d3/d7)까지 같이 보여주면
// '그때 이 판단이 맞았나'를 한 줄에서 확인할 수 있다.
type AnalysisRow = {
  id: number; at: string; market: string | null; ticker: string; name: string;
  price_at: number | null; rating: string; long_rating: string; view_pct: string;
  buy_target: string; d1: number | null; d3: number | null; d7: number | null; checked: boolean;
};

function MyAnalysisHistory() {
  const router = useRouter();
  const [onlyKR, setOnlyKR] = useState<"all" | "KR" | "US">("all");
  const [ratingF, setRatingF] = useState<"all" | "추천" | "비추천">("all");
  // [왜] 분석을 많이 할수록 표가 그만큼 길어져 페이지가 다시 늘어난다(탭으로 나눈 의미가 없어진다).
  // 그래서 ① 기본을 '종목별'로 두어 **줄 수가 종목 수만큼으로 고정**되고
  //        ② 시간순으로 볼 때는 표 안에서만 스크롤되게 높이를 묶는다.
  const [mode, setMode] = useState<"stock" | "time">("stock");
  // 기간 선택. '전체'는 100년으로 보낸다(서버가 36500일로 묶는다).
  const [days, setDays] = useState<number>(90);
  const { data } = useSWR<{ items: AnalysisRow[]; total: number; limit: number }>(
    `my-analyses-${days}`,            // ⚠️ 기간을 키에 넣어야 바꿀 때 다시 불러온다
    () => api.ai.recentAnalyses(days, 300),
    { refreshInterval: 300000 }
  );
  const all = data?.items ?? [];
  // 서버가 limit에 잘랐는지 — 잘렸으면 화면이 '전부'인 척하면 안 된다.
  const truncated = !!data && data.total > all.length;
  // ⚠️ "중간추천"도 문자열에 '추천'을 담고 있다. 추천계열 필터는 비추천만 걷어내는 것이고,
  //    라벨도 '추천'이 아니라 '추천계열'이라고 적어 오해를 막는다.
  const rows = useMemo(() => all.filter(r => {
    if (onlyKR !== "all" && (r.market || "KR") !== onlyKR) return false;
    const isNeg = r.rating.includes("비추천");
    if (ratingF === "추천" && isNeg) return false;
    if (ratingF === "추천" && !r.rating.includes("추천")) return false;
    if (ratingF === "비추천" && !isNeg) return false;
    return true;
  }), [all, onlyKR, ratingF]);

  // 같은 종목을 여러 번 분석했으면 몇 번째인지 보여준다(중복이 아니라 재분석이다).
  const counts = useMemo(() => {
    const c: Record<string, number> = {};
    for (const r of all) c[r.ticker] = (c[r.ticker] || 0) + 1;
    return c;
  }, [all]);

  // 종목별 묶음 — 종목당 1행. rows는 이미 최신순이므로 처음 만난 것이 최신 분석이다.
  // 분석을 몇 번 하든 줄 수가 종목 수를 넘지 않는다.
  const grouped = useMemo(() => {
    const seen = new Map<string, { latest: AnalysisRow; n: number; best: number | null; worst: number | null }>();
    for (const r of rows) {
      const g = seen.get(r.ticker);
      const d7 = r.d7;
      if (!g) {
        seen.set(r.ticker, { latest: r, n: 1, best: d7, worst: d7 });
      } else {
        g.n += 1;
        if (d7 != null) {
          g.best = g.best == null ? d7 : Math.max(g.best, d7);
          g.worst = g.worst == null ? d7 : Math.min(g.worst, d7);
        }
      }
    }
    return [...seen.values()];
  }, [rows]);

  const pctCell = (v: number | null) =>
    v == null ? <span style={{ color: "var(--color-subtle)" }}>—</span>
      : <span style={{ color: v >= 0 ? "#ff4b4b" : "#3b82f6", fontWeight: 700 }}>
          {v >= 0 ? "+" : ""}{v.toFixed(2)}%
        </span>;
  const ratingColor = (r: string) =>
    r.includes("비추천") ? "#ff4b4b" : r.includes("중간") ? "#ffd600" : r.includes("추천") ? "#00c853" : "var(--color-muted)";
  const btn = (on: boolean): React.CSSProperties => ({
    fontSize: "0.68rem", fontWeight: 700, padding: "3px 9px", borderRadius: "99px", cursor: "pointer",
    border: `1px solid ${on ? "var(--color-accent)" : "var(--color-border)"}`,
    background: on ? "rgba(99,102,241,0.15)" : "transparent",
    color: on ? "var(--color-text)" : "var(--color-muted)",
  });

  return (
    <div className="stockcy-card" style={{ padding: "0.9rem 1.1rem" }}>
      <div style={{ display: "flex", flexWrap: "wrap", gap: "8px", alignItems: "center", marginBottom: "8px" }}>
        <div style={{ fontWeight: 800, fontSize: "0.95rem" }}>🔎 내가 분석한 종목</div>
        <span style={{ fontSize: "0.7rem", color: "var(--color-muted)" }}>
          {rows.length}건{mode === "stock" && ` · ${grouped.length}종목`}
        </span>
        <div style={{ marginLeft: "auto", display: "flex", gap: "5px", flexWrap: "wrap" }}>
          {([[30, "1개월"], [90, "3개월"], [365, "1년"], [36500, "전체"]] as const).map(([d, l]) =>
            <button key={d} style={btn(days === d)} onClick={() => setDays(d)}>{l}</button>)}
          <span style={{ width: "6px" }} />
          {(["stock", "time"] as const).map(v =>
            <button key={v} style={btn(mode === v)} onClick={() => setMode(v)}
                    title={v === "stock" ? "종목당 한 줄 — 분석을 몇 번 하든 길이가 안 늘어난다"
                                         : "분석한 순서대로 — 표 안에서만 스크롤된다"}>
              {v === "stock" ? "종목별" : "시간순"}
            </button>)}
          {(["all", "KR", "US"] as const).map(v =>
            <button key={v} style={btn(onlyKR === v)} onClick={() => setOnlyKR(v)}>
              {v === "all" ? "전체" : v === "KR" ? "국내" : "미국"}
            </button>)}
          {(["all", "추천", "비추천"] as const).map(v =>
            <button key={v} style={btn(ratingF === v)} onClick={() => setRatingF(v)}>
              {v === "all" ? "등급 전체" : v === "추천" ? "추천계열" : "비추천"}
            </button>)}
        </div>
      </div>

      {rows.length === 0 ? (
        <div style={{ fontSize: "0.78rem", color: "var(--color-muted)", padding: "10px 0" }}>
          분석 이력이 없습니다. 종목검색에서 AI 분석을 돌리면 여기에 쌓입니다.
        </div>
      ) : mode === "stock" ? (
        /* 종목별 — 종목당 1행. 분석을 몇 번 하든 줄 수가 종목 수를 넘지 않는다. */
        <div style={{ overflowX: "auto" }}>
          <table style={{ borderCollapse: "collapse", width: "100%", minWidth: "620px", fontSize: "0.72rem" }}>
            <thead>
              <tr style={{ color: "var(--color-muted)", textAlign: "right" }}>
                <th style={{ textAlign: "left", padding: "5px 8px 5px 0" }}>종목</th>
                <th style={{ padding: "5px 8px" }}>분석</th>
                <th style={{ textAlign: "left", padding: "5px 8px" }}>최근 등급</th>
                <th style={{ textAlign: "left", padding: "5px 8px" }}>최근 분석</th>
                <th style={{ padding: "5px 8px" }}>최근 d7</th>
                <th style={{ padding: "5px 0 5px 8px" }}>d7 최고/최저</th>
              </tr>
            </thead>
            <tbody>
              {grouped.map(g => {
                const r = g.latest;
                const isKR = (r.market || "KR") === "KR";
                return (
                  <tr key={r.ticker}
                      onClick={() => router.push(`/search?q=${encodeURIComponent(r.ticker)}&market=${isKR ? "KR" : "US"}`)}
                      title="클릭하면 종목검색으로 이동"
                      style={{ borderTop: "1px solid var(--color-border)", cursor: "pointer" }}>
                    <td style={{ padding: "6px 8px 6px 0", whiteSpace: "nowrap" }}>
                      <b>{r.name}</b>
                      <span style={{ color: "var(--color-subtle)" }}> {r.ticker}</span>
                      <span style={{ color: "var(--color-subtle)" }}> {isKR ? "🇰🇷" : "🇺🇸"}</span>
                    </td>
                    <td style={{ padding: "6px 8px", textAlign: "right", fontWeight: 700 }}>{g.n}회</td>
                    <td style={{ padding: "6px 8px", color: ratingColor(r.rating), fontWeight: 700, whiteSpace: "nowrap" }}>
                      {r.rating || "—"}
                    </td>
                    <td style={{ padding: "6px 8px", color: "var(--color-muted)", whiteSpace: "nowrap" }}>
                      {r.at.slice(2, 16)}
                    </td>
                    <td style={{ padding: "6px 8px", textAlign: "right" }}>{pctCell(r.d7)}</td>
                    <td style={{ padding: "6px 0 6px 8px", textAlign: "right", whiteSpace: "nowrap" }}>
                      {g.n > 1 && (g.best != null || g.worst != null)
                        ? <>{pctCell(g.best)} <span style={{ color: "var(--color-subtle)" }}>/</span> {pctCell(g.worst)}</>
                        : <span style={{ color: "var(--color-subtle)" }}>—</span>}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      ) : (
        /* 시간순 — 표 안에서만 스크롤한다. 건수가 늘어도 패널 높이는 그대로다. */
        <div style={{ overflowX: "auto", maxHeight: "360px", overflowY: "auto" }}>
          <table style={{ borderCollapse: "collapse", width: "100%", minWidth: "640px", fontSize: "0.72rem" }}>
            <thead style={{ position: "sticky", top: 0, background: "var(--color-surface)", zIndex: 1 }}>
              <tr style={{ color: "var(--color-muted)", textAlign: "right" }}>
                <th style={{ textAlign: "left", padding: "5px 8px 5px 0" }}>분석일시</th>
                <th style={{ textAlign: "left", padding: "5px 8px" }}>종목</th>
                <th style={{ textAlign: "left", padding: "5px 8px" }}>등급</th>
                <th style={{ textAlign: "left", padding: "5px 8px" }}>중장기</th>
                <th style={{ padding: "5px 8px" }}>당시가</th>
                <th style={{ padding: "5px 8px" }}>d1</th>
                <th style={{ padding: "5px 8px" }}>d3</th>
                <th style={{ padding: "5px 0 5px 8px" }}>d7</th>
              </tr>
            </thead>
            <tbody>
              {rows.map(r => {
                const isKR = (r.market || "KR") === "KR";
                return (
                  <tr key={r.id}
                      onClick={() => router.push(`/search?q=${encodeURIComponent(r.ticker)}&market=${isKR ? "KR" : "US"}`)}
                      title="클릭하면 종목검색으로 이동"
                      style={{ borderTop: "1px solid var(--color-border)", cursor: "pointer" }}>
                    <td style={{ padding: "6px 8px 6px 0", whiteSpace: "nowrap", color: "var(--color-muted)" }}>
                      {r.at.slice(2, 16)}
                    </td>
                    <td style={{ padding: "6px 8px", whiteSpace: "nowrap" }}>
                      <b>{r.name}</b>
                      <span style={{ color: "var(--color-subtle)" }}> {r.ticker}</span>
                      {counts[r.ticker] > 1 && (
                        <span title="이 종목을 여러 번 분석했습니다"
                              style={{ marginLeft: "5px", fontSize: "0.6rem", color: "var(--color-subtle)" }}>
                          ×{counts[r.ticker]}
                        </span>
                      )}
                    </td>
                    <td style={{ padding: "6px 8px", color: ratingColor(r.rating), fontWeight: 700, whiteSpace: "nowrap" }}>
                      {r.rating || "—"}
                    </td>
                    <td style={{ padding: "6px 8px", color: "var(--color-muted)", whiteSpace: "nowrap" }}>
                      {r.long_rating || "—"}
                    </td>
                    <td style={{ padding: "6px 8px", textAlign: "right", whiteSpace: "nowrap" }}>
                      {r.price_at != null
                        ? (isKR ? `₩${Math.round(r.price_at).toLocaleString()}` : `$${r.price_at.toFixed(2)}`)
                        : "—"}
                    </td>
                    <td style={{ padding: "6px 8px", textAlign: "right" }}>{pctCell(r.d1)}</td>
                    <td style={{ padding: "6px 8px", textAlign: "right" }}>{pctCell(r.d3)}</td>
                    <td style={{ padding: "6px 0 6px 8px", textAlign: "right" }}>{pctCell(r.d7)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
      {truncated && (
        <div style={{ fontSize: "0.66rem", color: "var(--color-warning)", marginTop: "6px" }}>
          ⚠️ 이 기간에 {data!.total}건이 있는데 최근 {all.length}건만 불러왔습니다.
          기간을 좁히면 그 구간은 전부 보입니다.
        </div>
      )}
      <div style={{ fontSize: "0.64rem", color: "var(--color-subtle)", marginTop: "6px", lineHeight: 1.6 }}>
        d1·d3·d7은 분석일 종가 대비 1·3·7거래일 뒤 수익률입니다. 아직 그날이 안 지났으면 비어 있습니다.
        {mode === "stock"
          ? " 종목별 보기는 종목당 한 줄이라, 분석을 많이 해도 목록이 길어지지 않습니다. 'd7 최고/최저'는 그 종목을 여러 번 분석했을 때 결과가 얼마나 갈렸는지입니다."
          : " 시간순 보기는 표 안에서만 스크롤됩니다. 같은 종목이 여러 번 보이면 중복이 아니라 그만큼 다시 분석한 것입니다(×N 표시)."}
      </div>
    </div>
  );
}


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

// ── 성과·기록 페이지 (v3.183.0 — 탭 구조) ──────────────────────────────────
// [왜] 패널 7개가 세로로 쌓여 페이지가 끝없이 길었다. 성격이 다른 것들이라
// (성적 / 내 기록 / 자산 / AI 상태) 한 화면에 다 둘 이유가 없었다.
// 섀도우 리그 행을 누르면 뜨는 우측 상세 패널은 그대로 두되, '성적' 탭에서만 띄운다.
const PERF_TABS = [
  { id: "score",  label: "🏆 성적",    desc: "엔진별 성과와 섀도우 리그" },
  { id: "record", label: "🔎 내 기록", desc: "내가 분석한 종목과 그날의 시장" },
  { id: "equity", label: "💰 자산",    desc: "자산 곡선" },
  { id: "ai",     label: "🤖 AI 상태", desc: "ML 모델과 시나리오 적중률" },
] as const;
type PerfTab = (typeof PERF_TABS)[number]["id"];
const PERF_TAB_KEY = "stockcy.perf.tab";

export default function PerformancePage() {
  // 리그 행 클릭 → 우측 상세 패널 토글 (같은 행 재클릭 시 닫힘)
  const [selOwner, setSelOwner] = useState<string | null>(null);
  const toggleOwner = (o: string) => setSelOwner((cur) => (cur === o ? null : o));
  const [tab, setTab] = useState<PerfTab>("score");

  // 보던 탭을 기억한다 — 새로고침할 때마다 처음으로 돌아가면 성가시다.
  // (localStorage는 브라우저가 막아둘 수 있어 실패해도 조용히 넘어간다)
  useEffect(() => {
    try {
      const saved = localStorage.getItem(PERF_TAB_KEY) as PerfTab | null;
      if (saved && PERF_TABS.some(t => t.id === saved)) setTab(saved);
    } catch { /* 저장소 접근 불가 — 기본 탭으로 */ }
  }, []);
  const pickTab = (t: PerfTab) => {
    setTab(t);
    try { localStorage.setItem(PERF_TAB_KEY, t); } catch { /* 무시 */ }
  };

  const cur = PERF_TABS.find(t => t.id === tab) ?? PERF_TABS[0];
  // 상세 패널은 '성적' 탭에서만. 다른 탭으로 옮겼는데 옆에 리그 상세가 남아 있으면 뜬금없다.
  const showDetail = !!selOwner && tab === "score";

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
      <div>
        <h1 style={{ fontSize: "1.5rem", fontWeight: 800, margin: 0 }}>📊 성과 · 기록</h1>
        <div style={{ fontSize: "0.82rem", color: "var(--color-muted)", marginTop: "4px" }}>
          이 시스템이 실제로 맞고 있는지, 그때 시장을 어떻게 봤는지, 내 자산이 어떻게 변했는지.
        </div>
      </div>

      <div style={{ display: "flex", gap: "6px", flexWrap: "wrap", borderBottom: "1px solid var(--color-border)", paddingBottom: "10px" }}>
        {PERF_TABS.map(t => (
          <button key={t.id} onClick={() => pickTab(t.id)} title={t.desc}
            style={{
              fontSize: "0.82rem", fontWeight: 700, padding: "6px 14px", borderRadius: "8px", cursor: "pointer",
              border: `1px solid ${tab === t.id ? "rgba(255,255,255,0.2)" : "transparent"}`,
              background: tab === t.id ? "rgba(255,255,255,0.1)" : "transparent",
              color: tab === t.id ? "var(--color-text)" : "var(--color-muted)",
            }}>
            {t.label}
          </button>
        ))}
        <span style={{ marginLeft: "auto", alignSelf: "center", fontSize: "0.7rem", color: "var(--color-subtle)" }}>
          {cur.desc}
        </span>
      </div>

      <div style={{ display: "flex", gap: "16px", alignItems: "flex-start", flexWrap: "wrap" }}>
        <div style={{ display: "flex", flexDirection: "column", gap: "16px", maxWidth: "1100px", flex: "1 1 620px", minWidth: 0 }}>
          {tab === "score" && (
            <>
              <EngineScoreboard />
              <ShadowLeaguePanel selected={selOwner} onSelect={toggleOwner} />
            </>
          )}
          {tab === "record" && (
            <>
              <MyAnalysisHistory />
              <MarketLogArchive />
            </>
          )}
          {tab === "equity" && <EquityCurve />}
          {tab === "ai" && (
            <>
              <MlStatusPanel />
              {/* 시나리오 적중률·추적 종목 상세 (시나리오 페이지에서 이동) */}
              <ScenarioTrackingPanel />
            </>
          )}
        </div>

        {showDetail && selOwner && (
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
    </div>
  );
}
