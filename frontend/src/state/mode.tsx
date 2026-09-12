/** App-wide data mode. Fixed to real data — the Demo toggle was removed. The
 *  `mode` field is kept so data hooks/pages need no changes. */

import { createContext, useContext, useEffect, useState } from "react";
import type { Mode, StatusResponse } from "../lib/api";
import { api } from "../lib/api";

interface ModeState {
  mode: Mode;
  status: StatusResponse | null;
  refreshStatus: () => Promise<void>;
}

const ModeContext = createContext<ModeState | null>(null);

export function ModeProvider({ children }: { children: React.ReactNode }) {
  const mode: Mode = "real";
  const [status, setStatus] = useState<StatusResponse | null>(null);

  const refreshStatus = async () => {
    try {
      setStatus(await api.status());
    } catch {
      setStatus(null);
    }
  };

  useEffect(() => {
    void refreshStatus();
  }, []);

  return (
    <ModeContext.Provider value={{ mode, status, refreshStatus }}>
      {children}
    </ModeContext.Provider>
  );
}

export function useMode(): ModeState {
  const ctx = useContext(ModeContext);
  if (!ctx) throw new Error("useMode outside ModeProvider");
  return ctx;
}
