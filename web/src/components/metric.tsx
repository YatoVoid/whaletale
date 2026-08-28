import Link from "next/link";
import { cn } from "@/lib/cn";

/**
 * A labelled figure. The value is required to carry its own unit; `period` is
 * the "· Sat 11am–4pm" tail (spec 13). Metric labels link to their 6.4
 * definition.
 */
export function Metric({
  label,
  value,
  period,
  definition,
  flag,
  className,
}: {
  label: string;
  value: string;
  period?: string;
  definition?: string;
  flag?: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("min-w-0", className)}>
      <div className="flex items-baseline gap-2">
        <span className="wt-num font-serif text-xl text-ink">{value}</span>
        {flag}
      </div>
      <div className="mt-0.5 text-xs text-ink-soft">
        {definition ? (
          <Link
            href={`/definitions#${definition}`}
            className="underline decoration-rule decoration-dotted underline-offset-2 hover:decoration-ink-soft"
          >
            {label}
          </Link>
        ) : (
          label
        )}
        {period ? <span className="text-ink-soft"> · {period}</span> : null}
      </div>
    </div>
  );
}
