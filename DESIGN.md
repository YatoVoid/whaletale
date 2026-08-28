# WhaleTale console — visual world

**Mode:** Operate. The operator completes tasks; the interface recedes. Brand
lives in precise details, not expression.

**The world:** a working drawing set. Not a dashboard, not a monitoring product.
Closer to a surveyor's field book, a rent roll, an architect's plan sheet — flat
ink on paper, hairline rules doing the structural work, the grid itself as the
decoration. A daytime tool for a commercial decision.

Explicitly rejected (spec 13): the dark-dashboard-with-neon-accents NOC look;
the warm-cream-and-terracotta "AI default". This paper is cooler and more
archival than either.

## Color

Light, from the use scene (a back office, daytime, overhead light).

| Token | Value | Use |
|---|---|---|
| `--paper` | `#f6f5f1` | page ground |
| `--paper-raised` | `#fbfaf7` | the one elevation step (menus, editor panel) |
| `--ink` | `#1b1a16` | primary text, drawn lines |
| `--ink-soft` | `#5c584e` | secondary text (tinted from the paper hue, never a flat gray) |
| `--rule` | `#d7d3c8` | hairline dividers, table borders, grid lines — 1px only |
| `--field` | `#2f4f4f` | primary data fill: bars, occupied cells, the occupied timeline |
| `--field-weak` | `#b6c2bf` | secondary/baseline data |
| `--flag` | `#b23a26` | anomaly and alert, and nothing else — a surveyor's correction mark |
| `--vacant` | repeating 3px hatch of `--rule` on `--paper` | vacancy, everywhere it appears |
| `--degraded` | `#8a7d5c` dotted underline / marker | a bucket on a secondary camera |

Dark mode: not built. This is a daytime tool; ship light only and say so.

## Type

Self-hosted (never a system display face).

- **Display / headings / report-like prose:** IBM Plex Serif. It has a faint
  technical-drawing character and reads as a document, not a UI chrome label.
- **UI, tables, controls, data:** IBM Plex Sans, `font-feature-settings:
  "tnum" 1, "cv05" 1` so every column of numbers aligns.
- **Measurements and identifiers only** (bucket times, coordinates,
  `zone_version_id`): IBM Plex Mono. Earned here — this is data, not costume.

Scale: 12 / 13 / 15 / 18 / 24 / 32. Body measure 66ch in prose. Tracking floor
-0.01em on display sizes; UI text at 0.

## Structure

- Hairline rules and whitespace divide the page. **No cards as the page
  scaffold**, no nested cards, no icon+heading+text grid, no hero-metric block.
- One elevation step, and only for true overlays: `--paper-raised` with a soft
  shadow (real offset + blur: `0 8px 24px -12px rgba(27,26,22,.28)`). Everything
  else sits flat on the paper.
- A number is never shown without its unit and period: "142 entries · Sat
  11am–4pm", not "142".
- Left rail navigation (a plan-sheet index), thin, always visible on desktop; a
  top bar on tablet.

## Marks

- Icons: Lucide, 1.5px stroke, 16/20px. No emoji, no unicode glyphs.
- Charts: server-ish SVG style carried from the M3 report — thin axes, `--field`
  bars, `--flag` for the anomalous bar, no gridlines, no rounded caps.
- Focus: a 2px `--ink` outline offset 2px. Selection: `--field` at 18% alpha.
  Scrollbars, caret, and tabular figures themed from the palette.

## Motion

One authored moment: on first paint of a data view, the rules draw in and the
numbers settle (short, exponential ease-out, from an already-legible state —
never a blank). Route changes cross-fade the content column only. Nothing else
animates. `prefers-reduced-motion` disables all of it.
