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
 * 의존성 0 — 자체 force 시뮬레이션(SVG)으로 구현. 줌(휠)·가변폭 알약 노드·그라데이션/그림자(입체감).
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
  w?: number; h?: number; r?: number;   // 알약 크기(텍스트 기반) — 물리/렌더 공용
  ax?: number; ay?: number;             // 앵커(자리잡은 위치) — idle 미세 흔들림의 기준
  phase?: number;                       // idle bob 위상(노드별 다르게)
}

const TTL_MS = 3 * 24 * 60 * 60 * 1000; // 노드맵 보관 3일

function fontOf(depth: number) { return depth === 0 ? 15 : depth === 1 ? 13 : 12; }

// 텍스트 기반 알약 크기 — 한글 폭(≈fontSize)을 고려해 잘리지 않게 넉넉히.
function computeDims(label: string, depth: number) {
  const fs = fontOf(depth);
  const charW = fs * 0.98;                 // 한글 기준 넉넉히
  const w = Math.max(64, Math.round(label.length * charW + fs * 2.2));
  const h = depth === 0 ? 48 : depth === 1 ? 40 : 36;
  const r = Math.max(w, h) / 2;
  return { w, h, r };
}
function ensureDims(n: MNode) {
  if (n.w == null || n.h == null || n.r == null) {
    const d = computeDims(n.label, n.depth);
    n.w = d.w; n.h = d.h; n.r = d.r;
  }
  if (n.phase == null) n.phase = Math.random() * Math.PI * 2;
  return n as Required<Pick<MNode, "w" | "h" | "r">> & MNode;
}

function gradId(depth: number, selected: boolean) {
  if (selected) return "mmg-sel";
  return depth === 0 ? "mmg-0" : depth === 1 ? "mmg-1" : "mmg-2";
}
function strokeOf(depth: number, selected: boolean) {
  if (selected) return "#a5b4fc";
  return depth === 0 ? "#f472b6" : depth === 1 ? "#60a5fa" : "#94a3b8";
}

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
  const rafRef = useRef<number | null>(null);
  const lastPtr = useRef({ x: 0, y: 0 });
  const alphaRef = useRef(0);                         // 시뮬레이션 에너지(쿨링) — 0이면 정지
  const stepRef = useRef<(() => void) | null>(null);  // 최신 step 클로저

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
    } catch { /* 손상된 캐시 무시 */ }

    if (!restored) {
      idRef.current = 1;
      const cx = (typeof window !== "undefined" ? window.innerWidth : 800) / 2;
      const cy = (typeof window !== "undefined" ? window.innerHeight : 600) / 2;
      nodesRef.current = [ensureDims({
        id: 0, label: initialTopic, desc: "", parentId: null, depth: 0,
        x: cx, y: cy, vx: 0, vy: 0, expanded: false, loading: false,
      })];
      doExpand(0, false);
    }
    // 위치는 항상 화면 중앙 기준 동심원으로 새로 시드(트리 구조=탐색내역은 보존).
    // 이전 세션에 노드가 멀리 표류한 채 저장돼 화면 밖으로 사라지던 문제 방지.
    {
      const wcx = (typeof window !== "undefined" ? window.innerWidth : 800) / 2;
      const wcy = (typeof window !== "undefined" ? window.innerHeight : 600) / 2;
      for (const n of nodesRef.current) {
        const ring = n.depth * 160;
        const ang = Math.random() * Math.PI * 2;
        n.x = wcx + Math.cos(ang) * ring + (Math.random() - 0.5) * 40;
        n.y = wcy + Math.sin(ang) * ring + (Math.random() - 0.5) * 40;
        n.ax = n.x; n.ay = n.y; n.vx = 0; n.vy = 0;
      }
    }
    reheat(1);   // 열릴 때 한 번 자리잡기
    setTick(t => t + 1);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, initialTopic]);

  // ── 시뮬레이션 루프 ────────────────────────────────────────────────────────
  // 2단계: (1) 레이아웃 regime — 펼치거나 옮긴 직후 힘 시뮬레이션으로 '자리잡기'(쿨링),
  //        (2) idle regime — 자리잡으면 각 노드가 '앵커(고정 위치)' 주변 ±2~3px로만
  //        살짝살짝 흔들림(전체 표류 0, 풍선처럼 떠다니지 않음).
  stepRef.current = () => {
    const ns = nodesRef.current;
    const cx = (typeof window !== "undefined" ? window.innerWidth : 800) / 2;
    const cy = (typeof window !== "undefined" ? window.innerHeight : 600) / 2;
    const alpha = alphaRef.current;

    if (alpha > 0.02) {
      // (1) 레이아웃 — 힘 적용 후 쿨링
      for (let i = 0; i < ns.length; i++) {
        const a = ensureDims(ns[i]);
        if (dragRef.current.id === a.id) continue;
        let fx = 0, fy = 0;
        for (let j = 0; j < ns.length; j++) {
          if (i === j) continue;
          const b = ensureDims(ns[j]);
          let dx = a.x - b.x, dy = a.y - b.y;
          let d2 = dx * dx + dy * dy;
          if (d2 < 1) { d2 = 1; dx = Math.random() - 0.5; dy = Math.random() - 0.5; }
          const d = Math.sqrt(d2);
          const minD = a.r + b.r + 46;
          let f = 16000 / d2;
          if (d < minD) f += (minD - d) * 1.1;
          fx += (dx / d) * f;
          fy += (dy / d) * f;
        }
        if (a.parentId !== null) {
          const p = ns.find(n => n.id === a.parentId);
          if (p) {
            const pe = ensureDims(p);
            const rest = a.r + pe.r + 90 + a.depth * 12;
            const dx = pe.x - a.x, dy = pe.y - a.y;
            const d = Math.sqrt(dx * dx + dy * dy) || 1;
            const k = 0.010 * (d - rest);
            fx += (dx / d) * k * d;
            fy += (dy / d) * k * d;
          }
        } else {
          fx += (cx - a.x) * 0.02;
          fy += (cy - a.y) * 0.02;
        }
        a.vx = (a.vx + fx * 0.02) * 0.80;
        a.vy = (a.vy + fy * 0.02) * 0.80;
        const sp = Math.hypot(a.vx, a.vy);
        if (sp > 7) { a.vx = a.vx / sp * 7; a.vy = a.vy / sp * 7; }
      }
      // 전체 표류(평균 속도) 제거 → 무리가 통째로 흐르지 않음
      let mvx = 0, mvy = 0, c = 0;
      for (const a of ns) { if (dragRef.current.id === a.id) continue; mvx += a.vx; mvy += a.vy; c++; }
      if (c) { mvx /= c; mvy /= c; }
      for (const a of ns) {
        if (dragRef.current.id === a.id) continue;
        a.vx -= mvx; a.vy -= mvy;
        a.x += a.vx; a.y += a.vy;
        a.ax = a.x; a.ay = a.y;   // 앵커 = 자리잡는 위치 추적
      }
      alphaRef.current = alpha * 0.95;   // 쿨링(빠르게 가라앉음)
    } else {
      // (2) idle — 앵커 주변 미세 bob (국소·비표류)
      const t = (typeof performance !== "undefined" ? performance.now() : Date.now()) / 1000;
      for (const a0 of ns) {
        const a = ensureDims(a0);
        if (dragRef.current.id === a.id) continue;
        if (a.ax == null || a.ay == null) { a.ax = a.x; a.ay = a.y; }
        const amp = a.depth === 0 ? 1.8 : 2.6;
        a.x = a.ax + Math.sin(t * 0.8 + (a.phase ?? 0)) * amp;
        a.y = a.ay + Math.cos(t * 0.66 + (a.phase ?? 0)) * amp;
      }
      alphaRef.current = 0;
    }
    setTick(t => (t + 1) % 1000000);
    rafRef.current = requestAnimationFrame(stepRef.current!);
  };

  const ensureRunning = useCallback(() => {
    if (rafRef.current == null && stepRef.current) rafRef.current = requestAnimationFrame(stepRef.current);
  }, []);
  const reheat = useCallback((a = 0.7) => {
    alphaRef.current = Math.max(alphaRef.current, a);
    ensureRunning();
  }, [ensureRunning]);

  // 마운트 동안 루프 가동(idle bob 포함) + 언마운트 시 정리
  useEffect(() => {
    if (!open) return;
    ensureRunning();
    return () => { if (rafRef.current) { cancelAnimationFrame(rafRef.current); rafRef.current = null; } };
  }, [open, ensureRunning]);

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
          const ang = (Math.PI * 2 * i) / Math.max(1, n) + Math.random() * 0.25;
          const rr = 190 + Math.random() * 60;
          nodesRef.current.push(ensureDims({
            id: idRef.current++,
            label: k.label, desc: k.desc, parentId: id, depth: cur.depth + 1,
            x: cur.x + Math.cos(ang) * rr, y: cur.y + Math.sin(ang) * rr,
            vx: 0, vy: 0, expanded: false, loading: false,
          }));
        });
        cur.expanded = true;
      }
    } catch { /* 펼치기 실패 — 조용히 무시(다시 클릭하면 재시도) */ }
    finally {
      const cur2 = nodesRef.current.find(n => n.id === id);
      if (cur2) cur2.loading = false;
      persist();
      reheat(0.85);   // 새 노드 자리잡기
      setTick(t => t + 1);
    }
  }, [buildContext, onExpand, persist, reheat]);

  // ── 좌표 변환 / 포인터 / 줌 ────────────────────────────────────────────────
  const toSvg = (clientX: number, clientY: number) => {
    const svg = svgRef.current;
    if (!svg) return { x: clientX, y: clientY };
    const ctm = svg.getScreenCTM();
    if (!ctm) return { x: clientX, y: clientY };
    const inv = ctm.inverse();
    return { x: clientX * inv.a + clientY * inv.c + inv.e, y: clientX * inv.b + clientY * inv.d + inv.f };
  };
  // svg-space → node-space (translate+scale 역변환)
  const toNode = (sx: number, sy: number) => {
    const v = viewRef.current;
    return { x: (sx - v.tx) / v.scale, y: (sy - v.ty) / v.scale };
  };

  const onWheel = (e: React.WheelEvent) => {
    const v = viewRef.current;
    const p = toSvg(e.clientX, e.clientY);
    const factor = e.deltaY < 0 ? 1.12 : 1 / 1.12;
    const ns = Math.min(2.6, Math.max(0.3, v.scale * factor));
    // 커서 아래 지점이 고정되도록 tx,ty 보정
    v.tx = p.x - (ns / v.scale) * (p.x - v.tx);
    v.ty = p.y - (ns / v.scale) * (p.y - v.ty);
    v.scale = ns;
    setTick(t => t + 1);
  };
  const zoomBy = (factor: number) => {
    const v = viewRef.current;
    const cx = (typeof window !== "undefined" ? window.innerWidth : 800) / 2;
    const cy = (typeof window !== "undefined" ? window.innerHeight : 600) / 2;
    const ns = Math.min(2.6, Math.max(0.3, v.scale * factor));
    v.tx = cx - (ns / v.scale) * (cx - v.tx);
    v.ty = cy - (ns / v.scale) * (cy - v.ty);
    v.scale = ns;
    setTick(t => t + 1);
  };

  const onPointerDownNode = (e: React.PointerEvent, id: number) => {
    e.stopPropagation();
    (e.target as Element).setPointerCapture?.(e.pointerId);
    dragRef.current = { id, panning: false, moved: false, downId: id };
    lastPtr.current = { x: e.clientX, y: e.clientY };
    reheat(0.3);   // 옮기는 동안 주변 노드가 자연스럽게 비켜남
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
      if (node) { node.x = p.x; node.y = p.y; node.vx = 0; node.vy = 0; }
    } else if (dr.panning) {
      viewRef.current.tx += dx;
      viewRef.current.ty += dy;
    }
    lastPtr.current = { x: e.clientX, y: e.clientY };
  };
  const onPointerUp = () => {
    const dr = dragRef.current;
    if (dr.downId !== null && !dr.moved) {
      // 클릭 → 선택 + 펼치기
      const id = dr.downId;
      setSelectedId(id);
      doExpand(id, false);
    } else if (dr.id !== null && dr.moved) {
      // 드래그 종료 → 놓은 자리를 앵커로(거기서 살짝살짝) + 주변 재정렬
      const node = nodesRef.current.find(n => n.id === dr.id);
      if (node) { node.ax = node.x; node.ay = node.y; }
      reheat(0.3);
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
      background: "radial-gradient(120% 120% at 50% 40%, rgba(30,27,55,0.86), rgba(8,10,18,0.92))",
      backdropFilter: "blur(3px)",
      display: "flex", flexDirection: narrow ? "column" : "row",
    }}>
      {/* ── 그래프 영역 ── */}
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
          onWheel={onWheel}
          onPointerDown={onPointerDownBg}
          onPointerMove={onPointerMove}
          onPointerUp={onPointerUp}
        >
          <defs>
            <linearGradient id="mmg-0" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#fb7fc0" /><stop offset="100%" stopColor="#c026a3" />
            </linearGradient>
            <linearGradient id="mmg-1" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#7cb6ff" /><stop offset="100%" stopColor="#2563eb" />
            </linearGradient>
            <linearGradient id="mmg-2" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#aeb9cc" /><stop offset="100%" stopColor="#64748b" />
            </linearGradient>
            <linearGradient id="mmg-sel" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#c4b5fd" /><stop offset="100%" stopColor="#6d28d9" />
            </linearGradient>
            <filter id="mm-shadow" x="-40%" y="-40%" width="180%" height="180%">
              <feDropShadow dx="0" dy="3" stdDeviation="4" floodColor="#000" floodOpacity="0.5" />
            </filter>
          </defs>

          <g transform={`translate(${v.tx},${v.ty}) scale(${v.scale})`}>
            {/* 링크 */}
            {nodes.map(n => {
              if (n.parentId === null) return null;
              const p = nodes.find(x => x.id === n.parentId);
              if (!p) return null;
              return <line key={`l${n.id}`} x1={p.x} y1={p.y} x2={n.x} y2={n.y}
                stroke="rgba(148,163,184,0.4)" strokeWidth={1.4} />;
            })}
            {/* 노드 (가변폭 알약 + 그라데이션 + 그림자 = 입체) */}
            {nodes.map(n0 => {
              const n = ensureDims(n0);
              const sel = n.id === selectedId;
              const fs = fontOf(n.depth);
              return (
                <g key={n.id} transform={`translate(${n.x},${n.y})`}
                  style={{ cursor: "pointer" }}
                  onPointerDown={(e) => onPointerDownNode(e, n.id)}>
                  <rect x={-n.w / 2} y={-n.h / 2} width={n.w} height={n.h} rx={n.h / 2}
                    fill={`url(#${gradId(n.depth, sel)})`} stroke={strokeOf(n.depth, sel)}
                    strokeWidth={sel ? 3 : 1.4} filter="url(#mm-shadow)" />
                  {/* 상단 하이라이트(유광 입체감) */}
                  <rect x={-n.w / 2 + 5} y={-n.h / 2 + 4} width={n.w - 10} height={n.h * 0.36} rx={n.h * 0.2}
                    fill="rgba(255,255,255,0.18)" style={{ pointerEvents: "none" }} />
                  <text textAnchor="middle" dy="0.34em" fontSize={fs}
                    fontWeight={n.depth === 0 ? 800 : 700} fill="#fff"
                    style={{ pointerEvents: "none", userSelect: "none" }}>
                    {n.label}
                  </text>
                  {n.loading && (
                    <text textAnchor="middle" dy={n.h / 2 + 15} fontSize={11} fill="#cbd5e1" style={{ pointerEvents: "none" }}>펼치는 중…</text>
                  )}
                  {!n.loading && !n.expanded && n.depth > 0 && (
                    <circle cx={0} cy={n.h / 2 + 9} r={7} fill="#1e2330" stroke={strokeOf(n.depth, sel)} strokeWidth={1}
                      style={{ pointerEvents: "none" }} />
                  )}
                  {!n.loading && !n.expanded && n.depth > 0 && (
                    <text textAnchor="middle" dy={n.h / 2 + 12.5} fontSize={11} fill="#cbd5e1" style={{ pointerEvents: "none" }}>＋</text>
                  )}
                </g>
              );
            })}
          </g>
        </svg>

        {/* 줌 컨트롤 */}
        <div style={{ position: "absolute", right: 12, top: 56, zIndex: 5, display: "flex", flexDirection: "column", gap: 6 }}>
          <button onClick={() => zoomBy(1.2)} title="확대"
            style={{ width: 34, height: 34, borderRadius: 8, border: "1px solid #475569", background: "rgba(17,19,30,0.9)", color: "#e5e7eb", cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "center" }}>
            <Plus size={16} />
          </button>
          <button onClick={() => zoomBy(1 / 1.2)} title="축소"
            style={{ width: 34, height: 34, borderRadius: 8, border: "1px solid #475569", background: "rgba(17,19,30,0.9)", color: "#e5e7eb", cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "center" }}>
            <Minus size={16} />
          </button>
        </div>

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
          padding: "10px 12px", background: "linear-gradient(0deg, rgba(8,10,18,0.92), transparent)",
          display: "flex", alignItems: "center", gap: 10,
        }}>
          <div style={{ fontSize: "0.74rem", color: "#cbd5e1", flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
            {selectedNode ? <>선택: <b style={{ color: "#a5b4fc" }}>{selectedNode.label}</b></> : "노드를 선택하세요"}
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
                「<span style={{ color: "#a5b4fc" }}>{gen.keyword}</span>」 노드로<br />시나리오를 생성하시겠습니까?
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
            <Sparkles size={14} color="#a5b4fc" />
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
                style={{ marginTop: 12, width: "100%", padding: "9px", borderRadius: 8, border: "1px solid #6366f1", background: "transparent", color: "#a5b4fc", cursor: "pointer", fontWeight: 800, fontSize: "0.8rem", display: "flex", alignItems: "center", justifyContent: "center", gap: 4 }}>
                전체 시나리오 보기 <ChevronRight size={14} />
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
