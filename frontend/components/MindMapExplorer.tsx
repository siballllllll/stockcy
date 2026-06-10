"use client";
/**
 * 마인드맵 탐색 (커스텀 시나리오 보조 기능 / 프로토타입)
 * ─────────────────────────────────────────────────────────────────────────────
 * 주제를 던지면 보골보골 떠다니는 노드로 연관 키워드가 펼쳐지고, 노드를 클릭하며
 * 원하는 줄기를 탐색한 뒤 '선택 노드로 시나리오 생성'으로 기존 커스텀 시나리오를 뽑는다.
 *
 * 비용 설계:
 *  - 노드 펼치기(onExpand) = 검색X·무크레딧·캐시 → 거의 무과금. 재클릭은 캐시.
 *  - 시나리오 생성(onGenerate) = 기존 /scenarios/custom (과금) — 선택+확인 2단계 게이트로 오클릭 방지.
 *
 * 의존성 0 — 자체 force 시뮬레이션(SVG)으로 구현(이 프로젝트 Next.js 특수성 회피).
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { X, RefreshCw, Loader2, Sparkles, ChevronRight } from "lucide-react";

type ExpandFn = (topic: string, context: string, refresh: boolean) => Promise<{ label: string; desc: string }[]>;
type GenerateFn = (keyword: string) => Promise<{ issue: any; index: number } | null>;

interface Props {
  open: boolean;
  initialTopic: string;
  onClose: () => void;
  onExpand: ExpandFn;
  onGenerate: GenerateFn;
  onOpenIssue: (index: number) => void;   // '전체 시나리오 보기' → 메인 카드로
}

interface MNode {
  id: number;
  label: string;
  desc: string;
  parentId: number | null;
  depth: number;
  x: number; y: number; vx: number; vy: number;
  expanded: boolean;
  loading: boolean;
}

const TTL_MS = 3 * 24 * 60 * 60 * 1000; // 노드맵 보관 3일

function radiusOf(depth: number) {
  return depth === 0 ? 46 : depth === 1 ? 34 : 28;
}
function colorOf(depth: number, selected: boolean) {
  if (selected) return { fill: "rgba(99,102,241,0.25)", stroke: "#818cf8" };
  if (depth === 0) return { fill: "rgba(236,72,153,0.18)", stroke: "#ec4899" };
  if (depth === 1) return { fill: "rgba(59,130,246,0.14)", stroke: "#3b82f6" };
  return { fill: "rgba(148,163,184,0.12)", stroke: "#94a3b8" };
}
function clip(s: string, depth: number) {
  const max = depth === 0 ? 9 : depth === 1 ? 7 : 6;
  return s.length > max ? s.slice(0, max) + "…" : s;
}

export default function MindMapExplorer({
  open, initialTopic, onClose, onExpand, onGenerate, onOpenIssue,
}: Props) {
  const nodesRef = useRef<MNode[]>([]);
  const idRef = useRef(1);
  const viewRef = useRef({ tx: 0, ty: 0 });
  const svgRef = useRef<SVGSVGElement | null>(null);
  const dragRef = useRef<{ id: number | null; panning: boolean; moved: boolean; downId: number | null }>(
    { id: null, panning: false, moved: false, downId: null }
  );
  const rafRef = useRef<number | null>(null);
  const lastPtr = useRef({ x: 0, y: 0 });

  const [, setTick] = useState(0);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [gen, setGen] = useState<{ status: "idle" | "confirm" | "running" | "done" | "error"; keyword: string; result: any; index: number; msg: string }>(
    { status: "idle", keyword: "", result: null, index: -1, msg: "" }
  );
  const [narrow, setNarrow] = useState(false);

  const storeKey = `stockcy_mindmap_${initialTopic}`;

  // ── 영속(일정 기간 보관) ──────────────────────────────────────────────────
  const persist = useCallback(() => {
    try {
      localStorage.setItem(storeKey, JSON.stringify({ ts: Date.now(), nodes: nodesRef.current, idc: idRef.current }));
    } catch { /* 용량 초과 등 무시 */ }
  }, [storeKey]);

  // ── 초기화 (열릴 때) ───────────────────────────────────────────────────────
  useEffect(() => {
    if (!open) return;
    setNarrow(typeof window !== "undefined" && window.innerWidth < 760);
    setSelectedId(null);
    setGen({ status: "idle", keyword: "", result: null, index: -1, msg: "" });
    viewRef.current = { tx: 0, ty: 0 };

    let restored = false;
    try {
      const raw = localStorage.getItem(storeKey);
      if (raw) {
        const o = JSON.parse(raw);
        if (o?.ts && Date.now() - o.ts < TTL_MS && Array.isArray(o.nodes) && o.nodes.length) {
          nodesRef.current = o.nodes;
          idRef.current = o.idc ?? (Math.max(...o.nodes.map((n: MNode) => n.id)) + 1);
          restored = true;
        }
      }
    } catch { /* 손상된 캐시 무시 */ }

    if (!restored) {
      idRef.current = 1;
      const cx = (typeof window !== "undefined" ? window.innerWidth : 800) / 2;
      const cy = (typeof window !== "undefined" ? window.innerHeight : 600) / 2;
      nodesRef.current = [{
        id: 0, label: initialTopic, desc: "", parentId: null, depth: 0,
        x: cx, y: cy, vx: 0, vy: 0, expanded: false, loading: false,
      }];
      // 루트는 자동으로 한 번 펼친다
      doExpand(0, false);
    }
    setTick(t => t + 1);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, initialTopic]);

  // ── 물리 시뮬레이션 루프 ───────────────────────────────────────────────────
  useEffect(() => {
    if (!open) return;
    const step = () => {
      const ns = nodesRef.current;
      const cx = (typeof window !== "undefined" ? window.innerWidth : 800) / 2;
      const cy = (typeof window !== "undefined" ? window.innerHeight : 600) / 2;
      for (let i = 0; i < ns.length; i++) {
        const a = ns[i];
        if (dragRef.current.id === a.id) continue;
        let fx = 0, fy = 0;
        // 노드 간 반발
        for (let j = 0; j < ns.length; j++) {
          if (i === j) continue;
          const b = ns[j];
          let dx = a.x - b.x, dy = a.y - b.y;
          let d2 = dx * dx + dy * dy;
          if (d2 < 1) { d2 = 1; dx = Math.random() - 0.5; dy = Math.random() - 0.5; }
          const f = 5200 / d2;
          const d = Math.sqrt(d2);
          fx += (dx / d) * f;
          fy += (dy / d) * f;
        }
        // 부모와의 스프링
        if (a.parentId !== null) {
          const p = ns.find(n => n.id === a.parentId);
          if (p) {
            const rest = 120 + a.depth * 16;
            const dx = p.x - a.x, dy = p.y - a.y;
            const d = Math.sqrt(dx * dx + dy * dy) || 1;
            const k = 0.012 * (d - rest);
            fx += (dx / d) * k * d;
            fy += (dy / d) * k * d;
          }
        } else {
          // 루트는 화면 중앙으로 약하게
          fx += (cx - a.x) * 0.02;
          fy += (cy - a.y) * 0.02;
        }
        // 보골보골 — 미세 지터
        fx += (Math.random() - 0.5) * 1.4;
        fy += (Math.random() - 0.5) * 1.4;

        a.vx = (a.vx + fx * 0.02) * 0.82;
        a.vy = (a.vy + fy * 0.02) * 0.82;
        const sp = Math.hypot(a.vx, a.vy);
        const cap = 6;
        if (sp > cap) { a.vx = a.vx / sp * cap; a.vy = a.vy / sp * cap; }
        a.x += a.vx;
        a.y += a.vy;
      }
      setTick(t => (t + 1) % 1000000);
      rafRef.current = requestAnimationFrame(step);
    };
    rafRef.current = requestAnimationFrame(step);
    return () => { if (rafRef.current) cancelAnimationFrame(rafRef.current); };
  }, [open]);

  // ── 노드 펼치기 ───────────────────────────────────────────────────────────
  const buildContext = useCallback((id: number): string => {
    const ns = nodesRef.current;
    const path: string[] = [];
    let cur = ns.find(n => n.id === id);
    while (cur) {
      path.unshift(cur.label);
      cur = cur.parentId !== null ? ns.find(n => n.id === cur!.parentId) : undefined;
    }
    return path.join(" > ");
  }, []);

  const doExpand = useCallback(async (id: number, refresh: boolean) => {
    const ns = nodesRef.current;
    const node = ns.find(n => n.id === id);
    if (!node || node.loading) return;
    if (node.expanded && !refresh) return; // 재클릭=캐시(추가 호출 X)

    // refresh면 기존 자식 제거
    if (refresh) {
      const kill = new Set<number>();
      const collect = (pid: number) => {
        for (const c of nodesRef.current) if (c.parentId === pid) { kill.add(c.id); collect(c.id); }
      };
      collect(id);
      nodesRef.current = nodesRef.current.filter(n => !kill.has(n.id));
    }

    node.loading = true;
    setTick(t => t + 1);
    const ctxAncestors = buildContext(id).split(" > ").slice(0, -1).join(" > ");
    try {
      const kws = await onExpand(node.label, ctxAncestors, refresh);
      const cur = nodesRef.current.find(n => n.id === id);
      if (cur) {
        const n = kws.length;
        kws.forEach((k, i) => {
          const ang = (Math.PI * 2 * i) / Math.max(1, n) + Math.random() * 0.3;
          const r = 110 + Math.random() * 30;
          nodesRef.current.push({
            id: idRef.current++,
            label: k.label, desc: k.desc, parentId: id, depth: cur.depth + 1,
            x: cur.x + Math.cos(ang) * r, y: cur.y + Math.sin(ang) * r,
            vx: 0, vy: 0, expanded: false, loading: false,
          });
        });
        cur.expanded = true;
      }
    } catch { /* 펼치기 실패 — 조용히 무시(다시 클릭하면 재시도) */ }
    finally {
      const cur2 = nodesRef.current.find(n => n.id === id);
      if (cur2) cur2.loading = false;
      persist();
      setTick(t => t + 1);
    }
  }, [buildContext, onExpand, persist]);

  // ── 포인터(드래그/팬/클릭) ────────────────────────────────────────────────
  const toSvg = (clientX: number, clientY: number) => {
    const svg = svgRef.current;
    if (!svg) return { x: clientX, y: clientY };
    const ctm = svg.getScreenCTM();
    if (!ctm) return { x: clientX, y: clientY };
    const inv = ctm.inverse();
    return { x: clientX * inv.a + clientY * inv.c + inv.e, y: clientX * inv.b + clientY * inv.d + inv.f };
  };

  const onPointerDownNode = (e: React.PointerEvent, id: number) => {
    e.stopPropagation();
    (e.target as Element).setPointerCapture?.(e.pointerId);
    dragRef.current = { id, panning: false, moved: false, downId: id };
    lastPtr.current = { x: e.clientX, y: e.clientY };
  };
  const onPointerDownBg = (e: React.PointerEvent) => {
    dragRef.current = { id: null, panning: true, moved: false, downId: null };
    lastPtr.current = { x: e.clientX, y: e.clientY };
  };
  const onPointerMove = (e: React.PointerEvent) => {
    const dr = dragRef.current;
    const dx = e.clientX - lastPtr.current.x;
    const dy = e.clientY - lastPtr.current.y;
    if (Math.abs(dx) + Math.abs(dy) > 3) dr.moved = true;
    if (dr.id !== null) {
      const p = toSvg(e.clientX, e.clientY);
      const node = nodesRef.current.find(n => n.id === dr.id);
      if (node) { node.x = p.x - viewRef.current.tx; node.y = p.y - viewRef.current.ty; node.vx = 0; node.vy = 0; }
    } else if (dr.panning) {
      viewRef.current.tx += dx;
      viewRef.current.ty += dy;
    }
    lastPtr.current = { x: e.clientX, y: e.clientY };
  };
  const onPointerUp = (e: React.PointerEvent) => {
    const dr = dragRef.current;
    if (dr.downId !== null && !dr.moved) {
      // 클릭으로 간주 → 선택 + 펼치기
      const id = dr.downId;
      setSelectedId(id);
      doExpand(id, false);
    }
    dragRef.current = { id: null, panning: false, moved: false, downId: null };
  };

  // ── 시나리오 생성 ─────────────────────────────────────────────────────────
  const selectedNode = nodesRef.current.find(n => n.id === selectedId) || null;
  const genKeyword = (n: MNode) => (n.depth === 0 ? n.label : `${nodesRef.current[0]?.label ?? ""} ${n.label}`.trim());

  const requestGenerate = () => {
    if (!selectedNode) return;
    setGen({ status: "confirm", keyword: genKeyword(selectedNode), result: null, index: -1, msg: "" });
  };
  const confirmGenerate = async () => {
    const kw = gen.keyword;
    setGen(g => ({ ...g, status: "running", msg: "🔍 시나리오 분석 중... (최대 2분)" }));
    try {
      const out = await onGenerate(kw);
      if (!out || !out.issue) throw new Error("결과를 받지 못했습니다.");
      setGen({ status: "done", keyword: kw, result: out.issue, index: out.index, msg: "" });
    } catch (e) {
      setGen(g => ({ ...g, status: "error", msg: String(e instanceof Error ? e.message : e).replace(/^Error:\s*/, "") }));
    }
  };

  if (!open) return null;

  const v = viewRef.current;
  const nodes = nodesRef.current;
  const panelOpen = gen.status !== "idle";

  return (
    <div style={{
      position: "fixed", inset: 0, zIndex: 1000,
      background: "rgba(10,12,20,0.72)", backdropFilter: "blur(3px)",
      display: "flex", flexDirection: narrow ? "column" : "row",
    }}>
      {/* ── 그래프 영역 ── */}
      <div style={{ position: "relative", flex: 1, minHeight: 0, overflow: "hidden" }}>
        {/* 상단 바 */}
        <div style={{
          position: "absolute", top: 0, left: 0, right: 0, zIndex: 5,
          display: "flex", alignItems: "center", gap: 8, padding: "10px 12px",
          background: "linear-gradient(180deg, rgba(10,12,20,0.85), transparent)",
        }}>
          <Sparkles size={16} color="#818cf8" />
          <div style={{ fontWeight: 800, fontSize: "0.9rem", color: "#e5e7eb" }}>
            마인드맵 탐색 · <span style={{ color: "#818cf8" }}>{initialTopic}</span>
          </div>
          <div style={{ fontSize: "0.68rem", color: "#94a3b8" }}>노드를 클릭해 펼치고, 원하는 노드를 골라 시나리오를 생성하세요</div>
          <button onClick={onClose} style={{
            marginLeft: "auto", background: "transparent", border: "none", cursor: "pointer", color: "#cbd5e1",
            display: "flex", alignItems: "center", gap: 4, fontSize: "0.78rem",
          }}>
            <X size={18} /> 닫기
          </button>
        </div>

        <svg
          ref={svgRef}
          width="100%" height="100%"
          style={{ touchAction: "none", cursor: "grab", display: "block" }}
          onPointerDown={onPointerDownBg}
          onPointerMove={onPointerMove}
          onPointerUp={onPointerUp}
        >
          <g transform={`translate(${v.tx},${v.ty})`}>
            {/* 링크 */}
            {nodes.map(n => {
              if (n.parentId === null) return null;
              const p = nodes.find(x => x.id === n.parentId);
              if (!p) return null;
              return <line key={`l${n.id}`} x1={p.x} y1={p.y} x2={n.x} y2={n.y}
                stroke="rgba(148,163,184,0.35)" strokeWidth={1} />;
            })}
            {/* 노드 */}
            {nodes.map(n => {
              const r = radiusOf(n.depth);
              const sel = n.id === selectedId;
              const c = colorOf(n.depth, sel);
              return (
                <g key={n.id} transform={`translate(${n.x},${n.y})`}
                  style={{ cursor: "pointer" }}
                  onPointerDown={(e) => onPointerDownNode(e, n.id)}>
                  <circle r={r} fill={c.fill} stroke={c.stroke} strokeWidth={sel ? 3 : 1.5} />
                  <text textAnchor="middle" dy="0.1em" fontSize={n.depth === 0 ? 13 : 11}
                    fontWeight={n.depth === 0 ? 800 : 600} fill="#e5e7eb" style={{ pointerEvents: "none", userSelect: "none" }}>
                    {clip(n.label, n.depth)}
                  </text>
                  {n.loading && (
                    <text textAnchor="middle" dy={r + 14} fontSize={10} fill="#94a3b8" style={{ pointerEvents: "none" }}>펼치는 중…</text>
                  )}
                  {!n.loading && !n.expanded && n.depth > 0 && (
                    <text textAnchor="middle" dy={r + 13} fontSize={11} fill="#64748b" style={{ pointerEvents: "none" }}>＋</text>
                  )}
                </g>
              );
            })}
          </g>
        </svg>

        {/* 선택 노드 정보 + 갱신 */}
        {selectedNode && (
          <div style={{
            position: "absolute", left: 12, bottom: 76, maxWidth: 320, zIndex: 5,
            background: "rgba(17,19,30,0.92)", border: "1px solid #334155", borderRadius: 10, padding: "10px 12px",
          }}>
            <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
              <div style={{ fontWeight: 800, fontSize: "0.84rem", color: "#e5e7eb" }}>{selectedNode.label}</div>
              <button onClick={() => doExpand(selectedNode.id, true)} title="최신 이슈 반영해 갱신"
                style={{ marginLeft: "auto", background: "transparent", border: "none", cursor: "pointer", color: "#94a3b8", display: "flex", alignItems: "center", gap: 3, fontSize: "0.68rem" }}>
                <RefreshCw size={12} /> 갱신
              </button>
            </div>
            {selectedNode.desc && <div style={{ fontSize: "0.72rem", color: "#94a3b8", marginTop: 4, lineHeight: 1.4 }}>{selectedNode.desc}</div>}
          </div>
        )}

        {/* 하단 고정 생성 바 */}
        <div style={{
          position: "absolute", left: 0, right: 0, bottom: 0, zIndex: 5,
          padding: "10px 12px", background: "linear-gradient(0deg, rgba(10,12,20,0.92), transparent)",
          display: "flex", alignItems: "center", gap: 10,
        }}>
          <div style={{ fontSize: "0.74rem", color: "#cbd5e1", flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
            {selectedNode ? <>선택: <b style={{ color: "#818cf8" }}>{selectedNode.label}</b></> : "노드를 선택하세요"}
          </div>
          <button
            onClick={requestGenerate}
            disabled={!selectedNode || gen.status === "running"}
            style={{
              padding: "9px 16px", borderRadius: 8, border: "none", fontWeight: 800, fontSize: "0.82rem",
              cursor: selectedNode ? "pointer" : "not-allowed",
              background: selectedNode ? "linear-gradient(135deg,#6366f1,#8b5cf6)" : "#374151",
              color: "#fff", display: "flex", alignItems: "center", gap: 6, opacity: selectedNode ? 1 : 0.6,
            }}>
            <Sparkles size={15} /> 선택 노드로 시나리오 생성
          </button>
        </div>

        {/* 확인 다이얼로그 */}
        {gen.status === "confirm" && (
          <div style={{ position: "absolute", inset: 0, zIndex: 10, display: "flex", alignItems: "center", justifyContent: "center", background: "rgba(0,0,0,0.5)" }}>
            <div style={{ background: "#11131e", border: "1px solid #334155", borderRadius: 12, padding: 20, maxWidth: 340, textAlign: "center" }}>
              <div style={{ fontSize: "0.92rem", color: "#e5e7eb", fontWeight: 700, lineHeight: 1.5 }}>
                「<span style={{ color: "#818cf8" }}>{gen.keyword}</span>」 노드로<br />시나리오를 생성하시겠습니까?
              </div>
              <div style={{ fontSize: "0.72rem", color: "#94a3b8", marginTop: 8 }}>AI 분석 1회가 사용됩니다.</div>
              <div style={{ display: "flex", gap: 8, marginTop: 16 }}>
                <button onClick={() => setGen(g => ({ ...g, status: "idle" }))}
                  style={{ flex: 1, padding: "9px", borderRadius: 8, border: "1px solid #475569", background: "transparent", color: "#cbd5e1", cursor: "pointer", fontWeight: 700 }}>
                  취소
                </button>
                <button onClick={confirmGenerate}
                  style={{ flex: 1, padding: "9px", borderRadius: 8, border: "none", background: "linear-gradient(135deg,#6366f1,#8b5cf6)", color: "#fff", cursor: "pointer", fontWeight: 800 }}>
                  생성
                </button>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* ── 결과 패널(슬라이드인 / 모바일 바텀시트) ── */}
      {panelOpen && gen.status !== "confirm" && (
        <div style={{
          width: narrow ? "auto" : 340, maxHeight: narrow ? "45%" : "auto",
          borderLeft: narrow ? "none" : "1px solid #334155", borderTop: narrow ? "1px solid #334155" : "none",
          background: "#0f1118", overflowY: "auto", padding: 14, flexShrink: 0,
        }}>
          <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 10 }}>
            <Sparkles size={14} color="#818cf8" />
            <div style={{ fontWeight: 800, fontSize: "0.84rem", color: "#e5e7eb", flex: 1 }}>시나리오 결과</div>
            <button onClick={() => setGen({ status: "idle", keyword: "", result: null, index: -1, msg: "" })}
              style={{ background: "transparent", border: "none", cursor: "pointer", color: "#94a3b8" }}><X size={16} /></button>
          </div>

          {gen.status === "running" && (
            <div style={{ display: "flex", alignItems: "center", gap: 8, color: "#cbd5e1", fontSize: "0.8rem", padding: "20px 0" }}>
              <Loader2 className="animate-spin" size={16} /> {gen.msg}
            </div>
          )}
          {gen.status === "error" && (
            <div style={{ color: "#f87171", fontSize: "0.8rem", lineHeight: 1.5 }}>{gen.msg}</div>
          )}
          {gen.status === "done" && gen.result && (
            <div>
              <div style={{ fontWeight: 800, fontSize: "0.9rem", color: "#e5e7eb" }}>{gen.result.title}</div>
              {gen.result.summary && <div style={{ fontSize: "0.74rem", color: "#94a3b8", marginTop: 6, lineHeight: 1.5 }}>{gen.result.summary}</div>}
              {/* A/B 확률 */}
              {Array.isArray(gen.result.scenarios) && gen.result.scenarios.map((s: any, i: number) => (
                <div key={i} style={{ marginTop: 10, border: "1px solid #2a2f3e", borderRadius: 8, padding: 10 }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                    <span style={{ fontWeight: 800, color: i === 0 ? "#34d399" : "#f87171", fontSize: "0.8rem" }}>{s.label}</span>
                    <span style={{ fontSize: "0.76rem", color: "#cbd5e1", flex: 1 }}>{s.title}</span>
                    <span style={{ fontWeight: 800, color: "#818cf8", fontSize: "0.82rem" }}>{s.probability_pct}%</span>
                  </div>
                  {Array.isArray(s.theme_stocks) && s.theme_stocks.length > 0 && (
                    <div style={{ marginTop: 6, display: "flex", flexWrap: "wrap", gap: 4 }}>
                      {s.theme_stocks.slice(0, 5).map((t: any, j: number) => (
                        <span key={j} style={{ fontSize: "0.68rem", background: "#1e2330", color: "#cbd5e1", borderRadius: 4, padding: "2px 6px" }}>
                          {t.name}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              ))}
              <button
                onClick={() => { if (gen.index >= 0) onOpenIssue(gen.index); onClose(); }}
                style={{ marginTop: 12, width: "100%", padding: "9px", borderRadius: 8, border: "1px solid #6366f1", background: "transparent", color: "#818cf8", cursor: "pointer", fontWeight: 800, fontSize: "0.8rem", display: "flex", alignItems: "center", justifyContent: "center", gap: 4 }}>
                전체 시나리오 보기 <ChevronRight size={14} />
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
