"use client";
import { useState, useMemo, useEffect } from "react";
import { useRouter } from "next/navigation";
import useSWR from "swr";
import { api } from "@/lib/api";
import type { Favorite, KrStock, UsStock } from "@/lib/types";
import { Star, RefreshCw, Send, Trash2, Plus, Zap, BarChart2, Bell, TrendingUp, BookOpen, Loader2, Brain, Sparkles, AlertCircle } from "lucide-react";

const BASE_URL = "/backend";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { StatusBox } from "@/components/ui/StatusBox";
import { Skeleton } from "@/components/ui/LoadingSpinner";
import { SSEPanel } from "@/components/ui/SSEPanel";
import { StockModal } from "@/components/ui/StockModal";
import type { StockInfo } from "@/components/ui/StockModal";
import { useSSE } from "@/hooks/useSSE";

// ── 투자 가이드 배지 (Streamlit 원본 로직 동일) ─────────────────────────────
function getStatusInfo(pct: number | null, price?: number, w52High?: number, w52Low?: number) {
  if (pct === null) return null;

  // 52주 범위 내 현재가 위치 (0~100%)
  let posPct = 50;
  if (w52High && w52Low && w52High > w52Low && price) {
    posPct = ((price - w52Low) / (w52High - w52Low)) * 100;
  }
  const has52 = !!(w52High && w52Low && w52High > w52Low);

  if (pct >= 5)            return { label: "🔥 급등 중 (추격 신중)",   color: "#ff4b4b", bg: "rgba(255,75,75,0.12)",   border: "rgba(255,75,75,0.4)"   };
  if (pct <= -5)           return { label: "🔵 과매도 (반등 확인)",    color: "#2b7cff", bg: "rgba(43,124,255,0.12)",  border: "rgba(43,124,255,0.4)"  };
  if (has52 && posPct <= 15) return { label: "💎 바닥권 (매수 매력)",  color: "#00c853", bg: "rgba(0,200,83,0.12)",    border: "rgba(0,200,83,0.4)"    };
  if (has52 && posPct >= 85) return { label: "⚠️ 고점권 (돌파 체크)", color: "#ff9800", bg: "rgba(255,152,0,0.12)",   border: "rgba(255,152,0,0.4)"   };
  if (pct >= 2)            return { label: "🟢 상승세 유지",           color: "#4ade80", bg: "rgba(74,222,128,0.12)",  border: "rgba(74,222,128,0.4)"  };
  if (pct <= -2)           return { label: "🔴 약세 흐름",             color: "#ff6b6b", bg: "rgba(255,107,107,0.12)", border: "rgba(255,107,107,0.4)" };
  return                          { label: "⚪ 관망",                  color: "#888",    bg: "rgba(150,150,150,0.10)", border: "rgba(150,150,150,0.3)" };
}

// ── 즐겨찾기 카드 ─────────────────────────────────────────────────────────────
function FavRow({ fav, price, onRemove, onAnalyze, gapBulkMap }: {
  fav: Favorite;
  price?: { price: number; change_pct: number; w52_high?: number; w52_low?: number } | null;
  onRemove: (ticker: string) => void;
  onAnalyze: (s: StockInfo) => void;
  gapBulkMap: Record<string, any>;
}) {
  const router = useRouter();
  const isKr   = fav["시장"] === "국내";
  const pct    = price?.change_pct ?? null;
  const up     = (pct ?? 0) > 0;
  const down   = (pct ?? 0) < 0;
  const color  = up ? "var(--color-up)" : down ? "var(--color-down)" : "var(--color-flat)";
  const status = getStatusInfo(pct, price?.price, price?.w52_high, price?.w52_low);

  // 시간외 갭 데이터 분석
  const gapData = gapBulkMap?.[fav["티커"].toUpperCase()];
  const gapUp = gapData?.gap_direction?.includes("상승");
  const gapDown = gapData?.gap_direction?.includes("하락");
  const gapText = gapData?.gap_strength && gapData?.gap_strength !== "보합권" ? gapData.gap_strength : null;

  return (
    <div style={{
      background: "var(--color-surface)",
      border: "1px solid var(--color-border)",
      borderRadius: "10px",
      padding: "12px 14px",
      display: "flex", flexDirection: "column", gap: "8px",
    }}>
      {/* 제목 행 */}
      <div style={{ display: "flex", alignItems: "center", gap: "5px", flexWrap: "wrap" }}>
        <Star size={12} style={{ color: "var(--color-warning)", fill: "var(--color-warning)", flexShrink: 0 }} />
        <span style={{ fontWeight: 700, fontSize: "0.9rem" }}>{fav["종목명"]}</span>
        <span style={{ fontSize: "0.7rem", color: "var(--color-muted)", marginRight: "4px" }}>({fav["티커"]})</span>

        {/* 실시간 갭 배지 표출 */}
        {gapData && gapText && (
          <span 
            style={{
              fontSize: "0.65rem",
              padding: "1px 5px",
              borderRadius: "4px",
              background: gapUp ? "rgba(16, 185, 129, 0.15)" : gapDown ? "rgba(239, 68, 68, 0.15)" : "rgba(255,255,255,0.06)",
              color: gapUp ? "#34d399" : gapDown ? "#f87171" : "#a1a1aa",
              border: `1px solid ${gapUp ? "rgba(16, 185, 129, 0.3)" : gapDown ? "rgba(239, 68, 68, 0.3)" : "rgba(255, 255, 255, 0.12)"}`,
              fontWeight: 800,
              cursor: "help",
              display: "inline-flex",
              alignItems: "center",
              gap: "2px"
            }}
            title={`🌙 시간외 주요 변수:\n${gapData.overnight_issue_summary}\n\n💡 대응 가이드:\n${gapData.trading_action_guide}`}
          >
            {gapUp ? "🟢 갭상" : gapDown ? "🔴 갭하" : "⚪ 보합"} {gapText}
          </span>
        )}
      </div>

      {/* 시세 + 현황 배지 */}
      <div style={{ display: "flex", alignItems: "center", gap: "7px", flexWrap: "wrap" }}>
        <Badge variant={isKr ? "info" : "success"}>{fav["시장"]}</Badge>
        <span style={{ fontWeight: 700, fontSize: "0.88rem" }}>
          {price
            ? isKr ? `₩${price.price.toLocaleString()}` : `$${price.price.toFixed(2)}`
            : <span style={{ color: "var(--color-muted)", fontWeight: 400, fontSize: "0.8rem" }}>로딩중...</span>
          }
        </span>
        {price && (
          <span style={{ color, fontSize: "0.8rem", fontWeight: 600 }}>
            {up ? "+" : ""}{pct!.toFixed(2)}%
          </span>
        )}
        {status && (
          <span style={{
            fontSize: "0.7rem", padding: "2px 8px", borderRadius: "99px",
            background: status.bg, color: status.color, fontWeight: 700,
            border: `1px solid ${status.border}`,
          }}>
            {status.label}
          </span>
        )}
      </div>

      {/* 버튼 행 */}
      <div style={{ display: "flex", gap: "5px" }}>
        <button
          className="stockcy-btn stockcy-btn-secondary"
          style={{ flex: 1, padding: "5px 4px", fontSize: "0.71rem", display: "flex", alignItems: "center", justifyContent: "center", gap: "3px" }}
          onClick={() => router.push(`/search?q=${fav["티커"]}${isKr ? "&market=KR" : "&market=US"}`)}
        >
          <BarChart2 size={11} /> 차트보기
        </button>
        <button
          className="stockcy-btn stockcy-btn-secondary"
          style={{ flex: 1, padding: "5px 4px", fontSize: "0.71rem", display: "flex", alignItems: "center", justifyContent: "center", gap: "3px" }}
          onClick={() => onAnalyze({ code: fav["티커"], name: fav["종목명"], market: fav["시장"] as "국내" | "미국" })}
        >
          <Zap size={11} /> AI분석
        </button>
        <button
          className="stockcy-btn"
          style={{ flex: 1, padding: "5px 4px", fontSize: "0.71rem", display: "flex", alignItems: "center", justifyContent: "center", gap: "3px", border: "1px solid rgba(255,60,60,0.35)", color: "var(--color-danger)", background: "rgba(255,60,60,0.06)" }}
          onClick={() => { if (window.confirm(`${fav["종목명"]} 즐겨찾기에서 삭제할까요?`)) onRemove(fav["티커"]); }}
        >
          <Trash2 size={11} /> 삭제
        </button>
      </div>
    </div>
  );
}

// ── 즐겨찾기 추가 폼 ──────────────────────────────────────────────────────────
function AddFavoriteForm({ onAdded }: { onAdded: () => void }) {
  const [market, setMarket] = useState<"국내" | "미국">("미국");
  const [ticker, setTicker] = useState("");
  const [name,   setName]   = useState("");
  const [msg,    setMsg]    = useState<{ type: "success" | "danger"; text: string } | null>(null);
  const [loading, setLoading] = useState(false);

  const handleAdd = async () => {
    if (!ticker.trim() || !name.trim()) return;
    setLoading(true);
    try {
      const res = await api.portfolio.addFavorite(market, ticker.trim().toUpperCase(), name.trim()) as { success: boolean; message: string };
      setMsg({ type: res.success ? "success" : "danger", text: res.message });
      if (res.success) { setTicker(""); setName(""); onAdded(); }
    } catch (e) { setMsg({ type: "danger", text: String(e) }); }
    finally { setLoading(false); }
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
      <div style={{ display: "flex", gap: "0.5rem", alignItems: "center" }}>
        <select className="stockcy-input" style={{ width: "90px", flexShrink: 0 }} value={market} onChange={(e) => setMarket(e.target.value as "국내" | "미국")}>
          <option value="미국">미국</option>
          <option value="국내">국내</option>
        </select>
        <input className="stockcy-input" placeholder="티커 (예: NVDA, 005930)" value={ticker} onChange={(e) => setTicker(e.target.value)} style={{ flex: 1 }} />
        <input className="stockcy-input" placeholder="종목명 (예: 엔비디아)" value={name} onChange={(e) => setName(e.target.value)} style={{ flex: 1 }} />
        <button className="stockcy-btn stockcy-btn-primary" onClick={handleAdd} disabled={loading || !ticker || !name}>
          <Plus size={14} />추가
        </button>
      </div>
      {msg && <StatusBox type={msg.type}>{msg.text}</StatusBox>}
    </div>
  );
}

// ── 추천 상태 뱃지 ────────────────────────────────────────────────────────────
function RecommendBadge({ pct, hasPrice }: { pct: number; hasPrice?: boolean }) {
  if (hasPrice === false) return <Badge variant="info">⚪ 대기</Badge>;
  if (pct >= 10)       return <Badge variant="danger">🔴 수익실현 대기</Badge>;
  if (pct >= 3)        return <Badge variant="success">🟢 보유 유지</Badge>;
  if (pct >= -3)       return <Badge variant="info">🔵 보유 유지</Badge>;
  if (pct >= -10)      return <Badge variant="warning">🟡 추가매수 검토</Badge>;
  return                      <Badge variant="danger">⚠️ 물타기 필요</Badge>;
}

// ── 토글 버튼 그룹 ────────────────────────────────────────────────────────────
function ToggleGroup<T extends string>({ options, value, onChange, colors }: {
  options: { label: string; value: T }[];
  value: T;
  onChange: (v: T) => void;
  colors?: Record<T, string>;
}) {
  return (
    <div style={{ display: "inline-flex", borderRadius: "6px", overflow: "hidden", border: "1px solid var(--color-border)" }}>
      {options.map(opt => {
        const active = opt.value === value;
        const color = colors?.[opt.value] ?? "var(--color-accent)";
        return (
          <button
            key={opt.value}
            onClick={() => onChange(opt.value)}
            style={{
              padding: "4px 10px", fontSize: "0.78rem", fontWeight: 600, cursor: "pointer", border: "none",
              background: active ? color : "var(--color-elevated)",
              color: active ? "#fff" : "var(--color-muted)",
              transition: "all 0.15s",
            }}
          >{opt.label}</button>
        );
      })}
    </div>
  );
}

// ── 보유 종목 추가 폼 ─────────────────────────────────────────────────────────
function AddPortfolioForm({ onAdded }: { onAdded: () => void }) {
  const [market,      setMarket]      = useState<"국내" | "미국">("미국");
  const [ticker,      setTicker]      = useState("");
  const [name,        setName]        = useState("");
  const [price,       setPrice]       = useState("");
  const [qty,         setQty]         = useState("");
  const [tradeSource, setTradeSource] = useState<"리딩방" | "개인">("개인");
  const [tradeType,   setTradeType]   = useState<"실매매" | "테스트">("실매매");
  const [msg,         setMsg]         = useState<{ type: "success" | "danger"; text: string } | null>(null);
  const [loading,     setLoading]     = useState(false);

  const handleAdd = async () => {
    if (!ticker.trim() || !name.trim() || !price || !qty) return;
    setLoading(true);
    try {
      const currentList = await api.portfolio.loadPortfolio() as any[];
      const updatedList = [...(currentList ?? []), {
        ticker:       ticker.trim().toUpperCase(),
        name:         name.trim(),
        buy_price:    Number(price),
        quantity:     Number(qty),
        rating:       "-",
        trade_source: tradeSource,
        trade_type:   tradeType,
      }];
      const res = await fetch(`${BASE_URL}/api/portfolio`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ portfolio_list: updatedList }),
      });
      if (!res.ok) throw new Error(`서버 오류: ${res.status}`);
      setMsg({ type: "success", text: `${name.trim()} (${ticker.trim().toUpperCase()}) 추가 완료 [${tradeSource} · ${tradeType}]` });
      setTicker(""); setName(""); setPrice(""); setQty("");
      onAdded();
    } catch (e) {
      setMsg({ type: "danger", text: String(e) });
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ background: "var(--color-surface)", border: "1px solid var(--color-border)", borderRadius: "8px", padding: "1rem", marginBottom: "1rem", display: "flex", flexDirection: "column", gap: "0.6rem" }}>
      <div style={{ fontWeight: 700, fontSize: "0.9rem" }}>+ 보유 종목 추가</div>

      {/* 출처 · 유형 토글 */}
      <div style={{ display: "flex", gap: "0.75rem", alignItems: "center", flexWrap: "wrap" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}>
          <span style={{ fontSize: "0.75rem", color: "var(--color-muted)" }}>출처</span>
          <ToggleGroup
            options={[{ label: "리딩방", value: "리딩방" as const }, { label: "개인", value: "개인" as const }]}
            value={tradeSource}
            onChange={setTradeSource}
            colors={{ "리딩방": "#7c3aed", "개인": "#2563eb" }}
          />
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}>
          <span style={{ fontSize: "0.75rem", color: "var(--color-muted)" }}>유형</span>
          <ToggleGroup
            options={[{ label: "실매매", value: "실매매" as const }, { label: "테스트", value: "테스트" as const }]}
            value={tradeType}
            onChange={setTradeType}
            colors={{ "실매매": "#059669", "테스트": "#d97706" }}
          />
        </div>
      </div>

      {/* 종목 입력 */}
      <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap", alignItems: "center" }}>
        <select className="stockcy-input" style={{ width: "80px", flexShrink: 0 }} value={market} onChange={(e) => setMarket(e.target.value as "국내" | "미국")}>
          <option value="국내">국내</option>
          <option value="미국">미국</option>
        </select>
        <input className="stockcy-input" placeholder="티커 (예: 005930, NVDA)" value={ticker} onChange={(e) => setTicker(e.target.value)} style={{ flex: 1, minWidth: "120px" }} />
        <input className="stockcy-input" placeholder="종목명" value={name} onChange={(e) => setName(e.target.value)} style={{ flex: 1, minWidth: "100px" }} />
        <input className="stockcy-input" type="number" placeholder="매수가" value={price} onChange={(e) => setPrice(e.target.value)} style={{ width: "100px" }} />
        <input className="stockcy-input" type="number" placeholder="수량" value={qty} onChange={(e) => setQty(e.target.value)} style={{ width: "80px" }} />
        <button className="stockcy-btn stockcy-btn-primary" onClick={handleAdd} disabled={loading || !ticker || !name || !price || !qty}>
          <Plus size={14} /> 추가
        </button>
      </div>
      {msg && <StatusBox type={msg.type}>{msg.text}</StatusBox>}
    </div>
  );
}

// ── 보유 종목 탭 ──────────────────────────────────────────────────────────────
function PortfolioTab({ gapBulkMap }: { gapBulkMap: Record<string, any> }) {
  const { data: portfolio, isLoading, mutate } = useSWR<any[]>("/api/portfolio", () => api.portfolio.loadPortfolio() as Promise<any[]>);

  // KR/US 종목 분류 (1~6자리 숫자 = KR, 6자리로 패딩)
  const isKrCode  = (t: string) => /^\d{1,6}$/.test(String(t).trim());
  const padKr     = (t: string) => String(t).trim().padStart(6, "0");
  const krItems   = (portfolio ?? []).filter(p => isKrCode(p.ticker));
  const krTickers = krItems.map(p => padKr(p.ticker));
  const usTickers = (portfolio ?? []).filter(p => !isKrCode(p.ticker)).map(p => String(p.ticker).trim().toUpperCase());

  // KR 현재가
  const { data: krPrices } = useSWR(
    krTickers.length > 0 ? `kr-port-prices-${krTickers.join(",")}` : null,
    async () => {
      const map: Record<string, number> = {};
      await Promise.all(krTickers.map(async (code) => {
        try {
          const paddedCode = String(code).trim().padStart(6, "0");
          const d = await api.kr.stockPrice(paddedCode) as any;
          if (d?.price) map[paddedCode] = d.price;
        } catch {}
      }));
      return map;
    },
    { refreshInterval: 60000 }
  );

  // US 현재가
  const { data: usPrices } = useSWR(
    usTickers.length > 0 ? `us-port-prices-${usTickers.join(",")}` : null,
    async () => {
      const arr = await api.us.stocks(usTickers) as any[];
      const map: Record<string, number> = {};
      for (const s of (arr ?? [])) {
        const ticker = s["심볼"] ?? s.ticker ?? "";
        if (ticker) {
          map[ticker.trim().toUpperCase()] = s["현재가($)"] ?? s.price ?? 0;
        }
      }
      return map;
    },
    { refreshInterval: 60000 }
  );

  // USD/KRW 환율
  const { data: fxData } = useSWR(
    usTickers.length > 0 ? "usd-krw-rate" : null,
    () => api.us.exchangeRate(),
    { refreshInterval: 300000 }
  );
  const usdKrw = fxData?.rate ?? 1350;

  const enriched = useMemo(() => {
    return (portfolio ?? []).map(p => {
      const trimmed = String(p.ticker).trim();
      const isUs = !isKrCode(trimmed);
      const normalTicker = isUs ? trimmed.toUpperCase() : padKr(trimmed);
      const livePriceMap = isUs ? (usPrices ?? {}) : (krPrices ?? {});
      
      const currentPrice = livePriceMap[normalTicker] ?? livePriceMap[trimmed.toUpperCase()] ?? livePriceMap[trimmed] ?? 0;
      const hasPrice = currentPrice > 0;
      
      const cost = (p.buy_price ?? 0) * (p.quantity ?? 0);
      const value = hasPrice ? currentPrice * (p.quantity ?? 0) : cost;
      const profit = hasPrice ? value - cost : 0;
      const profitPct = (hasPrice && cost > 0) ? (profit / cost) * 100 : 0;
      
      const costKrw  = isUs ? cost  * usdKrw : cost;
      const valueKrw = isUs ? value * usdKrw : value;
      
      return { 
         ...p, 
         isUs, 
         normalTicker, 
         currentPrice, 
         hasPrice, 
         cost, 
         value, 
         profit, 
         profitPct, 
         costKrw, 
         valueKrw 
      };
    });
  }, [portfolio, krPrices, usPrices, usdKrw]);

  const totalCostKrw   = enriched.reduce((s, p) => s + (p.hasPrice ? p.costKrw : 0), 0);
  const totalValueKrw  = enriched.reduce((s, p) => s + (p.hasPrice ? p.valueKrw : 0), 0);
  const totalProfitKrw = totalValueKrw - totalCostKrw;
  const hasUsItems     = enriched.some(p => p.isUs);

  // 편집 상태
  const [editTicker, setEditTicker] = useState<string | null>(null);
  const [editPrice,  setEditPrice]  = useState<string>("");
  const [editQty,    setEditQty]    = useState<string>("");
  const [editSource, setEditSource] = useState<"리딩방" | "개인">("개인");
  const [editType,   setEditType]   = useState<"실매매" | "테스트">("실매매");

  // AI 매도 타이밍 패널
  const [sellTarget, setSellTarget] = useState<any | null>(null);
  const [sellResult, setSellResult] = useState<string>("");
  const [sellStatus, setSellStatus] = useState<"idle" | "loading" | "done" | "error">("idle");
  const [sellMsg,    setSellMsg]    = useState("");

  const openSellAnalysis = async (p: any) => {
    setSellTarget(p);
    setSellResult("");
    setSellStatus("loading");
    setSellMsg("AI 매도 타이밍 분석 중...");
    try {
      const res = await fetch(`${BASE_URL}/api/ai/sell-timing`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          ticker: p.ticker, name: p.name,
          avg_price: p.buy_price, current_price: p.currentPrice,
          market: p.isUs ? "US" : "KR",
        }),
      });
      if (!res.body) throw new Error("no body");
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
          if (!part.startsWith("data:")) continue;
          try {
            const d = JSON.parse(part.slice(5).trim());
            if (d.status === "running") setSellMsg(d.message ?? "분석 중...");
            if (d.status === "done")    { setSellResult(JSON.stringify(d.result, null, 2)); setSellStatus("done"); }
            if (d.status === "error")   { setSellMsg(d.message ?? "오류"); setSellStatus("error"); }
          } catch {}
        }
      }
    } catch (e) {
      setSellMsg(String(e));
      setSellStatus("error");
    }
  };

  const handleSellRecord = async (p: any, sellPrice: number, sellQty: number) => {
    const bp  = Number(p.buy_price ?? 0);
    const profit = (sellPrice - bp) * sellQty;
    const profitPct = bp > 0 ? ((sellPrice - bp) / bp) * 100 : 0;
    
    await api.portfolio.saveTrade({
      ticker: p.ticker, name: p.name, quantity: sellQty,
      buy_price: bp, sell_price: sellPrice,
      profit, profit_pct: profitPct,
      result: profit >= 0 ? "수익" : "손실",
      sell_date: new Date().toISOString().slice(0, 19),
      trade_source: p.trade_source ?? "개인",
      trade_type:   p.trade_type   ?? "실매매",
    });

    const remainingQty = p.quantity - sellQty;
    let updated = [...(portfolio ?? [])];
    if (remainingQty <= 0) {
      updated = updated.filter((item: any) => item.ticker !== p.ticker);
    } else {
      updated = updated.map((item: any) => 
        item.ticker === p.ticker ? { ...item, quantity: remainingQty } : item
      );
    }
    await fetch(`${BASE_URL}/api/portfolio`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ portfolio_list: updated }),
    }).catch(() => {});

    mutate();
  };

  const handleUpdateEntry = async (p: any) => {
    const newBuy = Number(editPrice) || p.buy_price;
    const newQty = Number(editQty)   || p.quantity;
    const updated = (portfolio ?? []).map((item: any) =>
      item.ticker === p.ticker ? { ...item, buy_price: newBuy, quantity: newQty, trade_source: editSource, trade_type: editType } : item
    );
    await fetch(`${BASE_URL}/api/portfolio`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ portfolio_list: updated }),
    }).catch(() => {});
    setEditTicker(null);
    mutate();
  };

  const handleDeleteEntry = async (ticker: string) => {
    const updated = (portfolio ?? []).filter((item: any) => item.ticker !== ticker);
    await fetch(`${BASE_URL}/api/portfolio`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ portfolio_list: updated }),
    }).catch(() => {});
    mutate();
  };

  if (isLoading) return <Skeleton height="200px" />;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
      {/* 종목 추가 폼 */}
      <AddPortfolioForm onAdded={() => mutate()} />

      {/* 총 손익 요약 */}
      {enriched.length > 0 && (
        <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
          {hasUsItems && (
            <div style={{ fontSize: "0.72rem", color: "var(--color-muted)", textAlign: "right" }}>
              USD/KRW: {usdKrw.toLocaleString()}원{fxData?.fallback ? " (기본값)" : ""}
            </div>
          )}
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: "10px" }}>
            {[
              { label: "총 매수금액",  val: `₩${Math.round(totalCostKrw).toLocaleString()}` },
              { label: "총 평가금액",  val: `₩${Math.round(totalValueKrw).toLocaleString()}`,  color: totalValueKrw >= totalCostKrw ? "var(--color-danger)" : "var(--color-primary)" },
              { label: "총 손익",      val: `${totalProfitKrw >= 0 ? "+" : ""}₩${Math.round(totalProfitKrw).toLocaleString()} (${totalCostKrw > 0 ? ((totalProfitKrw/totalCostKrw)*100).toFixed(2) : "0"}%)`, color: totalProfitKrw >= 0 ? "var(--color-danger)" : "var(--color-primary)" },
            ].map(({ label, val, color }) => (
              <div key={label} style={{ background: "var(--color-surface)", border: "1px solid var(--color-border)", borderRadius: "8px", padding: "12px", textAlign: "center" }}>
                <div style={{ fontSize: "0.75rem", color: "var(--color-muted)", marginBottom: "4px" }}>{label}</div>
                <div style={{ fontWeight: 800, fontSize: "0.95rem", color: color ?? "var(--color-text)" }}>{val}</div>
              </div>
            ))}
          </div>
        </div>
      )}

      {!portfolio || portfolio.length === 0 ? (
        <StatusBox type="info">보유 종목이 없습니다.</StatusBox>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: "0" }}>
          {/* 헤더 행 */}
          <div style={{ display: "grid", gridTemplateColumns: "2.2fr 1fr 1fr 0.7fr 1fr 0.8fr 1.2fr auto", gap: "6px", padding: "8px 12px", fontSize: "0.75rem", color: "var(--color-muted)", fontWeight: 600, borderBottom: "1px solid var(--color-border)" }}>
            <div>종목명</div>
            <div style={{ textAlign: "right" }}>평단가</div>
            <div style={{ textAlign: "right" }}>현재가</div>
            <div style={{ textAlign: "right" }}>수량</div>
            <div style={{ textAlign: "right" }}>손익</div>
            <div style={{ textAlign: "right" }}>손익률</div>
            <div style={{ textAlign: "center" }}>추천 상태</div>
            <div style={{ textAlign: "center" }}>액션</div>
          </div>

          {enriched.map((p, i) => {
            const isEditing = editTicker === p.ticker;
            const color = p.profitPct >= 0 ? "var(--color-danger)" : "var(--color-primary)";
            const priceStr = p.isUs
              ? `$${Number(p.currentPrice).toFixed(2)}`
              : `₩${Number(p.currentPrice).toLocaleString()}`;
            const buyStr = p.isUs
              ? `$${Number(p.buy_price).toFixed(2)}`
              : `₩${Number(p.buy_price).toLocaleString()}`;
            const profitStr = p.isUs
              ? `${p.profit >= 0 ? "+" : ""}$${p.profit.toFixed(2)}`
              : `${p.profit >= 0 ? "+" : ""}₩${Math.round(p.profit).toLocaleString()}`;
            const profitKrwHint = p.isUs && p.profit !== 0
              ? `≈${p.profit >= 0 ? "+" : ""}₩${Math.round(p.profit * usdKrw).toLocaleString()}`
              : null;

            // 시간외 갭 예측 배지 추가
            const gapData = gapBulkMap?.[p.ticker.toUpperCase()];
            const gapUp = gapData?.gap_direction?.includes("상승");
            const gapDown = gapData?.gap_direction?.includes("하락");
            const gapText = gapData?.gap_strength && gapData?.gap_strength !== "보합권" ? gapData.gap_strength : null;

            return (
              <div key={i} style={{ borderBottom: "1px solid rgba(255,255,255,0.04)" }}>
                <div style={{ display: "grid", gridTemplateColumns: "2.2fr 1fr 1fr 0.7fr 1fr 0.8fr 1.2fr auto", gap: "6px", padding: "10px 12px", alignItems: "center", fontSize: "0.85rem" }}>
                  <div style={{ fontWeight: 600, display: "flex", flexDirection: "column", gap: "2px" }}>
                    <div style={{ display: "flex", alignItems: "center", gap: "4px", flexWrap: "wrap" }}>
                      <span>{p.name || p.normalTicker || p.ticker}</span>
                      <span style={{ fontSize: "0.72rem", color: "var(--color-muted)" }}>
                        ({p.normalTicker || p.ticker})
                      </span>
                      {p.isUs && <span style={{ fontSize: "0.65rem", padding: "1px 5px", background: "rgba(50,200,100,0.15)", border: "1px solid rgba(50,200,100,0.3)", borderRadius: "3px", color: "var(--color-success)" }}>US</span>}
                      {/* 출처 태그 */}
                      {p.trade_source === "리딩방" && (
                        <span style={{ fontSize: "0.62rem", padding: "1px 5px", background: "rgba(124,58,237,0.15)", border: "1px solid rgba(124,58,237,0.35)", borderRadius: "3px", color: "#a78bfa", fontWeight: 700 }}>리딩방</span>
                      )}
                      {/* 유형 태그 */}
                      {p.trade_type === "테스트" && (
                        <span style={{ fontSize: "0.62rem", padding: "1px 5px", background: "rgba(217,119,6,0.15)", border: "1px solid rgba(217,119,6,0.35)", borderRadius: "3px", color: "#fbbf24", fontWeight: 700 }}>테스트</span>
                      )}
                    </div>

                    {/* 시간외 갭 배지 인라인 노출 */}
                    {gapData && gapText && (
                      <div style={{ display: "flex" }}>
                        <span 
                          style={{
                            fontSize: "0.65rem",
                            padding: "1px 4px",
                            borderRadius: "3px",
                            background: gapUp ? "rgba(16, 185, 129, 0.15)" : gapDown ? "rgba(239, 68, 68, 0.15)" : "rgba(255,255,255,0.06)",
                            color: gapUp ? "#34d399" : gapDown ? "#f87171" : "#a1a1aa",
                            border: `1px solid ${gapUp ? "rgba(16, 185, 129, 0.3)" : gapDown ? "rgba(239, 68, 68, 0.3)" : "rgba(255, 255, 255, 0.12)"}`,
                            fontWeight: 800,
                            cursor: "help",
                            display: "inline-flex",
                            alignItems: "center"
                          }}
                          title={`🌙 시간외 주요 변수:\n${gapData.overnight_issue_summary}\n\n💡 대응 가이드:\n${gapData.trading_action_guide}`}
                        >
                          {gapUp ? "🟢 갭상" : gapDown ? "🔴 갭하" : "⚪ 보합"} {gapText}
                        </span>
                      </div>
                    )}
                  </div>
                  <div style={{ textAlign: "right" }}>{buyStr}</div>
                  <div style={{ textAlign: "right", fontWeight: 600 }}>
                    {p.hasPrice ? priceStr : <span style={{ color: "var(--color-muted)", fontSize: "0.8rem", fontWeight: 400 }}>로딩중...</span>}
                  </div>
                  <div style={{ textAlign: "right" }}>{Number(p.quantity ?? 0).toLocaleString()}주</div>
                  <div style={{ textAlign: "right", color: p.hasPrice ? color : "var(--color-muted)", fontWeight: 600 }}>
                    {p.hasPrice ? profitStr : "-"}
                    {p.hasPrice && profitKrwHint && (
                      <div style={{ fontSize: "0.68rem", color: "var(--color-muted)", fontWeight: 400 }}>{profitKrwHint}</div>
                    )}
                  </div>
                  <div style={{ textAlign: "right", color: p.hasPrice ? color : "var(--color-muted)", fontWeight: 700 }}>
                    {p.hasPrice ? `${p.profitPct >= 0 ? "+" : ""}${p.profitPct.toFixed(2)}%` : "-"}
                  </div>
                  <div style={{ textAlign: "center" }}><RecommendBadge pct={p.profitPct} hasPrice={p.hasPrice} /></div>
                  <div style={{ display: "flex", gap: "4px", flexWrap: "wrap" }}>
                    <button className="stockcy-btn stockcy-btn-secondary" style={{ padding: "2px 6px", fontSize: "0.7rem" }} title="AI 매도 타이밍" onClick={() => openSellAnalysis(p)}>
                      AI
                    </button>
                    <button className="stockcy-btn stockcy-btn-secondary" style={{ padding: "2px 6px", fontSize: "0.7rem" }} title="편집"
                      onClick={() => { setEditTicker(isEditing ? null : p.ticker); setEditPrice(String(p.buy_price)); setEditQty(String(p.quantity)); setEditSource((p.trade_source as "리딩방" | "개인") || "개인"); setEditType((p.trade_type as "실매매" | "테스트") || "실매매"); }}>
                      ✏️
                    </button>
                    <button
                      className="stockcy-btn"
                      style={{ padding: "2px 6px", fontSize: "0.7rem", border: "1px solid rgba(255,60,60,0.35)", color: "var(--color-danger)", background: "rgba(255,60,60,0.06)" }}
                      title="삭제"
                      onClick={() => { if (window.confirm(`${p.name || p.ticker} 보유종목에서 삭제할까요?`)) handleDeleteEntry(p.ticker); }}
                    >
                      <Trash2 size={11} />
                    </button>
                  </div>
                </div>

                {/* 인라인 편집 폼 */}
                {isEditing && (
                  <div style={{ background: "rgba(0,0,0,0.3)", padding: "10px 12px", display: "flex", gap: "0.6rem", alignItems: "center", flexWrap: "wrap" }}>
                    <span style={{ fontSize: "0.75rem", color: "var(--color-muted)" }}>출처</span>
                    <ToggleGroup
                      options={[{ label: "리딩방", value: "리딩방" as const }, { label: "개인", value: "개인" as const }]}
                      value={editSource} onChange={setEditSource}
                      colors={{ "리딩방": "#7c3aed", "개인": "#2563eb" }}
                    />
                    <span style={{ fontSize: "0.75rem", color: "var(--color-muted)" }}>유형</span>
                    <ToggleGroup
                      options={[{ label: "실매매", value: "실매매" as const }, { label: "테스트", value: "테스트" as const }]}
                      value={editType} onChange={setEditType}
                      colors={{ "실매매": "#059669", "테스트": "#d97706" }}
                    />
                    <span style={{ fontSize: "0.75rem", color: "var(--color-muted)" }}>평단가</span>
                    <input className="stockcy-input" type="number" value={editPrice} onChange={e => setEditPrice(e.target.value)} style={{ width: "100px" }} />
                    <span style={{ fontSize: "0.75rem", color: "var(--color-muted)" }}>수량</span>
                    <input className="stockcy-input" type="number" value={editQty} onChange={e => setEditQty(e.target.value)} style={{ width: "80px" }} />
                    <button className="stockcy-btn stockcy-btn-primary" style={{ padding: "4px 10px", fontSize: "0.8rem" }} onClick={() => handleUpdateEntry(p)}>저장</button>
                    <div style={{ marginLeft: "auto" }}>
                      <SellButton p={p} onSell={handleSellRecord} />
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      {/* AI 매도 타이밍 결과 패널 */}
      {sellTarget && (
        <div style={{ background: "var(--color-surface)", border: "1px solid var(--color-accent)", borderRadius: "8px", padding: "1rem" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.75rem" }}>
            <div style={{ fontWeight: 700, fontSize: "0.95rem" }}>
              🤖 {sellTarget.name} AI 매도 타이밍 분석
              <span style={{ fontSize: "0.75rem", color: "var(--color-muted)", marginLeft: "8px" }}>평단 {sellTarget.isUs ? `$${sellTarget.buy_price}` : `₩${Number(sellTarget.buy_price).toLocaleString()}`}</span>
            </div>
            <button className="stockcy-btn stockcy-btn-secondary" style={{ padding: "2px 8px", fontSize: "0.75rem" }} onClick={() => setSellTarget(null)}>✕</button>
          </div>
          {sellStatus === "loading" && (
            <div style={{ display: "flex", alignItems: "center", gap: "8px", color: "var(--color-muted)", fontSize: "0.85rem" }}>
              <Loader2 className="animate-spin" size={16} /> {sellMsg}
            </div>
          )}
          {sellStatus === "done" && (() => {
            let parsed: any = null;
            try { parsed = JSON.parse(sellResult); } catch {}
            if (!parsed) return (
              <pre style={{ fontSize: "0.8rem", color: "var(--color-subtle)", whiteSpace: "pre-wrap", wordBreak: "break-word", background: "rgba(0,0,0,0.2)", padding: "12px", borderRadius: "6px" }}>{sellResult}</pre>
            );
            return (
              <div style={{ display: "flex", flexDirection: "column", gap: "10px", fontSize: "0.84rem" }}>
                {parsed.verdict && (
                  <div style={{ padding: "8px 14px", background: "rgba(99,102,241,0.12)", border: "1px solid rgba(99,102,241,0.3)", borderRadius: "8px", fontWeight: 700, fontSize: "0.97rem" }}>
                    📋 판단: {parsed.verdict}
                  </div>
                )}
                {parsed.timing && (
                  <div style={{ display: "flex", flexDirection: "column", gap: "4px" }}>
                    <div style={{ fontWeight: 600, fontSize: "0.73rem", color: "var(--color-muted)", textTransform: "uppercase", letterSpacing: "0.05em" }}>⏰ 매도 타이밍</div>
                    <div style={{ lineHeight: 1.6, color: "var(--color-text)" }}>{parsed.timing}</div>
                  </div>
                )}
                {parsed.target_exit && (
                  <div style={{ display: "flex", flexDirection: "column", gap: "4px" }}>
                    <div style={{ fontWeight: 600, fontSize: "0.73rem", color: "var(--color-muted)", textTransform: "uppercase", letterSpacing: "0.05em" }}>🎯 목표 매도가</div>
                    <div style={{ fontWeight: 600, color: "var(--color-text)" }}>{parsed.target_exit}</div>
                  </div>
                )}
                {parsed.reason && (
                  <div style={{ display: "flex", flexDirection: "column", gap: "4px" }}>
                    <div style={{ fontWeight: 600, fontSize: "0.73rem", color: "var(--color-muted)", textTransform: "uppercase", letterSpacing: "0.05em" }}>📊 분석 근거</div>
                    <div style={{ whiteSpace: "pre-line", lineHeight: 1.65, color: "var(--color-subtle)" }}>{parsed.reason}</div>
                  </div>
                )}
                {parsed.risk && (
                  <div style={{ display: "flex", flexDirection: "column", gap: "4px" }}>
                    <div style={{ fontWeight: 600, fontSize: "0.73rem", color: "var(--color-muted)", textTransform: "uppercase", letterSpacing: "0.05em" }}>⚠️ 주요 리스크</div>
                    <div style={{ lineHeight: 1.65, color: "var(--color-subtle)" }}>{parsed.risk}</div>
                  </div>
                )}
              </div>
            );
          })()}
          {sellStatus === "error" && <StatusBox type="danger">{sellMsg}</StatusBox>}
        </div>
      )}
    </div>
  );
}

// ── 매도 버튼 (인라인 폼) ──────────────────────────────────────────────────────
function SellButton({ p, onSell }: { p: any; onSell: (p: any, price: number, qty: number) => Promise<void> }) {
  const [open, setOpen] = useState(false);
  const [price, setPrice] = useState(String(p.currentPrice || p.buy_price || ""));
  const [qty, setQty] = useState(String(p.quantity || ""));
  const [saving, setSaving] = useState(false);

  const handleSell = async () => {
    const sp = Number(price);
    const sq = Number(qty);
    if (!sp || !sq) return;
    if (sq > p.quantity) {
      alert("보유 수량보다 많이 매도할 수 없습니다.");
      return;
    }
    setSaving(true);
    await onSell(p, sp, sq);
    setSaving(false);
    setOpen(false);
  };

  if (!open) {
    return (
      <button className="stockcy-btn" style={{ padding: "4px 10px", fontSize: "0.8rem", background: "rgba(255,60,60,0.15)", border: "1px solid var(--color-danger)", color: "var(--color-danger)" }} onClick={() => setOpen(true)}>
        📤 매도
      </button>
    );
  }
  return (
    <div style={{ display: "flex", gap: "6px", alignItems: "center" }}>
      <span style={{ fontSize: "0.8rem", color: "var(--color-muted)" }}>매도가</span>
      <input className="stockcy-input" type="number" value={price} onChange={e => setPrice(e.target.value)} style={{ width: "80px" }} />
      <span style={{ fontSize: "0.8rem", color: "var(--color-muted)", marginLeft: "4px" }}>수량</span>
      <input className="stockcy-input" type="number" value={qty} onChange={e => setQty(e.target.value)} style={{ width: "60px" }} />
      <button className="stockcy-btn stockcy-btn-primary" style={{ padding: "4px 8px", fontSize: "0.8rem" }} onClick={handleSell} disabled={saving}>
        {saving ? "진행중" : "확정"}
      </button>
      <button className="stockcy-btn stockcy-btn-secondary" style={{ padding: "4px 8px", fontSize: "0.8rem" }} onClick={() => setOpen(false)}>취소</button>
    </div>
  );
}

// ── AI 복기 리포트 모달 ─────────────────────────────────────────────────────────
function PostmortemModal({ trade, onClose, onRefresh }: { trade: any; onClose: () => void; onRefresh: () => void }) {
  const isUs = !String(trade["티커"]).match(/^[0-9]+$/);
  const [pmStatus, setPmStatus] = useState<"loading" | "done" | "error">("loading");
  const [pmMsg,    setPmMsg]    = useState("🤖 거래 복기 분석 중... (1~2분 소요)");
  const [pmResult, setPmResult] = useState<any>(null);

  const parseNum = (val: any) => {
    const n = Number(String(val ?? "0").replace(/[^0-9.-]+/g, ""));
    return isNaN(n) ? 0 : n;
  };

  const runAnalysis = async () => {
    setPmStatus("loading");
    setPmMsg("🤖 거래 복기 분석 중... (1~2분 소요)");
    setPmResult(null);
    try {
      const res = await fetch(`${BASE_URL}/api/ai/postmortem`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          ticker:     String(trade["티커"] ?? trade.ticker),
          name:       trade["종목명"]  ?? trade.name,
          market:     isUs ? "미국" : "국내",
          buy_price:  parseNum(trade["매수가($)"] ?? trade["매수가(원)"] ?? trade.buy_price),
          sell_price: parseNum(trade["매도가($)"] ?? trade["매도가(원)"] ?? trade.sell_price),
          buy_date:   trade["매수시간"] ?? trade.buy_date  ?? "알 수 없음",
          sell_date:  trade["매도시간"] ?? trade.sell_date ?? "알 수 없음",
          profit_pct: parseNum(trade["수익률(%)"] ?? trade.profit_pct),
          owner:      trade["소유자"]  ?? trade.owner ?? "USER",
        }),
      });
      if (!res.ok) {
        const text = await res.text();
        throw new Error(`API 오류 (${res.status}): ${text}`);
      }
      if (!res.body) throw new Error("no body");
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
          if (!part.trim().startsWith("data:")) continue;
          try {
            const d = JSON.parse(part.trim().slice(5).trim());
            if (d.status === "running") setPmMsg(d.message ?? "분석 중...");
            if (d.status === "done")    { setPmResult(d.result); setPmStatus("done"); }
            if (d.status === "error")   { setPmMsg(d.message ?? "오류 발생"); setPmStatus("error"); }
          } catch {}
        }
      }
    } catch (e) {
      setPmMsg(String(e));
      setPmStatus("error");
    }
  };

  useEffect(() => { runAnalysis(); }, []);

  return (
    <div style={{
      position: "fixed", top: 0, left: 0, right: 0, bottom: 0, 
      background: "rgba(0,0,0,0.6)", zIndex: 9999, display: "flex", alignItems: "center", justifyContent: "center"
    }}>
      <div style={{
        background: "var(--color-surface)", padding: "1.5rem", borderRadius: "12px", width: "90%", maxWidth: "600px", 
        border: "1px solid var(--color-border)", boxShadow: "0 10px 30px rgba(0,0,0,0.3)",
        maxHeight: "90vh", overflowY: "auto"
      }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1rem" }}>
          <h2 style={{ fontSize: "1.2rem", fontWeight: 700, margin: 0 }}>🧠 {trade["종목명"]} AI 복기 리포트</h2>
          <button className="stockcy-btn" style={{ padding: "4px 8px" }} onClick={() => { onClose(); if (pmStatus === "done") onRefresh(); }}>✕</button>
        </div>
        
        {pmStatus === "error" ? (
          <>
            <StatusBox type="danger">{pmMsg}</StatusBox>
            <button className="stockcy-btn stockcy-btn-secondary" style={{ marginTop: "1rem", fontSize: "0.8rem", padding: "4px 12px" }} onClick={runAnalysis}>
              <RefreshCw size={12} style={{ marginRight: "6px" }} /> 다시 시도
            </button>
          </>
        ) : pmStatus === "loading" ? (
          <div style={{ padding: "2rem", textAlign: "center", color: "var(--color-muted)" }}>
            <Loader2 className="animate-spin" size={24} style={{ margin: "0 auto 1rem auto" }} />
            <div style={{ marginTop: "1rem" }}>{pmMsg}</div>
          </div>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
            <div style={{ background: "rgba(255,255,255,0.03)", padding: "1rem", borderRadius: "8px" }}>
              <div style={{ fontSize: "0.85rem", color: "var(--color-muted)", marginBottom: "0.5rem" }}>📝 종합 평가</div>
              <div style={{ lineHeight: 1.6, whiteSpace: "pre-line" }}>{pmResult?.evaluation}</div>
            </div>
            <div style={{ background: "rgba(255,255,255,0.03)", padding: "1rem", borderRadius: "8px" }}>
              <div style={{ fontSize: "0.85rem", color: "var(--color-muted)", marginBottom: "0.5rem" }}>🔍 핵심 원인</div>
              <div style={{ lineHeight: 1.6, whiteSpace: "pre-line" }}>{pmResult?.cause}</div>
            </div>
            <div style={{ background: "rgba(99,102,241,0.15)", border: "1px solid rgba(99,102,241,0.3)", padding: "1rem", borderRadius: "8px" }}>
              <div style={{ fontSize: "0.85rem", color: "var(--color-primary)", fontWeight: 700, marginBottom: "0.5rem" }}>💡 학습 포인트 (교훈)</div>
              <div style={{ lineHeight: 1.6, fontWeight: 500, whiteSpace: "pre-line" }}>{pmResult?.learning_point}</div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

// ── 거래 내역 탭 ──────────────────────────────────────────────────────────────
function TradesTab() {
  const { data: tradeRes, isLoading, mutate } = useSWR("/api/trades", () => api.portfolio.loadTrades() as Promise<{ data: any[]; message: string }>);
  const trades: any[] = tradeRes?.data ?? [];

  const [form, setForm] = useState({ ticker: "", name: "", buy_price: "", sell_price: "", quantity: "", result: "수익", trade_source: "개인", trade_type: "실매매" });
  const [addMsg, setAddMsg] = useState<{ type: "success" | "danger"; text: string } | null>(null);
  const [adding, setAdding] = useState(false);
  const [showForm, setShowForm] = useState(false);
  const [postmortemTrade, setPostmortemTrade] = useState<any | null>(null);

  const [filterSource, setFilterSource] = useState<"전체" | "리딩방" | "개인">("전체");
  const [filterType,   setFilterType]   = useState<"전체" | "실매매" | "테스트">("전체");

  const [editTradeKey,    setEditTradeKey]    = useState<string | null>(null);
  const [editSrc,         setEditSrc]         = useState<"리딩방" | "개인">("개인");
  const [editTyp,         setEditTyp]         = useState<"실매매" | "테스트">("실매매");
  const [savingTag,       setSavingTag]       = useState(false);

  const usDates = useMemo(() => {
    return Array.from(new Set(
      trades
        .filter(t => {
          const ticker = String(t["티커"] ?? t.ticker ?? "").trim();
          return ticker !== "" && !ticker.match(/^[0-9]+$/);
        })
        .map(t => String(t["매도시간"] ?? t.sell_date ?? "").slice(0, 10))
        .filter(d => d.length === 10)
    ));
  }, [trades]);

  const { data: fxData } = useSWR(
    "usd-krw-rate-trades",
    () => api.us.exchangeRate(),
    { refreshInterval: 300000 }
  );
  const usdKrwFallback = fxData?.rate ?? 1350;

  const { data: historicalRates, isLoading: isRatesLoading } = useSWR(
    usDates.length > 0 ? `us-historical-rates-${usDates.join(",")}` : null,
    () => api.us.exchangeRatesHistorical(usDates)
  );

  const filteredTrades = useMemo(() => trades.filter(t => {
    const src = t["출처"] ?? t.trade_source ?? "개인";
    const typ = t["유형"] ?? t.trade_type   ?? "실매매";
    if (filterSource !== "전체" && src !== filterSource) return false;
    if (filterType   !== "전체" && typ !== filterType)   return false;
    return true;
  }), [trades, filterSource, filterType]);

  const totalProfit = useMemo(() => {
    return filteredTrades.reduce((sum, t) => {
      const ticker = String(t["티커"] ?? t.ticker ?? "").trim().toUpperCase();
      const isUs = ticker !== "" && !ticker.match(/^[0-9]+$/);
      const p = Number(t["수익금($)"] ?? t.profit ?? 0);
      if (isUs) {
        const d = String(t["매도시간"] ?? t.sell_date ?? "").slice(0, 10);
        const rate = historicalRates?.[d] || usdKrwFallback;
        return sum + (p * rate);
      } else {
        return sum + p;
      }
    }, 0);
  }, [filteredTrades, historicalRates, usdKrwFallback]);

  const winCount = filteredTrades.filter(t => (Number(t["수익금($)"] ?? t.profit ?? 0)) > 0).length;

  const handleAdd = async () => {
    if (!form.ticker || !form.buy_price || !form.sell_price || !form.quantity) return;
    setAdding(true);
    try {
      const bp = Number(form.buy_price);
      const sp = Number(form.sell_price);
      const qty = Number(form.quantity);
      const profit = (sp - bp) * qty;
      const profitPct = bp > 0 ? ((sp - bp) / bp) * 100 : 0;
      const trade = {
        ticker: form.ticker, name: form.name || form.ticker,
        quantity: qty, buy_price: bp, sell_price: sp,
        profit, profit_pct: profitPct,
        result: form.result,
        sell_date: new Date().toISOString().slice(0, 19),
        trade_source: form.trade_source,
        trade_type: form.trade_type,
      };
      const res = await api.portfolio.saveTrade(trade) as { success: boolean; message: string };
      setAddMsg({ type: res.success ? "success" : "danger", text: res.message });
      if (res.success) { setForm({ ticker: "", name: "", buy_price: "", sell_price: "", quantity: "", result: "수익", trade_source: "개인", trade_type: "실매매" }); mutate(); setShowForm(false); }
    } catch (e) { setAddMsg({ type: "danger", text: String(e) }); }
    finally { setAdding(false); }
  };

  const handleUpdateTag = async (ticker: string, sellDate: string) => {
    setSavingTag(true);
    try {
      await (api.portfolio as any).updateTradeTag(ticker, sellDate, editSrc, editTyp);
      mutate();
      setEditTradeKey(null);
    } finally {
      setSavingTag(false);
    }
  };

  const handleDelete = async (ticker: string, sellDate: string) => {
    if (!confirm("이 거래 기록을 삭제하시겠습니까?")) return;
    await api.portfolio.deleteTrade(ticker, sellDate);
    mutate();
  };

  if (isLoading) return <Skeleton height="200px" />;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
      {postmortemTrade && (
        <PostmortemModal trade={postmortemTrade} onClose={() => setPostmortemTrade(null)} onRefresh={() => mutate()} />
      )}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: "0.5rem" }}>
        <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
          {/* 필터 */}
          <div style={{ display: "flex", gap: "0.5rem", alignItems: "center", flexWrap: "wrap" }}>
            <span style={{ fontSize: "0.75rem", color: "var(--color-muted)" }}>출처</span>
            {(["전체", "리딩방", "개인"] as const).map(v => (
              <button key={v} onClick={() => setFilterSource(v)} style={{ padding: "3px 9px", fontSize: "0.75rem", fontWeight: 600, borderRadius: "4px", border: "1px solid var(--color-border)", cursor: "pointer", background: filterSource === v ? (v === "리딩방" ? "#7c3aed" : v === "개인" ? "#2563eb" : "var(--color-elevated)") : "var(--color-surface)", color: filterSource === v ? "#fff" : "var(--color-muted)" }}>{v}</button>
            ))}
            <span style={{ fontSize: "0.75rem", color: "var(--color-muted)", marginLeft: "0.5rem" }}>유형</span>
            {(["전체", "실매매", "테스트"] as const).map(v => (
              <button key={v} onClick={() => setFilterType(v)} style={{ padding: "3px 9px", fontSize: "0.75rem", fontWeight: 600, borderRadius: "4px", border: "1px solid var(--color-border)", cursor: "pointer", background: filterType === v ? (v === "실매매" ? "#059669" : v === "테스트" ? "#d97706" : "var(--color-elevated)") : "var(--color-surface)", color: filterType === v ? "#fff" : "var(--color-muted)" }}>{v}</button>
            ))}
          </div>
          {/* 통계 */}
          <div style={{ display: "flex", gap: "1rem", alignItems: "center" }}>
            <span style={{ fontSize: "0.85rem", color: "var(--color-muted)" }}>{filteredTrades.length}건{filterSource !== "전체" || filterType !== "전체" ? ` / 전체 ${trades.length}건` : ""}</span>
            <span style={{ fontWeight: 700, color: totalProfit >= 0 ? "var(--color-danger)" : "var(--color-primary)" }}>
              누적 손익: {usDates.length > 0 && isRatesLoading ? (
                <span style={{ color: "var(--color-muted)", fontWeight: 400, fontSize: "0.8rem" }}>환율 계산 중...</span>
              ) : (
                `${totalProfit >= 0 ? "+" : ""}₩${Math.round(totalProfit).toLocaleString()}`
              )}
            </span>
            {filteredTrades.length > 0 && <span style={{ fontSize: "0.85rem", color: "var(--color-muted)" }}>승률: {((winCount / filteredTrades.length) * 100).toFixed(0)}%</span>}
          </div>
        </div>
        <button className="stockcy-btn stockcy-btn-secondary" onClick={() => setShowForm(v => !v)}>
          <Plus size={14} /> 거래 기록
        </button>
      </div>

      {showForm && (
        <div style={{ background: "var(--color-surface)", border: "1px solid var(--color-border)", borderRadius: "8px", padding: "1rem", display: "flex", flexDirection: "column", gap: "0.5rem" }}>
          <div style={{ display: "flex", gap: "0.5rem", alignItems: "center", flexWrap: "wrap" }}>
            <span style={{ fontSize: "0.75rem", color: "var(--color-muted)" }}>출처</span>
            <ToggleGroup options={[{ label: "리딩방", value: "리딩방" as const }, { label: "개인", value: "개인" as const }]} value={form.trade_source as "리딩방" | "개인"} onChange={v => setForm(f => ({...f, trade_source: v}))} colors={{ "리딩방": "#7c3aed", "개인": "#2563eb" }} />
            <span style={{ fontSize: "0.75rem", color: "var(--color-muted)" }}>유형</span>
            <ToggleGroup options={[{ label: "실매매", value: "실매매" as const }, { label: "테스트", value: "테스트" as const }]} value={form.trade_type as "실매매" | "테스트"} onChange={v => setForm(f => ({...f, trade_type: v}))} colors={{ "실매매": "#059669", "테스트": "#d97706" }} />
          </div>
          <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
            <input className="stockcy-input" placeholder="티커" value={form.ticker} onChange={e => setForm(f => ({...f, ticker: e.target.value}))} style={{ width: "100px" }} />
            <input className="stockcy-input" placeholder="종목명" value={form.name} onChange={e => setForm(f => ({...f, name: e.target.value}))} style={{ flex: 1, minWidth: "100px" }} />
            <input className="stockcy-input" placeholder="매수가" type="number" value={form.buy_price} onChange={e => setForm(f => ({...f, buy_price: e.target.value}))} style={{ width: "100px" }} />
            <input className="stockcy-input" placeholder="매도가" type="number" value={form.sell_price} onChange={e => setForm(f => ({...f, sell_price: e.target.value}))} style={{ width: "100px" }} />
            <input className="stockcy-input" placeholder="수량" type="number" value={form.quantity} onChange={e => setForm(f => ({...f, quantity: e.target.value}))} style={{ width: "80px" }} />
            <select className="stockcy-input" value={form.result} onChange={e => setForm(f => ({...f, result: e.target.value}))} style={{ width: "80px" }}>
              <option>수익</option>
              <option>손실</option>
              <option>손익분기</option>
            </select>
            <button className="stockcy-btn stockcy-btn-primary" onClick={handleAdd} disabled={adding}>저장</button>
          </div>
          {addMsg && <StatusBox type={addMsg.type}>{addMsg.text}</StatusBox>}
        </div>
      )}

      {trades.length === 0 ? (
        <StatusBox type="info">거래 내역이 없습니다. 매도 시 기록을 추가해보세요.</StatusBox>
      ) : (
        <table className="stockcy-table">
          <thead>
            <tr>
              <th>종목</th>
              <th style={{ textAlign: "right" }}>매수가</th>
              <th style={{ textAlign: "right" }}>매도가</th>
              <th style={{ textAlign: "right" }}>수량</th>
              <th style={{ textAlign: "right" }}>손익</th>
              <th style={{ textAlign: "right" }}>손익률</th>
              <th>결과</th>
              <th>매도일</th>
              <th>학습/복기</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {filteredTrades.map((t, i) => {
              const profit    = Number(t["수익금($)"] ?? t.profit ?? 0);
              const profitPct = Number(t["수익률(%)"] ?? t.profit_pct ?? 0);
              const color     = profit >= 0 ? "var(--color-danger)" : "var(--color-primary)";
              const ticker    = String(t["티커"] ?? t.ticker ?? "").trim().toUpperCase();
              const isUs      = ticker !== "" && !ticker.match(/^[0-9]+$/);
              const sellDate  = String(t["매도시간"] ?? t.sell_date ?? "");
              const lp        = t["학습포인트"] ?? t.learning_point;

              const buyPrice  = Number(t["매수가($)"] ?? t.buy_price ?? 0);
              const sellPrice = Number(t["매도가($)"] ?? t.sell_price ?? 0);

              const buyStr    = isUs ? `$${buyPrice.toFixed(2)}` : `₩${Math.round(buyPrice).toLocaleString()}`;
              const sellStr   = isUs ? `$${sellPrice.toFixed(2)}` : `₩${Math.round(sellPrice).toLocaleString()}`;
              const profitStr = isUs ? `$${profit.toFixed(2)}` : `₩${Math.round(profit).toLocaleString()}`;

              const d = sellDate.slice(0, 10);
              const rate = isUs ? (historicalRates?.[d] || usdKrwFallback) : 1;
              const profitKrw = profit * rate;
              const tradeSource = t["출처"] ?? t.trade_source ?? "개인";
              const tradeType   = t["유형"] ?? t.trade_type   ?? "실매매";
              const rowKey = `${ticker}_${sellDate}`;
              const isEditingTag = editTradeKey === rowKey;

              return (
                <>
                  <tr key={i}>
                    <td style={{ fontWeight: 600 }}>
                      <div style={{ display: "flex", alignItems: "center", gap: "4px", flexWrap: "wrap" }}>
                        <span>{String(t["종목명"] ?? t.name ?? "")}</span>
                        <span style={{ fontSize: "0.72rem", color: "var(--color-muted)" }}>({ticker})</span>
                        {tradeSource === "리딩방" && (
                          <span style={{ fontSize: "0.62rem", padding: "1px 5px", background: "rgba(124,58,237,0.15)", border: "1px solid rgba(124,58,237,0.35)", borderRadius: "3px", color: "#a78bfa", fontWeight: 700 }}>리딩방</span>
                        )}
                        {tradeType === "테스트" && (
                          <span style={{ fontSize: "0.62rem", padding: "1px 5px", background: "rgba(217,119,6,0.15)", border: "1px solid rgba(217,119,6,0.35)", borderRadius: "3px", color: "#fbbf24", fontWeight: 700 }}>테스트</span>
                        )}
                      </div>
                    </td>
                    <td style={{ textAlign: "right" }}>{buyStr}</td>
                    <td style={{ textAlign: "right" }}>{sellStr}</td>
                    <td style={{ textAlign: "right" }}>{Number(t["수량"] ?? t.quantity ?? 0).toLocaleString()}주</td>
                    <td style={{ textAlign: "right", color, fontWeight: 600 }}>
                      {profit >= 0 ? "+" : ""}{profitStr}
                      {isUs && (
                        <div style={{ fontSize: "0.68rem", color: "var(--color-muted)", fontWeight: 400 }}>
                          {isRatesLoading ? "환율 계산 중..." : `≈${profit >= 0 ? "+" : ""}₩${Math.round(profitKrw).toLocaleString()}`}
                        </div>
                      )}
                    </td>
                    <td style={{ textAlign: "right", color, fontWeight: 700 }}>{profitPct >= 0 ? "+" : ""}{profitPct.toFixed(2)}%</td>
                    <td><Badge variant={profit >= 0 ? "success" : "danger"}>{String(t["결과"] ?? t.result ?? "-")}</Badge></td>
                    <td style={{ fontSize: "0.75rem", color: "var(--color-muted)" }}>{sellDate.slice(0, 10)}</td>
                    <td>
                      {lp ? (
                        <div style={{ fontSize: "0.75rem", color: "var(--color-primary)", maxWidth: "150px", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", cursor: "pointer" }} title={lp} onClick={() => setPostmortemTrade(t)}>
                          💡 {lp}
                        </div>
                      ) : (
                        <button className="stockcy-btn stockcy-btn-primary" style={{ padding: "2px 6px", fontSize: "0.7rem", background: "transparent", border: "1px solid var(--color-primary)", color: "var(--color-primary)" }} onClick={() => setPostmortemTrade(t)}>
                          <Brain size={10} style={{ marginRight: "4px" }} /> AI 복기
                        </button>
                      )}
                    </td>
                    <td>
                      <div style={{ display: "flex", gap: "3px" }}>
                        <button
                          className="stockcy-btn stockcy-btn-secondary"
                          style={{ padding: "2px 6px", fontSize: "0.7rem", color: isEditingTag ? "var(--color-accent)" : undefined }}
                          title="출처/유형 편집"
                          onClick={() => {
                            if (isEditingTag) { setEditTradeKey(null); return; }
                            setEditSrc((tradeSource as "리딩방" | "개인") || "개인");
                            setEditTyp((tradeType as "실매매" | "테스트") || "실매매");
                            setEditTradeKey(rowKey);
                          }}
                        >✏️</button>
                        <button className="stockcy-btn stockcy-btn-secondary" style={{ padding: "2px 6px", fontSize: "0.7rem" }} onClick={() => handleDelete(ticker, sellDate)}>
                          <Trash2 size={10} />
                        </button>
                      </div>
                    </td>
                  </tr>
                  {isEditingTag && (
                    <tr key={`${i}_edit`} style={{ background: "rgba(0,0,0,0.25)" }}>
                      <td colSpan={10} style={{ padding: "8px 12px" }}>
                        <div style={{ display: "flex", alignItems: "center", gap: "0.6rem", flexWrap: "wrap" }}>
                          <span style={{ fontSize: "0.75rem", color: "var(--color-muted)" }}>출처</span>
                          <ToggleGroup
                            options={[{ label: "리딩방", value: "리딩방" as const }, { label: "개인", value: "개인" as const }]}
                            value={editSrc} onChange={setEditSrc}
                            colors={{ "리딩방": "#7c3aed", "개인": "#2563eb" }}
                          />
                          <span style={{ fontSize: "0.75rem", color: "var(--color-muted)", marginLeft: "0.25rem" }}>유형</span>
                          <ToggleGroup
                            options={[{ label: "실매매", value: "실매매" as const }, { label: "테스트", value: "테스트" as const }]}
                            value={editTyp} onChange={setEditTyp}
                            colors={{ "실매매": "#059669", "테스트": "#d97706" }}
                          />
                          <button className="stockcy-btn stockcy-btn-primary" style={{ padding: "3px 10px", fontSize: "0.78rem" }} disabled={savingTag} onClick={() => handleUpdateTag(ticker, sellDate)}>
                            {savingTag ? "저장 중..." : "저장"}
                          </button>
                          <button className="stockcy-btn stockcy-btn-secondary" style={{ padding: "3px 8px", fontSize: "0.78rem" }} onClick={() => setEditTradeKey(null)}>취소</button>
                        </div>
                      </td>
                    </tr>
                  )}
                </>
              );
            })}
          </tbody>
        </table>
      )}
    </div>
  );
}

// ── 가격 알림 탭 ──────────────────────────────────────────────────────────────
function AlertCircleIcon() {
  return <AlertCircle size={14} style={{ color: "var(--color-danger)" }} />;
}

function AlertsTab() {
  const { data: alerts, isLoading, mutate } = useSWR<any[]>("/api/alerts", () => api.portfolio.loadAlerts() as Promise<any[]>);
  const [form, setForm] = useState({ market: "국내", ticker: "", name: "", alert_type: "목표가 도달", target_price: "" });
  const [msg, setMsg] = useState<{ type: "success" | "danger"; text: string } | null>(null);
  const [loading, setLoading] = useState(false);

  const handleAdd = async () => {
    if (!form.ticker || !form.target_price) return;
    setLoading(true);
    try {
      const res = await api.portfolio.saveAlert(form.market, form.ticker, form.name || form.ticker, form.alert_type, Number(form.target_price)) as { success: boolean; message: string };
      setMsg({ type: res.success ? "success" : "danger", text: res.message });
      if (res.success) { setForm(f => ({...f, ticker: "", name: "", target_price: ""})); mutate(); }
    } catch (e) { setMsg({ type: "danger", text: String(e) }); }
    finally { setLoading(false); }
  };

  const handleDelete = async (ticker: string, alertType: string) => {
    await api.portfolio.deleteAlert(ticker, alertType);
    mutate();
  };

  if (isLoading) return <Skeleton height="150px" />;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
      {/* 추가 폼 */}
      <div style={{ background: "var(--color-surface)", border: "1px solid var(--color-border)", borderRadius: "8px", padding: "1rem", display: "flex", flexDirection: "column", gap: "0.5rem" }}>
        <div style={{ fontWeight: 700, fontSize: "0.9rem", marginBottom: "0.25rem" }}>🔔 새 알림 설정</div>
        <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
          <select className="stockcy-input" style={{ width: "80px" }} value={form.market} onChange={e => setForm(f => ({...f, market: e.target.value}))}>
            <option>국내</option>
            <option>미국</option>
          </select>
          <input className="stockcy-input" placeholder="티커 (예: 005930)" value={form.ticker} onChange={e => setForm(f => ({...f, ticker: e.target.value}))} style={{ width: "130px" }} />
          <input className="stockcy-input" placeholder="종목명" value={form.name} onChange={e => setForm(f => ({...f, name: e.target.value}))} style={{ flex: 1, minWidth: "100px" }} />
          <select className="stockcy-input" style={{ width: "130px" }} value={form.alert_type} onChange={e => setForm(f => ({...f, alert_type: e.target.value}))}>
            <option>목표가 도달</option>
            <option>손절가 도달</option>
            <option>상한가 진입</option>
            <option>하한가 진입</option>
          </select>
          <input className="stockcy-input" placeholder="목표가" type="number" value={form.target_price} onChange={e => setForm(f => ({...f, target_price: e.target.value}))} style={{ width: "100px" }} />
          <button className="stockcy-btn stockcy-btn-primary" onClick={handleAdd} disabled={loading || !form.ticker || !form.target_price}>
            <Bell size={14} /> 설정
          </button>
        </div>
        {msg && <StatusBox type={msg.type}>{msg.text}</StatusBox>}
        <div style={{ fontSize: "0.75rem", color: "var(--color-muted)" }}>※ 알림 트리거는 텔레그램으로 발송됩니다. 실시간 감지는 백엔드 스케줄러가 필요합니다.</div>
      </div>

      {!alerts || alerts.length === 0 ? (
        <StatusBox type="info">설정된 알림이 없습니다.</StatusBox>
      ) : (
        <table className="stockcy-table">
          <thead>
            <tr>
              <th>종목</th>
              <th>시장</th>
              <th>알림 유형</th>
              <th style={{ textAlign: "right" }}>목표가</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {alerts.map((a, i) => (
              <tr key={i}>
                <td style={{ fontWeight: 600 }}>{a.name} <span style={{ fontSize: "0.72rem", color: "var(--color-muted)" }}>({a.ticker})</span></td>
                <td><Badge variant={a.market === "국내" ? "info" : "success"}>{a.market}</Badge></td>
                <td>{a.alert_type}</td>
                <td style={{ textAlign: "right", fontWeight: 700 }}>
                  {a.market === "국내" ? `₩${Number(a.target_price).toLocaleString()}` : `$${Number(a.target_price).toFixed(2)}`}
                </td>
                <td>
                  <button className="stockcy-btn stockcy-btn-secondary" style={{ padding: "2px 6px", fontSize: "0.7rem" }} onClick={() => handleDelete(a.ticker, a.alert_type)}>
                    <Trash2 size={10} />
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

// ── 메인 페이지 ───────────────────────────────────────────────────────────────
const TABS = [
  { id: "favorites", label: "⭐ 즐겨찾기",   icon: <Star size={14} /> },
  { id: "portfolio", label: "📊 보유 종목",   icon: <TrendingUp size={14} /> },
  { id: "trades",    label: "📋 거래 내역",   icon: <BookOpen size={14} /> },
  { id: "alerts",    label: "🔔 가격 알림",   icon: <Bell size={14} /> },
] as const;
type TabId = typeof TABS[number]["id"];

export default function FavoritesPage() {
  const [tab, setTab] = useState<TabId>("favorites");
  const [selectedStock, setSelectedStock] = useState<StockInfo | null>(null);

  const { data: favs, mutate: refetchFavs, isLoading } = useSWR("favorites", () => api.portfolio.loadFavorites() as Promise<Favorite[]>);
  const brief = useSSE<{ success: boolean; msg: string }>("/api/admin/daily-brief/send", { method: "POST" });

  const krTickers = (favs ?? []).filter(f => f["시장"] === "국내").map(f => f["티커"]);
  const usTickers = (favs ?? []).filter(f => f["시장"] === "미국").map(f => f["티커"]);

  // 시간외 갭 예측 관리 상태
  const [gapBulkMap, setGapBulkMap] = useState<Record<string, any>>({});
  const [gapBulkStatus, setGapBulkStatus] = useState<"idle" | "loading" | "done">("idle");
  const [gapBulkMsg, setGapBulkMsg] = useState("");

  type PriceEntry = { price: number; change_pct: number; w52_high?: number; w52_low?: number };

  const { data: krPriceMap } = useSWR(
    krTickers.length > 0 ? `kr-fav-prices-${krTickers.join(",")}` : null,
    async () => {
      const map: Record<string, PriceEntry> = {};
      await Promise.all(krTickers.map(async (code) => {
        try {
          const d = await api.kr.stockPrice(code) as KrStock;
          if (d?.price) map[code] = { price: d.price, change_pct: d.change_pct, w52_high: d.w52_high, w52_low: d.w52_low };
        } catch {}
      }));
      return map;
    },
    { refreshInterval: 60000 }
  );

  const { data: usPriceMap } = useSWR(
    usTickers.length > 0 ? `us-fav-prices-${usTickers.join(",")}` : null,
    async () => {
      const arr = await api.us.stocks(usTickers) as UsStock[];
      const map: Record<string, PriceEntry> = {};
      for (const s of (arr ?? [])) map[s["심볼"]] = { price: s["현재가($)"], change_pct: s["등락률(%)"] };
      return map;
    },
    { refreshInterval: 60000 }
  );

  const priceMap: Record<string, PriceEntry> = { ...(krPriceMap ?? {}), ...(usPriceMap ?? {}) };

  const handleRemove = async (ticker: string) => {
    await api.portfolio.removeFavorite(ticker);
    refetchFavs();
  };

  // 관심 및 보유 종목의 시간외 갭을 수집해 일괄적으로 캐시 조회 및 실시간 RAG 스캔 가동
  const handleGapBulkScan = async () => {
    // 1. 모든 감시 대상 티커 추출 (즐겨찾기 + 포트폴리오)
    const portfolioRes = await api.portfolio.loadPortfolio().catch(() => []) as any[];
    const allTickers = Array.from(new Set([
      ...(favs ?? []).map(f => f["티커"].toUpperCase().trim()),
      ...portfolioRes.map(p => p.ticker.toUpperCase().trim())
    ])).filter(Boolean);

    if (allTickers.length === 0) return;

    setGapBulkStatus("loading");
    setGapBulkMsg("🌙 시간외 갭 분석 작동 중...");

    try {
      // (1) 백엔드 캐시 고속 체크
      const bulkRes = await api.ai.overnightGapBulk(allTickers);
      const initialMap = { ...(bulkRes.results ?? {}) };
      setGapBulkMap(initialMap);

      // (2) 캐시 만료 혹은 미분석된 종목만 순차 실시간 RAG 스캐닝 가동
      const unanalyzed = allTickers.filter(t => !initialMap[t]);
      if (unanalyzed.length > 0) {
        for (let i = 0; i < unanalyzed.length; i++) {
          const ticker = unanalyzed[i];
          const isKr = /^\d+$/.test(ticker);
          setGapBulkMsg(`📡 [${i + 1}/${unanalyzed.length}] ${ticker} 뉴스 및 시간외 공시 추적 중...`);

          try {
            // 개별 갭 RAG API 동기식 처리 (SSE 스트림 읽기)
            const singleRes = await fetch(`${BASE_URL}/api/ai/overnight-gap`, {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({
                ticker: isKr ? ticker.padStart(6, "0") : ticker,
                name: ticker,
                market: isKr ? "국내" : "미국"
              })
            });

            if (singleRes.ok && singleRes.body) {
              const reader = singleRes.body.getReader();
              const dec = new TextDecoder();
              let buf = "";
              while (true) {
                const { done, value } = await reader.read();
                if (done) break;
                buf += dec.decode(value, { stream: true });
                const parts = buf.split("\n\n");
                buf = parts.pop() ?? "";
                for (const part of parts) {
                  if (part.trim().startsWith("data:")) {
                    try {
                      const d = JSON.parse(part.trim().slice(5).trim());
                      if (d.status === "done" && d.result) {
                        initialMap[ticker] = d.result;
                        setGapBulkMap({ ...initialMap });
                      }
                    } catch {}
                  }
                }
              }
            }
          } catch {}
        }
      }
      setGapBulkStatus("done");
      setGapBulkMsg("🌙 시간외 갭 일괄 스캔이 완료되었습니다!");
    } catch (err: any) {
      setGapBulkStatus("done");
      setGapBulkMsg(`❌ 갭 스캔 오류: ${err.message}`);
    }
  };

  // 장 마감 이후 시간외 시점에 자동으로 백그라운드 캐시 고속 체크 실행
  useEffect(() => {
    const checkHolidaysAndCachedGaps = async () => {
      if (!favs || favs.length === 0) return;
      const portfolioRes = await api.portfolio.loadPortfolio().catch(() => []) as any[];
      const allTickers = Array.from(new Set([
        ...favs.map(f => f["티커"].toUpperCase().trim()),
        ...portfolioRes.map(p => p.ticker.toUpperCase().trim())
      ])).filter(Boolean);

      try {
        const bulkRes = await api.ai.overnightGapBulk(allTickers);
        if (bulkRes?.results) {
          setGapBulkMap(bulkRes.results);
        }
      } catch {}
    };

    if (favs && favs.length > 0) {
      checkHolidaysAndCachedGaps();
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [favs]);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "1.25rem" }}>
      {selectedStock && <StockModal stock={selectedStock} onClose={() => setSelectedStock(null)} />}

      {/* 헤더 */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: "8px" }}>
        <h1 style={{ fontSize: "1.05rem", fontWeight: 700, display: "flex", alignItems: "center", gap: "0.5rem" }}>
          <Star size={18} style={{ color: "var(--color-accent)" }} /> 즐겨찾기 & 포트폴리오 관리
        </h1>
        <div style={{ display: "flex", gap: "6px" }}>
          {/* 일괄 시간외 갭 예측 스캐너 작동 버튼 */}
          <button 
            className="stockcy-btn"
            onClick={handleGapBulkScan}
            disabled={gapBulkStatus === "loading"}
            style={{ 
              padding: "6px 12px", 
              fontSize: "0.78rem", 
              background: "rgba(245, 158, 11, 0.15)", 
              border: "1px solid rgba(245, 158, 11, 0.3)", 
              color: "#fbbf24",
              display: "flex",
              alignItems: "center",
              gap: "4px",
              fontWeight: "bold"
            }}
          >
            {gapBulkStatus === "loading" ? (
              <>
                <Loader2 size={13} className="animate-spin" />
                분석 중...
              </>
            ) : (
              <>
                <Sparkles size={13} />
                🌙 시간외 갭 일괄 분석
              </>
            )}
          </button>

          <button className="stockcy-btn stockcy-btn-secondary" onClick={() => refetchFavs()}>
            <RefreshCw size={13} /> 새로고침
          </button>
        </div>
      </div>

      {/* 일괄 분석 진행률 정보창 */}
      {gapBulkMsg && (
        <div 
          style={{ 
            fontSize: "0.75rem", 
            background: "rgba(0,0,0,0.3)", 
            padding: "8px 12px", 
            borderRadius: "6px", 
            border: "1px solid var(--color-border)",
            color: "var(--color-subtle)",
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between"
          }}
        >
          <span>{gapBulkMsg}</span>
          <button style={{ background: "none", border: "none", color: "var(--color-muted)", cursor: "pointer", fontSize: "0.75rem" }} onClick={() => setGapBulkMsg("")}>✕</button>
        </div>
      )}

      {/* 탭 네비 */}
      <div style={{ display: "flex", gap: "6px", borderBottom: "1px solid var(--color-border)", paddingBottom: "2px" }}>
        {TABS.map(({ id, label }) => (
          <button
            key={id}
            onClick={() => setTab(id)}
            style={{
              padding: "6px 14px", fontWeight: 600, fontSize: "0.85rem",
              background: "transparent", border: "none", cursor: "pointer",
              color: tab === id ? "var(--color-text)" : "var(--color-muted)",
              borderBottom: tab === id ? "2px solid var(--color-accent)" : "2px solid transparent",
            }}
          >
            {label}
          </button>
        ))}
      </div>

      {/* 즐겨찾기 탭 */}
      {tab === "favorites" && (
        <>
          <Card title={`즐겨찾기 종목 (${favs?.length ?? 0}개)`}>
            <AddFavoriteForm onAdded={() => refetchFavs()} />
            <div className="stockcy-divider" />
            {isLoading ? <Skeleton height="150px" /> : !favs || favs.length === 0 ? (
              <StatusBox type="info">즐겨찾기에 등록된 종목이 없습니다.</StatusBox>
            ) : (
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(240px, 1fr))", gap: "10px" }}>
                {favs.map((f) => (
                  <FavRow key={f["티커"]} fav={f} price={priceMap[f["티커"]] ?? null} onRemove={handleRemove} onAnalyze={setSelectedStock} gapBulkMap={gapBulkMap} />
                ))}
              </div>
            )}
          </Card>

          <Card title={<span style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}><Send size={15} style={{ color: "var(--color-accent)" }} />텔레그램 장 마감 브리핑</span>}>
            <SSEPanel<{ success: boolean; msg: string }>
              status={brief.status} message={brief.message} result={brief.result}
              onStart={() => brief.start({ favorites: favs ?? [] })} startLabel="브리핑 발송"
              disabled={!favs || favs.length === 0}
              idleHint={favs && favs.length > 0
                ? `즐겨찾기 ${favs.length}개 종목의 시세와 최신 매크로 뉴스를 반영한 AI 리포트를 텔레그램으로 발송합니다.`
                : "즐겨찾기 종목을 먼저 추가해주세요."}
            >
              {(data) => <StatusBox type={data.success ? "success" : "danger"}>{data.msg}</StatusBox>}
            </SSEPanel>
          </Card>
        </>
      )}

      {tab === "portfolio" && <Card title="📊 보유 종목 현황"><PortfolioTab gapBulkMap={gapBulkMap} /></Card>}
      {tab === "trades"    && <Card title="📋 거래 내역"><TradesTab /></Card>}
      {tab === "alerts"    && <Card title="🔔 가격 알림 설정"><AlertsTab /></Card>}
    </div>
  );
}
