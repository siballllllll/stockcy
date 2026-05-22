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
}

export default function Chart({ data, height = 450, colors = {} }: ChartProps) {
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

    return () => {
      chart.remove();
      chartRef.current  = null;
      seriesRef.current = null;
    };
  }, [backgroundColor, textColor, upColor, downColor]);

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

    chartRef.current?.timeScale().fitContent();
  }, [data]);

  return <div ref={chartContainerRef} style={{ width: "100%", height: `${height}px` }} />;
}
