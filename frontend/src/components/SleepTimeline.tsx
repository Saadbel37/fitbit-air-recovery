/** Hypnogram: sleep stages laid out over the night in four lanes.
 *  Hover a segment for its stage + duration. */

import { useState } from "react";
import type { SleepStage } from "../lib/api";

const STAGE = {
  AWAKE: { lane: 0, label: "Awake", color: "#d1495b" },
  REM: { lane: 1, label: "REM", color: "#8b93ff" },
  LIGHT: { lane: 2, label: "Light", color: "#c7cbff" },
  DEEP: { lane: 3, label: "Deep", color: "#4a53ff" },
} as const;

type StageKey = keyof typeof STAGE;

function hhmm(iso: string, offsetS: number): string {
  const d = new Date(new Date(iso).getTime() + offsetS * 1000);
  return `${String(d.getUTCHours()).padStart(2, "0")}:${String(d.getUTCMinutes()).padStart(2, "0")}`;
}

export default function SleepTimeline({
  stages,
  offsetS,
  height = 150,
}: {
  stages: SleepStage[];
  offsetS: number;
  height?: number;
}) {
  const [hover, setHover] = useState<{ text: string; x: number } | null>(null);
  if (stages.length === 0) return null;

  const t0 = new Date(stages[0].start).getTime();
  const t1 = new Date(stages[stages.length - 1].end).getTime();
  const span = Math.max(1, t1 - t0);
  const laneH = (height - 24) / 4;

  return (
    <div>
      <div className="relative" style={{ height }}>
        {/* lane labels */}
        {(Object.keys(STAGE) as StageKey[]).map((k) => (
          <div
            key={k}
            className="absolute left-0 font-mono text-[10px] text-faint"
            style={{ top: STAGE[k].lane * laneH + 2 }}
          >
            {STAGE[k].label}
          </div>
        ))}
        {/* segments */}
        <div className="absolute inset-0" style={{ left: 44 }}>
          {stages.map((s, i) => {
            const meta = STAGE[s.stage as StageKey];
            if (!meta) return null;
            const left = ((new Date(s.start).getTime() - t0) / span) * 100;
            const width = ((new Date(s.end).getTime() - new Date(s.start).getTime()) / span) * 100;
            const mins = Math.round((new Date(s.end).getTime() - new Date(s.start).getTime()) / 60000);
            return (
              <div
                key={i}
                className="absolute rounded-sm"
                style={{
                  left: `${left}%`,
                  width: `calc(${width}% + 1px)`,
                  top: meta.lane * laneH + 14,
                  height: laneH - 5,
                  background: meta.color,
                  opacity: 0.9,
                }}
                onMouseEnter={(e) =>
                  setHover({
                    text: `${meta.label} · ${mins} min · ${hhmm(s.start, offsetS)}–${hhmm(s.end, offsetS)}`,
                    x: e.nativeEvent.offsetX + left,
                  })
                }
                onMouseLeave={() => setHover(null)}
              />
            );
          })}
        </div>
      </div>
      <div className="mt-1 flex justify-between px-11 font-mono text-[10px] text-faint">
        <span>{hhmm(stages[0].start, offsetS)}</span>
        {hover && <span className="text-muted">{hover.text}</span>}
        <span>{hhmm(stages[stages.length - 1].end, offsetS)}</span>
      </div>
    </div>
  );
}
