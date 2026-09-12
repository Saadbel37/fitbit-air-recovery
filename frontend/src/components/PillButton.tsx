/** Pill-shaped action button (radius 9999px). Three variants per the brief. */

import type { ButtonHTMLAttributes } from "react";

type Variant = "primary" | "dark" | "secondary";

const VARIANT: Record<Variant, string> = {
  primary: "bg-accent text-white hover:brightness-110",
  dark: "bg-bg-dark text-on-dark hover:brightness-125",
  secondary: "bg-transparent text-ink border border-line hover:bg-surface",
};

export default function PillButton({
  variant = "secondary",
  className = "",
  ...props
}: { variant?: Variant } & ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      {...props}
      className={`inline-flex items-center justify-center gap-2 rounded-button px-5 py-2 font-disp text-sm font-medium transition duration-180 disabled:opacity-40 disabled:pointer-events-none ${VARIANT[variant]} ${className}`}
    />
  );
}
