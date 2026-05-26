import { useEffect, useRef } from "react";
import { createChart, ColorType, IChartApi, CandlestickSeries, LineSeries, HistogramSeries } from "lightweight-charts";

interface ChartData {
  time: string | number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume?: number;
}

interface ChartProps {
  data: ChartData[];
  height?: number;
  colors?: {
    backgroundColor?: string;
    textColor?: string;
    upColor?: string;
    downColor?: string;
  };
  rightPadBars?: number; // 마감까지 남은 빈 봉 수
  showSessions?: boolean; // 미국 장 구간 배경 표시
}

export default function Chart({ data, height = 450, colors = {}, rightPadBars = 0, showSessions = false }: ChartProps) {
  const chartContainerRef = useRef<HTMLDivElement>(null);
  const chartRef          = useRef<IChartApi | null>(null);
  const seriesRef         = useRef<any>(null);

  const {
    backgroundColor = "transparent",
    textColor       = "#A3A3A3",
    upColor         = "#FF3C3C",
    downColor       = "#3296FF",
  } = colors;

  useEffect(() => {
    if (!chartContainerRef.current) return;

    const chart = createChart(chartContainerRef.current, {
      autoSize: true,           // 컨테이너 크기에 자동 맞춤
      layout: {
        background: { type: ColorType.Solid, color: backgroundColor },
        textColor,
      },
      grid: {
        vertLines: { color: "rgba(255,255,255,0.05)" },
        horzLines: { color: "rgba(255,255,255,0.05)" },
      },
      timeScale: {
        timeVisible: true,
        secondsVisible: false,
        fixLeftEdge: true,
        fixRightEdge: rightPadBars === 0, // 빈 봉 패딩 있을 때는 오른쪽 고정 해제
      },
    });

    const candlestickSeries = chart.addSeries(CandlestickSeries, {
      upColor,
      downColor,
      borderVisible: false,
      wickUpColor:   upColor,
      wickDownColor: downColor,
    });

    const ma5Series   = chart.addSeries(LineSeries, { color: "#FACC15", lineWidth: 1, crosshairMarkerVisible: false });
    const ma20Series  = chart.addSeries(LineSeries, { color: "#EC4899", lineWidth: 1, crosshairMarkerVisible: false });
    const ma60Series  = chart.addSeries(LineSeries, { color: "#22C55E", lineWidth: 1, crosshairMarkerVisible: false });
    const ma120Series = chart.addSeries(LineSeries, { color: "#3B82F6", lineWidth: 1, crosshairMarkerVisible: false });

    const volumeSeries = chart.addSeries(HistogramSeries, {
      color: "rgba(255,255,255,0.3)",
      priceFormat: { type: "volume" },
      priceScaleId: "",
    });

    chart.priceScale("").applyOptions({
      scaleMargins: { top: 0.75, bottom: 0 },
    });

    chartRef.current  = chart;
    seriesRef.current = { candlestick: candlestickSeries, ma5: ma5Series, ma20: ma20Series, ma60: ma60Series, ma120: ma120Series, volume: volumeSeries };

    // ── 차트 너비/높이 꽉 차도록 Resize 핸들러 복원 ───────────────────────
    const handleResize = () => {
      if (chartContainerRef.current && chartRef.current) {
        chartRef.current.applyOptions({
          width: chartContainerRef.current.clientWidth,
          height: chartContainerRef.current.clientHeight || height,
        });
      }
    };

    window.addEventListener("resize", handleResize);
    // 최초 렌더링 후 컨테이너 크기 안착 시점 보정 (100ms 딜레이 실행)
    const timer = setTimeout(handleResize, 100);

    return () => {
      window.removeEventListener("resize", handleResize);
      clearTimeout(timer);
      chart.remove();
      chartRef.current  = null;
      seriesRef.current = null;
    };
  }, [backgroundColor, textColor, upColor, downColor, height]);

  useEffect(() => {
    if (!seriesRef.current || !data || data.length === 0) return;
    const { candlestick, ma5, ma20, ma60, ma120, volume } = seriesRef.current;

    candlestick.setData(data as any);

    const calcMA = (period: number) => {
      const result = [];
      for (let i = period - 1; i < data.length; i++) {
        let sum = 0;
        for (let j = 0; j < period; j++) sum += data[i - j].close;
        result.push({ time: data[i].time, value: sum / period });
      }
      return result;
    };

    ma5.setData(calcMA(5) as any);
    ma20.setData(calcMA(20) as any);
    ma60.setData(calcMA(60) as any);
    ma120.setData(calcMA(120) as any);

    volume.setData(data.map(d => ({
      time:  d.time,
      value: d.volume || 0,
      color: d.close >= d.open ? "rgba(255,60,60,0.5)" : "rgba(50,150,255,0.5)",
    })) as any);

    if (rightPadBars > 0) {
      chartRef.current?.timeScale().applyOptions({ rightOffset: rightPadBars });
    }
    chartRef.current?.timeScale().fitContent();

    // ── 미국 장 구간 배경 오버레이 ──────────────────────────────────────
    if (!showSessions || !chartRef.current || !chartContainerRef.current) return;

    const chart     = chartRef.current;
    const container = chartContainerRef.current;
    container.style.position = "relative";

    const canvas = document.createElement("canvas");
    canvas.style.cssText = "position:absolute;top:0;left:0;pointer-events:none;z-index:1;";
    container.appendChild(canvas);

    // 데이터 타임스탬프에서 고유 거래일 추출 (fake-UTC = EST 그대로 저장)
    const dates = new Map<string, [number, number, number]>();
    for (const item of data) {
      if (typeof item.time !== "number") continue;
      const dt = new Date(item.time * 1000);
      const y = dt.getUTCFullYear(), m = dt.getUTCMonth(), d = dt.getUTCDate();
      const key = `${y}-${m}-${d}`;
      if (!dates.has(key)) dates.set(key, [y, m, d]);
    }

    const draw = () => {
      if (!chartContainerRef.current) return;
      const w = chartContainerRef.current.clientWidth;
      const h = chartContainerRef.current.clientHeight;
      canvas.width  = w;
      canvas.height = h;
      const ctx = canvas.getContext("2d");
      if (!ctx) return;
      ctx.clearRect(0, 0, w, h);

      const visibleRange = chart.timeScale().getVisibleRange();
      if (!visibleRange) return;
      const { from, to } = visibleRange as { from: number; to: number };

      const drawBand = (tStart: number, tEnd: number, fill: string, labelFill: string, label: string) => {
        // 가시 범위와 겹치지 않으면 스킵
        if (tEnd <= from || tStart >= to) return;
        const rawX1 = chart.timeScale().timeToCoordinate(tStart as any);
        const rawX2 = chart.timeScale().timeToCoordinate(tEnd as any);
        // null이거나 화면 밖이면 가장자리로 클램프
        const x1 = rawX1 !== null ? Math.max(0, rawX1) : 0;
        const x2 = rawX2 !== null ? Math.min(w, rawX2) : w;
        if (x2 <= x1) return;
        ctx.fillStyle = fill;
        ctx.fillRect(x1, 0, x2 - x1, h);
        if (x2 - x1 > 30) {
          ctx.fillStyle = labelFill;
          ctx.font = "10px sans-serif";
          ctx.fillText(label, x1 + 4, 14);
        }
      };

      for (const [y, m, d] of dates.values()) {
        drawBand(
          Date.UTC(y, m, d,  4,  0, 0) / 1000,
          Date.UTC(y, m, d,  9, 30, 0) / 1000,
          "rgba(250, 200, 0, 0.07)", "rgba(250, 200, 0, 0.45)", "PRE"
        );
        drawBand(
          Date.UTC(y, m, d, 16,  0, 0) / 1000,
          Date.UTC(y, m, d, 20,  0, 0) / 1000,
          "rgba(150, 100, 255, 0.07)", "rgba(150, 100, 255, 0.45)", "AH"
        );
      }
    };

    draw();
    chart.timeScale().subscribeVisibleTimeRangeChange(draw);
    window.addEventListener("resize", draw);

    return () => {
      try { chart.timeScale().unsubscribeVisibleTimeRangeChange(draw); } catch {}
      window.removeEventListener("resize", draw);
      try { canvas.remove(); } catch {}
    };
  }, [data, rightPadBars, showSessions]);

  return <div ref={chartContainerRef} style={{ width: "100%", height: `${height}px` }} />;
}
