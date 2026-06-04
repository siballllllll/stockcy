"use client";
import { useState, useEffect, useRef } from "react";
import { X, RefreshCw, ChevronDown, ChevronRight } from "lucide-react";
import { getToken } from "@/lib/auth-context";

interface SectorItem {
  keyword: string;
  reason: string;
  is_main?: boolean;
  reference_news_title?: string;
  reference_news_url?: string;
  related_stocks?: { ticker: string; name_kr: string }[];
}

interface BriefingData {
  sectors?: SectorItem[];
  summary?: string;
}

interface Props {
  onClose: () => void;
}

export function BriefingModal({ onClose }: Props) {
  const [status, setStatus] = useState<"idle" | "loading" | "done" | "error">("idle");
  const [data, setData] = useState<BriefingData | null>(null);
  const [msg, setMsg] = useState("");
  const [expanded, setExpanded] = useState<Record<number, boolean>>({});
  const abortRef = useRef<AbortController | null>(null);

  const fetchBriefing = async () => {
    if (abortRef.current) abortRef.current.abort();
    abortRef.current = new AbortController();
    setStatus("loading");
    setData(null);
    setMsg("🔍 Google Search 기반 주도 섹터 분석 중...");

    try {
      const BASE = typeof window === "undefined"
        ? (process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000")
        : "/backend";
      const token = getToken();
      const res = await fetch(`${BASE}/api/ai/daily-briefing`, {
        signal: abortRef.current.signal,
        headers: {
          "ngrok-skip-browser-warning": "69420",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
      });
      if (!res.body) throw new Error("No body");

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const parts = buffer.split("\n\n");
        buffer = parts.pop() ?? "";
        for (const part of parts) {
          const line = part.trim();
          if (!line.startsWith("data:")) continue;
          try {
            const payload = JSON.parse(line.slice(5).trim());
            if (payload.status === "running") setMsg(payload.message ?? msg);
            else if (payload.status === "done") {
              setData(payload.result);
              setStatus("done");
            } else if (payload.status === "error") {
              setMsg(`❌ ${payload.message}`);
              setStatus("error");
            }
          } catch {}
        }
      }
    } catch (e: any) {
      if (e?.name !== "AbortError") {
        setMsg("❌ 브리핑 생성 중 오류가 발생했습니다.");
        setStatus("error");
      }
    }
  };

  useEffect(() => {
    fetchBriefing();
    return () => abortRef.current?.abort();
  }, []);

  const toggleExpand = (i: number) =>
    setExpanded((prev) => ({ ...prev, [i]: !prev[i] }));

  return (
    <div
      style={{
        position: "fixed", inset: 0, zIndex: 9999,
        background: "rgba(0,0,0,0.7)", backdropFilter: "blur(4px)",
        display: "flex", alignItems: "center", justifyContent: "center",
        padding: "1rem",
      }}
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
    >
      <div
        style={{
          background: "var(--color-card)", border: "1px solid var(--color-border)",
          borderRadius: "12px", width: "100%", maxWidth: "720px",
          maxHeight: "85vh", display: "flex", flexDirection: "column",
          boxShadow: "0 24px 64px rgba(0,0,0,0.6)",
        }}
      >
        {/* 헤더 */}
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "1.25rem 1.5rem", borderBottom: "1px solid var(--color-border)" }}>
          <h2 style={{ margin: 0, fontSize: "1.1rem", fontWeight: 700 }}>📰 AI 일일 브리핑</h2>
          <div style={{ display: "flex", gap: "8px" }}>
            <button
              onClick={fetchBriefing}
              disabled={status === "loading"}
              style={{ background: "transparent", border: "1px solid var(--color-border)", borderRadius: "6px", padding: "4px 10px", cursor: "pointer", color: "var(--color-muted)", display: "flex", alignItems: "center", gap: "4px", fontSize: "0.8rem" }}
            >
              <RefreshCw size={13} className={status === "loading" ? "animate-spin" : ""} />
              재생성
            </button>
            <button
              onClick={onClose}
              style={{ background: "transparent", border: "none", cursor: "pointer", color: "var(--color-muted)", display: "flex", alignItems: "center" }}
            >
              <X size={20} />
            </button>
          </div>
        </div>

        {/* 바디 */}
        <div style={{ flex: 1, overflowY: "auto", padding: "1.5rem" }}>
          {status === "loading" && (
            <div style={{ textAlign: "center", padding: "3rem 0" }}>
              <div style={{ fontSize: "2.5rem", marginBottom: "1rem" }}>🧠</div>
              <div style={{ fontWeight: 600, marginBottom: "0.5rem" }}>{msg}</div>
              <div style={{ color: "var(--color-muted)", fontSize: "0.85rem" }}>약 30~60초 소요됩니다.</div>
            </div>
          )}

          {status === "error" && (
            <div style={{ textAlign: "center", padding: "3rem 0", color: "var(--color-danger)" }}>
              {msg}
            </div>
          )}

          {status === "done" && data && (
            <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
              {data.summary && (
                <div style={{ padding: "1rem", background: "rgba(28,131,225,0.08)", border: "1px solid rgba(28,131,225,0.2)", borderRadius: "8px", lineHeight: 1.6, fontSize: "0.95rem" }}>
                  {data.summary}
                </div>
              )}

              <div style={{ fontSize: "0.8rem", color: "var(--color-muted)", padding: "4px 10px", background: "rgba(255,215,64,0.05)", border: "1px solid rgba(255,215,64,0.2)", borderRadius: "4px" }}>
                ⚠️ AI가 Google Search로 자동 생성한 정보입니다. 투자 결정 전 반드시 직접 확인하세요.
              </div>

              <h3 style={{ margin: "0.5rem 0 0", fontSize: "1rem", fontWeight: 700 }}>🔥 오늘의 주요 섹터</h3>

              {data.sectors?.map((sector, i) => (
                <div
                  key={i}
                  style={{
                    border: `1px solid ${sector.is_main ? "var(--color-warning)" : "var(--color-border)"}`,
                    borderRadius: "8px", overflow: "hidden",
                    background: sector.is_main ? "rgba(255,152,0,0.04)" : "var(--color-surface)",
                  }}
                >
                  <div
                    onClick={() => toggleExpand(i)}
                    style={{ padding: "0.9rem 1rem", cursor: "pointer", display: "flex", justifyContent: "space-between", alignItems: "center" }}
                  >
                    <span style={{ fontWeight: 700, fontSize: "0.95rem" }}>
                      {sector.is_main ? "⭐ " : ""}{sector.keyword}
                      {sector.is_main && <span style={{ marginLeft: "8px", fontSize: "0.75rem", color: "var(--color-warning)", fontWeight: 500 }}>핵심 주도 테마</span>}
                    </span>
                    {expanded[i] ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
                  </div>

                  {expanded[i] && (
                    <div style={{ padding: "0 1rem 1rem", borderTop: "1px solid rgba(255,255,255,0.05)" }}>
                      <div style={{ marginTop: "0.75rem", fontSize: "0.9rem", lineHeight: 1.6, color: "var(--color-text)" }}>
                        <strong>💡 시장 영향 및 분석:</strong><br />
                        {sector.reason}
                      </div>
                      {sector.reference_news_title && sector.reference_news_url && (
                        <div style={{ marginTop: "0.75rem", fontSize: "0.85rem" }}>
                          <strong>📰 신뢰도 검증: </strong>
                          <a href={sector.reference_news_url} target="_blank" rel="noopener noreferrer" style={{ color: "var(--color-primary)", textDecoration: "underline" }}>
                            {sector.reference_news_title}
                          </a>
                        </div>
                      )}
                      {sector.related_stocks && sector.related_stocks.length > 0 && (
                        <div style={{ marginTop: "0.75rem", fontSize: "0.85rem", color: "var(--color-muted)" }}>
                          <strong style={{ color: "var(--color-text)" }}>📊 관련 종목: </strong>
                          {sector.related_stocks.map(s => `${s.name_kr} (${s.ticker})`).join(" · ")}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
