"use client";
import { useState, useMemo } from "react";
import { useRouter } from "next/navigation";
import useSWR from "swr";
import { api } from "@/lib/api";
import type { Favorite, KrStock, UsStock } from "@/lib/types";
import { Star, RefreshCw, Send, Trash2, Plus, Zap, BarChart2, Bell, TrendingUp, BookOpen, Loader2 } from "lucide-react";

const BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
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
function FavRow({ fav, price, onRemove, onAnalyze }: {
  fav: Favorite;
  price?: { price: number; change_pct: number; w52_high?: number; w52_low?: number } | null;
  onRemove: (ticker: string) => void;
  onAnalyze: (s: StockInfo) => void;
}) {
  const router = useRouter();
  const isKr   = fav["시장"] === "국내";
  const pct    = price?.change_pct ?? null;
  const up     = (pct ?? 0) > 0;
  const down   = (pct ?? 0) < 0;
  const color  = up ? "var(--color-up)" : down ? "var(--color-down)" : "var(--color-flat)";
  const status = getStatusInfo(pct, price?.price, price?.w52_high, price?.w52_low);

  return (
    <div style={{
      background: "var(--color-surface)",
      border: "1px solid var(--color-border)",
      borderRadius: "10px",
      padding: "12px 14px",
      display: "flex", flexDirection: "column", gap: "8px",
    }}>
      {/* 제목 행 */}
      <div style={{ display: "flex", alignItems: "center", gap: "5px" }}>
        <Star size={12} style={{ color: "var(--color-warning)", fill: "var(--color-warning)", flexShrink: 0 }} />
        <span style={{ fontWeight: 700, fontSize: "0.9rem" }}>{fav["종목명"]}</span>
        <span style={{ fontSize: "0.7rem", color: "var(--color-muted)" }}>({fav["티커"]})</span>
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
function RecommendBadge({ pct }: { pct: number }) {
  if (pct >= 10)       return <Badge variant="danger">🔴 수익실현 대기</Badge>;
  if (pct >= 3)        return <Badge variant="success">🟢 보유 유지</Badge>;
  if (pct >= -3)       return <Badge variant="info">🔵 보유 유지</Badge>;
  if (pct >= -10)      return <Badge variant="warning">🟡 추가매수 검토</Badge>;
  return                      <Badge variant="danger">⚠️ 물타기 필요</Badge>;
}

// ── 보유 종목 추가 폼 ─────────────────────────────────────────────────────────
function AddPortfolioForm({ onAdded }: { onAdded: () => void }) {
  const [market, setMarket] = useState<"국내" | "미국">("미국");
  const [ticker, setTicker] = useState("");
  const [name,   setName]   = useState("");
  const [price,  setPrice]  = useState("");
  const [qty,    setQty]    = useState("");
  const [msg,    setMsg]    = useState<{ type: "success" | "danger"; text: string } | null>(null);
  const [loading, setLoading] = useState(false);

  const handleAdd = async () => {
    if (!ticker.trim() || !name.trim() || !price || !qty) return;
    setLoading(true);
    try {
      const currentList = await api.portfolio.loadPortfolio() as any[];
      const updatedList = [...(currentList ?? []), {
        ticker: ticker.trim().toUpperCase(),
        name: name.trim(),
        buy_price: Number(price),
        quantity: Number(qty),
        rating: "-",
      }];
      const res = await fetch(`${BASE_URL}/api/portfolio`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ portfolio_list: updatedList }),
      });
      if (!res.ok) throw new Error(`서버 오류: ${res.status}`);
      setMsg({ type: "success", text: `${name.trim()} (${ticker.trim().toUpperCase()}) 추가 완료` });
      setTicker(""); setName(""); setPrice(""); setQty("");
      onAdded();
    } catch (e) {
      setMsg({ type: "danger", text: String(e) });
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ background: "var(--color-surface)", border: "1px solid var(--color-border)", borderRadius: "8px", padding: "1rem", marginBottom: "1rem", display: "flex", flexDirection: "column", gap: "0.5rem" }}>
      <div style={{ fontWeight: 700, fontSize: "0.9rem", marginBottom: "0.25rem" }}>+ 보유 종목 추가</div>
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
function PortfolioTab() {
  const { data: portfolio, isLoading, mutate } = useSWR<any[]>("/api/portfolio", () => api.portfolio.loadPortfolio() as Promise<any[]>);

  // KR/US 종목 분류 (1~6자리 숫자 = KR, 6자리로 패딩)
  const isKrCode  = (t: string) => /^\d{1,6}$/.test(String(t));
  const padKr     = (t: string) => String(t).padStart(6, "0");
  const krItems   = (portfolio ?? []).filter(p => isKrCode(p.ticker));
  const krTickers = krItems.map(p => padKr(p.ticker));
  const usTickers = (portfolio ?? []).filter(p => !isKrCode(p.ticker)).map(p => p.ticker);

  // KR 현재가
  const { data: krPrices } = useSWR(
    krTickers.length > 0 ? `kr-port-prices-${krTickers.join(",")}` : null,
    async () => {
      const map: Record<string, number> = {};
      await Promise.all(krTickers.map(async (code) => {
        try {
          const paddedCode = String(code).padStart(6, "0");
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
        if (ticker) map[ticker] = s["현재가($)"] ?? s.price ?? 0;
      }
      return map;
    },
    { refreshInterval: 60000 }
  );

  // USD/KRW 환율
  const { data: fxData } = useSWR(
    usTickers.length > 0 ? "usd-krw-rate" : null,
    () => api.us.exchangeRate(),
    { refreshInterval: 300000 }  // 5분마다 갱신
  );
  const usdKrw = fxData?.rate ?? 1350;

  const enriched = useMemo(() => {
    return (portfolio ?? []).map(p => {
      const isUs = !isKrCode(p.ticker);
      const normalTicker = isUs ? p.ticker : padKr(p.ticker);
      const livePriceMap = isUs ? (usPrices ?? {}) : (krPrices ?? {});
      const currentPrice = livePriceMap[normalTicker] ?? livePriceMap[p.ticker] ?? p.buy_price ?? 0;
      const cost = (p.buy_price ?? 0) * (p.quantity ?? 0);
      const value = currentPrice * (p.quantity ?? 0);
      const profit = value - cost;
      const profitPct = cost > 0 ? (profit / cost) * 100 : 0;
      // KRW 환산 (US 종목만)
      const costKrw  = isUs ? cost  * usdKrw : cost;
      const valueKrw = isUs ? value * usdKrw : value;
      return { ...p, isUs, normalTicker, currentPrice, cost, value, profit, profitPct, costKrw, valueKrw };
    });
  }, [portfolio, krPrices, usPrices, usdKrw]);

  const totalCostKrw   = enriched.reduce((s, p) => s + p.costKrw, 0);
  const totalValueKrw  = enriched.reduce((s, p) => s + p.valueKrw, 0);
  const totalProfitKrw = totalValueKrw - totalCostKrw;
  const hasUsItems     = enriched.some(p => p.isUs);

  // 편집 상태
  const [editTicker, setEditTicker] = useState<string | null>(null);
  const [editPrice,  setEditPrice]  = useState<string>("");
  const [editQty,    setEditQty]    = useState<string>("");

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

  const handleSellRecord = async (p: any, sellPrice: number) => {
    const qty = Number(p.quantity ?? 0);
    const bp  = Number(p.buy_price ?? 0);
    const profit = (sellPrice - bp) * qty;
    const profitPct = bp > 0 ? ((sellPrice - bp) / bp) * 100 : 0;
    await api.portfolio.saveTrade({
      ticker: p.ticker, name: p.name, quantity: qty,
      buy_price: bp, sell_price: sellPrice,
      profit, profit_pct: profitPct,
      result: profit >= 0 ? "수익" : "손실",
      sell_date: new Date().toISOString().slice(0, 19),
    });
    mutate();
  };

  const handleUpdateEntry = async (p: any) => {
    const newBuy = Number(editPrice) || p.buy_price;
    const newQty = Number(editQty)   || p.quantity;
    const updated = (portfolio ?? []).map((item: any) =>
      item.ticker === p.ticker ? { ...item, buy_price: newBuy, quantity: newQty } : item
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
          <div style={{ display: "grid", gridTemplateColumns: "2fr 1fr 1fr 0.7fr 1fr 0.8fr 1.2fr auto", gap: "6px", padding: "8px 12px", fontSize: "0.75rem", color: "var(--color-muted)", fontWeight: 600, borderBottom: "1px solid var(--color-border)" }}>
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

            return (
              <div key={i} style={{ borderBottom: "1px solid rgba(255,255,255,0.04)" }}>
                <div style={{ display: "grid", gridTemplateColumns: "2fr 1fr 1fr 0.7fr 1fr 0.8fr 1.2fr auto", gap: "6px", padding: "10px 12px", alignItems: "center", fontSize: "0.85rem" }}>
                  <div style={{ fontWeight: 600 }}>
                    {p.name || p.normalTicker || p.ticker}
                    <span style={{ fontSize: "0.72rem", color: "var(--color-muted)", marginLeft: "4px" }}>
                      ({p.normalTicker || p.ticker})
                    </span>
                    {p.isUs && <span style={{ marginLeft: "4px", fontSize: "0.65rem", padding: "1px 5px", background: "rgba(50,200,100,0.15)", border: "1px solid rgba(50,200,100,0.3)", borderRadius: "3px", color: "var(--color-success)" }}>US</span>}
                  </div>
                  <div style={{ textAlign: "right" }}>{buyStr}</div>
                  <div style={{ textAlign: "right", fontWeight: 600 }}>
                    {p.currentPrice > 0 ? priceStr : <span style={{ color: "var(--color-muted)" }}>로딩중...</span>}
                  </div>
                  <div style={{ textAlign: "right" }}>{Number(p.quantity ?? 0).toLocaleString()}주</div>
                  <div style={{ textAlign: "right", color, fontWeight: 600 }}>
                    {profitStr}
                    {profitKrwHint && (
                      <div style={{ fontSize: "0.68rem", color: "var(--color-muted)", fontWeight: 400 }}>{profitKrwHint}</div>
                    )}
                  </div>
                  <div style={{ textAlign: "right", color, fontWeight: 700 }}>
                    {p.profitPct >= 0 ? "+" : ""}{p.profitPct.toFixed(2)}%
                  </div>
                  <div style={{ textAlign: "center" }}><RecommendBadge pct={p.profitPct} /></div>
                  <div style={{ display: "flex", gap: "4px", flexWrap: "wrap" }}>
                    <button className="stockcy-btn stockcy-btn-secondary" style={{ padding: "2px 6px", fontSize: "0.7rem" }} title="AI 매도 타이밍" onClick={() => openSellAnalysis(p)}>
                      AI
                    </button>
                    <button className="stockcy-btn stockcy-btn-secondary" style={{ padding: "2px 6px", fontSize: "0.7rem" }} title="편집"
                      onClick={() => { setEditTicker(isEditing ? null : p.ticker); setEditPrice(String(p.buy_price)); setEditQty(String(p.quantity)); }}>
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
                  <div style={{ background: "rgba(0,0,0,0.3)", padding: "10px 12px", display: "flex", gap: "0.5rem", alignItems: "center", flexWrap: "wrap" }}>
                    <label style={{ fontSize: "0.8rem", color: "var(--color-muted)" }}>평단가</label>
                    <input className="stockcy-input" type="number" value={editPrice} onChange={e => setEditPrice(e.target.value)} style={{ width: "100px" }} />
                    <label style={{ fontSize: "0.8rem", color: "var(--color-muted)" }}>수량</label>
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
function SellButton({ p, onSell }: { p: any; onSell: (p: any, price: number) => Promise<void> }) {
  const [open, setOpen] = useState(false);
  const [price, setPrice] = useState(String(p.currentPrice || p.buy_price || ""));
  const [saving, setSaving] = useState(false);

  const handleSell = async () => {
    const sp = Number(price);
    if (!sp) return;
    setSaving(true);
    await onSell(p, sp);
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
      <input className="stockcy-input" type="number" value={price} onChange={e => setPrice(e.target.value)} style={{ width: "100px" }} />
      <button className="stockcy-btn stockcy-btn-primary" style={{ padding: "4px 8px", fontSize: "0.8rem" }} onClick={handleSell} disabled={saving}>
        {saving ? "저장중..." : "확정"}
      </button>
      <button className="stockcy-btn stockcy-btn-secondary" style={{ padding: "4px 8px", fontSize: "0.8rem" }} onClick={() => setOpen(false)}>취소</button>
    </div>
  );
}

// ── 거래 내역 탭 ──────────────────────────────────────────────────────────────
function TradesTab() {
  const { data: tradeRes, isLoading, mutate } = useSWR("/api/trades", () => api.portfolio.loadTrades() as Promise<{ data: any[]; message: string }>);
  const trades: any[] = tradeRes?.data ?? [];

  // 신규 거래 기록 폼
  const [form, setForm] = useState({ ticker: "", name: "", buy_price: "", sell_price: "", quantity: "", result: "수익" });
  const [addMsg, setAddMsg] = useState<{ type: "success" | "danger"; text: string } | null>(null);
  const [adding, setAdding] = useState(false);
  const [showForm, setShowForm] = useState(false);

  const totalProfit = trades.reduce((s, t) => s + (Number(t["수익금($)"] ?? t.profit ?? 0)), 0);
  const winCount    = trades.filter(t => (Number(t["수익금($)"] ?? t.profit ?? 0)) > 0).length;

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
      };
      const res = await api.portfolio.saveTrade(trade) as { success: boolean; message: string };
      setAddMsg({ type: res.success ? "success" : "danger", text: res.message });
      if (res.success) { setForm({ ticker: "", name: "", buy_price: "", sell_price: "", quantity: "", result: "수익" }); mutate(); setShowForm(false); }
    } catch (e) { setAddMsg({ type: "danger", text: String(e) }); }
    finally { setAdding(false); }
  };

  const handleDelete = async (ticker: string, sellDate: string) => {
    if (!confirm("이 거래 기록을 삭제하시겠습니까?")) return;
    await api.portfolio.deleteTrade(ticker, sellDate);
    mutate();
  };

  if (isLoading) return <Skeleton height="200px" />;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
      {/* 요약 + 추가 버튼 */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <div style={{ display: "flex", gap: "1rem" }}>
          <span style={{ fontSize: "0.85rem", color: "var(--color-muted)" }}>총 {trades.length}건</span>
          <span style={{ fontWeight: 700, color: totalProfit >= 0 ? "var(--color-danger)" : "var(--color-primary)" }}>
            누적 손익: {totalProfit >= 0 ? "+" : ""}₩{Math.round(totalProfit).toLocaleString()}
          </span>
          {trades.length > 0 && <span style={{ fontSize: "0.85rem", color: "var(--color-muted)" }}>승률: {((winCount / trades.length) * 100).toFixed(0)}%</span>}
        </div>
        <button className="stockcy-btn stockcy-btn-secondary" onClick={() => setShowForm(v => !v)}>
          <Plus size={14} /> 거래 기록
        </button>
      </div>

      {showForm && (
        <div style={{ background: "var(--color-surface)", border: "1px solid var(--color-border)", borderRadius: "8px", padding: "1rem", display: "flex", flexDirection: "column", gap: "0.5rem" }}>
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
              <th></th>
            </tr>
          </thead>
          <tbody>
            {trades.map((t, i) => {
              const profit    = Number(t["수익금($)"] ?? t.profit ?? 0);
              const profitPct = Number(t["수익률(%)"] ?? t.profit_pct ?? 0);
              const color     = profit >= 0 ? "var(--color-danger)" : "var(--color-primary)";
              const ticker    = String(t["티커"] ?? t.ticker ?? "");
              const sellDate  = String(t["매도시간"] ?? t.sell_date ?? "");
              return (
                <tr key={i}>
                  <td style={{ fontWeight: 600 }}>{String(t["종목명"] ?? t.name ?? "")} <span style={{ fontSize: "0.72rem", color: "var(--color-muted)" }}>({ticker})</span></td>
                  <td style={{ textAlign: "right" }}>₩{Number(t["매수가($)"] ?? t.buy_price ?? 0).toLocaleString()}</td>
                  <td style={{ textAlign: "right" }}>₩{Number(t["매도가($)"] ?? t.sell_price ?? 0).toLocaleString()}</td>
                  <td style={{ textAlign: "right" }}>{Number(t["수량"] ?? t.quantity ?? 0).toLocaleString()}주</td>
                  <td style={{ textAlign: "right", color, fontWeight: 600 }}>{profit >= 0 ? "+" : ""}₩{Math.round(profit).toLocaleString()}</td>
                  <td style={{ textAlign: "right", color, fontWeight: 700 }}>{profitPct >= 0 ? "+" : ""}{profitPct.toFixed(2)}%</td>
                  <td><Badge variant={profit >= 0 ? "success" : "danger"}>{String(t["결과"] ?? t.result ?? "-")}</Badge></td>
                  <td style={{ fontSize: "0.75rem", color: "var(--color-muted)" }}>{sellDate.slice(0, 10)}</td>
                  <td>
                    <button className="stockcy-btn stockcy-btn-secondary" style={{ padding: "2px 6px", fontSize: "0.7rem" }} onClick={() => handleDelete(ticker, sellDate)}>
                      <Trash2 size={10} />
                    </button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
    </div>
  );
}

// ── 가격 알림 탭 ──────────────────────────────────────────────────────────────
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

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "1.25rem" }}>
      {selectedStock && <StockModal stock={selectedStock} onClose={() => setSelectedStock(null)} />}

      {/* 헤더 */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <h1 style={{ fontSize: "1.05rem", fontWeight: 700, display: "flex", alignItems: "center", gap: "0.5rem" }}>
          <Star size={18} style={{ color: "var(--color-accent)" }} /> 즐겨찾기 & 포트폴리오 관리
        </h1>
        <button className="stockcy-btn stockcy-btn-secondary" onClick={() => refetchFavs()}>
          <RefreshCw size={13} /> 새로고침
        </button>
      </div>

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
                  <FavRow key={f["티커"]} fav={f} price={priceMap[f["티커"]] ?? null} onRemove={handleRemove} onAnalyze={setSelectedStock} />
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

      {tab === "portfolio" && <Card title="📊 보유 종목 현황"><PortfolioTab /></Card>}
      {tab === "trades"    && <Card title="📋 거래 내역"><TradesTab /></Card>}
      {tab === "alerts"    && <Card title="🔔 가격 알림 설정"><AlertsTab /></Card>}
    </div>
  );
}
