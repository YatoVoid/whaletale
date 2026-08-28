"use client";

import { useMemo, useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { ChevronLeft, ChevronRight, X } from "lucide-react";
import { cn } from "@/lib/cn";
import { dayLabel } from "@/lib/format";
import type { Occupant, ScheduleGrid } from "@/lib/types";
import { assignTenancy, type AssignResult } from "./actions";

type Kind = "permanent" | "recurring" | "one_off";
const WEEKDAYS = [
  ["MO", "Mon"],
  ["TU", "Tue"],
  ["WE", "Wed"],
  ["TH", "Thu"],
  ["FR", "Fri"],
  ["SA", "Sat"],
  ["SU", "Sun"],
] as const;

const key = (s: string, d: string) => `${s}|${d}`;

export function ScheduleBoard({
  grid,
  occupants,
  from,
  prev,
  next,
}: {
  grid: ScheduleGrid;
  occupants: Occupant[];
  from: string;
  prev: string;
  next: string;
}) {
  const router = useRouter();
  const [sel, setSel] = useState<Set<string>>(new Set());
  const [anchor, setAnchor] = useState<{ si: number; di: number } | null>(null);

  const occByCell = useMemo(() => {
    const m = new Map<string, string | null>();
    for (const c of grid.cells) m.set(key(c.space_id, c.day), c.occupant_name);
    return m;
  }, [grid.cells]);

  function toggle(si: number, di: number, e: React.MouseEvent) {
    const spaceId = grid.space_ids[si]!;
    const day = grid.days[di]!;
    const k = key(spaceId, day);
    setSel((cur) => {
      const nextSel = new Set(cur);
      if (e.shiftKey && anchor) {
        const [s0, s1] = [Math.min(anchor.si, si), Math.max(anchor.si, si)];
        const [d0, d1] = [Math.min(anchor.di, di), Math.max(anchor.di, di)];
        for (let s = s0; s <= s1; s++)
          for (let d = d0; d <= d1; d++)
            nextSel.add(key(grid.space_ids[s]!, grid.days[d]!));
      } else if (e.metaKey || e.ctrlKey) {
        if (nextSel.has(k)) nextSel.delete(k);
        else nextSel.add(k);
        setAnchor({ si, di });
      } else {
        nextSel.clear();
        nextSel.add(k);
        setAnchor({ si, di });
      }
      return nextSel;
    });
  }

  const selectedSpaceIds = useMemo(
    () => [...new Set([...sel].map((k) => k.split("|")[0]!))],
    [sel],
  );

  return (
    <div className="wt-settle">
      <div className="flex items-end justify-between">
        <div>
          <h1 className="font-serif text-2xl text-ink">Schedule</h1>
          <p className="mt-1 text-sm text-ink-soft">
            {dayLabel(grid.days[0]!)} – {dayLabel(grid.days[grid.days.length - 1]!)}.
            Click a cell, shift-click to select a block, then assign an occupant.
          </p>
        </div>
        <div className="flex items-center gap-1 text-sm text-ink-soft">
          <button
            aria-label="Previous fortnight"
            onClick={() => router.push(`/schedule?from=${prev}`)}
            className="wt-hairline border p-1 hover:text-ink"
          >
            <ChevronLeft size={16} strokeWidth={1.5} />
          </button>
          <button
            aria-label="Next fortnight"
            onClick={() => router.push(`/schedule?from=${next}`)}
            className="wt-hairline border p-1 hover:text-ink"
          >
            <ChevronRight size={16} strokeWidth={1.5} />
          </button>
        </div>
      </div>

      <div className="mt-5 flex gap-6">
        <div className="min-w-0 flex-1 overflow-x-auto">
          <div
            className="grid text-xs"
            style={{
              gridTemplateColumns: `10rem repeat(${grid.days.length}, minmax(2.4rem, 1fr))`,
            }}
          >
            <div className="wt-hairline sticky left-0 z-10 border-b border-r bg-paper" />
            {grid.days.map((d) => (
              <div
                key={d}
                className="wt-hairline border-b border-l px-1 py-1.5 text-center text-ink-soft"
              >
                <div>{dayLabel(d).split(" ")[0]}</div>
                <div className="wt-num text-ink">{d.slice(8)}</div>
              </div>
            ))}

            {grid.space_ids.map((spaceId, si) => (
              <FragmentRow
                key={spaceId}
                name={grid.space_names[spaceId] ?? spaceId}
                days={grid.days}
                render={(day, di) => {
                  const occ = occByCell.get(key(spaceId, day)) ?? null;
                  const selected = sel.has(key(spaceId, day));
                  return (
                    <button
                      key={day}
                      onClick={(e) => toggle(si, di, e)}
                      aria-pressed={selected}
                      title={occ ?? "vacant"}
                      className={cn(
                        "wt-hairline h-9 border-b border-l text-[11px] leading-none",
                        occ ? "bg-[color-mix(in_srgb,var(--color-field)_14%,transparent)] text-ink" : "wt-vacant",
                        selected && "outline outline-2 -outline-offset-2 outline-ink",
                      )}
                    >
                      <span className="line-clamp-1 px-1">{occ ? initials(occ) : ""}</span>
                    </button>
                  );
                }}
              />
            ))}
          </div>
        </div>

        {sel.size > 0 && (
          <AssignPanel
            count={sel.size}
            spaceCount={selectedSpaceIds.length}
            occupants={occupants}
            defaultStart={from}
            onClose={() => setSel(new Set())}
            onDone={() => {
              setSel(new Set());
              router.refresh();
            }}
            spaceIds={selectedSpaceIds}
          />
        )}
      </div>
    </div>
  );
}

function FragmentRow({
  name,
  days,
  render,
}: {
  name: string;
  days: string[];
  render: (day: string, di: number) => React.ReactNode;
}) {
  return (
    <>
      <div className="wt-hairline sticky left-0 z-10 flex items-center border-b border-r bg-paper px-2 py-1 text-ink">
        <span className="line-clamp-1">{name}</span>
      </div>
      {days.map((d, di) => render(d, di))}
    </>
  );
}

function AssignPanel({
  count,
  spaceCount,
  spaceIds,
  occupants,
  defaultStart,
  onClose,
  onDone,
}: {
  count: number;
  spaceCount: number;
  spaceIds: string[];
  occupants: Occupant[];
  defaultStart: string;
  onClose: () => void;
  onDone: () => void;
}) {
  const [kind, setKind] = useState<Kind>("permanent");
  const [occupantId, setOccupantId] = useState(occupants[0]?.id ?? "");
  const [startsOn, setStartsOn] = useState(defaultStart);
  const [endsOn, setEndsOn] = useState("");
  const [weekdays, setWeekdays] = useState<string[]>(["SA"]);
  const [dailyStart, setDailyStart] = useState("08:00");
  const [dailyEnd, setDailyEnd] = useState("14:00");
  const [result, setResult] = useState<AssignResult | null>(null);
  const [pending, startTransition] = useTransition();

  function save() {
    setResult(null);
    startTransition(async () => {
      const r = await assignTenancy({
        spaceIds,
        occupantId,
        kind,
        startsOn,
        endsOn: endsOn || null,
        weekdays,
        dailyStart,
        dailyEnd,
      });
      setResult(r);
      if (r.ok) setTimeout(onDone, 600);
    });
  }

  return (
    <aside
      className="wt-hairline sticky top-4 h-fit w-72 shrink-0 border bg-paper-raised p-4"
      style={{ boxShadow: "var(--shadow-panel)" }}
    >
      <div className="flex items-start justify-between">
        <div>
          <div className="font-serif text-base text-ink">Assign occupant</div>
          <div className="mt-0.5 text-xs text-ink-soft">
            {count} cell{count === 1 ? "" : "s"} · {spaceCount} space
            {spaceCount === 1 ? "" : "s"}
          </div>
        </div>
        <button aria-label="Clear selection" onClick={onClose} className="text-ink-soft hover:text-ink">
          <X size={16} strokeWidth={1.5} />
        </button>
      </div>

      <label className="mt-4 flex flex-col gap-1 text-xs">
        <span className="text-ink-soft">Occupant</span>
        <select
          value={occupantId}
          onChange={(e) => setOccupantId(e.target.value)}
          className="wt-hairline border-b bg-transparent py-1.5 text-sm outline-none focus-visible:border-ink"
        >
          {occupants.map((o) => (
            <option key={o.id} value={o.id}>
              {o.name}
            </option>
          ))}
        </select>
      </label>

      <fieldset className="mt-4 text-xs">
        <legend className="text-ink-soft">Kind</legend>
        <div className="mt-1 flex gap-3">
          {(
            [
              ["permanent", "Permanent"],
              ["recurring", "Weekly"],
              ["one_off", "One-off"],
            ] as const
          ).map(([v, l]) => (
            <label key={v} className="flex items-center gap-1.5">
              <input
                type="radio"
                name="kind"
                checked={kind === v}
                onChange={() => setKind(v)}
                className="accent-[var(--color-field)]"
              />
              {l}
            </label>
          ))}
        </div>
      </fieldset>

      <label className="mt-4 flex flex-col gap-1 text-xs">
        <span className="text-ink-soft">
          {kind === "one_off" ? "Date" : "Starts"}
        </span>
        <input
          type="date"
          value={startsOn}
          onChange={(e) => setStartsOn(e.target.value)}
          className="wt-hairline border-b bg-transparent py-1.5 text-sm outline-none focus-visible:border-ink"
        />
      </label>

      {kind === "permanent" && (
        <label className="mt-3 flex flex-col gap-1 text-xs">
          <span className="text-ink-soft">Ends (optional)</span>
          <input
            type="date"
            value={endsOn}
            onChange={(e) => setEndsOn(e.target.value)}
            className="wt-hairline border-b bg-transparent py-1.5 text-sm outline-none focus-visible:border-ink"
          />
        </label>
      )}

      {kind === "recurring" && (
        <div className="mt-3 flex flex-col gap-2 text-xs">
          <span className="text-ink-soft">On</span>
          <div className="flex flex-wrap gap-1">
            {WEEKDAYS.map(([v, l]) => {
              const on = weekdays.includes(v);
              return (
                <button
                  key={v}
                  type="button"
                  aria-pressed={on}
                  onClick={() =>
                    setWeekdays((w) =>
                      on ? w.filter((x) => x !== v) : [...w, v],
                    )
                  }
                  className={cn(
                    "wt-hairline border px-1.5 py-0.5",
                    on ? "bg-[color-mix(in_srgb,var(--color-field)_16%,transparent)] text-ink" : "text-ink-soft",
                  )}
                >
                  {l}
                </button>
              );
            })}
          </div>
          <div className="mt-1 flex items-center gap-2">
            <input
              type="time"
              value={dailyStart}
              onChange={(e) => setDailyStart(e.target.value)}
              className="wt-hairline border-b bg-transparent py-1 outline-none focus-visible:border-ink"
            />
            <span className="text-ink-soft">to</span>
            <input
              type="time"
              value={dailyEnd}
              onChange={(e) => setDailyEnd(e.target.value)}
              className="wt-hairline border-b bg-transparent py-1 outline-none focus-visible:border-ink"
            />
          </div>
        </div>
      )}

      {result && !result.ok && (
        <p role="alert" className="mt-4 text-xs text-flag">
          {result.error}
        </p>
      )}
      {result?.ok && (
        <p className="mt-4 text-xs text-field">Assigned {result.assigned}.</p>
      )}

      <button
        onClick={save}
        disabled={pending || !occupantId}
        className="wt-hairline mt-5 w-full border py-1.5 text-sm text-ink hover:bg-[color-mix(in_srgb,var(--color-field)_8%,transparent)] disabled:opacity-50"
      >
        {pending ? "Saving…" : "Assign"}
      </button>
    </aside>
  );
}

function initials(name: string): string {
  return name
    .split(/\s+/)
    .slice(0, 2)
    .map((w) => w[0]?.toUpperCase() ?? "")
    .join("");
}
