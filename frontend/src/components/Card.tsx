/** Surfaces & headers. Flat rounded cards; hierarchy from spacing + background,
 *  not shadows. */

export default function Card({
  title,
  sub,
  right,
  children,
  className = "",
  tone = "surface",
}: {
  title?: string;
  sub?: string;
  right?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
  tone?: "surface" | "card" | "dark";
}) {
  const toneClass =
    tone === "dark"
      ? "bg-bg-dark text-on-dark"
      : tone === "card"
        ? "bg-card border border-line"
        : "bg-surface";
  return (
    <section className={`rounded-card p-6 transition duration-180 ${toneClass} ${className}`}>
      {(title || right) && (
        <div className="mb-4 flex items-start justify-between gap-3">
          <div>
            {title && <h2 className="heading text-base font-semibold">{title}</h2>}
            {sub && <div className="mt-1 text-[13px] text-muted">{sub}</div>}
          </div>
          {right}
        </div>
      )}
      {children}
    </section>
  );
}

export function PageHeader({
  title,
  subtitle,
  children,
}: {
  title: string;
  subtitle?: string;
  children?: React.ReactNode;
}) {
  return (
    <div className="mb-8 flex flex-wrap items-end justify-between gap-4">
      <div>
        <h1 className="heading text-4xl font-bold leading-none">{title}</h1>
        {subtitle && <p className="mt-2 text-[15px] text-muted">{subtitle}</p>}
      </div>
      {children}
    </div>
  );
}

export function SectionHeader({ title, right }: { title: string; right?: React.ReactNode }) {
  return (
    <div className="mb-4 mt-2 flex items-center justify-between">
      <h2 className="eyebrow">{title}</h2>
      {right}
    </div>
  );
}
