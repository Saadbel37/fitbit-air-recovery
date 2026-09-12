/** AppShell: black TopNavigation, light content canvas, mobile bottom nav.
 *  Mode toggle, sync, and the auth-error reconnect banner (Auth ≠ Sync). */

import { useEffect, useState } from "react";
import { NavLink, Outlet } from "react-router-dom";
import { api } from "../lib/api";
import { useMode } from "../state/mode";
import PillButton from "./PillButton";

const AUTO_SYNC_MAX_AGE_MS = 30 * 60 * 1000; // re-sync real data if older than 30 min
// Module-scoped so StrictMode's double-mount (and remounts) can't double-fire it.
const autoSyncAttempted = new Set<string>();

const NAV = [
  { to: "/", label: "Overview", short: "Home" },
  { to: "/recovery", label: "Recovery", short: "Recovery" },
  { to: "/strain", label: "Strain", short: "Strain" },
  { to: "/sleep", label: "Sleep", short: "Sleep" },
  { to: "/health", label: "Health", short: "More" },
  { to: "/trends", label: "Trends" },
  { to: "/explorer", label: "Data Explorer" },
];

export default function Layout() {
  const { mode, status, refreshStatus } = useMode();
  const [syncing, setSyncing] = useState(false);

  const modeStatus = status?.modes[mode];
  const authError = modeStatus?.sync_status === "auth_error";

  const runSync = async () => {
    setSyncing(true);
    try {
      await api.sync(mode);
      await refreshStatus();
      window.dispatchEvent(new CustomEvent("signals:synced"));
    } catch {
      /* surfaced via status banner */
    } finally {
      setSyncing(false);
    }
  };

  // Auto-sync on start (real mode only, once per mode per session) when the
  // last sync is missing or older than 30 min. Non-blocking: the UI stays
  // usable and pages reload via the "signals:synced" event when it finishes.
  useEffect(() => {
    if (!status || mode !== "real" || syncing || autoSyncAttempted.has(mode)) return;
    autoSyncAttempted.add(mode);
    const last = status.modes[mode]?.last_sync;
    const stale = !last || Date.now() - new Date(last).getTime() > AUTO_SYNC_MAX_AGE_MS;
    if (stale) void runSync();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [status, mode]);

  return (
    <div className="flex min-h-screen flex-col bg-bg">
      {/* ---- top navigation (black bar) ---- */}
      <header className="sticky top-0 z-20 bg-bg-dark text-on-dark">
        <div className="mx-auto flex h-16 max-w-content items-center gap-6 px-5">
          <div className="flex items-center gap-2.5">
            <span className="relative flex h-2.5 w-2.5">
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-accent opacity-60" />
              <span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-accent" />
            </span>
            <span className="heading text-lg font-bold tracking-tight">Signals</span>
          </div>

          <nav className="hidden flex-1 items-center gap-1 md:flex" aria-label="Main navigation">
            {NAV.map((n) => (
              <NavLink
                key={n.to}
                to={n.to}
                end={n.to === "/"}
                className={({ isActive }) =>
                  `rounded-button px-3.5 py-1.5 font-disp text-[13px] font-medium transition duration-180 ${
                    isActive ? "bg-white/12 text-on-dark" : "text-on-dark-muted hover:text-on-dark"
                  }`
                }
              >
                {n.label}
              </NavLink>
            ))}
          </nav>

          <div className="ml-auto flex items-center gap-2 md:ml-0">
            <PillButton variant="primary" onClick={runSync} disabled={syncing}>
              {syncing ? "Sync…" : "Sync"}
            </PillButton>
          </div>
        </div>

        {/* context strip */}
        <div className="mx-auto flex max-w-content items-center gap-3 px-5 pb-2 font-mono text-[10px] text-on-dark-muted">
          {modeStatus?.last_sync && (
            <span>
              Last sync:{" "}
              {new Date(modeStatus.last_sync).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
            </span>
          )}
        </div>
      </header>

      {/* ---- failure banners (Auth ≠ Sync) ---- */}
      {authError && (
        <div className="bg-status-low/10 px-5 py-2.5 text-center text-sm text-ink">
          Connection to Google Health expired — please reconnect (terminal:{" "}
          <code className="font-mono text-xs">python authorize.py</code>).
        </div>
      )}
      {modeStatus?.sync_status === "sync_error" && !authError && (
        <div className="bg-status-mid/10 px-5 py-2 text-center font-mono text-xs text-muted">
          Last sync failed (temporary) — showing the last successful data.
        </div>
      )}

      {/* ---- content canvas ---- */}
      <main className="mx-auto w-full max-w-content flex-1 px-5 py-8 pb-24 md:pb-8">
        <Outlet />
      </main>

      {/* ---- mobile bottom nav ---- */}
      <nav
        className="fixed inset-x-0 bottom-0 z-20 flex border-t border-line bg-bg-dark md:hidden"
        aria-label="Mobile Navigation"
      >
        {NAV.filter((n) => n.short).map((n) => (
          <NavLink
            key={n.to}
            to={n.to}
            end={n.to === "/"}
            className={({ isActive }) =>
              `flex-1 py-3 text-center font-disp text-[11px] font-medium ${
                isActive ? "text-on-dark" : "text-on-dark-muted"
              }`
            }
          >
            {n.short}
          </NavLink>
        ))}
      </nav>
    </div>
  );
}
