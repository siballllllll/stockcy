"use client";
import { useState } from "react";
import { Star, RefreshCw, Send, Trash2, Plus } from "lucide-react";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { StatusBox } from "@/components/ui/StatusBox";
import { Skeleton } from "@/components/ui/LoadingSpinner";
import { SSEPanel } from "@/components/ui/SSEPanel";
import { useSSE } from "@/hooks/useSSE";
import useSWR from "swr";
import { api } from "@/lib/api";
import type { Favorite } from "@/lib/types";

// ── 가격 행 ───────────────────────────────────────────────────────────────────
function FavRow({
  fav, price, onRemove,
}: {
  fav: Favorite;
  price?: { price: number; change_pct: number } | null;
  onRemove: (ticker: string) => void;
}) {
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
          ? isKr
            ? `₩${price.price.toLocaleString()}`
            : `$${price.price.toFixed(2)}`
          : <span className="skeleton" style={{ display: "inline-block", width: "60px", height: "1rem" }} />
        }
      </td>
      <td style={{ textAlign: "right", color }}>
        {price ? `${up ? "+" : ""}${price.change_pct.toFixed(2)}%` : "—"}
      </td>
      <td>
        <button
          className="stockcy-btn stockcy-btn-secondary"
          style={{ padding: "2px 8px", fontSize: "0.72rem" }}
          onClick={() => onRemove(fav["티커"])}
        >
          <Trash2 size={11} />
        </button>
      </td>
    </tr>
  );
}

// ── 종목 추가 폼 ──────────────────────────────────────────────────────────────
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
    } catch (e) {
      setMsg({ type: "danger", text: String(e) });
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
      <div style={{ display: "flex", gap: "0.5rem", alignItems: "center" }}>
        <select
          className="stockcy-input"
          style={{ width: "90px", flexShrink: 0 }}
          value={market}
          onChange={(e) => setMarket(e.target.value as "국내" | "미국")}
        >
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

// ── 메인 페이지 ───────────────────────────────────────────────────────────────
export default function FavoritesPage() {
  const { data: favs, mutate: refetchFavs, isLoading } =
    useSWR("favorites", () => api.portfolio.loadFavorites() as Promise<Favorite[]>);

  const brief = useSSE<{ success: boolean; msg: string }>("/api/admin/daily-brief/send", { method: "POST" });

  const handleRemove = async (ticker: string) => {
    await api.portfolio.removeFavorite(ticker);
    refetchFavs();
  };

  const handleSendBrief = () => {
    brief.start({ favorites: favs ?? [] });
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "1.25rem" }}>

      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
          <Star size={18} style={{ color: "var(--color-accent)" }} />
          <h1 style={{ fontSize: "1.05rem", fontWeight: 700 }}>즐겨찾기 & 장 마감 리포트</h1>
        </div>
        <button
          className="stockcy-btn stockcy-btn-secondary"
          onClick={() => refetchFavs()}
        >
          <RefreshCw size={13} /> 새로고침
        </button>
      </div>

      {/* ── 즐겨찾기 테이블 ─────────────────────────────────────────── */}
      <Card
        title={`즐겨찾기 종목 (${favs?.length ?? 0}개)`}
        action={
          <StatusBox type="info" className="text-xs">
            실시간 시세는 별도 조회 필요 (Step 4 구현 예정)
          </StatusBox>
        }
      >
        <AddFavoriteForm onAdded={() => refetchFavs()} />

        <div className="stockcy-divider" />

        {isLoading ? (
          <Skeleton height="150px" />
        ) : !favs || favs.length === 0 ? (
          <StatusBox type="info">즐겨찾기에 등록된 종목이 없습니다. 위에서 추가해주세요.</StatusBox>
        ) : (
          <table className="stockcy-table">
            <thead>
              <tr>
                <th>종목명</th>
                <th>시장</th>
                <th style={{ textAlign: "right" }}>현재가</th>
                <th style={{ textAlign: "right" }}>등락률</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {favs.map((f) => (
                <FavRow key={f["티커"]} fav={f} price={null} onRemove={handleRemove} />
              ))}
            </tbody>
          </table>
        )}
      </Card>

      {/* ── 장 마감 브리핑 ─────────────────────────────────────────── */}
      <Card title={<span style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}><Send size={15} style={{ color: "var(--color-accent)" }} />텔레그램 장 마감 브리핑</span>}>
        <SSEPanel<{ success: boolean; msg: string }>
          status={brief.status}
          message={brief.message}
          result={brief.result}
          onStart={handleSendBrief}
          startLabel="브리핑 발송"
          disabled={!favs || favs.length === 0}
          idleHint={
            favs && favs.length > 0
              ? `즐겨찾기 ${favs.length}개 종목의 시세와 최신 매크로 뉴스를 반영한 AI 리포트를 텔레그램으로 발송합니다.`
              : "즐겨찾기 종목을 먼저 추가해주세요."
          }
        >
          {(data) => (
            <StatusBox type={data.success ? "success" : "danger"}>
              {data.msg}
            </StatusBox>
          )}
        </SSEPanel>
      </Card>
    </div>
  );
}
