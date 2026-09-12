/** Small data-fetching hook: reload on mode change and on sync events. */

import { useEffect, useState } from "react";
import { useMode } from "../state/mode";

export function useApiData<T>(fetcher: (mode: "real" | "demo") => Promise<T>, deps: unknown[] = []) {
  const { mode } = useMode();
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let alive = true;
    const load = async () => {
      setLoading(true);
      setError(null);
      try {
        const d = await fetcher(mode);
        if (alive) setData(d);
      } catch (e) {
        if (alive) setError(String(e));
      } finally {
        if (alive) setLoading(false);
      }
    };
    void load();
    const onSync = () => void load();
    window.addEventListener("signals:synced", onSync);
    return () => {
      alive = false;
      window.removeEventListener("signals:synced", onSync);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mode, ...deps]);

  return { data, error, loading };
}

/** The latest day that has scores in the active mode (fallback: yesterday). */
export function useLatestDay(): string {
  const { status, mode } = useMode();
  const last = status?.modes[mode]?.last_day;
  if (last) return last;
  const d = new Date();
  d.setDate(d.getDate() - 1);
  return d.toISOString().slice(0, 10);
}
