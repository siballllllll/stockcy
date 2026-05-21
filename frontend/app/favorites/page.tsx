"use client";
import { useState, useMemo } from "react";
import { useRouter } from "next/navigation";
import useSWR from "swr";
import { api } from "@/lib/api";
import type { Favorite, KrStock, UsStock } from "@/lib/types";
import { Star, RefreshCw, Send, Trash2, Plus, Zap, BarChart2, Bell, TrendingUp, BookOpen } from "lucide-react";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { StatusBox } from "@/components/ui/StatusBox";
import { Skeleton } from "@/components/ui/LoadingSpinner";
import { SSEPanel } from "@/components/ui/SSEPanel";
import { StockModal } from "@/components/ui/StockModal";
import type { StockInfo } from "@/components/ui/StockModal";
import { useSSE } from "@/hooks/useSSE";

// ── 즐겨찾기 행 ───────────────────────────────────────────────────────────────
function FavRow({ fav, price, onRemove, onAnalyze }: {
  fav: Favorite;
  price?: { price: number; change_pct: number } | null;
  onRemove: (ticker: string) => void;
  onAnalyze: (s: StockInfo) => void;
}) {
  const router = useRouter();
  const isKr = fav["시장"] === "국내";
  const up   = (price?.change_pct ?? 0) > 0;
  const down = (price?.change_pct ?? 0) < 0;
  const color = up ? "var(--color-up)" : down ? "var(--color-down)" : "var(--color-flat)";

  return (
    <tr>
      <td>
        <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
          <Star size={13} style={{ color: "var(--color-warning)", fill: "var(--color-warning)" }} />
          <span style={{ fontWeight: 500 }}>{fav["종목명"]}</span>
          <span style={{ fontSize: "0.72rem", color: "var(--color-muted)" }}>({fav["티커"]})</span>
        </div>
      </td>
      <td><Badge variant={isKr ? "info" : "success"}>{fav["시장"]}</Badge></td>
      <td style={{ textAlign: "right", fontWeight: 600 }}>
        {price
          ? isKr ? `₩${price.price.toLocaleString()}` : `$${price.price.toFixed(2)}`
          : <span className="skeleton" style={{ display: "inline-block", width: "60px", height: "1rem" }} />
        }
      </td>
      <td style={{ textAlign: "right", color }}>
        {price ? `${up ? "+" : ""}${price.change_pct.toFixed(2)}%` : "—"}
      </td>
      <td>
        <div style={{ display: "flex", gap: "4px" }}>
          <button className="stockcy-btn stockcy-btn-secondary" style={{ padding: "2px 8px", fontSize: "0.72rem" }} title="차트 보기"
            onClick={() => router.push(`/search?q=${fav["티커"]}${isKr ? "" : "&market=US"}`)}>
            <BarChart2 size={11} />
          </button>
          <button className="stockcy-btn stockcy-btn-secondary" style={{ padding: "2px 8px", fontSize: "0.72rem" }} title="AI 분석"
            onClick={() => onAnalyze({ code: fav["티커"], name: fav["종목명"], market: fav["시장"] as "국내" | "미국" })}>
            <Zap size={11} />
          </button>
          <button className="stockcy-btn stockcy-btn-secondary" style={{ padding: "2px 8px", fontSize: "0.72rem" }}
            onClick={() => onRemove(fav["티커"])}>
            <Trash2 size={11} />
          </button>
        </div>
      </td>
    </tr>
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

// ── 보유 종목 탭 ──────────────────────────────────────────────────────────────
function PortfolioTab() {
  const { data: portfolio, isLoading, mutate } = useSWR<any[]>("/api/portfolio", () => api.portfolio.loadPortfolio() as Promise<any[]>);

  // KR 종목 현재가 일괄 로드
  const krTickers = (portfolio ?? []).filter(p => String(p.ticker).match(/^\d{6}$/)).map(p => p.ticker);
  const { data: krPrices } = useSWR(
    krTickers.length > 0 ? `kr-portfolio-prices-${krTickers.join(",")}` : null,
    async () => {
      const map: Record<string, number> = {};
      await Promise.all(krTickers.map(async (code) => {
        try {
          const d = await api.kr.stockPrice(code) as any;
          if (d?.price) map[code] = d.price;
        } catch {}
      }));
      return map;
    },
    { refreshInterval: 60000 }
  );

  const enriched = useMemo(() => {
    return (portfolio ?? []).map(p => {
      const currentPrice = (krPrices ?? {})[p.ticker] ?? p.buy_price;
      const cost = p.buy_price * p.quantity;
      const value = currentPrice * p.quantity;
      const profit = value - cost;
      const profitPct = cost > 0 ? (profit / cost) * 100 : 0;
      return { ...p, currentPrice, cost, value, profit, profitPct };
    });
  }, [portfolio, krPrices]);

  const totalCost   = enriched.reduce((s, p) => s + p.cost, 0);
  const totalValue  = enriched.reduce((s, p) => s + p.value, 0);
  const totalProfit = totalValue - totalCost;

  if (isLoading) return <Skeleton height="200px" />;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
      {/* 총 손익 요약 */}
      {enriched.length > 0 && (
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: "10px" }}>
          {[
            { label: "총 매수금액", val: `₩${Math.round(totalCost).toLocaleString()}` },
            { label: "총 평가금액", val: `₩${Math.round(totalValue).toLocaleString()}`, color: totalValue >= totalCost ? "var(--color-danger)" : "var(--color-primary)" },
            { label: "총 손익",    val: `${totalProfit >= 0 ? "+" : ""}₩${Math.round(totalProfit).toLocaleString()} (${totalProfit >= 0 ? "+" : ""}${totalCost > 0 ? ((totalProfit/totalCost)*100).toFixed(2) : "0"}%)`, color: totalProfit >= 0 ? "var(--color-danger)" : "var(--color-primary)" },
          ].map(({ label, val, color }) => (
            <div key={label} style={{ background: "var(--color-surface)", border: "1px solid var(--color-border)", borderRadius: "8px", padding: "12px", textAlign: "center" }}>
              <div style={{ fontSize: "0.75rem", color: "var(--color-muted)", marginBottom: "4px" }}>{label}</div>
              <div style={{ fontWeight: 800, fontSize: "0.95rem", color: color ?? "var(--color-text)" }}>{val}</div>
            </div>
          ))}
        </div>
      )}

      {!portfolio || portfolio.length === 0 ? (
        <StatusBox type="info">보유 종목이 없습니다. AI 타점 보드에서 종목을 추가해보세요.</StatusBox>
      ) : (
        <table className="stockcy-table">
          <thead>
            <tr>
              <th>종목명</th>
              <th style={{ textAlign: "right" }}>매수가</th>
              <th style={{ textAlign: "right" }}>현재가</th>
              <th style={{ textAlign: "right" }}>수량</th>
              <th style={{ textAlign: "right" }}>손익</th>
              <th style={{ textAlign: "right" }}>손익률</th>
              <th>등급</th>
            </tr>
          </thead>
          <tbody>
            {enriched.map((p, i) => {
              const color = p.profitPct >= 0 ? "var(--color-danger)" : "var(--color-primary)";
              return (
                <tr key={i}>
                  <td style={{ fontWeight: 600 }}>{p.name} <span style={{ fontSize: "0.75rem", color: "var(--color-muted)" }}>({p.ticker})</span></td>
                  <td style={{ textAlign: "right" }}>₩{Number(p.buy_price).toLocaleString()}</td>
                  <td style={{ textAlign: "right" }}>₩{Number(p.currentPrice).toLocaleString()}</td>
                  <td style={{ textAlign: "right" }}>{Number(p.quantity).toLocaleString()}주</td>
                  <td style={{ textAlign: "right", color, fontWeight: 600 }}>
                    {p.profit >= 0 ? "+" : ""}₩{Math.round(p.profit).toLocaleString()}
                  </td>
                  <td style={{ textAlign: "right", color, fontWeight: 700 }}>
                    {p.profitPct >= 0 ? "+" : ""}{p.profitPct.toFixed(2)}%
                  </td>
                  <td><Badge variant="info">{p.rating || "-"}</Badge></td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
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

  const { data: krPriceMap } = useSWR(
    krTickers.length > 0 ? `kr-fav-prices-${krTickers.join(",")}` : null,
    async () => {
      const map: Record<string, { price: number; change_pct: number }> = {};
      await Promise.all(krTickers.map(async (code) => {
        try {
          const d = await api.kr.stockPrice(code) as KrStock;
          if (d?.price) map[code] = { price: d.price, change_pct: d.change_pct };
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
      const map: Record<string, { price: number; change_pct: number }> = {};
      for (const s of (arr ?? [])) map[s["심볼"]] = { price: s["현재가($)"], change_pct: s["등락률(%)"] };
      return map;
    },
    { refreshInterval: 60000 }
  );

  const priceMap: Record<string, { price: number; change_pct: number }> = { ...(krPriceMap ?? {}), ...(usPriceMap ?? {}) };

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
              <table className="stockcy-table">
                <thead>
                  <tr>
                    <th>종목명</th><th>시장</th>
                    <th style={{ textAlign: "right" }}>현재가</th>
                    <th style={{ textAlign: "right" }}>등락률</th>
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  {favs.map((f) => (
                    <FavRow key={f["티커"]} fav={f} price={priceMap[f["티커"]] ?? null} onRemove={handleRemove} onAnalyze={setSelectedStock} />
                  ))}
                </tbody>
              </table>
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
