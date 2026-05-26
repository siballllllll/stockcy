"use client";

import { useState, useEffect } from "react";
import { Target, TrendingUp, Award, BarChart2, CheckCircle, XCircle, Clock, RefreshCw, Plus, Trash2 } from "lucide-react";
import { useRouter } from "next/navigation";

// 로컬스토리지 키
const BACKTEST_KEY = "stockcy_backtest_picks";

interface TrackedPick {
  id: string;
  code: string;
  name: string;
  theme: string;
  entry: number;
  target: number;
  stop: number;
  addedAt: string;          // ISO string
  closedAt?: string;
  closePrice?: number;
  result?: "win" | "loss" | "pending";
}

function ResultBadge({ result }: { result?: string }) {
  if (!result || result === "pending") {
    return (
      <span className="flex items-center gap-1 text-[0.7rem] font-bold px-2 py-1 rounded-full bg-zinc-700/60 text-zinc-400 border border-zinc-600/50">
        <Clock size={11} /> 보유 중
      </span>
    );
  }
  if (result === "win") {
    return (
      <span className="flex items-center gap-1 text-[0.7rem] font-bold px-2 py-1 rounded-full bg-emerald-500/20 text-emerald-400 border border-emerald-500/30">
        <CheckCircle size={11} /> 목표 달성
      </span>
    );
  }
  return (
    <span className="flex items-center gap-1 text-[0.7rem] font-bold px-2 py-1 rounded-full bg-red-500/20 text-red-400 border border-red-500/30">
      <XCircle size={11} /> 손절
    </span>
  );
}

export function BacktestBoard() {
  const router = useRouter();
  const [picks, setPicks] = useState<TrackedPick[]>([]);
  const [closeModal, setCloseModal] = useState<TrackedPick | null>(null);
  const [closePrice, setClosePrice] = useState("");

  useEffect(() => {
    try {
      const saved = localStorage.getItem(BACKTEST_KEY);
      if (saved) setPicks(JSON.parse(saved));
    } catch {}
  }, []);

  const save = (data: TrackedPick[]) => {
    setPicks(data);
    localStorage.setItem(BACKTEST_KEY, JSON.stringify(data));
  };

  const removePick = (id: string) => {
    save(picks.filter(p => p.id !== id));
  };

  const closePick = (pick: TrackedPick, price: number) => {
    const result: "win" | "loss" = price >= pick.target ? "win" : "loss";
    save(picks.map(p => p.id === pick.id ? {
      ...p,
      closePrice: price,
      closedAt: new Date().toISOString(),
      result,
    } : p));
    setCloseModal(null);
    setClosePrice("");
  };

  // 통계 계산
  const closed = picks.filter(p => p.result && p.result !== "pending");
  const wins   = closed.filter(p => p.result === "win").length;
  const losses = closed.filter(p => p.result === "loss").length;
  const winRate = closed.length > 0 ? Math.round((wins / closed.length) * 100) : null;
  const avgReturn = closed.length > 0
    ? (closed.reduce((sum, p) => {
        if (!p.closePrice) return sum;
        return sum + ((p.closePrice - p.entry) / p.entry * 100);
      }, 0) / closed.length).toFixed(1)
    : null;
  const pending = picks.filter(p => !p.result || p.result === "pending").length;

  return (
    <div className="flex flex-col gap-6 animate-in fade-in duration-300">
      <header className="border-b border-white/5 pb-4 flex justify-between items-end">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-white mb-1 flex items-center gap-2">
            <Target className="text-indigo-400" size={26} /> AI 타점 추적 보드
          </h1>
          <p className="text-zinc-400 text-sm">
            AI가 포착한 타점의 실제 목표 달성률을 직접 추적하고 통계를 확인하세요.
          </p>
        </div>
        <button
          onClick={() => router.push("/")}
          className="flex items-center gap-2 text-sm font-semibold bg-indigo-500/20 hover:bg-indigo-500/30 text-indigo-300 px-4 py-2 rounded-lg border border-indigo-500/30 transition-all"
        >
          <Plus size={15} /> AI 타점 보드로 이동
        </button>
      </header>

      {/* 통계 요약 카드 */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {[
          {
            label: "총 추적 종목",
            value: picks.length,
            icon: <BarChart2 size={20} className="text-indigo-400" />,
            sub: `보유 중 ${pending}개`,
            color: "border-indigo-500/30 bg-indigo-500/5",
          },
          {
            label: "승률",
            value: winRate !== null ? `${winRate}%` : "-",
            icon: <Award size={20} className="text-yellow-400" />,
            sub: closed.length > 0 ? `${wins}승 ${losses}패` : "결과 없음",
            color: "border-yellow-500/30 bg-yellow-500/5",
          },
          {
            label: "평균 수익률",
            value: avgReturn !== null ? `${Number(avgReturn) > 0 ? "+" : ""}${avgReturn}%` : "-",
            icon: <TrendingUp size={20} className={Number(avgReturn) >= 0 ? "text-emerald-400" : "text-red-400"} />,
            sub: `청산 완료 ${closed.length}건`,
            color: Number(avgReturn) >= 0 ? "border-emerald-500/30 bg-emerald-500/5" : "border-red-500/30 bg-red-500/5",
          },
          {
            label: "목표 달성",
            value: wins,
            icon: <CheckCircle size={20} className="text-emerald-400" />,
            sub: `손절 ${losses}건`,
            color: "border-emerald-500/30 bg-emerald-500/5",
          },
        ].map((stat, i) => (
          <div key={i} className={`stockcy-card p-5 border ${stat.color} flex flex-col gap-2`}>
            <div className="flex justify-between items-start">
              <span className="text-zinc-400 text-xs font-medium">{stat.label}</span>
              {stat.icon}
            </div>
            <div className="text-2xl font-black text-white">{stat.value}</div>
            <div className="text-xs text-zinc-500">{stat.sub}</div>
          </div>
        ))}
      </div>

      {/* 종목 리스트 */}
      {picks.length === 0 ? (
        <div className="stockcy-card p-16 flex flex-col items-center justify-center gap-4 text-zinc-500">
          <Target size={40} className="text-zinc-700" />
          <p className="text-sm">추적 중인 AI 타점이 없습니다.</p>
          <p className="text-xs text-zinc-600">AI 타점 보드에서 종목을 포착한 후,<br />상세 카드의 <strong className="text-indigo-400">📌 백테스트 추가</strong> 버튼으로 등록하세요.</p>
          <button
            onClick={() => router.push("/")}
            className="mt-2 flex items-center gap-2 text-sm font-bold bg-indigo-500/20 hover:bg-indigo-500/30 text-indigo-300 px-5 py-2.5 rounded-lg border border-indigo-500/30 transition-all"
          >
            <Plus size={15} /> 타점 보드 바로가기
          </button>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {picks.map(pick => {
            const retPct = pick.closePrice
              ? ((pick.closePrice - pick.entry) / pick.entry * 100).toFixed(1)
              : (((pick.target - pick.entry) / pick.entry) * 100).toFixed(1);
            const riskPct = (((pick.stop - pick.entry) / pick.entry) * 100).toFixed(1);
            const isPending = !pick.result || pick.result === "pending";

            return (
              <div key={pick.id} className={`stockcy-card border flex flex-col gap-4 ${
                pick.result === "win" ? "border-emerald-500/30" :
                pick.result === "loss" ? "border-red-500/30" :
                "border-white/5"
              }`}>
                <div className="flex justify-between items-start">
                  <div>
                    <div className="flex items-center gap-2 mb-1">
                      <span className="text-base font-black text-white">{pick.name}</span>
                      <span className="text-xs text-zinc-500 font-mono">{pick.code}</span>
                      <ResultBadge result={pick.result} />
                    </div>
                    <span className="text-[0.7rem] px-2 py-0.5 bg-white/5 text-zinc-400 rounded-full">{pick.theme}</span>
                  </div>
                  <button onClick={() => removePick(pick.id)} className="text-zinc-600 hover:text-red-400 transition-colors">
                    <Trash2 size={14} />
                  </button>
                </div>

                <div className="grid grid-cols-3 gap-2 text-center">
                  <div className="bg-emerald-500/5 border border-emerald-500/20 rounded-lg p-2">
                    <div className="text-[0.65rem] text-emerald-400/70 mb-0.5">진입가</div>
                    <div className="text-sm font-bold text-emerald-400">₩{pick.entry.toLocaleString()}</div>
                  </div>
                  <div className="bg-red-500/5 border border-red-500/20 rounded-lg p-2">
                    <div className="text-[0.65rem] text-red-400/70 mb-0.5">목표가 ({retPct}%)</div>
                    <div className="text-sm font-bold text-red-400">₩{pick.target.toLocaleString()}</div>
                  </div>
                  <div className="bg-blue-500/5 border border-blue-500/20 rounded-lg p-2">
                    <div className="text-[0.65rem] text-blue-400/70 mb-0.5">손절가 ({riskPct}%)</div>
                    <div className="text-sm font-bold text-blue-400">₩{pick.stop.toLocaleString()}</div>
                  </div>
                </div>

                {pick.closePrice && (
                  <div className="text-xs text-zinc-400 flex items-center gap-2 border-t border-white/5 pt-3">
                    <span>청산가: <strong className="text-white">₩{pick.closePrice.toLocaleString()}</strong></span>
                    <span className={`font-bold ${Number(retPct) >= 0 ? "text-emerald-400" : "text-red-400"}`}>
                      실현 {Number(retPct) >= 0 ? "+" : ""}{retPct}%
                    </span>
                  </div>
                )}

                {isPending && (
                  <div className="flex gap-2">
                    <button
                      onClick={() => { setCloseModal(pick); setClosePrice(String(pick.target)); }}
                      className="flex-1 py-2 text-xs font-bold bg-emerald-500/10 hover:bg-emerald-500/20 text-emerald-400 border border-emerald-500/20 rounded-lg transition-all flex items-center justify-center gap-1"
                    >
                      <CheckCircle size={13} /> 청산 결과 입력
                    </button>
                    <button
                      onClick={() => router.push(`/search?market=KR&q=${pick.code}`)}
                      className="flex-1 py-2 text-xs font-bold bg-white/5 hover:bg-white/10 text-zinc-300 border border-white/10 rounded-lg transition-all flex items-center justify-center gap-1"
                    >
                      <BarChart2 size={13} /> 차트 보기
                    </button>
                  </div>
                )}

                <div className="text-[0.65rem] text-zinc-600 flex items-center gap-1">
                  <Clock size={10} /> 등록: {new Date(pick.addedAt).toLocaleDateString("ko-KR")}
                  {pick.closedAt && ` · 청산: ${new Date(pick.closedAt).toLocaleDateString("ko-KR")}`}
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* 청산가 입력 모달 */}
      {closeModal && (
        <div className="fixed inset-0 bg-black/60 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="stockcy-card w-full max-w-sm border border-white/10 p-6 flex flex-col gap-5">
            <h2 className="text-lg font-bold text-white">청산 결과 입력</h2>
            <div>
              <p className="text-sm text-zinc-400 mb-1">{closeModal.name} ({closeModal.code})</p>
              <p className="text-xs text-zinc-500">
                목표가 ₩{closeModal.target.toLocaleString()} · 손절가 ₩{closeModal.stop.toLocaleString()}
              </p>
            </div>
            <div>
              <label className="text-xs font-bold text-zinc-400 mb-1 block">실제 청산가 (원)</label>
              <input
                type="number"
                value={closePrice}
                onChange={e => setClosePrice(e.target.value)}
                className="stockcy-input"
                placeholder="청산 가격 입력"
                autoFocus
              />
              {closePrice && (
                <p className={`text-xs mt-2 font-bold ${
                  Number(closePrice) >= closeModal.target ? "text-emerald-400" :
                  Number(closePrice) <= closeModal.stop ? "text-red-400" : "text-yellow-400"
                }`}>
                  {Number(closePrice) >= closeModal.target ? "✅ 목표가 달성" :
                   Number(closePrice) <= closeModal.stop ? "❌ 손절가 이탈" : "⚠️ 목표/손절 사이에서 청산"}
                  {" "}— 수익률 {((Number(closePrice) - closeModal.entry) / closeModal.entry * 100).toFixed(2)}%
                </p>
              )}
            </div>
            <div className="flex gap-3">
              <button
                onClick={() => { setCloseModal(null); setClosePrice(""); }}
                className="flex-1 py-2.5 text-sm font-bold bg-white/5 hover:bg-white/10 text-zinc-300 border border-white/10 rounded-lg transition-all"
              >
                취소
              </button>
              <button
                onClick={() => closePrice && closePick(closeModal, Number(closePrice))}
                disabled={!closePrice || Number(closePrice) <= 0}
                className="flex-1 py-2.5 text-sm font-bold bg-indigo-500 hover:bg-indigo-400 text-white rounded-lg transition-all disabled:opacity-40"
              >
                결과 저장
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
