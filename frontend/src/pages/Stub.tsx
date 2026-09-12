/** Placeholder for pages built in phases 7/8 — honest, not broken. */

export default function Stub({ title }: { title: string }) {
  return (
    <div className="rounded-card border border-line bg-surface p-8">
      <h1 className="font-disp text-xl font-semibold">{title}</h1>
      <p className="mt-2 font-mono text-xs text-faint">
        This page is coming in a later build phase. Its data is already available in the API.
      </p>
    </div>
  );
}
