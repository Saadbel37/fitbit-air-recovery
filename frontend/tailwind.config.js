/** Signals design tokens (see CONTEXT.md + styles.css).
 *  WHOOP-inspired clinical light theme — monochrome + single violet accent.
 *  Components use these names, never literal hex values. */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        bg: "var(--bg)",
        "bg-dark": "var(--bg-dark)",
        "surface-dark": "var(--surface-dark)",
        surface: "var(--surface)",
        card: "var(--card)",
        line: "var(--line)",
        ink: "var(--ink)",
        muted: "var(--muted)",
        faint: "var(--faint)",
        "on-dark": "var(--on-dark)",
        "on-dark-muted": "var(--on-dark-muted)",
        accent: "var(--accent)",
        "accent-soft": "var(--accent-soft)",
        "status-good": "var(--status-good)",
        "status-mid": "var(--status-mid)",
        "status-low": "var(--status-low)",
        // legacy aliases
        "bg-2": "var(--bg-2)",
        "surface-2": "var(--surface-2)",
        heart: "var(--heart)",
        move: "var(--move)",
        rest: "var(--rest)",
      },
      fontFamily: {
        disp: ["DM Sans", "system-ui", "sans-serif"],
        body: ["DM Sans", "system-ui", "sans-serif"],
        mono: ["IBM Plex Mono", "ui-monospace", "monospace"],
      },
      borderRadius: {
        card: "24px",
        button: "9999px",
      },
      spacing: { card: "24px", 18: "4.5rem" },
      maxWidth: { content: "1360px" },
      transitionDuration: { 180: "180ms" },
    },
  },
  plugins: [],
};
