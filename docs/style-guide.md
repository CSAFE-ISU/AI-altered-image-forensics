# Style guide

A reference of the app's text styles — the canvas header, the two accordion types, and the analysis sub-sections — read from `static/tracker.css` (and the inline SVG/JS styles for dashboard plots).

## Token legend

| Token | Resolves to |
|----|----|
| `var(--mono)` | **Geist Mono** (`'Geist Mono', ui-monospace, 'SF Mono', monospace`) |
| `var(--sans)` | **Geist** (body default; used when no `font-family` is set) |
| `var(--text)` = `--ink-black` | **#0d1f2d** (ink-black) |
| `var(--text-muted)` | `oklch(0.553 0.013 58)` — medium warm gray |
| `var(--text-faint)` | `oklch(0.709 0.01 56)` — light gray |
| `var(--accent)` = `--rose-wine` | **#bd4f6c** |
| `var(--label-color)` = `--rose-wine` | **#bd4f6c** — field labels & "(auto)" tags |
| `var(--velvet-purple)` | **#5F3370** — deep velvet purple (section headings) |

### Type scale & the `.ui-label` utility

Font sizes use a scale defined in `:root`: `--text-xs` 10px, `--text-sm` 11px, `--text-base` 13px, `--text-md` 15px, `--text-lg` 18px, `--text-xl` 22px.

`.ui-label` (Geist Mono, `--text-sm`, weight 500, `0.06em`, uppercase) is a utility class **added to the label elements in markup** (`tracker.html` and via `className` in `tracker.js`) alongside their own class. The label classes below keep only their own color/layout declarations and get their font/size/weight/spacing/case from `.ui-label`: `.img-caption`, `.filter-label`, `.gallery-bar-title`, `.dash-indicator-label`, `.gallery-row-label`, `.gallery-actions-title`, `.analysis-summary`, `.dash-bar-label`, the dashboard `th` cells, `.dash-bar-count`, `.dash-bar-count-wide`, `.record-count`, `.form-subtitle`.

------------------------------------------------------------------------

## Canvas header

The record title and subtitle at the top of the canvas, above the accordions.

| Text element | Selector | Font | Size | Weight | Color |
|----|----|----|----|----|----|
| **Title** (record name) | `.form-title` | Geist Mono | 22px | 600 | `--text` (#0d1f2d) |
| **Subtitle** (record type, e.g. "AI ALTERATION") | `.form-subtitle` (`.ui-label`) | Geist Mono | 11px | 500 | `--text-faint` |

------------------------------------------------------------------------

## A. Image-records accordion (`.section-card` → `.accordion-item`)

| Text element | Selector | Font | Size | Weight | Transform / spacing | Color |
|----|----|----|----|----|----|----|
| **Section heading** (trigger title) | `.section-label` | Geist | 15px | 600 | uppercase, `0.04em` | **velvet-purple** (`--velvet-purple` #5F3370) — **white** when incomplete |
| **External link in heading** (e.g. aiornot.com) | inline on `<a>` | inherits Geist Mono | inherits 15px | **400** | inherits uppercase | rose-wine (`--accent`) |
| **Chevron** (icon, not text) | `.accordion-chevron` | 16×16 SVG | — | — | rotates 180° when open | **velvet-purple** (`--velvet-purple`) — **white** when incomplete |
| **Field labels** (content) | `.field label` | Geist Mono | 12px | 500 | none | **rose-wine** (`--label-color`) — **white** when incomplete |
| **"(auto)" tags** | `.auto-tag` | inherits Geist Mono | 11px | 400 | none | **rose-wine** (`--label-color`) — **white** when incomplete |
| **Field values** (inputs) | inherited | Geist | 13px | normal | — | `--text` (#0d1f2d) |

Trigger layout (not text): `padding 0.9rem 1.5rem`, flex `space-between`, `:hover { opacity 0.7 }`, bottom border when open.

Incomplete ("to-do") accordions (`.acc-incomplete`) are solid **rose-wine** (background + border) with **white** title and field labels. Complete accordions have a **lime-cream** border with a lime-cream strip behind the title, over white content.

### Input field states

Base input geometry (all states): `width: 100%`, `padding: 7px 10px`, `border-radius: var(--radius)`, Geist (sans) 13px.

| State | Selector | Background | Border | Text / notes |
|----|----|----|----|----|
| **Default** | `.field input[type=text]` / `[datetime-local]`, `.field select`, `.field textarea` | `--surface` (white) | 1px `--border` | `--text` (#0d1f2d) |
| **Focus** | `.field input:focus`, `…select:focus`, `…textarea:focus` | `--card` (white) | `--accent-border` (rose-wine tint) + 3px `--ring` focus ring | — |
| **Auto / read-only** | `.auto-field` | `--surface2` (light gray) | `--border` | `--text-muted`, `cursor: default` |
| **Required-but-empty** | `.field-blank` | `--surface` (white) | **2px** `--burnt-peach` (#d7816a) | rating / region widgets get a 2px `--burnt-peach` outline instead |
| **Optional** | `.field-optional` | — | — | JS status marker only — renders like **Default** |
| **Required-and-filled** | *(no class)* | — | — | renders like **Default** |

------------------------------------------------------------------------

## B. Dashboard accordion (`.dash-group`)

| Text element | Selector | Font | Size | Weight | Transform / spacing | Color |
|----|----|----|----|----|----|----|
| **Group title** (summary) | `.dash-group > summary` | Geist | 18px | 600 | uppercase, `0.04em` | **velvet-purple** (`--velvet-purple`) |
| ↳ chevron (right, rotates) | `summary::after` (CSS mask) | 16×16 | — | — | rotates 180° when open | **velvet-purple** (`--velvet-purple`) |
| **Section title** | `.section-label` (shared with the form) | Geist | 15px | 600 | uppercase, `0.04em` | **velvet-purple** (`--velvet-purple`) |
| **Section subtitle** | `.dash-section-subtitle` | Geist (sans) | 12px | normal | none | `--text-muted` |
| **Summary card number** | `.dash-card-num` | Geist Mono | 2rem | 600 | `line-height 1` | rose-wine (`--accent`) |
| **Summary card label** | `.dash-card-label` | Geist (sans) | 11px | normal | none | `--text-muted` |
| **Bar label** | `.dash-bar-label` (`.ui-label`) | Geist Mono | 11px | 500 | uppercase, right-aligned | `--text` (#0d1f2d) |
| **Bar count** | `.dash-bar-count` (`.ui-label`) | Geist Mono | 11px | 500 | uppercase, right-aligned | `--text-muted` |
| **Bar count (wide)** | `.dash-bar-count-wide` (`.ui-label`) | Geist Mono | 11px | 500 | uppercase, right-aligned | `--text-muted` |
| **Indicator label** | `.dash-indicator-label` (`.ui-label`) | Geist Mono | 11px | 500 | uppercase, `0.06em` | `--text-muted` |
| **Table header** | `.dash-table th` | Geist Mono | 11px | 500 | uppercase, `0.06em` | `--text-muted` |
| **Table cell** | `.dash-table td` | Geist (sans) | 12px | normal | none | `--text` (#0d1f2d) |
| **Confusion-matrix cell** | inline | Geist Mono | 18px | normal | centered | `--text` (#0d1f2d) |

### Plot text (SVG; styles set inline in `tracker.js`)

| Text element                         | Font       | Size    | Color (`fill`)     |
|--------------------------------------|------------|---------|--------------------|
| Axis tick labels                     | Geist Mono | 9px     | `--text-muted`     |
| X-axis unit label                    | Geist Mono | 9px     | `--text-faint`     |
| Legend items                         | Geist Mono | 11px    | `--text-muted`     |
| Scatter model labels / RF checkboxes | Geist Mono | 0.82rem | `--text` (#0d1f2d) |

------------------------------------------------------------------------

Both accordion types share the same section-heading treatment (Geist, uppercase, velvet-purple, 15px). Dashboard group titles (`.dash-group > summary`) are Geist, velvet-purple, at 18px. `.dash-group` is styled to visually match the form `.accordion-item`: a 2px lime-cream outline + card radius, a lime-cream title strip, `0.9rem 1.5rem` trigger padding, a right-side rotating chevron (same SVG, via a CSS mask), and an open border-bottom — while staying a native `<details>` element. Smaller body labels in the dashboard use gray (`--text-muted` / `--text-faint`).

------------------------------------------------------------------------

## C. Analysis sub-section (inside the image-records accordions)

These live in the **Image preview**, **Metadata forensics**, and **C2PA Viewer Results** accordions. Each element now has a dedicated class for easy editing.

| Text element | Selector | Font | Size | Weight | Transform / spacing | Color |
|----|----|----|----|----|----|----|
| **"Analysis results" toggle** | `.analysis-summary` (`.ui-label`) | Geist Mono | 11px | 500 | uppercase, `0.06em` | `--text-faint` |
| **Image-caption prefix** ("Original" / "Input" / …) | `.img-caption` (`.ui-label`) | Geist Mono | 11px | 500 | uppercase, `0.06em` | `--text-faint` |
| **Image name** (filename) | `.img-name` | Geist Mono | 10px | 400 | none, `word-break: break-all` | `--text-faint` |
| **Expandable summary** ("Camera EXIF fields", "Photoshop / Adobe markers", "ICC…", "Grok signatures", "C2PA Results – Auto-detected") | `.analysis-detail > summary` | Geist (sans) | 0.82rem | normal | `cursor: pointer` | `--text-muted` |
| **Field name** (expandable table, left cell) | `.c2pa-table td:first-child` | Geist (sans) | inherited | normal | `white-space: nowrap` | `--text-muted` |
| **Field value** (expandable table, right cell) | `.c2pa-table td` | Geist (sans) | inherited | normal | none | `--text` (#0d1f2d) |
| ↳ "Absent" / warning value | `.c2pa-table .c2pa-warn` | — | — | 500 | — | `#c0392b` (red) |
| ↳ OK value | `.c2pa-table .c2pa-ok` | — | — | normal | — | `#27ae60` (green) |
| **"C2PA data found"** label | `.viewer-found-label` | Geist (sans) | 0.9rem | normal | `white-space: nowrap` | `--text` (#0d1f2d) |

The expandable panels (`.analysis-detail`) keep an inline `display:none` so the JS show/hide toggle in `tracker.js` still works; all other styling is in the CSS classes above.

------------------------------------------------------------------------

## Palette contrast

Palette color pairs that meet the WCAG 4.5:1 contrast ratio (from the Coolors contrast checker):

![Palette contrast matrix](color-contrast.png)
