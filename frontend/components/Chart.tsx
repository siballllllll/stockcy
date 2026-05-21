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
  colors?: {
    backgroundColor?: string;
    textColor?: string;
    upColor?: string;
    downColor?: string;
  };
}

export default function Chart({ data, colors = {} }: ChartProps) {
  const chartContainerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);

  const {
    backgroundColor = "transparent",
    textColor = "#A3A3A3",
    upColor = "#FF3C3C",
    downColor = "#3296FF",
  } = colors;

  const seriesRef = useRef<any>(null);

  useEffect(() => {
    if (!chartContainerRef.current) return;

    const chart = createChart(chartContainerRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: backgroundColor },
        textColor,
      },
      grid: {
        vertLines: { color: "rgba(255, 255, 255, 0.05)" },
        horzLines: { color: "rgba(255, 255, 255, 0.05)" },
      },
      width: chartContainerRef.current.clientWidth,
      height: chartContainerRef.current.clientHeight,
      timeScale: {
        timeVisible: true,
        secondsVisible: false,
      },
    });

    const candlestickSeries = chart.addSeries(CandlestickSeries, {
      upColor,
      downColor,
      borderVisible: false,
      wickUpColor: upColor,
      wickDownColor: downColor,
    });

    // 이동평균선(MA) 시리즈 생성
    const ma5Series = chart.addSeries(LineSeries, { color: "#FACC15", lineWidth: 1, crosshairMarkerVisible: false });
    const ma20Series = chart.addSeries(LineSeries, { color: "#EC4899", lineWidth: 1, crosshairMarkerVisible: false });
    const ma60Series = chart.addSeries(LineSeries, { color: "#22C55E", lineWidth: 1, crosshairMarkerVisible: false });
    const ma120Series = chart.addSeries(LineSeries, { color: "#3B82F6", lineWidth: 1, crosshairMarkerVisible: false });

    // 거래량(Volume) 바 시리즈 생성 (별도의 priceScale 영역 사용)
    const volumeSeries = chart.addSeries(HistogramSeries, {
      color: "rgba(255, 255, 255, 0.3)", // 디폴트
      priceFormat: { type: "volume" },
      priceScaleId: "", // 빈 문자열 지정 시 메인 스케일과 분리된 독립 스케일이 생성됨
    });

    // 차트 하단 25% 정도의 높이만 거래량이 차지하도록 설정
    chart.priceScale("").applyOptions({
      scaleMargins: {
        top: 0.75, // 위쪽 75%는 빈 공간
        bottom: 0,
      },
    });

    chartRef.current = chart;
    seriesRef.current = {
      candlestick: candlestickSeries,
      ma5: ma5Series,
      ma20: ma20Series,
      ma60: ma60Series,
      ma120: ma120Series,
      volume: volumeSeries,
    };

    const handleResize = () => {
      chart.applyOptions({ width: chartContainerRef.current?.clientWidth });
    };

    window.addEventListener("resize", handleResize);

    return () => {
      window.removeEventListener("resize", handleResize);
      chart.remove();
      chartRef.current = null;
      seriesRef.current = null;
    };
  }, [backgroundColor, textColor, upColor, downColor]);

  useEffect(() => {
    if (seriesRef.current && data && data.length > 0) {
      const { candlestick, ma5, ma20, ma60, ma120, volume } = seriesRef.current;
      
      // 캔들 데이터 세팅
      candlestick.setData(data as any);

      // MA 계산 헬퍼 함수
      const calculateMA = (period: number) => {
        const maData = [];
        for (let i = 0; i < data.length; i++) {
          if (i < period - 1) continue;
          let sum = 0;
          for (let j = 0; j < period; j++) {
            sum += data[i - j].close;
          }
          maData.push({ time: data[i].time, value: sum / period });
        }
        return maData;
      };

      // MA 데이터 세팅
      ma5.setData(calculateMA(5) as any);
      ma20.setData(calculateMA(20) as any);
      ma60.setData(calculateMA(60) as any);
      ma120.setData(calculateMA(120) as any);

      // 거래량 데이터 세팅
      const volumeData = data.map(d => ({
        time: d.time,
        value: d.volume || 0,
        color: d.close > d.open ? "rgba(255, 60, 60, 0.5)" : "rgba(50, 150, 255, 0.5)" // 상승은 빨강, 하락은 파랑 반투명
      }));
      volume.setData(volumeData as any);

      chartRef.current?.timeScale().fitContent();
    }
  }, [data]);

  return <div ref={chartContainerRef} style={{ width: "100%", height: "100%" }} />;
}
