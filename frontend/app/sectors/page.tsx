"use client";
import { useState, useMemo } from "react";
import useSWR from "swr";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { useMarket } from "@/lib/market-context";
import { Activity, Flame, ChevronRight, ChevronDown, Bot } from "lucide-react";

export default function SectorsPage() {
  const { market } = useMarket();
  const isKR = market === "KR";

  const [activeTab, setActiveTab] = useState<"hot" | "explore">("explore");

  // ── 섹터 맵 ──────────────────────────────────────────────────────────────────
  const { data: krSectorMap } = useSWR<any>(
    isKR ? "/api/kr/sector-map" : null,
    () => api.kr.sectorMap()
  );
  const { data: usSectorMap } = useSWR<any>(
    !isKR ? "/api/us/sector-map" : null,
    () => api.us.sectorMap()
  );
  const sectorMap = isKR ? krSectorMap : usSectorMap;

  // ── KR 핫 섹터 (AI 분석) ─────────────────────────────────────────────────────
  const { data: cachedHotSectors, isLoading: hsLoading, mutate: mutateHs } = useSWR(
    isKR ? "/api/kr/hot-sectors" : null,
    () => api.kr.hotSectors(),
    { revalidateOnFocus: false }
  );

  // ── 오늘의 시장 분석 (hot 탭 전용) ───────────────────────────────────────────
  const { data: todayMarketData, isLoading: tmLoading, mutate: mutateTm } = useSWR(
    isKR && activeTab === "hot" ? "/api/kr/today-market" : null,
    () => api.kr.todayMarket(),
    { revalidateOnFocus: false }
  );

  // ── 거래량 TOP 10 (hot 탭 전용) ──────────────────────────────────────────────
  const { data: volumeRankData, isLoading: vrLoading, mutate: mutateVr } = useSWR(
    isKR && activeTab === "hot" ? "/api/kr/volume-ranking" : null,
    () => api.kr.volumeRanking(),
    { revalidateOnFocus: false }
  );

  const handleRefresh = () => { mutateTm(); mutateVr(); mutateHs(); };

  const hotKeywords = useMemo(() => {
    const hs = cachedHotSectors as any;
    if (!hs?.sectors) return [];
    return (hs.sectors as any[]).map((s) => s.keyword as string);
  }, [cachedHotSectors]);

  // ── UI 상태 ───────────────────────────────────────────────────────────────
  const [selectedMainSector, setSelectedMainSector] = useState<string>("");
  const [expandedSubSectors, setExpandedSubSectors] = useState<Record<string, boolean>>({});

  const toggleSubSector = (sub: string) => {
    setExpandedSubSectors(prev => ({ ...prev, [sub]: !prev[sub] }));
  };

  const mainSectors = sectorMap ? Object.keys(sectorMap) : [];
  const activeMain = selectedMainSector && mainSectors.includes(selectedMainSector)
    ? selectedMainSector
    : (mainSectors[0] ?? "");

  const isHotMain = isKR && hotKeywords.includes(activeMain);

  return (
    <div style={{ maxWidth: "1200px", margin: "0 auto", padding: "1.5rem" }}>

      <h1 style={{ fontSize: "1.8rem", fontWeight: 800, marginBottom: "1.5rem", display: "flex", alignItems: "center", gap: "8px" }}>
        <Flame color="var(--color-danger)" />
        {isKR ? "🇰🇷 국내 이슈 섹터" : "🇺🇸 미국 이슈 섹터"}
      </h1>

      {/* ── 상단 탭 ─────────────────────────────────────────────────────────── */}
      <div style={{ display: "flex", gap: "1rem", marginBottom: "2rem" }}>
        {isKR && (
          <button
            onClick={() => setActiveTab("hot")}
            style={{ flex: 1, padding: "1rem", borderRadius: "8px", border: "1px solid", borderColor: activeTab === "hot" ? "var(--color-accent)" : "var(--color-border)", background: activeTab === "hot" ? "rgba(255,255,255,0.05)" : "var(--color-surface)", color: "var(--color-text)", fontWeight: 700, fontSize: "1rem", cursor: "pointer", transition: "0.2s" }}
          >
            🔥 오늘의 이슈섹터
          </button>
        )}
        <button
          onClick={() => setActiveTab("explore")}
          style={{ flex: 1, padding: "1rem", borderRadius: "8px", border: "1px solid", borderColor: activeTab === "explore" ? "var(--color-accent)" : "var(--color-border)", background: activeTab === "explore" ? "rgba(255,255,255,0.05)" : "var(--color-surface)", color: "var(--color-text)", fontWeight: 700, fontSize: "1rem", cursor: "pointer", transition: "0.2s" }}
        >
          🗺️ 전체 섹터 탐색
        </button>
      </div>

      {/* ── 오늘의 이슈섹터 (KR 전용) ──────────────────────────────────────── */}
      {activeTab === "hot" && isKR && (
        <div>
          {/* 새로고침 버튼 */}
          <div style={{ display: "flex", justifyContent: "flex-end", marginBottom: "1rem" }}>
            <button
              className="stockcy-btn stockcy-btn-primary"
              onClick={handleRefresh}
              disabled={tmLoading || vrLoading || hsLoading}
            >
              {(tmLoading || vrLoading || hsLoading) ? "분석 중..." : "🔄 새로고침"}
            </button>
          </div>

          {/* 로딩 */}
          {(tmLoading || (hsLoading && !cachedHotSectors)) && (
            <div className="stockcy-card" style={{ height: "300px", display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", color: "var(--color-muted)" }}>
              <div style={{ fontSize: "2.5rem", marginBottom: "1rem" }}>⏳</div>
              <div>AI 섹터 분석 중... (1~2분 소요)</div>
            </div>
          )}

          {/* 오류 */}
          {(todayMarketData as any)?.error && (
            <div style={{ background: "rgba(255,75,75,0.08)", border: "1px solid rgba(255,75,75,0.3)", borderRadius: "8px", padding: "12px 16px", marginBottom: "12px", color: "#ff6b6b" }}>
              ⚠️ {(todayMarketData as any).error}
            </div>
          )}

          {/* ── 시장 요약 배너 ── */}
          {(todayMarketData as any)?.market_summary && (
            <div style={{ background: "rgba(255,152,0,0.06)", borderLeft: "3px solid #ff9800", padding: "8px 14px", borderRadius: "4px", marginBottom: "12px" }}>
              <div style={{ color: "#ff9800", fontWeight: 700, fontSize: "0.94rem", marginBottom: "4px" }}>📌 오늘 시장 요약</div>
              <div style={{ color: "#ccc", fontSize: "0.95rem", lineHeight: 1.6 }}>{(todayMarketData as any).market_summary}</div>
            </div>
          )}

          {/* ── 주도 테마 태그 ── */}
          {(todayMarketData as any)?.leading_themes?.length > 0 && (
            <div style={{ marginBottom: "14px", display: "flex", flexWrap: "wrap", gap: "6px", alignItems: "center" }}>
              <span style={{ fontSize: "0.9rem", color: "#aaa" }}>🔥 주도 테마:</span>
              {((todayMarketData as any).leading_themes as string[]).map((t) => {
                const isTop = t === (todayMarketData as any).top_theme;
                return (
                  <span key={t} style={{
                    background: isTop ? "rgba(255,75,75,0.2)" : "rgba(255,255,255,0.06)",
                    border: `1px solid ${isTop ? "#ff4b4b" : "rgba(255,255,255,0.15)"}`,
                    borderRadius: "12px", padding: "2px 10px", fontSize: "0.88rem",
                    color: isTop ? "#ff4b4b" : "#aaa", fontWeight: 700,
                  }}>{t}</span>
                );
              })}
            </div>
          )}

          {/* ── 💎 AI 선정 핫 섹터 & 종목 제목 ── */}
          {(cachedHotSectors || todayMarketData) && !hsLoading && (
            <div style={{ fontWeight: 800, fontSize: "1.05rem", marginBottom: "12px", color: "var(--color-text)" }}>
              💎 AI 선정 핫 섹터 &amp; 종목
            </div>
          )}

          {/* ── 거래량 TOP 10 ── */}
          {Array.isArray(volumeRankData) && volumeRankData.length > 0 && (
            <VolumeTop10Table data={(volumeRankData as any[]).slice(0, 10)} />
          )}

          {/* ── 오늘의 급등 종목 ── */}
          {(todayMarketData as any)?.stocks?.length > 0 && (
            <div style={{ marginBottom: "20px" }}>
              <div style={{ fontWeight: 700, color: "#aaa", marginBottom: "8px", fontSize: "1.01rem" }}>📈 오늘의 급등 종목</div>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))", gap: "10px" }}>
                {((todayMarketData as any).stocks as any[]).map((stk: any) => (
                  <RisingStockCard key={stk.code} stock={stk} />
                ))}
              </div>
            </div>
          )}

          {/* ── AI 핫 섹터 ── */}
          {(cachedHotSectors as any)?.sectors?.length > 0 && (
            <div>
              <div style={{ fontWeight: 700, color: "#aaa", marginBottom: "10px", fontSize: "1.01rem" }}>🔥 AI 핫 섹터</div>

              {/* 신규 이슈 섹터 패널 */}
              {(() => {
                const sectors: any[] = (cachedHotSectors as any).sectors ?? [];
                const newSecs = sectors.filter((s: any) =>
                  !krSectorMap || !Object.keys(krSectorMap).includes(s.keyword)
                );
                if (newSecs.length === 0) return null;
                return (
                  <div style={{ marginBottom: "12px" }}>
                    <div style={{ fontWeight: 700, color: "#4caf50", fontSize: "0.95rem", marginBottom: "6px" }}>⚡ 오늘의 신규 이슈 감지</div>
                    <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(200px, 1fr))", gap: "8px" }}>
                      {newSecs.map((s: any, i: number) => (
                        <div key={i} style={{ background: "rgba(76,175,80,0.1)", border: "1px solid #4caf50", borderRadius: "8px", padding: "8px 12px" }}>
                          <div style={{ fontWeight: 700, color: "#4caf50", fontSize: "0.9rem" }}>🆕 {s.keyword}</div>
                          <div style={{ fontSize: "0.82rem", color: "#aaa", marginTop: "2px" }}>{String(s.reason ?? "").slice(0, 50)}...</div>
                        </div>
                      ))}
                    </div>
                    <div style={{ height: "1px", background: "var(--color-border)", marginTop: "12px" }} />
                  </div>
                );
              })()}

              <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
                {[...((cachedHotSectors as any).sectors as any[])]
                  .sort((a, b) => (b.hot_score ?? 0) - (a.hot_score ?? 0))
                  .map((sector: any, i: number) => (
                    <HotSectorCard key={i} sector={sector} sectorMap={krSectorMap} />
                  ))}
              </div>
            </div>
          )}

          {/* 데이터 없음 */}
          {!tmLoading && !hsLoading && !todayMarketData && !cachedHotSectors && (
            <div className="stockcy-card" style={{ padding: "3rem", textAlign: "center", color: "var(--color-muted)" }}>
              <Flame size={48} style={{ marginBottom: "1rem", opacity: 0.4 }} />
              <div>데이터를 불러올 수 없습니다. 새로고침 버튼을 눌러 다시 시도하세요.</div>
            </div>
          )}
        </div>
      )}

      {/* ── 전체 섹터 탐색 ─────────────────────────────────────────────────── */}
      {activeTab === "explore" && (
        <div>
          {/* HOT / 관심 섹터 박스 (KR only, 캐시 결과) */}
          {isKR && (() => {
            const sectors: any[] = (cachedHotSectors as any)?.sectors ?? [];
            const hot  = sectors.filter((s: any) => (s.hot_score ?? 0) >= 8);
            const star = sectors.filter((s: any) => (s.hot_score ?? 0) >= 5 && (s.hot_score ?? 0) < 8);
            if (sectors.length === 0) return null;
            return (
              <div style={{ display: "flex", flexDirection: "column", gap: "12px", marginBottom: "1.5rem" }}>
                {hot.length > 0 && (
                  <>
                    <div style={{ fontSize: "0.95rem", fontWeight: 800, color: "var(--color-danger)", display: "flex", alignItems: "center", gap: "6px" }}>
                      <Flame size={16} /> 🔥 HOT 섹터
                    </div>
                    {hot.map((sec: any, i: number) => (
                      <div key={i} className="stockcy-card hover-highlight" onClick={() => { setSelectedMainSector(sec.keyword); setExpandedSubSectors({}); }} style={{ padding: "12px 16px", border: "1px solid rgba(255,60,60,0.35)", background: "rgba(255,60,60,0.04)", cursor: "pointer" }}>
                        <div style={{ display: "flex", alignItems: "center", gap: "8px", marginBottom: "4px" }}>
                          <span>🔥</span>
                          <span style={{ fontWeight: 800 }}>{sec.keyword}</span>
                          <span style={{ fontSize: "0.8rem", fontWeight: 700, color: "var(--color-warning)" }}>[{sec.hot_score}점]</span>
                        </div>
                        {sec.reason && <div style={{ fontSize: "0.78rem", color: "var(--color-muted)", lineHeight: 1.5 }}>{String(sec.reason).slice(0, 100)}{String(sec.reason).length > 100 ? "…" : ""}</div>}
                      </div>
                    ))}
                  </>
                )}
                {star.length > 0 && (
                  <>
                    <div style={{ fontSize: "0.95rem", fontWeight: 800, color: "var(--color-warning)", display: "flex", alignItems: "center", gap: "6px" }}>
                      ⭐ 관심 섹터
                    </div>
                    {star.map((sec: any, i: number) => (
                      <div key={i} className="stockcy-card hover-highlight" onClick={() => { setSelectedMainSector(sec.keyword); setExpandedSubSectors({}); }} style={{ padding: "12px 16px", border: "1px solid rgba(255,180,50,0.25)", background: "rgba(255,180,50,0.03)", cursor: "pointer" }}>
                        <div style={{ display: "flex", alignItems: "center", gap: "8px", marginBottom: "4px" }}>
                          <span>⭐</span>
                          <span style={{ fontWeight: 700 }}>{sec.keyword}</span>
                          <span style={{ fontSize: "0.8rem", fontWeight: 700, color: "var(--color-warning)" }}>[{sec.hot_score}점]</span>
                        </div>
                        {sec.reason && <div style={{ fontSize: "0.78rem", color: "var(--color-muted)", lineHeight: 1.5 }}>{String(sec.reason).slice(0, 100)}{String(sec.reason).length > 100 ? "…" : ""}</div>}
                      </div>
                    ))}
                  </>
                )}
                <div style={{ height: "1px", background: "var(--color-border)" }} />
              </div>
            );
          })()}

          <div style={{ fontSize: "0.9rem", color: "var(--color-muted)", marginBottom: "0.75rem" }}>
            섹터를 클릭해 종목을 탐색하세요{isKR ? " · 🔥 = 오늘의 이슈 섹터" : ""}
          </div>

          <div style={{ marginBottom: "0.5rem", fontWeight: 700 }}>섹터 선택 (직접 선택)</div>
          <select
            value={activeMain}
            onChange={(e) => { setSelectedMainSector(e.target.value); setExpandedSubSectors({}); }}
            style={{ width: "100%", padding: "1rem", borderRadius: "8px", border: `1px solid ${isHotMain ? "rgba(255,75,75,0.5)" : "var(--color-border)"}`, background: "var(--color-surface)", color: "var(--color-text)", fontSize: "1rem", marginBottom: "1.5rem", outline: "none", cursor: "pointer" }}
          >
            {mainSectors.map(s => (
              <option key={s} value={s}>
                {hotKeywords.includes(s) ? "🔥 " : ""}{s}
              </option>
            ))}
          </select>

          <div style={{ display: "grid", gridTemplateColumns: "60px 2fr 1fr 1fr 100px", padding: "10px 1rem", borderBottom: "1px solid var(--color-border)", fontSize: "0.85rem", color: "var(--color-muted)", fontWeight: 600 }}>
            <div>단타</div>
            <div>종목명</div>
            <div style={{ textAlign: "right" }}>현재가</div>
            <div style={{ textAlign: "right" }}>등락률</div>
            <div></div>
          </div>

          {sectorMap && sectorMap[activeMain] && Object.entries(sectorMap[activeMain]).map(([subSector, stocks]: [string, any]) => {
            const isHot = isKR && hotKeywords.includes(activeMain);
            const isOpen = expandedSubSectors[subSector];
            return (
              <div key={subSector} style={{ borderBottom: "1px solid rgba(255,255,255,0.05)" }}>
                <div
                  onClick={() => toggleSubSector(subSector)}
                  style={{ display: "grid", gridTemplateColumns: "60px 2fr 1fr 1fr 100px", padding: "1rem", alignItems: "center", background: "var(--color-surface)", cursor: "pointer", transition: "0.2s" }}
                  className="hover-highlight"
                >
                  <div style={{ display: "flex", justifyContent: "center" }}>
                    {isOpen ? <ChevronDown size={18} /> : <ChevronRight size={18} />}
                  </div>
                  <div style={{ display: "flex", alignItems: "center", gap: "8px", fontWeight: 700, fontSize: "1.05rem" }}>
                    📌 {subSector}
                    <span style={{ fontSize: "0.85rem", color: "var(--color-muted)", fontWeight: 500 }}>{stocks.length}개</span>
                    {isHot && <Flame size={14} color="var(--color-danger)" style={{ marginLeft: "4px" }} />}
                  </div>
                  <div style={{ textAlign: "right", color: "var(--color-muted)" }}>-</div>
                  <div style={{ textAlign: "right", fontWeight: 700, color: "var(--color-danger)" }}>-</div>
                  <div style={{ display: "flex", justifyContent: "flex-end" }}>
                    <button
                      onClick={(e) => { e.stopPropagation(); alert(`${subSector} AI 분석 시작`); }}
                      style={{ padding: "4px 12px", background: "transparent", border: "1px solid var(--color-border)", borderRadius: "4px", color: "var(--color-text)", fontWeight: 600, display: "flex", alignItems: "center", gap: "4px", cursor: "pointer" }}
                    >
                      <Bot size={14} /> AI
                    </button>
                  </div>
                </div>

                {isOpen && (
                  <div style={{ background: "rgba(0,0,0,0.2)", padding: "0" }}>
                    {stocks.map((stock: any, i: number) => (
                      <SubSectorStockRow key={i} stock={stock} market={market} />
                    ))}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

// ── 거래량 TOP 10 테이블 ─────────────────────────────────────────────────────
function VolumeTop10Table({ data }: { data: any[] }) {
  return (
    <div style={{ marginBottom: "20px" }}>
      <div style={{ fontWeight: 700, color: "#aaa", marginBottom: "6px", fontSize: "1.01rem" }}>📊 거래량 TOP 10</div>
      <div className="stockcy-card" style={{ overflow: "auto" }}>
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.88rem" }}>
          <thead>
            <tr style={{ color: "var(--color-muted)", borderBottom: "1px solid rgba(255,255,255,0.07)" }}>
              <th style={{ padding: "6px 10px", textAlign: "left", fontWeight: 600 }}>#</th>
              <th style={{ padding: "6px 10px", textAlign: "left", fontWeight: 600 }}>종목명</th>
              <th style={{ padding: "6px 10px", textAlign: "right", fontWeight: 600 }}>현재가</th>
              <th style={{ padding: "6px 10px", textAlign: "right", fontWeight: 600 }}>등락률</th>
              <th style={{ padding: "6px 10px", textAlign: "right", fontWeight: 600 }}>거래량</th>
            </tr>
          </thead>
          <tbody>
            {data.map((row: any, i: number) => {
              const pct = row["등락률(%)"] ?? 0;
              const color = pct > 0 ? "#ff4b4b" : pct < 0 ? "#2b7cff" : "#888";
              const price = row["현재가"] ?? 0;
              const vol = row["거래량"] ?? 0;
              return (
                <tr key={i} style={{ borderBottom: "1px solid rgba(255,255,255,0.04)" }}>
                  <td style={{ padding: "5px 10px", color: "var(--color-muted)" }}>{i + 1}</td>
                  <td style={{ padding: "5px 10px", fontWeight: 600 }}>{row["종목명"] ?? "-"}</td>
                  <td style={{ padding: "5px 10px", textAlign: "right" }}>
                    {price > 0 ? `₩${price.toLocaleString()}` : "-"}
                  </td>
                  <td style={{ padding: "5px 10px", textAlign: "right", color, fontWeight: 700 }}>
                    {typeof pct === "number" ? `${pct > 0 ? "+" : ""}${pct.toFixed(2)}%` : "-"}
                  </td>
                  <td style={{ padding: "5px 10px", textAlign: "right", color: "var(--color-muted)" }}>
                    {typeof vol === "number" ? vol.toLocaleString() : "-"}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ── 오늘의 급등 종목 카드 ────────────────────────────────────────────────────
function RisingStockCard({ stock }: { stock: any }) {
  const router = useRouter();
  const pct = stock.change_pct ?? 0;
  const pctColor = pct > 0 ? "#ff4b4b" : pct < 0 ? "#2b7cff" : "#888";
  const label = pct >= 5 ? "🔥 급등" : pct >= 2 ? "▲ 상승" : pct <= -2 ? "▼ 하락" : "⚪ 보합";
  const labelColor = pct >= 2 ? "#ff4b4b" : pct <= -2 ? "#2b7cff" : "#888";

  return (
    <div className="stockcy-card" style={{ padding: "10px 14px" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
        <div>
          <span style={{ fontWeight: 700, fontSize: "1.05rem" }}>{stock.name}</span>
          <span style={{ fontSize: "0.78rem", color: "#888", marginLeft: "6px" }}>{stock.market}</span>
          <span style={{ fontSize: "0.78rem", color: "#555", marginLeft: "4px" }}>{stock.code}</span>
        </div>
        <span style={{ fontWeight: 700, color: pctColor, fontSize: "1.05rem" }}>
          {pct > 0 ? "+" : ""}{pct.toFixed(1)}%
        </span>
      </div>
      <div style={{ marginTop: "6px", display: "flex", gap: "6px", flexWrap: "wrap", alignItems: "center" }}>
        <span style={{ padding: "1px 7px", borderRadius: "4px", background: `${labelColor}22`, border: `1px solid ${labelColor}55`, color: labelColor, fontSize: "0.78rem", fontWeight: 700 }}>
          {label}
        </span>
        {stock.theme && (
          <span style={{ background: "rgba(255,152,0,0.15)", borderRadius: "10px", padding: "1px 8px", color: "#ff9800", fontSize: "0.78rem" }}>
            #{stock.theme}
          </span>
        )}
      </div>
      {stock.reason && (
        <div style={{ fontSize: "0.85rem", color: "#bbb", marginTop: "6px", lineHeight: 1.45 }}>{stock.reason}</div>
      )}
      {stock.code && (
        <button
          onClick={() => router.push(`/search?q=${stock.code}`)}
          style={{ marginTop: "8px", padding: "3px 10px", background: "transparent", border: "1px solid var(--color-border)", borderRadius: "4px", color: "var(--color-muted)", fontSize: "0.8rem", cursor: "pointer" }}
        >
          ▶ 차트
        </button>
      )}
    </div>
  );
}

// ── AI 핫 섹터 카드 ──────────────────────────────────────────────────────────
function HotSectorCard({ sector, sectorMap }: { sector: any; sectorMap: any }) {
  const allStocks = useMemo(() => {
    if (!sectorMap) return [];
    const subSectors = sectorMap[sector.keyword] ?? {};
    const all: any[] = [];
    Object.values(subSectors).forEach((stocks: any) => all.push(...(stocks as any[])));
    return all;
  }, [sectorMap, sector.keyword]);

  const displayStocks = useMemo(() => {
    const hotCodes: string[] = sector.hot_codes ?? [];
    if (hotCodes.length > 0) {
      const filtered = allStocks.filter((s: any) => hotCodes.includes(s.code));
      return (filtered.length > 0 ? filtered : allStocks).slice(0, 10);
    }
    return allStocks.slice(0, 10);
  }, [allStocks, sector.hot_codes]);

  const isNew = allStocks.length === 0;
  const score = sector.hot_score ?? 0;
  const fires = "🔥".repeat(Math.max(1, Math.min(Math.floor(score / 2.5), 4)));

  return (
    <div className="stockcy-card" style={{ padding: "12px 16px" }}>
      {/* 헤더 */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "4px" }}>
        <span style={{ fontWeight: 800, fontSize: "1.1rem" }}>
          {sector.keyword}
          {isNew && (
            <span style={{ fontSize: "0.75rem", color: "#4caf50", border: "1px solid #4caf50", borderRadius: "3px", padding: "1px 5px", marginLeft: "8px" }}>NEW</span>
          )}
        </span>
        <span style={{ color: "#ff9800", fontSize: "0.95rem" }}>{fires} {score}/10</span>
      </div>

      {sector.reason && (
        <div style={{ fontSize: "0.88rem", color: "#aaa", marginBottom: "4px", lineHeight: 1.5 }}>{sector.reason}</div>
      )}
      {sector.news_title && (
        <div style={{ fontSize: "0.82rem", color: "#666", marginBottom: "8px" }}>📰 {sector.news_title}</div>
      )}

      {/* 종목 목록 */}
      {displayStocks.length > 0 && (
        <div style={{ borderTop: "1px solid rgba(255,255,255,0.07)", paddingTop: "8px" }}>
          {displayStocks.map((stk: any) => (
            <HotSectorStockRow key={stk.code} stock={stk} />
          ))}
        </div>
      )}

      {/* AI 신규 종목 */}
      {sector.new_stocks?.length > 0 && (
        <div style={{ borderTop: "1px solid rgba(255,255,255,0.06)", paddingTop: "6px", marginTop: "4px" }}>
          {(sector.new_stocks as any[]).slice(0, 2).map((ns: any, i: number) => (
            <div key={i} style={{ fontSize: "0.82rem", color: "#aaa", padding: "2px 0" }}>
              🤖 {ns.name} — {ns.reason}
            </div>
          ))}
        </div>
      )}

      {/* 동적 서브섹터 */}
      {sector.dynamic_subsectors?.length > 0 && (
        <div style={{ borderTop: "1px solid rgba(255,152,0,0.2)", marginTop: "8px", paddingTop: "6px" }}>
          {(sector.dynamic_subsectors as any[]).map((ds: any, i: number) => (
            <div key={i} style={{ padding: "4px 8px", background: "rgba(255,152,0,0.07)", borderLeft: "2px solid #ff9800", borderRadius: "0 4px 4px 0", marginBottom: "4px" }}>
              <span style={{ fontSize: "0.88rem", color: "#ff9800", fontWeight: 700 }}>📡 {ds.name}</span>
              {ds.reason && <span style={{ fontSize: "0.82rem", color: "#aaa", marginLeft: "8px" }}>{ds.reason}</span>}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ── 핫 섹터 내 종목 행 ────────────────────────────────────────────────────────
function HotSectorStockRow({ stock }: { stock: any }) {
  const router = useRouter();
  const { data } = useSWR(
    stock.code ? `/api/kr/stocks/${stock.code}` : null,
    () => api.kr.stockPrice(stock.code),
    { revalidateOnFocus: false }
  ) as { data: any };

  const price = data?.price ?? 0;
  const pct = data?.change_pct ?? 0;
  const isCore = stock.r === "core";
  const pctColor = pct > 0 ? "#ff4b4b" : pct < 0 ? "#2b7cff" : "#888";

  return (
    <div
      onClick={() => router.push(`/search?q=${stock.code}`)}
      className="hover-highlight"
      style={{ display: "flex", alignItems: "center", gap: "8px", padding: "4px 0", cursor: "pointer", fontSize: "0.9rem", borderBottom: "1px solid rgba(255,255,255,0.03)" }}
    >
      <span style={{ minWidth: "1.4rem", fontSize: "0.8rem" }}>{pct >= 3 ? "✅" : ""}</span>
      <span style={{ flex: 1 }}>{isCore ? "🔑 " : ""}{stock.name}</span>
      <span style={{ color: "var(--color-text)" }}>{price > 0 ? `₩${price.toLocaleString()}` : "---"}</span>
      <span style={{ color: pctColor, fontWeight: 700, minWidth: "64px", textAlign: "right" }}>
        {data ? `${pct > 0 ? "+" : ""}${pct.toFixed(2)}%` : "..."}
      </span>
    </div>
  );
}

// ── 개별 종목 행 (KR / US 분기) ─────────────────────────────────────────────
function SubSectorStockRow({ stock, market }: { stock: any; market: "KR" | "US" }) {
  const router = useRouter();
  const isKR = market === "KR";

  const { data: krData } = useSWR<any>(
    isKR && stock.code ? `/api/kr/stocks/${stock.code}` : null,
    () => api.kr.stockPrice(stock.code),
    { refreshInterval: 30000 }
  );
  const { data: usData } = useSWR<any>(
    !isKR && stock.ticker ? `/api/us/stocks/${stock.ticker}` : null,
    () => api.us.stockDetail(stock.ticker),
    { refreshInterval: 30000 }
  );

  const data = isKR ? krData : usData;
  const price  = (data?.price  ?? 0) as number;
  const change = (data?.change_pct ?? 0) as number;
  const isUp   = change > 0;
  const isDown = change < 0;
  const color  = isUp ? "var(--color-danger)" : isDown ? "var(--color-primary)" : "var(--color-text)";

  const identifier = isKR ? stock.code : stock.ticker;
  const marketParam = isKR ? "" : "&market=US";

  return (
    <div
      onClick={() => router.push(`/search?q=${identifier}${marketParam}`)}
      className="hover-highlight"
      style={{ display: "grid", gridTemplateColumns: "60px 2fr 1fr 1fr 100px", padding: "12px 1rem", borderBottom: "1px solid rgba(255,255,255,0.03)", fontSize: "0.95rem", alignItems: "center", cursor: "pointer" }}
    >
      <div style={{ textAlign: "center" }} onClick={(e) => e.stopPropagation()}>
        <input type="checkbox" />
      </div>
      <div style={{ fontWeight: 600 }}>
        {stock.name}
        {!isKR && <span style={{ fontSize: "0.75rem", color: "var(--color-muted)", marginLeft: "4px" }}>({stock.ticker})</span>}
      </div>
      <div style={{ textAlign: "right" }}>
        {data ? (isKR ? price.toLocaleString() : `$${price.toFixed(2)}`) : "..."}
      </div>
      <div style={{ textAlign: "right", color, fontWeight: 700 }}>
        {data ? `${change > 0 ? "+" : ""}${change.toFixed(2)}%` : "..."}
      </div>
      <div></div>
    </div>
  );
}
