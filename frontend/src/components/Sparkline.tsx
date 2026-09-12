/** Thin ECharts sparkline: line or bar, one accent color, tooltip on hover. */

import * as echarts from "echarts/core";
import { BarChart, LineChart } from "echarts/charts";
import { GridComponent, TooltipComponent } from "echarts/components";
import { CanvasRenderer } from "echarts/renderers";
import { useEffect, useRef } from "react";

echarts.use([LineChart, BarChart, GridComponent, TooltipComponent, CanvasRenderer]);

interface Props {
  labels: string[];
  values: (number | null)[];
  color: string;
  type?: "line" | "bar";
  height?: number;
  unit?: string;
}

export default function Sparkline({ labels, values, color, type = "line", height = 44, unit = "" }: Props) {
  const ref = useRef<HTMLDivElement>(null);
  const chartRef = useRef<echarts.ECharts | null>(null);

  // init + dispose together (StrictMode-safe: a fresh instance per mount)
  useEffect(() => {
    if (!ref.current) return;
    const chart = echarts.init(ref.current);
    chartRef.current = chart;
    const obs = new ResizeObserver(() => chart.resize());
    obs.observe(ref.current);
    return () => {
      obs.disconnect();
      chart.dispose();
      chartRef.current = null;
    };
  }, []);

  useEffect(() => {
    const chart = chartRef.current;
    if (!chart || chart.isDisposed()) return;
    chart.setOption({
      grid: { left: 0, right: 0, top: 4, bottom: 0 },
      xAxis: { type: "category", data: labels, show: false },
      yAxis: { type: "value", show: false, scale: true },
      tooltip: {
        trigger: "axis",
        backgroundColor: "#ffffff",
        borderColor: "#e5e7eb",
        borderWidth: 1,
        textStyle: { color: "#000000", fontFamily: "IBM Plex Mono", fontSize: 11 },
        formatter: (p: unknown) => {
          const items = p as { axisValue: string; data: number | null }[];
          const it = items[0];
          if (!it || it.data == null) return "";
          const [, m, d] = it.axisValue.split("-");
          return `${d}.${m}. · ${it.data}${unit ? " " + unit : ""}`;
        },
      },
      series: [
        {
          type,
          data: values,
          showSymbol: false,
          connectNulls: true,
          smooth: 0.35,
          lineStyle: { color, width: 2 },
          itemStyle: { color, borderRadius: type === "bar" ? [2, 2, 0, 0] : 0 },
          areaStyle:
            type === "line"
              ? { color, opacity: 0.08 }
              : undefined,
          barCategoryGap: "25%",
        },
      ],
      animationDuration: 400,
    });
  }, [labels, values, color, type, unit]);

  return <div ref={ref} style={{ height, width: "100%" }} aria-hidden="true" />;
}
