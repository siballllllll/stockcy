"use client";
import { useState, useEffect, useRef, useMemo } from "react";
import { useRouter } from "next/navigation";
import useSWR from "swr";
import { Globe, TrendingUp, AlertTriangle, DollarSign, Loader2, ChevronDown, ChevronUp, RefreshCw, X } from "lucide-react";
import dynamic from "next/dynamic";
import { api } from "@/lib/api";
import { useAnalysisReady } from "@/lib/analysis-ready-context";

// Next.js 프록시 우회 — 프록시가 큰 done JSON을 버퍼링해서 결과가 안 뜨는 문제 방지
const BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";

// ── 타입 정의 ──────────────────────────────────────────────────────────────────
interface StockEntry {
  name: string;
  ticker: string;
  reason: string;
  valuation_note?: string;
  signal: string;
  signal_reason: string;
  buy_target?: string;
  sell_target?: string;
  stop_loss?: string;
}

interface ThemeStock {
  name: string;
  ticker: string;
  type: string;
  historical_pattern: string;
  reason: string;
  signal?: string;
  signal_reason?: string;
}

interface Scenario {
  label: string;
  title: string;
  probability_pct: number;
  market_direction: string;
  trigger: string;
  economic_analysis: string;
  rising_stocks: StockEntry[];
  falling_stocks: StockEntry[];
  theme_stocks: ThemeStock[];
  short_strategy: string;
  long_strategy: string;
}

interface Issue {
  issue_no?: number;
  title: string;
  summary: string;
  urgency?: string;
  category?: string;
  scenarios: Scenario[];
}

interface DetailResult {
  deep_analysis: string;
  historical_precedent: string;
  key_risks: string[];
  short_detail: {
    entry: string;
    exit: string;
    timing: string;
    stocks: Array<{ name: string; ticker: string; entry_point: string; target: string; stop: string; note: string }>;
  };
  long_detail: {
    thesis: string;
    hold_period: string;
    position_sizing: string;
    stocks: Array<{ name: string; ticker: string; reason: string; catalyst: string }>;
  };
}

// ── 헬퍼 함수 ─────────────────────────────────────────────────────────────────
function isKrTicker(ticker: string) {
  return /^\d{6}$/.test(ticker);
}

function signalColor(signal: string): string {
  if (signal === "매우 강력 추천") return "#00c853";
  if (signal === "추천")           return "#69f0ae";
  if (signal === "중간추천")       return "#ffd740";
  if (signal === "비추천")         return "#ff7043";
  if (signal === "매우 비추천")    return "#f44336";
  return "var(--color-muted)";
}

async function readSSE(
  url: string,
  method: "GET" | "POST" = "GET",
  body?: object,
  onMessage?: (msg: string) => void,
  signal?: AbortSignal
): Promise<any> {
  const opts: RequestInit = {
    method,
    headers: { "Content-Type": "application/json" },
    signal,
  };
  if (body) opts.body = JSON.stringify(body);
  const res = await fetch(`${BASE_URL}${url}`, opts);
  if (!res.body) throw new Error("No SSE body");
  const reader = res.body.getReader();
  const dec = new TextDecoder();
  let buf = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += dec.decode(value, { stream: true });
    const parts = buf.split("\n\n");
    buf = parts.pop() ?? "";
    for (const part of parts) {
      const line = part.trim();
      if (!line.startsWith("data:")) continue;
      try {
        const d = JSON.parse(line.slice(5).trim());
        if (d.status === "running" && onMessage) onMessage(d.message ?? "분석 중...");
        if (d.status === "done") return d.result;
        if (d.status === "error") throw new Error(d.message ?? "SSE 오류");
      } catch (e) {
        if (e instanceof SyntaxError) continue;
        throw e;
      }
    }
  }
  return null;
}

// ── 시그널 뱃지 ────────────────────────────────────────────────────────────────
function SignalBadge({ signal }: { signal: string }) {
  return (
    <span style={{
      display: "inline-block",
      padding: "1px 7px",
      borderRadius: "10px",
      fontSize: "0.7rem",
      fontWeight: 700,
      background: `${signalColor(signal)}22`,
      border: `1px solid ${signalColor(signal)}`,
      color: signalColor(signal),
      flexShrink: 0,
    }}>
      {signal}
    </span>
  );
}

// ── 시장 뱃지 ─────────────────────────────────────────────────────────────────
function MarketBadge({ ticker }: { ticker: string }) {
  const kr = isKrTicker(ticker);
  return (
    <span style={{
      display: "inline-block",
      padding: "1px 6px",
      borderRadius: "4px",
      fontSize: "0.68rem",
      fontWeight: 700,
      background: kr ? "rgba(0,120,255,0.15)" : "rgba(50,200,100,0.15)",
      border: kr ? "1px solid rgba(0,120,255,0.4)" : "1px solid rgba(50,200,100,0.4)",
      color: kr ? "#60a5fa" : "var(--color-success)",
    }}>
      {kr ? "🇰🇷 KR" : "🇺🇸 US"}
    </span>
  );
}

// ── 종목 카드 행 (상승/하락) ───────────────────────────────────────────────────
type PriceEntry = { price: number; change_pct: number };

function StockRow({ stock, priceEntry, onClick }: {
  stock: StockEntry;
  priceEntry?: PriceEntry | null;
  onClick: () => void;
}) {
  const isKr = isKrTicker(stock.ticker);
  const up   = (priceEntry?.change_pct ?? 0) >= 0;
  const hasTargets = stock.buy_target || stock.sell_target || stock.stop_loss;

  return (
    <div
      onClick={onClick}
      style={{
        display: "flex", flexDirection: "column", gap: "5px",
        padding: "10px 12px",
        background: "rgba(0,0,0,0.2)",
        borderRadius: "6px",
        border: "1px solid var(--color-border)",
        cursor: "pointer",
        transition: "border-color 0.15s",
      }}
      onMouseEnter={e => (e.currentTarget.style.borderColor = "var(--color-accent)")}
      onMouseLeave={e => (e.currentTarget.style.borderColor = "var(--color-border)")}
    >
      {/* 종목명 + 배지 + 현재가 */}
      <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: "6px" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "5px", flexWrap: "wrap", flex: 1 }}>
          <span style={{ fontWeight: 700, fontSize: "0.88rem" }}>{stock.name}</span>
          <span style={{ fontSize: "0.7rem", color: "var(--color-muted)" }}>({stock.ticker})</span>
          <MarketBadge ticker={stock.ticker} />
          {stock.signal && <SignalBadge signal={stock.signal} />}
        </div>
        {/* 현재가 */}
        {priceEntry && priceEntry.price > 0 && (
          <div style={{ textAlign: "right", flexShrink: 0, minWidth: "70px" }}>
            <div style={{ fontWeight: 700, fontSize: "0.8rem", color: "var(--color-text)" }}>
              {isKr ? `₩${priceEntry.price.toLocaleString()}` : `$${priceEntry.price.toFixed(2)}`}
            </div>
            <div style={{ fontSize: "0.72rem", fontWeight: 700, color: up ? "var(--color-danger)" : "var(--color-primary)" }}>
              {up ? "▲" : "▼"} {Math.abs(priceEntry.change_pct).toFixed(2)}%
            </div>
          </div>
        )}
      </div>

      {stock.signal_reason && (
        <div style={{ fontSize: "0.76rem", color: "var(--color-text)", fontWeight: 600 }}>{stock.signal_reason}</div>
      )}
      <div style={{ fontSize: "0.74rem", color: "var(--color-muted)", lineHeight: 1.4 }}>{stock.reason}</div>
      {stock.valuation_note && (
        <div style={{ fontSize: "0.71rem", color: "var(--color-muted)", fontStyle: "italic" }}>{stock.valuation_note}</div>
      )}

      {/* 매수타점 / 목표가 / 손절선 */}
      {hasTargets && (
        <div style={{
          display: "flex", gap: "8px", flexWrap: "wrap", marginTop: "2px",
          background: "rgba(0,0,0,0.25)", borderRadius: "5px", padding: "6px 8px",
          fontSize: "0.72rem",
        }}
          onClick={e => e.stopPropagation()}
        >
          {stock.buy_target && (
            <span>💰 매수 <strong style={{ color: "#69f0ae" }}>{stock.buy_target}</strong></span>
          )}
          {stock.sell_target && (
            <span>🎯 목표 <strong style={{ color: "#ff6b6b" }}>{stock.sell_target}</strong></span>
          )}
          {stock.stop_loss && (
            <span>🛡️ 손절 <strong style={{ color: "#60a5fa" }}>{stock.stop_loss}</strong></span>
          )}
        </div>
      )}
    </div>
  );
}

// ── 테마주 카드 ───────────────────────────────────────────────────────────────
function ThemeStockRow({ stock, priceEntry, onClick }: {
  stock: ThemeStock;
  priceEntry?: PriceEntry | null;
  onClick: () => void;
}) {
  const isKr = isKrTicker(stock.ticker);
  const up   = (priceEntry?.change_pct ?? 0) >= 0;

  return (
    <div
      onClick={onClick}
      style={{
        display: "flex", flexDirection: "column", gap: "5px",
        padding: "10px 12px",
        background: "rgba(0,0,0,0.2)",
        borderRadius: "6px",
        border: "1px solid var(--color-border)",
        cursor: "pointer",
        transition: "border-color 0.15s",
      }}
      onMouseEnter={e => (e.currentTarget.style.borderColor = "var(--color-accent)")}
      onMouseLeave={e => (e.currentTarget.style.borderColor = "var(--color-border)")}
    >
      <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: "6px" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "5px", flexWrap: "wrap", flex: 1 }}>
          <span style={{ fontWeight: 700, fontSize: "0.88rem" }}>{stock.name}</span>
          <span style={{ fontSize: "0.7rem", color: "var(--color-muted)" }}>({stock.ticker})</span>
          <MarketBadge ticker={stock.ticker} />
          <span style={{
            display: "inline-block", padding: "1px 7px", borderRadius: "10px", fontSize: "0.7rem", fontWeight: 700,
            background: stock.type === "직접관련주" ? "rgba(255,180,50,0.15)" : "rgba(180,100,255,0.15)",
            border: stock.type === "직접관련주" ? "1px solid var(--color-warning)" : "1px solid rgba(180,100,255,0.6)",
            color: stock.type === "직접관련주" ? "var(--color-warning)" : "#c084fc",
          }}>
            {stock.type}
          </span>
          {stock.signal && <SignalBadge signal={stock.signal} />}
        </div>
        {priceEntry && priceEntry.price > 0 && (
          <div style={{ textAlign: "right", flexShrink: 0, minWidth: "70px" }}>
            <div style={{ fontWeight: 700, fontSize: "0.8rem", color: "var(--color-text)" }}>
              {isKr ? `₩${priceEntry.price.toLocaleString()}` : `$${priceEntry.price.toFixed(2)}`}
            </div>
            <div style={{ fontSize: "0.72rem", fontWeight: 700, color: up ? "var(--color-danger)" : "var(--color-primary)" }}>
              {up ? "▲" : "▼"} {Math.abs(priceEntry.change_pct).toFixed(2)}%
            </div>
          </div>
        )}
      </div>
      {stock.signal_reason && (
        <div style={{ fontSize: "0.74rem", color: "var(--color-text)", fontWeight: 600 }}>{stock.signal_reason}</div>
      )}
      {stock.historical_pattern && (
        <div style={{ fontSize: "0.74rem", color: "var(--color-accent)", fontWeight: 600 }}>
          과거 패턴: {stock.historical_pattern}
        </div>
      )}
      <div style={{ fontSize: "0.74rem", color: "var(--color-muted)", lineHeight: 1.4 }}>{stock.reason}</div>
    </div>
  );
}

// ── 섹션 헤더 ─────────────────────────────────────────────────────────────────
function SectionHeader({ title, count }: { title: string; count?: number }) {
  return (
    <div style={{
      fontSize: "0.82rem", fontWeight: 800, color: "var(--color-muted)",
      padding: "6px 0 4px",
      borderBottom: "1px solid var(--color-border)",
      marginBottom: "8px",
      display: "flex", alignItems: "center", gap: "6px",
    }}>
      {title}
      {count !== undefined && (
        <span style={{ fontWeight: 600, color: "var(--color-muted)", fontSize: "0.75rem" }}>({count})</span>
      )}
    </div>
  );
}

// ── 전략 박스 ─────────────────────────────────────────────────────────────────
function StrategyBox({ label, text, color }: { label: string; text: string; color: string }) {
  return (
    <div style={{
      background: `${color}0d`,
      border: `1px solid ${color}44`,
      borderRadius: "6px",
      padding: "10px 12px",
      flex: 1,
    }}>
      <div style={{ fontSize: "0.75rem", fontWeight: 800, color, marginBottom: "6px" }}>{label}</div>
      <div style={{ fontSize: "0.82rem", color: "var(--color-text)", lineHeight: 1.5 }}>{text}</div>
    </div>
  );
}

// ── 상세 분석 패널 ────────────────────────────────────────────────────────────
function DetailPanel({ detail }: { detail: DetailResult }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
      {/* deep_analysis */}
      <div>
        <SectionHeader title="심층 분석" />
        <div style={{ fontSize: "0.85rem", color: "var(--color-text)", lineHeight: 1.7, whiteSpace: "pre-wrap" }}>
          {detail.deep_analysis}
        </div>
      </div>

      {/* historical_precedent */}
      {detail.historical_precedent && (
        <div>
          <SectionHeader title="역사적 선례" />
          <div style={{ fontSize: "0.85rem", color: "var(--color-muted)", lineHeight: 1.6, fontStyle: "italic" }}>
            {detail.historical_precedent}
          </div>
        </div>
      )}

      {/* key_risks */}
      {detail.key_risks?.length > 0 && (
        <div>
          <SectionHeader title="핵심 리스크" count={detail.key_risks.length} />
          <ul style={{ margin: 0, padding: "0 0 0 1.2rem" }}>
            {detail.key_risks.map((r, i) => (
              <li key={i} style={{ fontSize: "0.82rem", color: "var(--color-text)", lineHeight: 1.6, marginBottom: "2px" }}>{r}</li>
            ))}
          </ul>
        </div>
      )}

      {/* short_detail */}
      {detail.short_detail && (
        <div>
          <SectionHeader title="단타 상세 전략" />
          <div style={{ display: "flex", gap: "8px", flexWrap: "wrap", marginBottom: "10px" }}>
            {[
              { l: "진입", v: detail.short_detail.entry },
              { l: "청산", v: detail.short_detail.exit },
              { l: "타이밍", v: detail.short_detail.timing },
            ].map(({ l, v }) => v ? (
              <div key={l} style={{ background: "rgba(0,0,0,0.2)", border: "1px solid var(--color-border)", borderRadius: "6px", padding: "8px 12px", fontSize: "0.8rem" }}>
                <span style={{ color: "var(--color-muted)", fontWeight: 700 }}>{l}: </span>
                <span style={{ color: "var(--color-text)" }}>{v}</span>
              </div>
            ) : null)}
          </div>
          {detail.short_detail.stocks?.length > 0 && (
            <div style={{ overflowX: "auto" }}>
              <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.8rem" }}>
                <thead>
                  <tr style={{ borderBottom: "1px solid var(--color-border)", color: "var(--color-muted)" }}>
                    {["종목", "티커", "진입점", "목표가", "손절가", "메모"].map(h => (
                      <th key={h} style={{ padding: "6px 8px", textAlign: "left", fontWeight: 700 }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {detail.short_detail.stocks.map((s, i) => (
                    <tr key={i} style={{ borderBottom: "1px solid rgba(255,255,255,0.04)" }}>
                      <td style={{ padding: "6px 8px", fontWeight: 600 }}>{s.name}</td>
                      <td style={{ padding: "6px 8px", color: "var(--color-muted)" }}>{s.ticker}</td>
                      <td style={{ padding: "6px 8px" }}>{s.entry_point}</td>
                      <td style={{ padding: "6px 8px", color: "var(--color-success)" }}>{s.target}</td>
                      <td style={{ padding: "6px 8px", color: "var(--color-danger)" }}>{s.stop}</td>
                      <td style={{ padding: "6px 8px", color: "var(--color-muted)", fontSize: "0.75rem" }}>{s.note}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* long_detail */}
      {detail.long_detail && (
        <div>
          <SectionHeader title="장타 상세 전략" />
          <div style={{ display: "flex", gap: "8px", flexWrap: "wrap", marginBottom: "10px" }}>
            {[
              { l: "투자 논지", v: detail.long_detail.thesis },
              { l: "보유 기간", v: detail.long_detail.hold_period },
              { l: "포지션 사이징", v: detail.long_detail.position_sizing },
            ].map(({ l, v }) => v ? (
              <div key={l} style={{ background: "rgba(0,0,0,0.2)", border: "1px solid var(--color-border)", borderRadius: "6px", padding: "8px 12px", fontSize: "0.8rem", flex: 1, minWidth: "140px" }}>
                <span style={{ color: "var(--color-muted)", fontWeight: 700 }}>{l}: </span>
                <span style={{ color: "var(--color-text)" }}>{v}</span>
              </div>
            ) : null)}
          </div>
          {detail.long_detail.stocks?.length > 0 && (
            <div style={{ overflowX: "auto" }}>
              <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.8rem" }}>
                <thead>
                  <tr style={{ borderBottom: "1px solid var(--color-border)", color: "var(--color-muted)" }}>
                    {["종목", "티커", "분할매수 타점", "장기 목표가 (+30%)", "손절가 (-15%)", "보유 기간", "촉매 및 투자 근거"].map(h => (
                      <th key={h} style={{ padding: "6px 8px", textAlign: "left", fontWeight: 700 }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {detail.long_detail.stocks.map((s: any, i) => (
                    <tr key={i} style={{ borderBottom: "1px solid rgba(255,255,255,0.04)" }}>
                      <td style={{ padding: "6px 8px", fontWeight: 600 }}>{s.name}</td>
                      <td style={{ padding: "6px 8px", color: "var(--color-muted)" }}>{s.ticker}</td>
                      <td style={{ padding: "6px 8px", color: "#69f0ae" }}>{s.entry_point || "-"}</td>
                      <td style={{ padding: "6px 8px", color: "#ff6b6b" }}>{s.target || "-"}</td>
                      <td style={{ padding: "6px 8px", color: "#60a5fa" }}>{s.stop || "-"}</td>
                      <td style={{ padding: "6px 8px", color: "var(--color-text)", fontWeight: 600 }}>{s.hold_period || "-"}</td>
                      <td style={{ padding: "6px 8px", color: "var(--color-muted)", fontSize: "0.75rem" }}>
                        {s.catalyst && <strong style={{ color: "var(--color-accent)" }}>[촉매: {s.catalyst}] </strong>}
                        {s.reason || ""}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ── 시나리오 콘텐츠 ────────────────────────────────────────────────────────────
function ScenarioContent({ scenario, issueTitle }: { scenario: Scenario; issueTitle: string }) {
  const router = useRouter();
  const [detailStatus, setDetailStatus] = useState<"idle" | "loading" | "done" | "error">("idle");
  const [detailMsg, setDetailMsg] = useState("");
  const [detailResult, setDetailResult] = useState<DetailResult | null>(null);
  const [showDetail, setShowDetail] = useState(false);

  const krRising   = scenario.rising_stocks?.filter(s => isKrTicker(s.ticker))  ?? [];
  const usRising   = scenario.rising_stocks?.filter(s => !isKrTicker(s.ticker)) ?? [];
  const krFalling  = scenario.falling_stocks?.filter(s => isKrTicker(s.ticker)) ?? [];
  const usFalling  = scenario.falling_stocks?.filter(s => !isKrTicker(s.ticker))?? [];
  const themeStocks = scenario.theme_stocks ?? [];

  // ── 실시간 현재가 조회 ─────────────────────────────────────────────────────
  const allStocks = useMemo(() => [
    ...(scenario.rising_stocks ?? []),
    ...(scenario.falling_stocks ?? []),
    ...(scenario.theme_stocks ?? []),
  ], [scenario]);

  const krTickers = useMemo(() =>
    [...new Set(allStocks.map(s => s.ticker).filter(t => isKrTicker(t)))],
    [allStocks]
  );
  const usTickers = useMemo(() =>
    [...new Set(allStocks.map(s => s.ticker).filter(t => !isKrTicker(t)))],
    [allStocks]
  );

  const { data: krPrices } = useSWR(
    krTickers.length > 0 ? `sc-kr-prices-${krTickers.join(",")}` : null,
    async () => {
      const map: Record<string, PriceEntry> = {};
      await Promise.all(krTickers.map(async (code) => {
        try {
          const d = await api.kr.stockPrice(code) as any;
          if (d?.price) map[code] = { price: d.price, change_pct: d.change_pct ?? 0 };
        } catch {}
      }));
      return map;
    },
    { revalidateOnFocus: false }
  );

  const { data: usPrices } = useSWR(
    usTickers.length > 0 ? `sc-us-prices-${usTickers.join(",")}` : null,
    async () => {
      const arr = await api.us.stocks(usTickers) as any[];
      const map: Record<string, PriceEntry> = {};
      for (const s of (arr ?? [])) {
        const ticker = s["심볼"] ?? s.ticker ?? "";
        if (ticker) map[ticker] = { price: s["현재가($)"] ?? 0, change_pct: s["등락률(%)"] ?? 0 };
      }
      return map;
    },
    { revalidateOnFocus: false }
  );

  const priceMap: Record<string, PriceEntry> = { ...(krPrices ?? {}), ...(usPrices ?? {}) };

  const fetchDetail = async () => {
    setDetailStatus("loading");
    setDetailMsg("상세 분석 중...");
    setShowDetail(true);
    try {
      const result = await readSSE(
        "/api/ai/scenarios/detail",
        "POST",
        {
          issue_title: issueTitle,
          scenario_title: scenario.title,
          economic_analysis: scenario.economic_analysis,
          rising: scenario.rising_stocks ?? [],
          falling: scenario.falling_stocks ?? [],
        },
        (msg) => setDetailMsg(msg)
      );
      setDetailResult(result);
      setDetailStatus("done");
    } catch (e) {
      setDetailMsg(String(e));
      setDetailStatus("error");
    }
  };

  const navigate = (ticker: string) => {
    if (isKrTicker(ticker)) {
      router.push(`/search?q=${ticker}&market=KR`);
    } else {
      router.push(`/search?q=${ticker}&market=US`);
    }
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
      {/* 기본 정보 */}
      <div style={{ display: "flex", gap: "6px", flexWrap: "wrap", alignItems: "center" }}>
        <span style={{
          padding: "2px 10px", borderRadius: "10px", fontSize: "0.78rem", fontWeight: 700,
          background: scenario.market_direction === "강세" ? "rgba(255,60,60,0.15)" :
                      scenario.market_direction === "약세" ? "rgba(0,120,255,0.15)" : "rgba(255,180,50,0.15)",
          border: `1px solid ${scenario.market_direction === "강세" ? "var(--color-danger)" :
                               scenario.market_direction === "약세" ? "var(--color-primary)" : "var(--color-warning)"}`,
          color: scenario.market_direction === "강세" ? "var(--color-danger)" :
                 scenario.market_direction === "약세" ? "var(--color-primary)" : "var(--color-warning)",
        }}>
          {scenario.market_direction}
        </span>
        <span style={{ fontSize: "0.82rem", color: "var(--color-muted)" }}>확률: <strong style={{ color: "var(--color-text)" }}>{scenario.probability_pct}%</strong></span>
      </div>

      {/* 현실화 조건 */}
      {scenario.trigger && (
        <div style={{ background: "rgba(0,0,0,0.3)", border: "1px solid var(--color-border)", borderRadius: "6px", padding: "10px 14px" }}>
          <div style={{ fontSize: "0.72rem", fontWeight: 800, color: "var(--color-muted)", marginBottom: "4px" }}>현실화 조건</div>
          <div style={{ fontSize: "0.85rem", color: "var(--color-text)", lineHeight: 1.5 }}>{scenario.trigger}</div>
        </div>
      )}

      {/* 경제 분석 */}
      {scenario.economic_analysis && (
        <div style={{ background: "rgba(0,0,0,0.2)", borderLeft: "3px solid var(--color-accent)", borderRadius: "0 6px 6px 0", padding: "10px 14px" }}>
          <div style={{ fontSize: "0.72rem", fontWeight: 800, color: "var(--color-muted)", marginBottom: "4px" }}>경제 분석</div>
          <div style={{ fontSize: "0.85rem", color: "var(--color-text)", lineHeight: 1.6 }}>{scenario.economic_analysis}</div>
        </div>
      )}

      {/* 전략 박스 */}
      <div style={{ display: "flex", gap: "8px", flexWrap: "wrap" }}>
        {scenario.short_strategy && <StrategyBox label="단타 전략" text={scenario.short_strategy} color="var(--color-warning)" />}
        {scenario.long_strategy  && <StrategyBox label="장타 전략" text={scenario.long_strategy}  color="var(--color-accent)" />}
      </div>

      {/* 상승 예상 종목 */}
      {(krRising.length > 0 || usRising.length > 0) && (
        <div>
          <SectionHeader title="🟢 상승 수혜주" count={(scenario.rising_stocks ?? []).length} />
          {krRising.length > 0 && (
            <div style={{ marginBottom: "8px" }}>
              <div style={{ fontSize: "0.72rem", color: "var(--color-muted)", fontWeight: 700, marginBottom: "4px" }}>🇰🇷 국내</div>
              <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
                {krRising.map((s, i) => (
                  <StockRow key={i} stock={s} priceEntry={priceMap[s.ticker]} onClick={() => navigate(s.ticker)} />
                ))}
              </div>
            </div>
          )}
          {usRising.length > 0 && (
            <div>
              <div style={{ fontSize: "0.72rem", color: "var(--color-muted)", fontWeight: 700, marginBottom: "4px" }}>🇺🇸 미국</div>
              <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
                {usRising.map((s, i) => (
                  <StockRow key={i} stock={s} priceEntry={priceMap[s.ticker]} onClick={() => navigate(s.ticker)} />
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* 하락 예상 종목 */}
      {(krFalling.length > 0 || usFalling.length > 0) && (
        <div>
          <SectionHeader title="🔴 하락 위험주" count={(scenario.falling_stocks ?? []).length} />
          {krFalling.length > 0 && (
            <div style={{ marginBottom: "8px" }}>
              <div style={{ fontSize: "0.72rem", color: "var(--color-muted)", fontWeight: 700, marginBottom: "4px" }}>🇰🇷 국내</div>
              <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
                {krFalling.map((s, i) => (
                  <StockRow key={i} stock={s} priceEntry={priceMap[s.ticker]} onClick={() => navigate(s.ticker)} />
                ))}
              </div>
            </div>
          )}
          {usFalling.length > 0 && (
            <div>
              <div style={{ fontSize: "0.72rem", color: "var(--color-muted)", fontWeight: 700, marginBottom: "4px" }}>🇺🇸 미국</div>
              <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
                {usFalling.map((s, i) => (
                  <StockRow key={i} stock={s} priceEntry={priceMap[s.ticker]} onClick={() => navigate(s.ticker)} />
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* 테마주 */}
      {themeStocks.length > 0 && (
        <div>
          <SectionHeader title="🔥 테마 연동주" count={themeStocks.length} />
          <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
            {themeStocks.map((s, i) => (
              <ThemeStockRow key={i} stock={s} priceEntry={priceMap[s.ticker]} onClick={() => navigate(s.ticker)} />
            ))}
          </div>
        </div>
      )}

      {/* 상세 분석 버튼 */}
      <div style={{ borderTop: "1px solid var(--color-border)", paddingTop: "1rem" }}>
        {detailStatus === "idle" && (
          <button
            className="stockcy-btn stockcy-btn-primary"
            style={{ width: "100%", padding: "10px", fontWeight: 700 }}
            onClick={fetchDetail}
          >
            상세 분석보기
          </button>
        )}
        {detailStatus === "loading" && (
          <div style={{ display: "flex", alignItems: "center", gap: "8px", justifyContent: "center", color: "var(--color-muted)", fontSize: "0.85rem", padding: "10px" }}>
            <Loader2 className="animate-spin" size={18} /> {detailMsg}
          </div>
        )}
        {(detailStatus === "done" || detailStatus === "error") && (
          <div>
            <button
              className="stockcy-btn stockcy-btn-secondary"
              style={{ width: "100%", padding: "8px", fontWeight: 600, display: "flex", alignItems: "center", justifyContent: "center", gap: "6px" }}
              onClick={() => setShowDetail(v => !v)}
            >
              {showDetail ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
              {showDetail ? "상세 분석 접기" : "상세 분석 펼치기"}
            </button>
            {showDetail && (
              <div style={{ marginTop: "1rem", background: "var(--color-surface)", border: "1px solid var(--color-border)", borderRadius: "8px", padding: "1rem" }}>
                {detailStatus === "error"
                  ? <div style={{ color: "var(--color-danger)", fontSize: "0.85rem" }}>{detailMsg}</div>
                  : detailResult && <DetailPanel detail={detailResult} />
                }
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

// ── 이슈 패널 ─────────────────────────────────────────────────────────────────
function IssuePanel({ issue }: { issue: Issue }) {
  const [scenarioIdx, setScenarioIdx] = useState(0);
  const scenarios = issue.scenarios ?? [];
  const activeScenario = scenarios[scenarioIdx];

  const urgencyColor = (u?: string) => {
    if (u === "긴급") return "var(--color-danger)";
    if (u === "보통") return "var(--color-warning)";
    return "var(--color-muted)";
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
      {/* 이슈 헤더 */}
      <div>
        <div style={{ display: "flex", gap: "6px", alignItems: "center", flexWrap: "wrap", marginBottom: "6px" }}>
          {issue.urgency && (
            <span style={{
              padding: "1px 8px", borderRadius: "10px", fontSize: "0.72rem", fontWeight: 800,
              background: `${urgencyColor(issue.urgency)}22`,
              border: `1px solid ${urgencyColor(issue.urgency)}`,
              color: urgencyColor(issue.urgency),
            }}>
              {issue.urgency}
            </span>
          )}
          {issue.category && (
            <span style={{
              padding: "1px 8px", borderRadius: "10px", fontSize: "0.72rem", fontWeight: 700,
              background: "rgba(255,255,255,0.06)",
              border: "1px solid var(--color-border)",
              color: "var(--color-muted)",
            }}>
              {issue.category}
            </span>
          )}
        </div>
        <h2 style={{ fontSize: "1.1rem", fontWeight: 800, margin: "0 0 8px 0", color: "var(--color-text)" }}>
          {issue.title}
        </h2>
        {issue.summary && (
          <div style={{ background: "rgba(255,60,60,0.08)", borderLeft: "3px solid var(--color-danger)", padding: "10px 14px", borderRadius: "0 6px 6px 0", fontSize: "0.9rem", color: "var(--color-text)", lineHeight: 1.6 }}>
            {issue.summary}
          </div>
        )}
      </div>

      {/* 시나리오 탭 */}
      {scenarios.length > 0 && (
        <div>
          <div style={{ display: "flex", gap: "6px", marginBottom: "1rem" }}>
            {scenarios.map((sc, idx) => (
              <button
                key={idx}
                onClick={() => setScenarioIdx(idx)}
                style={{
                  padding: "6px 14px", fontWeight: 700, fontSize: "0.85rem", borderRadius: "6px",
                  border: "1px solid",
                  borderColor: scenarioIdx === idx ? "var(--color-accent)" : "var(--color-border)",
                  background: scenarioIdx === idx ? "rgba(255,255,255,0.08)" : "transparent",
                  color: scenarioIdx === idx ? "var(--color-text)" : "var(--color-muted)",
                  cursor: "pointer",
                  transition: "0.15s",
                }}
              >
                시나리오 {sc.label}: {sc.title} ({sc.probability_pct}%)
              </button>
            ))}
          </div>
          {activeScenario && <ScenarioContent scenario={activeScenario} issueTitle={issue.title} />}
        </div>
      )}
    </div>
  );
}

// ── 지역 분류 헬퍼 ────────────────────────────────────────────────────────────
type RegionFilter = "전체" | "글로벌" | "국내" | "이머징마켓" | "커스텀";

function classifyIssueRegion(issue: Issue): "글로벌" | "국내" | "이머징마켓" | "mixed" {
  const cat = (issue.category ?? "").toLowerCase();
  if (cat.includes("암호화폐") || cat.includes("지정학") || cat.includes("이머징")) return "이머징마켓";
  let krCount = 0, usCount = 0;
  for (const sc of issue.scenarios ?? []) {
    for (const s of [...(sc.rising_stocks ?? []), ...(sc.falling_stocks ?? [])]) {
      if (isKrTicker(s.ticker)) krCount++; else usCount++;
    }
  }
  if (usCount > krCount) return "글로벌";
  if (krCount > usCount) return "국내";
  return "mixed";
}

// ── 메인 페이지 ───────────────────────────────────────────────────────────────
const SC_DATA_KEY = "stockcy_scenarios_data";
const SC_TS_KEY   = "stockcy_scenarios_ts";

function ScenariosPageInner() {
  const { setReady } = useAnalysisReady();

  const [mounted, setMounted] = useState(false);
  const [loading, setLoading]     = useState(false);
  const [statusMsg, setStatusMsg] = useState("AI 모델에 연결 중...");
  const [issues, setIssues]       = useState<Issue[]>([]);
  const [lastUpdated, setLastUpdated] = useState<string>("");
  const [issueIdx, setIssueIdx]   = useState(0);
  const [loadError, setLoadError] = useState("");
  const [regionFilter, setRegionFilter] = useState<RegionFilter>("전체");
  const [fetchTrigger, setFetchTrigger] = useState<number | null>(null);

  // 커스텀 이슈 (localStorage 영속)
  const CUSTOM_KEY   = "stockcy_custom_issues";
  const RECENT_KEY   = "stockcy_recent_searches";
  const [customKeyword, setCustomKeyword] = useState("");
  const [customLoading, setCustomLoading] = useState(false);
  const [customError, setCustomError]     = useState("");
  const [showRecent, setShowRecent]       = useState(false);

  const [customIssues, setCustomIssues] = useState<Array<Issue & { isCustom: true; keyword: string }>>([]);
  const [recentSearches, setRecentSearches] = useState<string[]>([]);

  // 마운트 직후 localStorage 안전 조회 (Hydration Mismatch 방지)
  useEffect(() => {
    setMounted(true);
    try {
      const savedIssues = localStorage.getItem(SC_DATA_KEY);
      if (savedIssues) {
        const parsed = JSON.parse(savedIssues);
        if (Array.isArray(parsed) && parsed.length > 0) {
          setIssues(parsed);
        } else {
          // 빈 배열 등 비정상 캐시 제거 (구버전 코드가 저장한 경우)
          localStorage.removeItem(SC_DATA_KEY);
          localStorage.removeItem(SC_TS_KEY);
        }
      }

      const savedTs = localStorage.getItem(SC_TS_KEY);
      if (savedTs) setLastUpdated(savedTs);

      const savedCustom = localStorage.getItem(CUSTOM_KEY);
      if (savedCustom) setCustomIssues(JSON.parse(savedCustom));

      const savedRecent = localStorage.getItem(RECENT_KEY);
      if (savedRecent) setRecentSearches(JSON.parse(savedRecent));
    } catch (e) {
      console.error("[Scenarios] LocalStorage load failed:", e);
    }
  }, []);

  // 유효한 캐시가 없으면 자동 분석 시작
  useEffect(() => {
    if (!mounted) return;
    try {
      const stored = localStorage.getItem(SC_DATA_KEY);
      const parsed = stored ? JSON.parse(stored) : null;
      if (!parsed || !Array.isArray(parsed) || parsed.length === 0) {
        setFetchTrigger(0);
      }
    } catch {
      setFetchTrigger(0);
    }
  }, [mounted]);

  const { data: us } = useSWR("us-indices", () => api.us.indices() as Promise<any>, { refreshInterval: 60000 });

  // fetchTrigger가 null이 아닐 때만 실행
  useEffect(() => {
    if (fetchTrigger === null) return;
    let cancelled = false;
    setLoading(true);
    setLoadError("");
    setStatusMsg("AI 시나리오 분석 중...");
    setIssueIdx(0);
    setReady("scenarios", false);

    // 최대 3분 후 자동 타임아웃 (서버 무응답 시 로딩 영구 대기 방지)
    const controller = new AbortController();
    const timeoutId = setTimeout(() => { if (!cancelled) controller.abort(); }, 180_000);

    (async () => {
      try {
        const result = await readSSE(
          `/api/ai/scenarios?use_cache=false`,
          "GET",
          undefined,
          (msg) => { if (!cancelled) setStatusMsg(msg); },
          controller.signal
        );
        if (!cancelled) {
          if (result?.error) {
            setLoadError(`AI 분석 오류: ${result.error}`);
            setLoading(false);
            return;
          }
          const newIssues = result?.issues ?? [];
          if (newIssues.length === 0) {
            setLoadError("AI 분석 결과를 받지 못했습니다. 잠시 후 다시 시도해주세요.");
            setLoading(false);
            return;
          }
          setIssues(newIssues);
          const ts = new Date().toLocaleString("ko-KR");
          setLastUpdated(ts);
          try {
            localStorage.setItem(SC_DATA_KEY, JSON.stringify(newIssues));
            localStorage.setItem(SC_TS_KEY, ts);
          } catch {}
          setLoading(false);
          setReady("scenarios", true);
        }
      } catch (e: any) {
        if (!cancelled) {
          if (e?.name === "AbortError") {
            setLoadError("AI 시나리오 분석 시간이 초과됐습니다 (3분). 잠시 후 다시 시도해주세요.");
          } else {
            setLoadError(String(e));
          }
          setLoading(false);
        }
      } finally {
        clearTimeout(timeoutId);
      }
    })();
    return () => { cancelled = true; controller.abort(); clearTimeout(timeoutId); };
  }, [fetchTrigger]);

  const handleUpdate = () => {
    setRegionFilter("전체");
    setFetchTrigger(n => (n ?? -1) + 1);
  };

  const handleCustomSearch = async (kw?: string) => {
    const keyword = (kw ?? customKeyword).trim();
    if (!keyword) return;
    setCustomLoading(true);
    setCustomError("");
    setShowRecent(false);

    // 최근 검색어 저장 (최대 10개)
    const newRecent = [keyword, ...recentSearches.filter(k => k !== keyword)].slice(0, 10);
    setRecentSearches(newRecent);
    localStorage.setItem(RECENT_KEY, JSON.stringify(newRecent));

    const newIdx = customIssues.length >= 6 ? 5 : customIssues.length;
    try {
      const result = await readSSE(
        "/api/ai/scenarios/custom",
        "POST",
        { keyword },
        () => {}
      );
      const newIssue = { ...(result as Issue), isCustom: true as const, keyword };
      const updated = [...customIssues, newIssue].slice(-6); // FIFO max 6
      setCustomIssues(updated);
      localStorage.setItem(CUSTOM_KEY, JSON.stringify(updated));
      setRegionFilter("커스텀");
      setIssueIdx(newIdx);
      setCustomKeyword("");
    } catch (e) {
      setCustomError(String(e));
    } finally {
      setCustomLoading(false);
    }
  };

  const handleDeleteCustomIssue = (idx: number) => {
    const updated = customIssues.filter((_, i) => i !== idx);
    setCustomIssues(updated);
    localStorage.setItem(CUSTOM_KEY, JSON.stringify(updated));
    setIssueIdx(prev => (prev >= idx ? Math.max(0, prev - 1) : prev));
  };

  const filteredIssues: Array<Issue & { isCustom?: boolean }> = regionFilter === "커스텀"
    ? customIssues
    : regionFilter === "전체"
      ? issues
      : issues.filter(issue => {
          const region = classifyIssueRegion(issue);
          if (regionFilter === "글로벌")    return region === "글로벌"  || region === "mixed";
          if (regionFilter === "국내")      return region === "국내"    || region === "mixed";
          if (regionFilter === "이머징마켓") return region === "이머징마켓";
          return true;
        });

  const clampedIdx  = issueIdx < filteredIssues.length ? issueIdx : 0;
  const activeIssue = filteredIssues[clampedIdx] ?? filteredIssues[0];

  if (!mounted) {
    return (
      <div style={{ width: "100%", padding: "2rem", display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", minHeight: "300px", color: "var(--color-muted)" }}>
        <Loader2 className="animate-spin" size={24} style={{ marginBottom: "8px" }} />
        <span>화면을 준비하는 중입니다...</span>
      </div>
    );
  }

  return (
    <div style={{ width: "100%", margin: "0 auto", display: "flex", flexDirection: "column", gap: "1rem" }}>

      {/* 헤더 */}
      <div style={{ borderBottom: "1px solid rgba(255,255,255,0.05)", paddingBottom: "1rem", display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
        <div>
          <h1 style={{ fontSize: "1.4rem", fontWeight: 800, margin: "0 0 4px 0", display: "flex", alignItems: "center", gap: "8px" }}>
            <Globe color="var(--color-accent)" size={22} /> 매크로 시나리오 분석
          </h1>
          <div style={{ fontSize: "0.82rem", color: "var(--color-muted)" }}>
            글로벌 주요 이슈에 대한 A/B 시나리오와 투자 전략을 AI가 분석합니다.
          </div>
        </div>
        <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: "4px" }}>
          {lastUpdated && !loading && (
            <div style={{ fontSize: "0.7rem", color: "var(--color-muted)" }}>마지막 업데이트: {lastUpdated}</div>
          )}
          <button
            onClick={handleUpdate}
            disabled={loading}
            className="stockcy-btn stockcy-btn-primary"
            style={{ display: "flex", alignItems: "center", gap: "6px", padding: "6px 14px", fontSize: "0.82rem", fontWeight: 700, flexShrink: 0 }}
            title="AI 새로 분석 (약 1~2분)"
          >
            {loading ? <Loader2 className="animate-spin" size={15} /> : <RefreshCw size={15} />}
            {loading ? "분석 중..." : "AI 업데이트"}
          </button>
        </div>
      </div>

      {/* 2단 레이아웃 */}
      <div style={{ display: "grid", gridTemplateColumns: "220px 1fr", gap: "1.5rem", alignItems: "start" }}>

        {/* ── 좌측: 시장 지표 ── */}
        <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>

          <div className="stockcy-card" style={{ padding: "12px", display: "flex", flexDirection: "column", gap: "10px" }}>
            <div style={{ fontSize: "0.82rem", fontWeight: 800, color: "var(--color-muted)", display: "flex", alignItems: "center", gap: "4px" }}>
              <TrendingUp size={13} /> 주요 지수 (미국)
            </div>
            {[
              { label: "S&P 500", key: "S&P 500" },
              { label: "NASDAQ",  key: "NASDAQ" },
              { label: "VIX",     key: "VIX" },
            ].map(({ label, key }) => {
              const d = (us as any)?.[key];
              const up = (d?.change_pct ?? 0) >= 0;
              return (
                <div key={key} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", borderBottom: "1px solid rgba(255,255,255,0.04)", paddingBottom: "6px" }}>
                  <span style={{ fontSize: "0.8rem", fontWeight: 700 }}>{label}</span>
                  <span style={{ fontSize: "0.8rem", fontWeight: 800, color: key === "VIX" ? "var(--color-muted)" : up ? "var(--color-danger)" : "var(--color-primary)" }}>
                    {d ? `${d.price.toLocaleString()} (${d.change_pct >= 0 ? "+" : ""}${d.change_pct.toFixed(2)}%)` : "조회중"}
                  </span>
                </div>
              );
            })}
          </div>

          <div className="stockcy-card" style={{ padding: "12px", display: "flex", flexDirection: "column", gap: "10px" }}>
            <div style={{ fontSize: "0.82rem", fontWeight: 800, color: "var(--color-muted)", display: "flex", alignItems: "center", gap: "4px" }}>
              <DollarSign size={13} /> 환율 및 채권
            </div>
            <div style={{ display: "flex", justifyContent: "space-between", borderBottom: "1px solid rgba(255,255,255,0.04)", paddingBottom: "6px" }}>
              <span style={{ fontSize: "0.8rem", fontWeight: 700 }}>원/달러</span>
              <span style={{ fontSize: "0.8rem", fontWeight: 800, color: "var(--color-warning)" }}>—</span>
            </div>
            <div style={{ display: "flex", justifyContent: "space-between" }}>
              <span style={{ fontSize: "0.8rem", fontWeight: 700 }}>미 10년물</span>
              <span style={{ fontSize: "0.8rem", fontWeight: 800, color: "var(--color-primary)" }}>—</span>
            </div>
          </div>

          <div className="stockcy-card" style={{ padding: "12px", border: "1px solid var(--color-warning)", background: "rgba(255,180,50,0.05)" }}>
            <div style={{ fontSize: "0.8rem", fontWeight: 800, color: "var(--color-warning)", display: "flex", alignItems: "center", gap: "4px", marginBottom: "6px" }}>
              <AlertTriangle size={13} /> 시장 경보
            </div>
            <div style={{ fontSize: "0.72rem", color: "var(--color-muted)", lineHeight: 1.5 }}>
              AI 분석 결과를 통해 확인하세요.
            </div>
          </div>

          {/* 커스텀 이슈 검색 */}
          <div className="stockcy-card" style={{ padding: "12px", display: "flex", flexDirection: "column", gap: "8px" }}>
            <div style={{ fontSize: "0.82rem", fontWeight: 800, color: "var(--color-muted)" }}>커스텀 이슈 검색</div>
            <div style={{ position: "relative" }}>
              <input
                className="stockcy-input"
                placeholder="키워드 (예: 반도체 관세)"
                value={customKeyword}
                onChange={e => setCustomKeyword(e.target.value)}
                onFocus={() => setShowRecent(true)}
                onBlur={() => setTimeout(() => setShowRecent(false), 150)}
                onKeyDown={e => e.key === "Enter" && handleCustomSearch()}
                style={{ fontSize: "0.82rem", width: "100%", boxSizing: "border-box" }}
              />
              {/* 최근 검색어 드롭다운 */}
              {showRecent && recentSearches.length > 0 && (
                <div style={{
                  position: "absolute", top: "100%", left: 0, right: 0, zIndex: 50,
                  background: "var(--color-card)", border: "1px solid var(--color-border)",
                  borderRadius: "6px", marginTop: "4px", overflow: "hidden",
                }}>
                  <div style={{ padding: "6px 10px", fontSize: "0.7rem", color: "var(--color-muted)", fontWeight: 700, borderBottom: "1px solid var(--color-border)" }}>
                    최근 검색어
                  </div>
                  {recentSearches.map((kw, i) => (
                    <div
                      key={i}
                      onMouseDown={() => { setCustomKeyword(kw); handleCustomSearch(kw); }}
                      style={{ padding: "6px 10px", fontSize: "0.8rem", cursor: "pointer", color: "var(--color-text)" }}
                      className="hover-highlight"
                    >
                      {kw}
                    </div>
                  ))}
                </div>
              )}
            </div>
            <button
              className="stockcy-btn stockcy-btn-primary"
              onClick={() => handleCustomSearch()}
              disabled={customLoading || !customKeyword.trim()}
              style={{ width: "100%", padding: "8px", fontWeight: 700, fontSize: "0.82rem", display: "flex", alignItems: "center", justifyContent: "center", gap: "6px" }}
            >
              {customLoading ? <><Loader2 className="animate-spin" size={14} /> 분석중...</> : "분석하기"}
            </button>
            {customError && <div style={{ fontSize: "0.75rem", color: "var(--color-danger)" }}>{customError}</div>}

            {/* 저장된 커스텀 이슈 목록 */}
            {customIssues.length > 0 && (
              <div style={{ display: "flex", flexDirection: "column", gap: "4px", marginTop: "4px" }}>
                <div style={{ fontSize: "0.72rem", color: "var(--color-muted)", fontWeight: 700 }}>저장된 이슈 ({customIssues.length}/6)</div>
                {customIssues.map((issue, i) => (
                  <div
                    key={i}
                    style={{ display: "flex", alignItems: "center", gap: "4px" }}
                  >
                    <button
                      onClick={() => { setRegionFilter("커스텀"); setIssueIdx(i); }}
                      style={{
                        flex: 1, textAlign: "left", padding: "4px 8px", fontSize: "0.75rem",
                        borderRadius: "4px", border: "1px solid var(--color-border)",
                        background: "transparent", color: "var(--color-text)", cursor: "pointer",
                        overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
                      }}
                      title={issue.title}
                    >
                      {issue.keyword || issue.title.slice(0, 16)}
                    </button>
                    <button
                      onClick={() => handleDeleteCustomIssue(i)}
                      style={{ flexShrink: 0, padding: "4px", background: "transparent", border: "none", cursor: "pointer", color: "var(--color-muted)" }}
                      title="삭제"
                    >
                      <X size={12} />
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>

        </div>

        {/* ── 우측: 메인 콘텐츠 ── */}
        <div className="stockcy-card" style={{ padding: "1.5rem", minHeight: "500px" }}>

          {loading ? (
            <div style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", minHeight: "400px", gap: "1rem" }}>
              <Loader2 className="animate-spin" size={36} color="var(--color-accent)" />
              <div style={{ color: "var(--color-muted)", fontSize: "0.9rem", fontWeight: 600 }}>{statusMsg}</div>
            </div>
          ) : loadError ? (
            <div style={{ color: "var(--color-danger)", textAlign: "center", padding: "2rem" }}>{loadError}</div>
          ) : issues.length === 0 ? (
            <div style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", minHeight: "400px", gap: "1rem" }}>
              <div style={{ fontSize: "2.5rem" }}>🤖</div>
              <div style={{ fontWeight: 700, fontSize: "1rem", color: "var(--color-text)" }}>AI 시나리오 분석이 필요합니다</div>
              <div style={{ fontSize: "0.85rem", color: "var(--color-muted)", textAlign: "center", lineHeight: 1.6 }}>
                상단 <strong>AI 업데이트</strong> 버튼을 눌러 글로벌 시장 시나리오를 분석하세요.<br />
                분석 결과는 이 기기에 저장되어 다음 방문 시 즉시 표시됩니다.
              </div>
              <button
                onClick={handleUpdate}
                className="stockcy-btn stockcy-btn-primary"
                style={{ padding: "10px 24px", fontWeight: 700, fontSize: "0.9rem", display: "flex", alignItems: "center", gap: "8px" }}
              >
                <RefreshCw size={16} /> AI 시나리오 분석 시작
              </button>
            </div>
          ) : (
            <>
              {/* 지역 필터 탭 */}
              <div style={{ display: "flex", gap: "4px", flexWrap: "wrap", marginBottom: "12px" }}>
                {(["전체", "글로벌", "국내", "이머징마켓", "커스텀"] as RegionFilter[]).map(r => {
                  const labels: Record<RegionFilter, string> = {
                    "전체":      "전체",
                    "글로벌":    "🌍 글로벌 (미국)",
                    "국내":      "🇰🇷 국내",
                    "이머징마켓": "🌏 이머징마켓",
                    "커스텀":    `🔍 커스텀${customIssues.length > 0 ? ` (${customIssues.length})` : ""}`,
                  };
                  const active = regionFilter === r;
                  return (
                    <button
                      key={r}
                      onClick={() => { setRegionFilter(r); setIssueIdx(0); }}
                      style={{
                        padding: "5px 12px", fontSize: "0.78rem", fontWeight: 700, borderRadius: "6px",
                        border: "1px solid",
                        borderColor: active ? (r === "커스텀" ? "var(--color-warning)" : "var(--color-accent)") : "var(--color-border)",
                        background: active ? (r === "커스텀" ? "rgba(255,180,50,0.12)" : "rgba(255,255,255,0.1)") : "transparent",
                        color: active ? (r === "커스텀" ? "var(--color-warning)" : "var(--color-text)") : "var(--color-muted)",
                        cursor: "pointer",
                        transition: "0.15s",
                      }}
                    >
                      {labels[r]}
                    </button>
                  );
                })}
              </div>

              {/* 커스텀 탭: 검색 UI */}
              {regionFilter === "커스텀" && (
                <div style={{ display: "flex", gap: "8px", alignItems: "center", marginBottom: "12px", padding: "10px 12px", background: "rgba(255,180,50,0.06)", border: "1px solid rgba(255,180,50,0.2)", borderRadius: "8px" }}>
                  <input
                    className="stockcy-input"
                    placeholder="키워드 입력 (예: 반도체 관세, 금리 동결)"
                    value={customKeyword}
                    onChange={e => setCustomKeyword(e.target.value)}
                    onKeyDown={e => e.key === "Enter" && handleCustomSearch()}
                    style={{ flex: 1, fontSize: "0.85rem" }}
                  />
                  <button
                    className="stockcy-btn stockcy-btn-primary"
                    onClick={() => handleCustomSearch()}
                    disabled={customLoading || !customKeyword.trim()}
                    style={{ padding: "8px 16px", fontWeight: 700, fontSize: "0.82rem", flexShrink: 0, display: "flex", alignItems: "center", gap: "6px" }}
                  >
                    {customLoading ? <><Loader2 className="animate-spin" size={14} /> 분석중...</> : "분석하기"}
                  </button>
                  {customError && <div style={{ fontSize: "0.75rem", color: "var(--color-danger)", flexShrink: 0 }}>{customError}</div>}
                </div>
              )}

              {/* 이슈 탭 */}
              {filteredIssues.length === 0 ? (
                <div style={{ color: "var(--color-muted)", fontSize: "0.85rem", padding: "2rem", textAlign: "center" }}>
                  {regionFilter === "커스텀"
                    ? "위 검색창에 키워드를 입력하고 분석하기를 눌러보세요."
                    : "해당 지역의 이슈가 없습니다."
                  }
                </div>
              ) : (
                <>
                  <div style={{ display: "flex", gap: "6px", flexWrap: "wrap", marginBottom: "1.25rem", borderBottom: "1px solid var(--color-border)", paddingBottom: "10px" }}>
                    {filteredIssues.map((issue, idx) => (
                      <div key={idx} style={{ display: "flex", alignItems: "center", gap: "2px" }}>
                        <button
                          onClick={() => setIssueIdx(idx)}
                          style={{
                            padding: "4px 12px", fontSize: "0.78rem", fontWeight: 600, borderRadius: "4px",
                            border: "1px solid",
                            borderColor: clampedIdx === idx ? "var(--color-accent)" : "var(--color-border)",
                            background: clampedIdx === idx ? "rgba(255,255,255,0.08)" : "transparent",
                            color: clampedIdx === idx ? "var(--color-text)" : "var(--color-muted)",
                            cursor: "pointer",
                            transition: "0.15s",
                          }}
                        >
                          {(issue as any).isCustom
                            ? `Custom ${idx + 1}: ${String(issue.title).slice(0, 14)}${issue.title.length > 14 ? "…" : ""}`
                            : `Issue ${idx + 1}: ${String(issue.title).slice(0, 16)}${issue.title.length > 16 ? "…" : ""}`
                          }
                        </button>
                        {(issue as any).isCustom && (
                          <button
                            onClick={() => handleDeleteCustomIssue(customIssues.findIndex(ci => ci === issue))}
                            style={{ padding: "2px", background: "transparent", border: "none", cursor: "pointer", color: "var(--color-muted)", flexShrink: 0 }}
                            title="삭제"
                          >
                            <X size={11} />
                          </button>
                        )}
                      </div>
                    ))}
                  </div>

                  {activeIssue && <IssuePanel key={`${regionFilter}-${clampedIdx}`} issue={activeIssue} />}
                </>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}

const ScenariosPageContent = dynamic(() => Promise.resolve(ScenariosPageInner), {
  ssr: false,
  loading: () => (
    <div style={{ width: "100%", padding: "2rem", display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", minHeight: "300px", color: "var(--color-muted)" }}>
      <Loader2 className="animate-spin" size={24} style={{ marginBottom: "8px" }} />
      <span>화면을 준비하는 중입니다...</span>
    </div>
  )
});

export default function ScenariosPage() {
  return <ScenariosPageContent />;
}
