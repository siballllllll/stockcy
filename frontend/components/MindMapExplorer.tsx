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
  const freeRef = useRef<Set<number> | null>(null);   // 이번 레이아웃에서 움직일 노드(null=전체). 펼침 시 새 자식만.

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
    freeRef.current = null;   // 열 때는 전체 레이아웃

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
        if (n.parentId === null) {       // 루트(주제)는 정확히 화면 중앙에 못 박음
          n.x = wcx; n.y = wcy;
        } else {
          const ring = n.depth * 160;
          const ang = Math.random() * Math.PI * 2;
          n.x = wcx + Math.cos(ang) * ring + (Math.random() - 0.5) * 40;
          n.y = wcy + Math.sin(ang) * ring + (Math.random() - 0.5) * 40;
        }
        n.ax = n.x; n.ay = n.y; n.vx = 0; n.vy = 0;
      }
    }
    reheat(1);   // 열릴 때 한 번 자리잡기
    setTick(t => t + 1);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, initialTopic]);

  // ── 시뮬레이션 루프 (정지형) ──────────────────────────────────────────────
  // 펼치거나 옮긴 직후에만 힘 시뮬레이션으로 '자리잡기'(쿨링) → 가라앉으면 루프를 완전히 멈춘다.
  // 자리잡은 뒤엔 어떤 움직임도 없음(idle 흔들림 없음). 루트(주제)는 항상 완전 고정.
  stepRef.current = () => {
    const ns = nodesRef.current;
    const alpha = alphaRef.current;
    const dragging = dragRef.current.id !== null || dragRef.current.panning;
    const free = freeRef.current;                       // null=전체 / Set=그 노드만 움직임(나머지 고정)
    const isFree = (id: number) => free === null || free.has(id);

    if (alpha > 0.02) {
      for (let i = 0; i < ns.length; i++) {
        const a = ensureDims(ns[i]);
        if (a.parentId === null || dragRef.current.id === a.id || !isFree(a.id)) continue;
        let fx = 0, fy = 0;
        for (let j = 0; j < ns.length; j++) {
          if (i === j) continue;
          const b = ensureDims(ns[j]);
          let dx = a.x - b.x, dy = a.y - b.y;
          let d2 = dx * dx + dy * dy;
          if (d2 < 1) { d2 = 1; dx = Math.random() - 0.5; dy = Math.random() - 0.5; }
          const d = Math.sqrt(d2);
          const f = 5000 / d2;   // 부드러운 일반 반발(정밀 비겹침은 아래 하드 분리에서 보장)
          fx += (dx / d) * f;
          fy += (dy / d) * f;
        }
        const p = ns.find(n => n.id === a.parentId);
        if (p) {
          const pe = ensureDims(p);
          const rest = a.r + pe.r + (a.depth <= 1 ? 96 : 58);
          const dx = pe.x - a.x, dy = pe.y - a.y;
          const d = Math.sqrt(dx * dx + dy * dy) || 1;
          const k = 0.010 * (d - rest);
          fx += (dx / d) * k * d;
          fy += (dy / d) * k * d;
        }
        a.vx = (a.vx + fx * 0.02) * 0.75;
        a.vy = (a.vy + fy * 0.02) * 0.75;
        const sp = Math.hypot(a.vx, a.vy);
        if (sp > 2.6) { a.vx = a.vx / sp * 2.6; a.vy = a.vy / sp * 2.6; }   // 상한 낮춰 '날아감' 방지
      }
      if (free === null) {   // 전체 레이아웃일 때만 전체 표류 제거
        let mvx = 0, mvy = 0, c = 0;
        for (const a of ns) { if (a.parentId === null) continue; mvx += a.vx; mvy += a.vy; c++; }
        if (c) { mvx /= c; mvy /= c; }
        for (const a of ns) { if (a.parentId === null) continue; a.vx -= mvx; a.vy -= mvy; }
      }
      for (const a of ns) {
        if (a.parentId === null || dragRef.current.id === a.id || !isFree(a.id)) continue;
        a.x += a.vx; a.y += a.vy;
        a.ax = a.x; a.ay = a.y;
      }
      alphaRef.current = alpha * 0.90;   // 쿨링(빠르게 가라앉음)
    }

    // ── 하드 분리: 사각형 겹침을 위치로 직접 밀어내 '절대 안 겹치게' 보장(항상 실행) ──
    let movedSep = false;
    const GAP = 14;
    const movable = (n: MNode) => n.parentId !== null && dragRef.current.id !== n.id && isFree(n.id);
    for (let iter = 0; iter < 3; iter++) {
      for (let i = 0; i < ns.length; i++) {
        const a = ensureDims(ns[i]);
        for (let j = i + 1; j < ns.length; j++) {
          const b = ensureDims(ns[j]);
          let dx = b.x - a.x, dy = b.y - a.y;
          const ox = (a.w / 2 + b.w / 2 + GAP) - Math.abs(dx);
          const oy = (a.h / 2 + b.h / 2 + GAP) - Math.abs(dy);
          if (ox <= 0 || oy <= 0) continue;           // 한 축이라도 안 겹치면 통과
          const aMov = movable(a), bMov = movable(b);
          if (!aMov && !bMov) continue;
          if (Math.min(ox, oy) > 0.5) movedSep = true; // 미세 잔여는 루프 지속에서 제외(줄다리기 방지)
          if (ox < oy) {                               // x축으로 적게 겹침 → x로 분리
            const sgn = dx === 0 ? (Math.random() < 0.5 ? -1 : 1) : Math.sign(dx);
            if (aMov && bMov) { a.x -= sgn * ox / 2; b.x += sgn * ox / 2; }
            else if (aMov) a.x -= sgn * ox; else b.x += sgn * ox;
          } else {                                     // y로 분리
            const sgn = dy === 0 ? (Math.random() < 0.5 ? -1 : 1) : Math.sign(dy);
            if (aMov && bMov) { a.y -= sgn * oy / 2; b.y += sgn * oy / 2; }
            else if (aMov) a.y -= sgn * oy; else b.y += sgn * oy;
          }
        }
      }
    }
    if (movedSep) for (const a of ns) { if (a.parentId !== null) { a.ax = a.x; a.ay = a.y; } }

    setTick(t => (t + 1) % 1000000);

    if (alphaRef.current > 0.02 || dragging || movedSep) {
      rafRef.current = requestAnimationFrame(stepRef.current!);
    } else {
      // 자리잡음 → 루프 정지(완전히 멈춤). 다음 펼치기/드래그 때 reheat로 재시작.
      rafRef.current = null;
      freeRef.current = null;
      persist();
    }
  };

  const ensureRunning = useCallback(() => {
    if (rafRef.current == null && stepRef.current) rafRef.current = requestAnimationFrame(stepRef.current);
  }, []);
  const reheat = useCallback((a = 0.7) => {
    alphaRef.current = Math.max(alphaRef.current, a);
    ensureRunning();
  }, [ensureRunning]);

  // 언마운트 시 루프 정리
  useEffect(() => {
    return () => { if (rafRef.current) { cancelAnimationFrame(rafRef.current); rafRef.current = null; } };
  }, []);

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
      const curNode = nodesRef.current.find(n => n.id === id);
      if (curNode) {
        const cur = ensureDims(curNode);
        const n = kws.length;
        const newIds: number[] = [];
        // 바깥 방향 = 부모→클릭노드 방향(중심에서 멀어지는 쪽). 루트는 전방위.
        const par = cur.parentId !== null ? nodesRef.current.find(p => p.id === cur.parentId) : null;
        const baseAng = par ? Math.atan2(cur.y - par.y, cur.x - par.x) : Math.random() * Math.PI * 2;
        const arc = par ? Math.PI * 0.85 : Math.PI * 2;   // 부모 반대쪽 부채꼴(루트만 전방위)
        // 클릭한 노드를 바깥으로 살짝 튀어나오게(앞으로) → 새 자식이 그 근처에서 자람.
        if (par) { cur.x += Math.cos(baseAng) * 34; cur.y += Math.sin(baseAng) * 34; cur.ax = cur.x; cur.ay = cur.y; }
        const dist = cur.r + 70;
        kws.forEach((k, i) => {
          const off = par ? (n === 1 ? 0 : (i / (n - 1) - 0.5)) * arc : (i / n) * arc;
          const ang = baseAng + off + (Math.random() - 0.5) * 0.1;
          const rr = dist + Math.random() * 16;
          const nid = idRef.current++;
          newIds.push(nid);
          nodesRef.current.push(ensureDims({
            id: nid,
            label: k.label, desc: k.desc, parentId: id, depth: cur.depth + 1,
            x: cur.x + Math.cos(ang) * rr, y: cur.y + Math.sin(ang) * rr,
            vx: 0, vy: 0, expanded: false, loading: false,
          }));
        });
        cur.expanded = true;
        // 기존 노드는 전부 '고정'(속도0 + 앵커로 스냅) → 부모가 비행기처럼 날아다니지 않게.
        // 새 자식만 free-set으로 자리잡는다.
        for (const nd of nodesRef.current) {
          if (newIds.includes(nd.id)) continue;
          nd.vx = 0; nd.vy = 0;
          if (nd.ax != null && nd.ay != null) { nd.x = nd.ax; nd.y = nd.ay; }
        }
        freeRef.current = new Set(newIds);
      }
    } catch { /* 펼치기 실패 — 조용히 무시(다시 클릭하면 재시도) */ }
    finally {
      const cur2 = nodesRef.current.find(n => n.id === id);
      if (cur2) cur2.loading = false;
      persist();
      reheat(0.55);   // 새 노드만 부드럽게 자리잡기(낮은 에너지 → 날아가지 않음)
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
    ensureRunning();   // 정지 상태에서도 드래그 중 재렌더되도록 루프 깨움
  };
  const onPointerDownBg = (e: React.PointerEvent) => {
    dragRef.current = { id: null, panning: true, moved: false, downId: null };
    lastPtr.current = { x: e.clientX, y: e.clientY };
    ensureRunning();   // 팬(이동) 중 재렌더
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
      // 드래그 종료 → 놓은 자리를 앵커로(거기서 살짝살짝만). 주변은 건드리지 않아 차분함.
      const node = nodesRef.current.find(n => n.id === dr.id);
      if (node) { node.ax = node.x; node.ay = node.y; }
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

  // ── 초기화 — 저장된 맵을 비우고 주제부터 새로 시작 ─────────────────────────
  const resetMap = useCallback(() => {
    try { localStorage.removeItem(storeKey); } catch { /* noop */ }
    idRef.current = 1;
    const wcx = (typeof window !== "undefined" ? window.innerWidth : 800) / 2;
    const wcy = (typeof window !== "undefined" ? window.innerHeight : 600) / 2;
    nodesRef.current = [ensureDims({
      id: 0, label: initialTopic, desc: "", parentId: null, depth: 0,
      x: wcx, y: wcy, vx: 0, vy: 0, expanded: false, loading: false,
    })];
    freeRef.current = null;
    viewRef.current = { tx: 0, ty: 0, scale: 1 };
    setSelectedId(null);
    setGen({ status: "idle", keyword: "", result: null, index: -1, msg: "" });
    reheat(1);
    setTick(t => t + 1);
    doExpand(0, false);
  }, [storeKey, initialTopic, reheat, doExpand]);

  if (!open) return null;

  const v = viewRef.current;
  const nodes = nodesRef.current;
  const panelOpen = gen.status !== "idle";

  // ── 가지(branch)별 색 — 1단계 자식마다 고유 색, 자손은 같은 색을 물려받아 소속을 구분 ──
  const PALETTE = [265, 210, 150, 35, 330, 188, 95, 18, 290, 130];   // 서로 잘 구분되는 hue들
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
  const nodeFill = (n: MNode, sel: boolean) => {
    const hue = hueOf(n);
    if (hue == null) return `url(#${gradId(0, sel)})`;          // 루트(주제)는 기존 그라데이션
    const light = Math.min(70, 48 + (n.depth - 1) * 8);          // 깊을수록 밝게
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
            {/* 미세한 '숨쉬기' 동적 효과 — CSS라 JS 루프 없이도 생기만 살림(자리·겹침엔 영향 없음) */}
            <style>{`@keyframes mm-bob{0%,100%{transform:translateY(0)}50%{transform:translateY(-2.5px)}}`}</style>
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
            {/* 노드 (가변폭 알약 + 그라데이션 + 그림자 = 입체) */}
            {nodes.map(n0 => {
              const n = ensureDims(n0);
              const sel = n.id === selectedId;
              const fs = fontOf(n.depth);
              return (
                <g key={n.id} transform={`translate(${n.x},${n.y})`}
                  style={{ cursor: "pointer" }}
                  onPointerDown={(e) => onPointerDownNode(e, n.id)}>
                  <g style={n.depth === 0 ? undefined : {
                    animation: `mm-bob ${3 + (n.id % 5) * 0.6}s ease-in-out infinite`,
                    animationDelay: `${-((n.phase ?? 0) / (Math.PI * 2)) * 4}s`,
                  }}>
                    <rect x={-n.w / 2} y={-n.h / 2} width={n.w} height={n.h} rx={n.h / 2}
                      fill={nodeFill(n, sel)} stroke={nodeStroke(n, sel)}
                      strokeWidth={sel ? 3.5 : 1.6} filter="url(#mm-shadow)" />
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
                      <circle cx={0} cy={n.h / 2 + 9} r={7} fill="#1e2330" stroke={nodeStroke(n, sel)} strokeWidth={1}
                        style={{ pointerEvents: "none" }} />
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
