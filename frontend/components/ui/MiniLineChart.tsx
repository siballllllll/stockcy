"use client";

interface MiniLineChartProps {
  data:    number[];
  width?:  number;
  height?: number;
}

export function MiniLineChart({ data, width = 200, height = 52 }: MiniLineChartProps) {
  if (!data || data.length < 2) return null;

  const min   = Math.min(...data);
  const max   = Math.max(...data);
  const range = max - min || 1;
  const isUp  = data[data.length - 1] >= data[0];
  const color = isUp ? "var(--color-up)" : "var(--color-down)";
  const fill  = isUp ? "#00c85318" : "#ff174418";
  const pad   = 3;

  const pts = data.map((v, i): [number, number] => [
    (i / (data.length - 1)) * width,
    height - pad - ((v - min) / range) * (height - pad * 2),
  ]);

  const polyline = pts.map(([x, y]) => `${x},${y}`).join(" ");
  const area = [
    `M${pts[0][0]},${height}`,
    ...pts.map(([x, y]) => `L${x},${y}`),
    `L${pts[pts.length - 1][0]},${height}`,
    "Z",
  ].join(" ");

  return (
    <svg width={width} height={height} style={{ display: "block", overflow: "visible" }}>
      <path   d={area}     fill={fill} />
      <polyline points={polyline} fill="none" stroke={color} strokeWidth="1.5" strokeLinejoin="round" />
    </svg>
  );
}
