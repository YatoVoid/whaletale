import { Triangle } from "lucide-react";
import { cn } from "@/lib/cn";

/** Vacancy is a state, not a blank (spec 13). A "not surveyed" hatch. */
export function VacantTag({ className }: { className?: string }) {
  return (
    <span
      className={cn("inline-flex items-center gap-1.5 text-xs text-ink-soft", className)}
    >
      <span className="wt-vacant wt-hairline inline-block h-3 w-4 border" aria-hidden />
      vacant
    </span>
  );
}

/** >2 SD from the trailing baseline (spec 6.5) — a surveyor's correction mark. */
export function AnomalyMark({ label = "anomalous" }: { label?: string }) {
  return (
    <span className="inline-flex items-center gap-1 text-xs font-medium text-flag">
      <Triangle aria-hidden size={11} strokeWidth={1.75} />
      {label}
    </span>
  );
}

/** A bucket that fell back to a secondary camera (spec 6.6). */
export function DegradedMark({ count }: { count: number }) {
  if (count <= 0) return null;
  return (
    <span
      className="text-xs text-degraded"
      title={`${count} bucket(s) fell back to a secondary camera`}
    >
      {count} degraded
    </span>
  );
}
