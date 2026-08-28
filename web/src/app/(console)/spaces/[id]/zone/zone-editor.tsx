"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { Redo2, Undo2 } from "lucide-react";
import { cn } from "@/lib/cn";
import { saveZone, type SaveZoneResult } from "./actions";

type Pt = [number, number];
const SNAP = 0.02; // normalized distance that snaps to an existing vertex

export function ZoneEditor({
  spaceId,
  spaceName,
  initial,
  createdBy,
}: {
  spaceId: string;
  spaceName: string;
  initial: Pt[];
  createdBy: string;
}) {
  const router = useRouter();
  const svgRef = useRef<SVGSVGElement>(null);
  const [past, setPast] = useState<Pt[][]>([]);
  const [future, setFuture] = useState<Pt[][]>([]);
  const [pts, setPts] = useState<Pt[]>(initial.length >= 3 ? initial : DEFAULT);
  const [dragging, setDragging] = useState<number | null>(null);
  const [result, setResult] = useState<SaveZoneResult | null>(null);
  const [saving, setSaving] = useState(false);

  const commit = useCallback(
    (next: Pt[]) => {
      setPast((p) => [...p, pts]);
      setFuture([]);
      setPts(next);
    },
    [pts],
  );

  function toNorm(e: { clientX: number; clientY: number }): Pt {
    const r = svgRef.current!.getBoundingClientRect();
    return [
      clamp((e.clientX - r.left) / r.width),
      clamp((e.clientY - r.top) / r.height),
    ];
  }

  function snap([x, y]: Pt, exclude: number): Pt {
    for (let i = 0; i < pts.length; i++) {
      if (i === exclude) continue;
      const [px, py] = pts[i]!;
      if (Math.hypot(px - x, py - y) < SNAP) return [px, py];
    }
    return [x, y];
  }

  function onCanvasClick(e: React.MouseEvent) {
    if (dragging !== null) return;
    if ((e.target as SVGElement).dataset.vertex) return;
    commit([...pts, toNorm(e)]);
  }

  function onVertexPointerDown(i: number, e: React.PointerEvent) {
    e.stopPropagation();
    (e.target as SVGElement).setPointerCapture(e.pointerId);
    setPast((p) => [...p, pts]);
    setFuture([]);
    setDragging(i);
  }

  function onPointerMove(e: React.PointerEvent) {
    if (dragging === null) return;
    const p = snap(toNorm(e), dragging);
    setPts((cur) => cur.map((v, i) => (i === dragging ? p : v)));
  }

  function deleteVertex(i: number) {
    if (pts.length <= 3) return;
    commit(pts.filter((_, idx) => idx !== i));
  }

  const undo = useCallback(() => {
    setPast((p) => {
      if (p.length === 0) return p;
      setFuture((f) => [pts, ...f]);
      setPts(p[p.length - 1]!);
      return p.slice(0, -1);
    });
  }, [pts]);

  const redo = useCallback(() => {
    setFuture((f) => {
      if (f.length === 0) return f;
      setPast((p) => [...p, pts]);
      setPts(f[0]!);
      return f.slice(1);
    });
  }, [pts]);

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "z") {
        e.preventDefault();
        if (e.shiftKey) redo();
        else undo();
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [undo, redo]);

  async function save() {
    setSaving(true);
    setResult(null);
    const r = await saveZone(spaceId, pts, createdBy);
    setSaving(false);
    setResult(r);
    if (r.ok) setTimeout(() => router.push(`/spaces/${spaceId}`), 1400);
  }

  const path = pts.map((p) => `${p[0] * 100},${p[1] * 100}`).join(" ");
  const dirty = JSON.stringify(pts) !== JSON.stringify(initial);

  return (
    <div className="wt-settle max-w-3xl">
      <h1 className="font-serif text-2xl text-ink">Zone · {spaceName}</h1>
      <p className="mt-1 text-sm text-ink-soft">
        Click to add a point, drag a point to move it, double-click to delete.
        Points snap to each other. Coordinates are normalized to the frame, so a
        camera resolution change never invalidates the zone.
      </p>

      <div className="mt-5 flex items-center gap-2 text-sm">
        <button
          onClick={undo}
          disabled={past.length === 0}
          className="wt-hairline inline-flex items-center gap-1.5 border px-2.5 py-1 text-ink-soft hover:text-ink disabled:opacity-40"
        >
          <Undo2 size={14} strokeWidth={1.5} /> Undo
        </button>
        <button
          onClick={redo}
          disabled={future.length === 0}
          className="wt-hairline inline-flex items-center gap-1.5 border px-2.5 py-1 text-ink-soft hover:text-ink disabled:opacity-40"
        >
          <Redo2 size={14} strokeWidth={1.5} /> Redo
        </button>
        <span className="wt-num ml-auto text-xs text-ink-soft">
          {pts.length} points
        </span>
      </div>

      <div
        className="wt-hairline mt-3 border"
        style={{ aspectRatio: "16 / 9", background: "var(--color-paper-raised)" }}
      >
        <svg
          ref={svgRef}
          viewBox="0 0 100 100"
          preserveAspectRatio="none"
          className="h-full w-full cursor-crosshair touch-none"
          onClick={onCanvasClick}
          onPointerMove={onPointerMove}
          onPointerUp={() => setDragging(null)}
          role="application"
          aria-label="Zone polygon editor"
        >
          {/* Reference-frame grid until a live camera still is wired in (M7). */}
          {Array.from({ length: 15 }, (_, i) => (
            <line
              key={`v${i}`}
              x1={(i + 1) * 6.25}
              y1={0}
              x2={(i + 1) * 6.25}
              y2={100}
              stroke="var(--color-rule)"
              strokeWidth={0.15}
            />
          ))}
          {Array.from({ length: 8 }, (_, i) => (
            <line
              key={`h${i}`}
              x1={0}
              y1={(i + 1) * 11.11}
              x2={100}
              y2={(i + 1) * 11.11}
              stroke="var(--color-rule)"
              strokeWidth={0.15}
            />
          ))}
          <polygon
            points={path}
            fill="color-mix(in srgb, var(--color-field) 16%, transparent)"
            stroke="var(--color-field)"
            strokeWidth={0.5}
          />
          {pts.map((p, i) => (
            <circle
              key={i}
              data-vertex="1"
              cx={p[0] * 100}
              cy={p[1] * 100}
              r={1.4}
              className={cn(
                "cursor-grab",
                dragging === i ? "fill-flag" : "fill-field",
              )}
              stroke="var(--color-paper)"
              strokeWidth={0.5}
              onPointerDown={(e) => onVertexPointerDown(i, e)}
              onDoubleClick={(e) => {
                e.stopPropagation();
                deleteVertex(i);
              }}
            />
          ))}
        </svg>
      </div>

      <p className="mt-2 text-xs text-ink-soft">
        The live detection overlay (people boxes on the camera still, spec 10.2)
        needs a frame + detection endpoint from the edge box; it lands with
        onboarding (M7).
      </p>

      <div className="mt-5 flex items-center gap-3">
        <button
          onClick={save}
          disabled={saving || !dirty || pts.length < 3}
          className="wt-hairline border px-4 py-1.5 text-sm text-ink hover:bg-[color-mix(in_srgb,var(--color-field)_8%,transparent)] disabled:opacity-50"
        >
          {saving ? "Saving…" : "Save zone"}
        </button>
        <button
          onClick={() => router.push(`/spaces/${spaceId}`)}
          className="text-sm text-ink-soft underline decoration-rule decoration-dotted underline-offset-2 hover:text-ink"
        >
          Cancel
        </button>
        {pts.length > 2 && !isSimple(pts) ? (
          <span className="text-xs text-flag">Edges cross — untangle before saving.</span>
        ) : null}
      </div>

      {result && !result.ok ? (
        <p role="alert" className="mt-4 text-sm text-flag">
          {result.error}
        </p>
      ) : null}
      {result?.ok ? (
        <p className="mt-4 text-sm text-field">{result.message}</p>
      ) : null}
    </div>
  );
}

const DEFAULT: Pt[] = [
  [0.3, 0.55],
  [0.7, 0.55],
  [0.78, 0.92],
  [0.22, 0.92],
];

function clamp(n: number): number {
  return Math.min(1, Math.max(0, n));
}

/** Cheap self-intersection guard for the disabled-save hint; the server does
 *  the authoritative shapely check. */
function isSimple(p: Pt[]): boolean {
  const n = p.length;
  for (let i = 0; i < n; i++) {
    for (let j = i + 1; j < n; j++) {
      if (i === j || (i + 1) % n === j || (j + 1) % n === i) continue;
      if (segIntersect(p[i]!, p[(i + 1) % n]!, p[j]!, p[(j + 1) % n]!)) return false;
    }
  }
  return true;
}

function segIntersect(a: Pt, b: Pt, c: Pt, d: Pt): boolean {
  const o = (p: Pt, q: Pt, r: Pt) =>
    Math.sign((q[1] - p[1]) * (r[0] - q[0]) - (q[0] - p[0]) * (r[1] - q[1]));
  return o(a, b, c) !== o(a, b, d) && o(c, d, a) !== o(c, d, b);
}
