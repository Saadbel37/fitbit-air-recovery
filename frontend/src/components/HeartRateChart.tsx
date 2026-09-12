/** Intraday heart-rate line colored by Fitbit zones (visualMap piecewise).
 *  Zones are display-only (ADR 0001). x = minute of day; gaps stay broken. */

import * as echarts from "echarts/core";
import { LineChart } from "echarts/charts";
import { GridComponent, TooltipComponent, VisualMapComponent } from "echarts/components";
import { CanvasRenderer } from "echarts/renderers";
import { useEffect, useRef } from "react";

echarts.use([LineChart, GridComponent, TooltipComponent, VisualMapComponent, CanvasRenderer]);

// Restrained clinical ramp (grey → violet → deep red) instead of a rainbow.
export const ZONE_COLOR: Record<string, string> = {
  LIGHT: "#c2c6cd",
  MODERATE: "#8b93ff",
  VIGOROUS: "#4a53ff",
  PEAK: "#d1495b",
};

interface Zone {
  name: string;
  min_bpm: number;
  max_bpm: number;
}

export default function HeartRateChart({
  minutes,
  zones,
  height = 300,
}: {
  minutes: { minute: number; bpm: number }[];
  zones: Zone[];
  height?: number;
}) {
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

    // dense 1440-slot series with nulls in gaps (keeps x scaled to the full day)
    const data: (number | null)[] = Array(1440).fill(null);
    for (const m of minutes) data[m.minute] = Math.round(m.bpm);
    const labels = Array.from({ length: 1440 }, (_, i) => i);

    const ordered = [...zones].sort((a, b) => a.min_bpm - b.min_bpm);
    const pieces = ordered.map((z) => ({
      gte: z.min_bpm,
      lte: z.max_bpm,
      color: ZONE_COLOR[z.name] ?? "#9384e8",
    }));

    chart.setOption(
      {
        grid: { left: 40, right: 12, top: 12, bottom: 26 },
        tooltip: {
          trigger: "axis",
          backgroundColor: "#ffffff",
          borderColor: "#e5e7eb",
          borderWidth: 1,
          textStyle: { color: "#000000", fontFamily: "IBM Plex Mono", fontSize: 11 },
          formatter: (p: unknown) => {
            const items = p as { axisValue: number; data: number | null }[];
            const it = items[0];
            if (!it || it.data == null) return "";
            const h = Math.floor(it.axisValue / 60);
            const m = it.axisValue % 60;
            return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")} · ${it.data} bpm`;
          },
        },
        visualMap: {
          show: false,
          dimension: 1,
          pieces,
          outOfRange: { color: "#191919" },
        },
        xAxis: {
          type: "category",
          data: labels,
          boundaryGap: false,
          axisLine: { lineStyle: { color: "#e5e7eb" } },
          axisTick: { show: false },
          axisLabel: {
            color: "#999999",
            fontFamily: "IBM Plex Mono",
            fontSize: 10,
            interval: 179, // every 3 h
            formatter: (v: string) => `${String(Math.floor(Number(v) / 60)).padStart(2, "0")}:00`,
          },
        },
        yAxis: {
          type: "value",
          scale: true,
          splitLine: { lineStyle: { color: "#eef0f3" } },
          axisLabel: { color: "#999999", fontFamily: "IBM Plex Mono", fontSize: 10 },
        },
        series: [
          {
            type: "line",
            data,
            showSymbol: false,
            connectNulls: false,
            smooth: 0.2,
            lineStyle: { width: 1.6 },
            sampling: "lttb",
          },
        ],
        animationDuration: 400,
      },
      true,
    );
  }, [minutes, zones]);

  return <div ref={ref} style={{ height, width: "100%" }} />;
}
