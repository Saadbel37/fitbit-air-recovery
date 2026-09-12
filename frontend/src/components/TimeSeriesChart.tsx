/** Reusable interactive ECharts time-series: hover crosshair, zoom, legend,
 *  responsive. Used by history and trends views. */

import * as echarts from "echarts/core";
import { BarChart, LineChart } from "echarts/charts";
import {
  DataZoomComponent,
  GridComponent,
  LegendComponent,
  MarkLineComponent,
  TooltipComponent,
} from "echarts/components";
import { CanvasRenderer } from "echarts/renderers";
import { useEffect, useRef } from "react";

echarts.use([
  LineChart,
  BarChart,
  GridComponent,
  TooltipComponent,
  LegendComponent,
  DataZoomComponent,
  MarkLineComponent,
  CanvasRenderer,
]);

export interface Series {
  name: string;
  data: (number | null)[];
  color: string;
  type?: "line" | "bar";
  yAxisIndex?: number;
  areaOpacity?: number;
  unit?: string;
}

interface Props {
  labels: string[];
  series: Series[];
  height?: number;
  zoom?: boolean;
  yAxes?: { min?: number | "dataMin"; max?: number | "dataMax" }[];
  dateLabels?: boolean;
  formatLabel?: (v: string) => string;
}

export default function TimeSeriesChart({
  labels,
  series,
  height = 300,
  zoom = false,
  yAxes,
  dateLabels = true,
  formatLabel,
}: Props) {
  const ref = useRef<HTMLDivElement>(null);
  const chartRef = useRef<echarts.ECharts | null>(null);

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
    const fmt =
      formatLabel ??
      ((v: string) => {
        const parts = v.split("-");
        return parts.length === 3 ? `${parts[2]}.${parts[1]}.` : v;
      });
    chart.setOption(
      {
        grid: { left: 44, right: 16, top: series.length > 1 ? 34 : 12, bottom: zoom ? 46 : 26 },
        legend:
          series.length > 1
            ? {
                data: series.map((s) => s.name),
                textStyle: { color: "#808080", fontFamily: "IBM Plex Mono", fontSize: 11 },
                icon: "roundRect",
                top: 0,
              }
            : undefined,
        tooltip: {
          trigger: "axis",
          backgroundColor: "#ffffff",
          borderColor: "#e5e7eb",
          borderWidth: 1,
          textStyle: { color: "#000000", fontFamily: "IBM Plex Mono", fontSize: 11 },
          axisPointer: { type: "line", lineStyle: { color: "#4a53ff", width: 1, type: "dashed" } },
          valueFormatter: undefined,
        },
        xAxis: {
          type: "category",
          data: labels,
          boundaryGap: series.some((s) => s.type === "bar"),
          axisLine: { lineStyle: { color: "#e5e7eb" } },
          axisTick: { show: false },
          axisLabel: {
            color: "#999999",
            fontFamily: "IBM Plex Mono",
            fontSize: 10,
            formatter: dateLabels ? fmt : undefined,
            hideOverlap: true,
          },
        },
        yAxis: (yAxes ?? [{}]).map((y) => ({
          type: "value",
          scale: true,
          min: y.min,
          max: y.max,
          splitLine: { lineStyle: { color: "#eef0f3" } },
          axisLabel: { color: "#999999", fontFamily: "IBM Plex Mono", fontSize: 10 },
        })),
        dataZoom: zoom
          ? [
              { type: "inside", throttle: 50 },
              {
                type: "slider",
                height: 18,
                bottom: 8,
                borderColor: "#e5e7eb",
                fillerColor: "rgba(74,83,255,0.10)",
                handleStyle: { color: "#4a53ff" },
                textStyle: { color: "#999999", fontFamily: "IBM Plex Mono", fontSize: 9 },
              },
            ]
          : undefined,
        series: series.map((s) => ({
          name: s.name,
          type: s.type ?? "line",
          data: s.data,
          yAxisIndex: s.yAxisIndex ?? 0,
          showSymbol: false,
          connectNulls: true,
          smooth: 0.3,
          lineStyle: { color: s.color, width: 2 },
          itemStyle: { color: s.color, borderRadius: s.type === "bar" ? [3, 3, 0, 0] : 0 },
          areaStyle: s.areaOpacity ? { color: s.color, opacity: s.areaOpacity } : undefined,
        })),
        animationDuration: 500,
      },
      true,
    );
  }, [labels, series, zoom, yAxes, dateLabels, formatLabel]);

  return <div ref={ref} style={{ height, width: "100%" }} />;
}
