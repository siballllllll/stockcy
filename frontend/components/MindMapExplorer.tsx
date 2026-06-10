"use client";
/**
 * 마인드맵 탐색 (커스텀 시나리오 보조 기능 / 프로토타입)
 * ─────────────────────────────────────────────────────────────────────────────
 * 주제를 던지면 연관 키워드가 '방사형 트리'로 펼쳐진다. 각 1단계 가지는 자기 각도 영역(부채꼴)을
 * 차지하고, 자손은 부모의 부채꼴을 나눠 가지며 바깥 링으로 뻗는다 → 가지별로 깔끔히 정돈.
 * 노드를 클릭하며 탐색한 뒤 '선택 노드로 시나리오 생성'으로 기존 커스텀 시나리오를 뽑는다.
 *
 * 배치는 결정적(force 시뮬레이션 X) — 떠다니지 않고 겹치지 않는다. 생기(動)는 CSS 미세 흔들림만.
 * 비용: 펼치기=검색X·thinking0·무크레딧·캐시(거의 무과금) / 생성=기존 /scenarios/custom(과금).
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { X, RefreshCw, Loader2, Sparkles, ChevronRight, Plus, Minus } from "lucide-react";

type ExpandFn = (topic: string, context: string, refresh: boolean) => Promise<{ label: string; desc: string }[]>;
type GenerateFn = (keyword: string) => Promise<{ issue: any; index: number } | null>;

interface Props {
  open: boolean;
  initialTopic: string;
  onClose: () => void;
  onExpand: ExpandFn;
  onGenerate: GenerateFn;
  onOpenIssue: (index: number) => void;
}

interface MNode {
  id: number;
  label: string;
  desc: string;
  parentId: number | null;
  depth: number;
  x: number; y: number;
  expanded: boolean;
  loading: boolean;
  w?: number; h?: number;
  phase?: number;     // CSS bob 위상(노드별 다르게)
}

const TTL_MS = 3 * 24 * 60 * 60 * 1000;

function fontOf(depth: number) { return depth === 0 ? 15 : depth === 1 ? 13 : 12; }
function computeDims(label: string, depth: number) {
  const fs = fontOf(depth);
  const charW = fs * 0.98;
  const w = Math.max(64, Math.round(label.length * charW + fs * 2.2));
  const h = depth === 0 ? 48 : depth === 1 ? 40 : 36;
  return { w, h };
}
function ensureDims(n: MNode) {
  if (n.w == null || n.h == null) { const d = computeDims(n.label, n.depth); n.w = d.w; n.h = d.h; }
  if (n.phase == null) n.phase = Math.random() * Math.PI * 2;
  return n as Required<Pick<MNode, "w" | "h">> & MNode;
}
function radiusOfDepth(depth: number) { return depth <= 0 ? 0 : 250 + (depth - 1) * 230; }

export default function MindMapExplorer({
  open, initialTopic, onClose, onExpand, onGenerate, onOpenIssue,
}: Props) {
  const nodesRef = useRef<MNode[]>([]);
  const idRef = useRef(1);
  const viewRef = useRef({ tx: 0, ty: 0, scale: 1 });
  const svgRef = useRef<SVGSVGElement | null>(null);
  const dragRef = useRef<{ id: number | null; panning: boolean; moved: boolean; downId: number | null }>(
    { id: null, panning: false, moved: false, downId: null }
  );
  const lastPtr = useRef({ x: 0, y: 0 });

  const [, setTick] = useState(0);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [gen, setGen] = useState<{ status: "idle" | "confirm" | "running" | "done" | "error"; keyword: string; result: any; index: number; msg: string }>(
    { status: "idle", keyword: "", result: null, index: -1, msg: "" }
  );
  const [narrow, setNarrow] = useState(false);

  const storeKey = `stockcy_mindmap_${initialTopic}`;
  const render = () => setTick(t => (t + 1) % 1000000);

  const persist = useCallback(() => {
    try { localStorage.setItem(storeKey, JSON.stringify({ ts: Date.now(), nodes: nodesRef.current, idc: idRef.current })); }
    catch { /* noop */ }
  }, [storeKey]);

  // ── 방사형 트리 배치(결정적) ───────────────────────────────────────────────
  // 각 노드에 각도 영역[a0,a1]을 배정: 루트는 전원(360°), 자식은 부모 영역을 자손 수 비율로 나눔.
  // 노드는 자기 영역의 중앙 각도 + 깊이별 반지름에 배치 → 가지마다 부채꼴, 겹침 없음.
  const layout = useCallback(() => {
    const ns = nodesRef.current;
    const root = ns.find(n => n.parentId === null);
    if (!root) return;
    const childrenOf = (id: number) => ns.filter(n => n.parentId === id);
    const leafCount = (n: MNode): number => {
      const ch = childrenOf(n.id);
      return ch.length === 0 ? 1 : ch.reduce((s, c) => s + leafCount(c), 0);
    };
    const wcx = (typeof window !== "undefined" ? window.innerWidth : 800) / 2;
    const wcy = (typeof window !== "undefined" ? window.innerHeight : 600) / 2;
    root.x = wcx; root.y = wcy;
    const assign = (node: MNode, a0: number, a1: number) => {
      const ch = childrenOf(node.id);
      if (ch.length === 0) return;
      const total = ch.reduce((s, c) => s + leafCount(c), 0) || 1;
      let cur = a0;
      for (const c of ch) {
        const w = (a1 - a0) * (leafCount(c) / total);
        const ang = cur + w / 2;
        const r = radiusOfDepth(c.depth);
        c.x = wcx + Math.cos(ang) * r;
        c.y = wcy + Math.sin(ang) * r;
        assign(c, cur, cur + w);
        cur += w;
      }
    };
    assign(root, -Math.PI / 2, -Math.PI / 2 + Math.PI * 2);
    render();
  }, []);

  // ── 초기화(열릴 때) — 트리 복원 후 배치 ───────────────────────────────────
  useEffect(() => {
    if (!open) return;
    setNarrow(typeof window !== "undefined" && window.innerWidth < 760);
    setSelectedId(null);
    setGen({ status: "idle", keyword: "", result: null, index: -1, msg: "" });
    viewRef.current = { tx: 0, ty: 0, scale: 1 };

    let restored = false;
    try {
      const raw = localStorage.getItem(storeKey);
      if (raw) {
        const o = JSON.parse(raw);
        if (o?.ts && Date.now() - o.ts < TTL_MS && Array.isArray(o.nodes) && o.nodes.length) {
          nodesRef.current = o.nodes.map((n: MNode) => ensureDims(n));
          idRef.current = o.idc ?? (Math.max(...o.nodes.map((n: MNode) => n.id)) + 1);
          restored = true;
        }
      }
    } catch { /* noop */ }

    if (!restored) {
      idRef.current = 1;
      const wcx = (typeof window !== "undefined" ? window.innerWidth : 800) / 2;
      const wcy = (typeof window !== "undefined" ? window.innerHeight : 600) / 2;
      nodesRef.current = [ensureDims({
        id: 0, label: initialTopic, desc: "", parentId: null, depth: 0,
        x: wcx, y: wcy, expanded: false, loading: false,
      })];
      doExpand(0, false);
    }
    layout();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, initialTopic]);

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
    if (node.expanded && !refresh) return; // 재클릭=캐시

    if (refresh) {
      const kill = new Set<number>();
      const collect = (pid: number) => { for (const c of nodesRef.current) if (c.parentId === pid) { kill.add(c.id); collect(c.id); } };
      collect(id);
      nodesRef.current = nodesRef.current.filter(n => !kill.has(n.id));
    }

    node.loading = true;
    render();
    const ctxAncestors = buildContext(id).split(" > ").slice(0, -1).join(" > ");
    try {
      const kws = await onExpand(node.label, ctxAncestors, refresh);
      const cur = nodesRef.current.find(n => n.id === id);
      if (cur) {
        for (const k of kws) {
          nodesRef.current.push(ensureDims({
            id: idRef.current++, label: k.label, desc: k.desc, parentId: id, depth: cur.depth + 1,
            x: cur.x, y: cur.y, expanded: false, loading: false,
          }));
        }
        cur.expanded = true;
      }
    } catch { /* 실패 시 조용히 무시 */ }
    finally {
      const cur2 = nodesRef.current.find(n => n.id === id);
      if (cur2) cur2.loading = false;
      layout();           // 트리 변경 → 재배치(결정적·정돈)
      persist();
      render();
    }
  }, [buildContext, onExpand, persist, layout]);

  // ── 좌표 변환 / 포인터 / 줌 ────────────────────────────────────────────────
  const toSvg = (clientX: number, clientY: number) => {
    const svg = svgRef.current;
    if (!svg) return { x: clientX, y: clientY };
    const ctm = svg.getScreenCTM();
    if (!ctm) return { x: clientX, y: clientY };
    const inv = ctm.inverse();
    return { x: clientX * inv.a + clientY * inv.c + inv.e, y: clientX * inv.b + clientY * inv.d + inv.f };
  };
  const toNode = (sx: number, sy: number) => {
    const v = viewRef.current;
    return { x: (sx - v.tx) / v.scale, y: (sy - v.ty) / v.scale };
  };

  const onWheel = (e: React.WheelEvent) => {
    const v = viewRef.current;
    const p = toSvg(e.clientX, e.clientY);
    const factor = e.deltaY < 0 ? 1.12 : 1 / 1.12;
    const nscale = Math.min(2.6, Math.max(0.25, v.scale * factor));
    v.tx = p.x - (nscale / v.scale) * (p.x - v.tx);
    v.ty = p.y - (nscale / v.scale) * (p.y - v.ty);
    v.scale = nscale;
    render();
  };
  const zoomBy = (factor: number) => {
    const v = viewRef.current;
    const cx = (typeof window !== "undefined" ? window.innerWidth : 800) / 2;
    const cy = (typeof window !== "undefined" ? window.innerHeight : 600) / 2;
    const nscale = Math.min(2.6, Math.max(0.25, v.scale * factor));
    v.tx = cx - (nscale / v.scale) * (cx - v.tx);
    v.ty = cy - (nscale / v.scale) * (cy - v.ty);
    v.scale = nscale;
    render();
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
      const s = toSvg(e.clientX, e.clientY);
      const p = toNode(s.x, s.y);
      const node = nodesRef.current.find(n => n.id === dr.id);
      if (node && node.parentId !== null) { node.x = p.x; node.y = p.y; render(); }   // 루트는 못 옮김
    } else if (dr.panning) {
      viewRef.current.tx += dx; viewRef.current.ty += dy; render();
    }
    lastPtr.current = { x: e.clientX, y: e.clientY };
  };
  const onPointerUp = () => {
    const dr = dragRef.current;
    if (dr.downId !== null && !dr.moved) { setSelectedId(dr.downId); doExpand(dr.downId, false); }
    else if (dr.id !== null && dr.moved) persist();
    dragRef.current = { id: null, panning: false, moved: false, downId: null };
  };

  // ── 시나리오 생성 ─────────────────────────────────────────────────────────
  const selectedNode = nodesRef.current.find(n => n.id === selectedId) || null;
  const genKeyword = (n: MNode) => (n.depth === 0 ? n.label : `${nodesRef.current[0]?.label ?? ""} ${n.label}`.trim());
  const requestGenerate = () => { if (selectedNode) setGen({ status: "confirm", keyword: genKeyword(selectedNode), result: null, index: -1, msg: "" }); };
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

  // ── 초기화 ────────────────────────────────────────────────────────────────
  const resetMap = useCallback(() => {
    try { localStorage.removeItem(storeKey); } catch { /* noop */ }
    idRef.current = 1;
    const wcx = (typeof window !== "undefined" ? window.innerWidth : 800) / 2;
    const wcy = (typeof window !== "undefined" ? window.innerHeight : 600) / 2;
    nodesRef.current = [ensureDims({ id: 0, label: initialTopic, desc: "", parentId: null, depth: 0, x: wcx, y: wcy, expanded: false, loading: false })];
    viewRef.current = { tx: 0, ty: 0, scale: 1 };
    setSelectedId(null);
    setGen({ status: "idle", keyword: "", result: null, index: -1, msg: "" });
    layout();
    doExpand(0, false);
  }, [storeKey, initialTopic, layout, doExpand]);

  if (!open) return null;

  const v = viewRef.current;
  const nodes = nodesRef.current;
  const panelOpen = gen.status !== "idle";

  // ── 가지(branch)별 색 ──
  const PALETTE = [265, 210, 150, 35, 330, 188, 95, 18, 290, 130];
  const branchIdx = new Map<number, number>();
  nodes.filter(n => n.depth === 1).sort((a, b) => a.id - b.id).forEach((n, i) => branchIdx.set(n.id, i));
  const branchRootId = (n: MNode): number | null => {
    let cur: MNode | undefined = n;
    while (cur && cur.depth > 1) cur = nodes.find(x => x.id === cur!.parentId);
    return cur && cur.depth === 1 ? cur.id : null;
  };
  const hueOf = (n: MNode): number | null => {
    if (n.depth === 0) return null;
    const br = branchRootId(n);
    return br == null ? null : PALETTE[(branchIdx.get(br) ?? 0) % PALETTE.length];
  };
  const nodeFill = (n: MNode) => {
    const hue = hueOf(n);
    if (hue == null) return `url(#mmg-root)`;
    const light = Math.min(70, 48 + (n.depth - 1) * 8);
    return `hsl(${hue} 58% ${light}%)`;
  };
  const nodeStroke = (n: MNode, sel: boolean) => {
    if (sel) return "#ffffff";
    const hue = hueOf(n);
    return hue == null ? "#f472b6" : `hsl(${hue} 72% 80%)`;
  };
  const linkStroke = (n: MNode) => {
    const hue = hueOf(n);
    return hue == null ? "rgba(148,163,184,0.4)" : `hsl(${hue} 60% 62% / 0.6)`;
  };

  return (
    <div style={{
      position: "fixed", inset: 0, zIndex: 1000,
      background: "radial-gradient(120% 120% at 50% 40%, rgba(30,27,55,0.86), rgba(8,10,18,0.92))",
      backdropFilter: "blur(3px)", display: "flex", flexDirection: narrow ? "column" : "row",
    }}>
      <div style={{ position: "relative", flex: 1, minHeight: 0, overflow: "hidden" }}>
        {/* 상단 바 */}
        <div style={{
          position: "absolute", top: 0, left: 0, right: 0, zIndex: 5,
          display: "flex", alignItems: "center", gap: 8, padding: "10px 12px",
          background: "linear-gradient(180deg, rgba(8,10,18,0.85), transparent)",
        }}>
          <Sparkles size={16} color="#a5b4fc" />
          <div style={{ fontWeight: 800, fontSize: "0.9rem", color: "#e5e7eb" }}>
            마인드맵 탐색 · <span style={{ color: "#a5b4fc" }}>{initialTopic}</span>
          </div>
          {!narrow && <div style={{ fontSize: "0.68rem", color: "#94a3b8" }}>노드 클릭=펼치기 · 휠=확대/축소 · 빈 곳 드래그=이동</div>}
          <button onClick={() => { if (confirm("이 주제의 마인드맵을 초기화할까요? (저장된 노드가 모두 삭제됩니다)")) resetMap(); }} style={{
            marginLeft: "auto", background: "transparent", border: "1px solid #475569", borderRadius: 6, cursor: "pointer", color: "#cbd5e1",
            display: "flex", alignItems: "center", gap: 4, fontSize: "0.74rem", padding: "5px 10px",
          }} title="저장된 맵을 비우고 주제부터 새로 시작">
            <RefreshCw size={14} /> 초기화
          </button>
          <button onClick={onClose} style={{
            background: "transparent", border: "none", cursor: "pointer", color: "#cbd5e1",
            display: "flex", alignItems: "center", gap: 4, fontSize: "0.78rem",
          }}>
            <X size={18} /> 닫기
          </button>
        </div>

        <svg ref={svgRef} width="100%" height="100%"
          style={{ touchAction: "none", cursor: "grab", display: "block" }}
          onWheel={onWheel} onPointerDown={onPointerDownBg} onPointerMove={onPointerMove} onPointerUp={onPointerUp}>
          <defs>
            <linearGradient id="mmg-root" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#fb7fc0" /><stop offset="100%" stopColor="#c026a3" />
            </linearGradient>
            <filter id="mm-shadow" x="-40%" y="-40%" width="180%" height="180%">
              <feDropShadow dx="0" dy="3" stdDeviation="4" floodColor="#000" floodOpacity="0.5" />
            </filter>
            <style>{`@keyframes mm-bob{0%,100%{transform:translate(0,0)}50%{transform:translate(1px,-3px)}}`}</style>
          </defs>

          <g transform={`translate(${v.tx},${v.ty}) scale(${v.scale})`}>
            {/* 링크 */}
            {nodes.map(n => {
              if (n.parentId === null) return null;
              const p = nodes.find(x => x.id === n.parentId);
              if (!p) return null;
              return <line key={`l${n.id}`} x1={p.x} y1={p.y} x2={n.x} y2={n.y}
                stroke={linkStroke(n)} strokeWidth={n.depth === 1 ? 2.2 : 1.6} />;
            })}
            {/* 노드 */}
            {nodes.map(n0 => {
              const n = ensureDims(n0);
              const sel = n.id === selectedId;
              const fs = fontOf(n.depth);
              return (
                <g key={n.id} transform={`translate(${n.x},${n.y})`} style={{ cursor: "pointer" }}
                  onPointerDown={(e) => onPointerDownNode(e, n.id)}>
                  <g style={n.depth === 0 ? undefined : {
                    animation: `mm-bob ${3 + (n.id % 5) * 0.6}s ease-in-out infinite`,
                    animationDelay: `${-((n.phase ?? 0) / (Math.PI * 2)) * 4}s`,
                  }}>
                    <rect x={-n.w / 2} y={-n.h / 2} width={n.w} height={n.h} rx={n.h / 2}
                      fill={nodeFill(n)} stroke={nodeStroke(n, sel)} strokeWidth={sel ? 3.5 : 1.6} filter="url(#mm-shadow)" />
                    <rect x={-n.w / 2 + 5} y={-n.h / 2 + 4} width={n.w - 10} height={n.h * 0.36} rx={n.h * 0.2}
                      fill="rgba(255,255,255,0.18)" style={{ pointerEvents: "none" }} />
                    <text textAnchor="middle" dy="0.34em" fontSize={fs} fontWeight={n.depth === 0 ? 800 : 700} fill="#fff"
                      style={{ pointerEvents: "none", userSelect: "none" }}>{n.label}</text>
                    {n.loading && (
                      <text textAnchor="middle" dy={n.h / 2 + 15} fontSize={11} fill="#cbd5e1" style={{ pointerEvents: "none" }}>펼치는 중…</text>
                    )}
                    {!n.loading && !n.expanded && n.depth > 0 && (
                      <circle cx={0} cy={n.h / 2 + 9} r={7} fill="#1e2330" stroke={nodeStroke(n, sel)} strokeWidth={1} style={{ pointerEvents: "none" }} />
                    )}
                    {!n.loading && !n.expanded && n.depth > 0 && (
                      <text textAnchor="middle" dy={n.h / 2 + 12.5} fontSize={11} fill="#cbd5e1" style={{ pointerEvents: "none" }}>＋</text>
                    )}
                  </g>
                </g>
              );
            })}
          </g>
        </svg>

        {/* 줌 컨트롤 */}
        <div style={{ position: "absolute", right: 12, top: 56, zIndex: 5, display: "flex", flexDirection: "column", gap: 6 }}>
          <button onClick={() => zoomBy(1.2)} title="확대" style={{ width: 34, height: 34, borderRadius: 8, border: "1px solid #475569", background: "rgba(17,19,30,0.9)", color: "#e5e7eb", cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "center" }}><Plus size={16} /></button>
          <button onClick={() => zoomBy(1 / 1.2)} title="축소" style={{ width: 34, height: 34, borderRadius: 8, border: "1px solid #475569", background: "rgba(17,19,30,0.9)", color: "#e5e7eb", cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "center" }}><Minus size={16} /></button>
        </div>

        {/* 선택 노드 정보 + 갱신 */}
        {selectedNode && (
          <div style={{ position: "absolute", left: 12, bottom: 76, maxWidth: 320, zIndex: 5, background: "rgba(17,19,30,0.92)", border: "1px solid #334155", borderRadius: 10, padding: "10px 12px" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
              <div style={{ fontWeight: 800, fontSize: "0.84rem", color: "#e5e7eb" }}>{selectedNode.label}</div>
              <button onClick={() => doExpand(selectedNode.id, true)} title="최신 이슈 반영해 갱신" style={{ marginLeft: "auto", background: "transparent", border: "none", cursor: "pointer", color: "#94a3b8", display: "flex", alignItems: "center", gap: 3, fontSize: "0.68rem" }}>
                <RefreshCw size={12} /> 갱신
              </button>
            </div>
            {selectedNode.desc && <div style={{ fontSize: "0.72rem", color: "#94a3b8", marginTop: 4, lineHeight: 1.4 }}>{selectedNode.desc}</div>}
          </div>
        )}

        {/* 하단 고정 생성 바 */}
        <div style={{ position: "absolute", left: 0, right: 0, bottom: 0, zIndex: 5, padding: "10px 12px", background: "linear-gradient(0deg, rgba(8,10,18,0.92), transparent)", display: "flex", alignItems: "center", gap: 10 }}>
          <div style={{ fontSize: "0.74rem", color: "#cbd5e1", flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
            {selectedNode ? <>선택: <b style={{ color: "#a5b4fc" }}>{selectedNode.label}</b></> : "노드를 선택하세요"}
          </div>
          <button onClick={requestGenerate} disabled={!selectedNode || gen.status === "running"} style={{
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
                「<span style={{ color: "#a5b4fc" }}>{gen.keyword}</span>」 노드로<br />시나리오를 생성하시겠습니까?
              </div>
              <div style={{ fontSize: "0.72rem", color: "#94a3b8", marginTop: 8 }}>AI 분석 1회가 사용됩니다.</div>
              <div style={{ display: "flex", gap: 8, marginTop: 16 }}>
                <button onClick={() => setGen(g => ({ ...g, status: "idle" }))} style={{ flex: 1, padding: "9px", borderRadius: 8, border: "1px solid #475569", background: "transparent", color: "#cbd5e1", cursor: "pointer", fontWeight: 700 }}>취소</button>
                <button onClick={confirmGenerate} style={{ flex: 1, padding: "9px", borderRadius: 8, border: "none", background: "linear-gradient(135deg,#6366f1,#8b5cf6)", color: "#fff", cursor: "pointer", fontWeight: 800 }}>생성</button>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* 결과 패널 */}
      {panelOpen && gen.status !== "confirm" && (
        <div style={{ width: narrow ? "auto" : 340, maxHeight: narrow ? "45%" : "auto", borderLeft: narrow ? "none" : "1px solid #334155", borderTop: narrow ? "1px solid #334155" : "none", background: "#0f1118", overflowY: "auto", padding: 14, flexShrink: 0 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 10 }}>
            <Sparkles size={14} color="#a5b4fc" />
            <div style={{ fontWeight: 800, fontSize: "0.84rem", color: "#e5e7eb", flex: 1 }}>시나리오 결과</div>
            <button onClick={() => setGen({ status: "idle", keyword: "", result: null, index: -1, msg: "" })} style={{ background: "transparent", border: "none", cursor: "pointer", color: "#94a3b8" }}><X size={16} /></button>
          </div>
          {gen.status === "running" && (
            <div style={{ display: "flex", alignItems: "center", gap: 8, color: "#cbd5e1", fontSize: "0.8rem", padding: "20px 0" }}>
              <Loader2 className="animate-spin" size={16} /> {gen.msg}
            </div>
          )}
          {gen.status === "error" && <div style={{ color: "#f87171", fontSize: "0.8rem", lineHeight: 1.5 }}>{gen.msg}</div>}
          {gen.status === "done" && gen.result && (
            <div>
              <div style={{ fontWeight: 800, fontSize: "0.9rem", color: "#e5e7eb" }}>{gen.result.title}</div>
              {gen.result.summary && <div style={{ fontSize: "0.74rem", color: "#94a3b8", marginTop: 6, lineHeight: 1.5 }}>{gen.result.summary}</div>}
              {Array.isArray(gen.result.scenarios) && gen.result.scenarios.map((s: any, i: number) => (
                <div key={i} style={{ marginTop: 10, border: "1px solid #2a2f3e", borderRadius: 8, padding: 10 }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                    <span style={{ fontWeight: 800, color: i === 0 ? "#34d399" : "#f87171", fontSize: "0.8rem" }}>{s.label}</span>
                    <span style={{ fontSize: "0.76rem", color: "#cbd5e1", flex: 1 }}>{s.title}</span>
                    <span style={{ fontWeight: 800, color: "#a5b4fc", fontSize: "0.82rem" }}>{s.probability_pct}%</span>
                  </div>
                  {Array.isArray(s.theme_stocks) && s.theme_stocks.length > 0 && (
                    <div style={{ marginTop: 6, display: "flex", flexWrap: "wrap", gap: 4 }}>
                      {s.theme_stocks.slice(0, 5).map((t: any, j: number) => (
                        <span key={j} style={{ fontSize: "0.68rem", background: "#1e2330", color: "#cbd5e1", borderRadius: 4, padding: "2px 6px" }}>{t.name}</span>
                      ))}
                    </div>
                  )}
                </div>
              ))}
              <button onClick={() => { if (gen.index >= 0) onOpenIssue(gen.index); onClose(); }} style={{ marginTop: 12, width: "100%", padding: "9px", borderRadius: 8, border: "1px solid #6366f1", background: "transparent", color: "#a5b4fc", cursor: "pointer", fontWeight: 800, fontSize: "0.8rem", display: "flex", alignItems: "center", justifyContent: "center", gap: 4 }}>
                전체 시나리오 보기 <ChevronRight size={14} />
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
