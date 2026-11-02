# Vedanta Inventory Dashboard — Design Direction

> **Direction:** "Grafana-calm" — data-dense, muted backgrounds, crisp type, status
> colours that mean something. The dashboard reads like an operations control room:
> calm when things are healthy, loud only where action is needed.

---

## 1. Layout Approach

### Page Structure

```
┌─────────────────────────────────────────────────────────────┐
│  Header  (logo · title · theme toggle)          h = 56px    │
├─────────────────────────────────────────────────────────────┤
│  KPI Strip  (4 metric cards in a row)           h ≈ 120px   │
├──────────────────────┬──────────────────────────────────────┤
│  Chart Panel (2/3)   │  Flag Summary (1/3)                  │
│  • Gross Inventory   │  • NMI / SMI badges                  │
│    by Plant (bar)    │  • Overstock / Understock counts      │
├──────────────────────┴──────────────────────────────────────┤
│  Chart Row  (50/50)                                         │
│  • Stock by Category (bar)  │  Days-on-Hand (histogram)     │
├─────────────────────────────────────────────────────────────┤
│  Table Summary  (22-row data table, full width)             │
│  Columns: # · Table · Description · Columns · Rows · Size  │
└─────────────────────────────────────────────────────────────┘
```

- **Max content width:** 1280 px, centred.
- **Page padding:** 24 px (desktop), 16 px (mobile).
- **Grid:** 12-column at desktop; single-column stack at ≤ 768 px.

### Responsive Breakpoints

| Breakpoint | Width   | Behaviour                                      |
|------------|---------|-------------------------------------------------|
| `desktop`  | ≥ 1440  | Full grid, side-by-side panels                  |
| `tablet`   | 768–1439| 2-column where possible, charts stack           |
| `phone`    | ≤ 390   | Single column, cards stack vertically, table scrolls horizontally |

---

## 2. Colour Palette

### Light Theme

| Token                  | Hex       | Usage                                    |
|------------------------|-----------|------------------------------------------|
| `--surface-primary`    | `#FFFFFF` | Card / panel backgrounds                 |
| `--surface-page`       | `#F8FAFC` | Page background (slate-50)               |
| `--surface-elevated`   | `#FFFFFF` | Elevated cards (with shadow)             |
| `--border-default`     | `rgba(15, 23, 42, 0.08)` | Card borders, dividers      |
| `--border-strong`      | `rgba(15, 23, 42, 0.15)` | Table header border         |
| `--text-primary`       | `#0F172A` | Headings, primary numbers (slate-900)    |
| `--text-secondary`     | `#475569` | Body text, descriptions (slate-600)      |
| `--text-muted`         | `#94A3B8` | Captions, timestamps (slate-400)         |
| `--accent`             | `#2563EB` | Primary actions, focus rings (blue-600)  |
| `--accent-hover`       | `#1D4ED8` | Accent hover state (blue-700)            |
| `--accent-subtle`      | `#EFF6FF` | Accent background tint (blue-50)         |

### Dark Theme

| Token                  | Hex       | Usage                                    |
|------------------------|-----------|------------------------------------------|
| `--surface-primary`    | `#1E293B` | Card backgrounds (slate-800)             |
| `--surface-page`       | `#0F172A` | Page background (slate-900)              |
| `--surface-elevated`   | `#334155` | Elevated cards (slate-700)               |
| `--border-default`     | `rgba(248, 250, 252, 0.08)` | Card borders             |
| `--border-strong`      | `rgba(248, 250, 252, 0.15)` | Table header border      |
| `--text-primary`       | `#F8FAFC` | Headings (slate-50)                      |
| `--text-secondary`     | `#CBD5E1` | Body text (slate-300)                    |
| `--text-muted`         | `#64748B` | Captions (slate-500)                     |
| `--accent`             | `#3B82F6` | Primary actions (blue-500)               |
| `--accent-hover`       | `#60A5FA` | Accent hover (blue-400)                  |
| `--accent-subtle`      | `rgba(59, 130, 246, 0.1)` | Accent tint              |

### Semantic / Status Colours

These are used exclusively for inventory status flags and chart segments.

| Token                  | Light       | Dark        | Meaning                        |
|------------------------|-------------|-------------|--------------------------------|
| `--status-success`     | `#16A34A`   | `#4ADE80`   | Healthy / adequate stock       |
| `--status-success-bg`  | `#F0FDF4`   | `rgba(74, 222, 128, 0.1)` | Success badge bg   |
| `--status-warning`     | `#D97706`   | `#FBBF24`   | Overstock, slow-moving (SMI)   |
| `--status-warning-bg`  | `#FFFBEB`   | `rgba(251, 191, 36, 0.1)` | Warning badge bg   |
| `--status-danger`      | `#DC2626`   | `#F87171`   | Understock, critical shortage  |
| `--status-danger-bg`   | `#FEF2F2`   | `rgba(248, 113, 113, 0.1)` | Danger badge bg   |
| `--status-info`        | `#0284C7`   | `#38BDF8`   | Informational, NMI flag        |
| `--status-info-bg`     | `#F0F9FF`   | `rgba(56, 189, 248, 0.1)` | Info badge bg      |
| `--status-neutral`     | `#64748B`   | `#94A3B8`   | Inactive, no flag              |
| `--status-neutral-bg`  | `#F1F5F9`   | `rgba(148, 163, 184, 0.1)` | Neutral badge bg  |

### Chart Palette (ordered for bar/histogram segments)

```
blue-600  → #2563EB   (primary series)
emerald-500 → #10B981 (secondary)
amber-500 → #F59E0B   (tertiary)
rose-500  → #F43F5E   (quaternary)
violet-500 → #8B5CF6  (quinary — rarely needed)
```

Dark-mode chart colours use the 400-weight variants for legibility on dark surfaces.

---

## 3. Typography

**Typeface:** `Inter` via Google Fonts, fallback `system-ui, -apple-system, sans-serif`.
Never the browser default serif.

### Type Scale

| Token            | Size | Weight | Line-height | Usage                          |
|------------------|------|--------|-------------|--------------------------------|
| `--text-display` | 32px | 700    | 1.2         | Page title                     |
| `--text-h1`      | 24px | 600    | 1.3         | Section headings               |
| `--text-h2`      | 20px | 600    | 1.3         | Card titles, chart titles      |
| `--text-body`    | 14px | 400    | 1.5         | Body text, table cells         |
| `--text-label`   | 14px | 500    | 1.4         | Form labels, column headers    |
| `--text-caption` | 12px | 400    | 1.5         | Timestamps, footnotes, badges  |
| `--text-metric`  | 32px | 700    | 1.0         | KPI card primary number        |
| `--text-metric-label` | 12px | 500 | 1.4       | KPI card label (uppercase)     |

### Hierarchy Rules

- Headings: `--text-primary` colour, semibold/bold weight.
- Body: `--text-secondary` colour, regular weight.
- Captions / muted: `--text-muted` colour, regular weight.
- Never rely on size alone — always pair size + weight + colour to create rank.

---

## 4. Spacing & Radii

### Spacing Scale (4 px base)

| Token   | Value | Usage                                    |
|---------|-------|------------------------------------------|
| `--sp-1`| 4 px  | Inline icon gap, badge padding           |
| `--sp-2`| 8 px  | Tight element gap, input padding         |
| `--sp-3`| 12 px | Card inner padding (compact)             |
| `--sp-4`| 16 px | Card inner padding (standard), grid gap  |
| `--sp-5`| 20 px | Between related sections                 |
| `--sp-6`| 24 px | Page padding (desktop), section gap      |
| `--sp-8`| 32 px | Between major sections                   |
| `--sp-10`| 40 px | Hero spacing                            |
| `--sp-12`| 48 px | Page top/bottom margin                  |

### Radii

| Token              | Value | Usage                              |
|--------------------|-------|------------------------------------|
| `--radius-sm`      | 6 px  | Badges, small chips, inputs        |
| `--radius-md`      | 8 px  | Cards, panels, dropdowns           |
| `--radius-full`    | 9999 px | Pill buttons, avatar circles     |

### Elevation (box-shadow)

| Token              | Value                                        | Usage              |
|--------------------|----------------------------------------------|--------------------|
| `--shadow-sm`      | `0 1px 2px rgba(0,0,0,0.05)`                | Subtle card lift   |
| `--shadow-md`      | `0 4px 6px -1px rgba(0,0,0,0.07), 0 2px 4px -2px rgba(0,0,0,0.05)` | Elevated panels |
| `--shadow-lg`      | `0 10px 15px -3px rgba(0,0,0,0.08), 0 4px 6px -4px rgba(0,0,0,0.04)` | Modals, popovers |

Dark mode: shadows are replaced by lighter surface colours (depth via luminance, not shadow).

---

## 5. Motion

| Token                | Value              | Usage                          |
|----------------------|--------------------|--------------------------------|
| `--duration-fast`    | 150 ms             | Hover colour change, tooltips  |
| `--duration-normal`  | 200 ms             | Panel open/close, theme toggle |
| `--duration-slow`    | 300 ms             | Page transitions (if any)      |
| `--easing-default`   | `ease-out`         | All transitions                |

- Honour `prefers-reduced-motion: reduce` — set all durations to `0ms`.
- Nothing bounces. Nothing animates without a user trigger.

---

## 6. Component Inventory

Every component reads tokens. No literal colour or pixel value in a component file.

### 6.1 Summary Card (KPI Metric)

- Height: 120 px (desktop), auto (mobile).
- Layout: metric value (32 px, bold) top, label (12 px, uppercase, muted) below, optional delta badge.
- Border: 1 px `--border-default`, radius `--radius-md`.
- Background: `--surface-primary`.
- Hover: subtle `--shadow-sm` lift (150 ms ease-out).

### 6.2 Bar Chart Panel

- Used for: Gross Inventory by Plant, Stock by Material Category.
- Chart library: lightweight (Chart.js or Recharts if React).
- Bars use the chart palette; axis labels in `--text-caption`.
- Gridlines: `--border-default` at 0.5 px.
- Tooltip: `--surface-elevated` bg, `--shadow-md`, `--radius-sm`, appears on hover (150 ms).
- Responsive: chart reflows; on phone, bars go horizontal.

### 6.3 Histogram Panel

- Used for: Days-on-Hand distribution.
- Bins with `--accent` fill, lighter on hover.
- X-axis: day ranges; Y-axis: material count.
- Same tooltip pattern as bar chart.

### 6.4 Flag Badge

- Used for: NMI, SMI, Overstock, Understock, Healthy status indicators.
- Pill shape (`--radius-full`), height 24 px.
- Colour mapping:
  - **Healthy** → `--status-success` text on `--status-success-bg`
  - **Overstock** → `--status-warning` text on `--status-warning-bg`
  - **Understock** → `--status-danger` text on `--status-danger-bg`
  - **NMI** → `--status-info` text on `--status-info-bg`
  - **SMI** → `--status-warning` text on `--status-warning-bg`
  - **No flag** → `--status-neutral` text on `--status-neutral-bg`
- Text: `--text-caption` size, `500` weight, uppercase.

### 6.5 Data Table (Table Summary)

- 22 rows (one per SAP table).
- Columns: `#`, `Table Name`, `Description`, `Columns`, `Rows`, `Size`.
- Sticky header row with `--border-strong` bottom border.
- Numeric columns right-aligned, monospace numerals (`font-variant-numeric: tabular-nums`).
- Row hover: `--surface-page` background (light) / `--surface-elevated` (dark).
- Alternating row stripes: subtle `--border-default` bg on even rows.
- Horizontal scroll on mobile with a fade-out gradient at the right edge.
- Density: 40 px row height, 12 px horizontal cell padding.

### 6.6 Theme Toggle

- Icon-only button (sun/moon from Lucide), 36 × 36 px.
- Position: header, right-aligned.
- Transition: icon cross-fade, 200 ms.
- Persists preference in `localStorage`.

### 6.7 Flag Summary Panel

- Card with a vertical list of flag categories.
- Each row: flag badge + count + percentage bar (thin, inline).
- Sorted by count descending.

---

## 7. Interaction Notes

### Hover States

- **Cards:** subtle shadow lift (`--shadow-sm` → `--shadow-md`), 150 ms.
- **Chart bars/bins:** lighten fill 10%, show tooltip.
- **Table rows:** background change to `--surface-page`.
- **Buttons:** darken accent (`--accent` → `--accent-hover`), 150 ms.
- **Badges:** no hover change (they are read-only indicators).

### Focus States

- All interactive elements: 2 px `--accent` ring, 2 px offset, `--radius-sm`.
- Keyboard-navigable: tab order follows visual order.
- Focus ring visible only on keyboard navigation (`:focus-visible`).

### Chart Tooltips

- Appear on hover after 100 ms delay.
- Content: value, label, percentage of total.
- Position: above the element, centred, with 8 px gap.
- Style: `--surface-elevated` bg, `--shadow-md`, `--radius-sm`, `--text-body` size.

### Empty / Loading / Error States

- **Loading:** skeleton placeholders matching final layout (pulsing `--border-default` bg).
- **Empty:** centred icon (Lucide `inbox`) + "No data available" + muted description.
- **Error:** inline banner, `--status-danger-bg` background, specific message, retry action.

---

## 8. Icon Set

**Lucide** icons exclusively, at these sizes:

| Context       | Size  |
|---------------|-------|
| Inline (text) | 16 px |
| Button        | 20 px |
| Empty state   | 48 px |

---

## 9. Stack

| Layer        | Choice                                    |
|--------------|-------------------------------------------|
| Bundler      | Vite                                      |
| Language     | TypeScript                                |
| Styling      | Tailwind CSS (tokens in `tailwind.config`) |
| Components   | shadcn/ui (Radix primitives)              |
| Charts       | Recharts (lightweight, React-native)      |
| Icons        | lucide-react                              |
| Reset        | Tailwind Preflight                        |

---

## 10. File Conventions

```
dashboard/
├── DESIGN.md                  ← this file
├── design-tokens.json         ← machine-readable tokens
├── src/
│   ├── tokens/                ← CSS variables generated from JSON
│   ├── components/            ← one file per component
│   ├── charts/                ← chart wrapper components
│   ├── layouts/               ← page shell, grid
│   └── pages/                 ← assembled views
├── tailwind.config.ts
└── index.html
```

---

## 11. Design Review Checklist (Pre-Ship)

Before any screen ships, the designer (that's me) reviews against:

- [ ] First impression: does it look like a professional operations dashboard?
- [ ] Hierarchy: one primary KPI strip, clear heading/body/caption distinction.
- [ ] Alignment: everything on the 4 px grid, gaps from the scale.
- [ ] Typography: Inter loaded, scale applied, no default serif anywhere.
- [ ] Colour: neutral surfaces, blue accent, semantic status colours only where meaningful.
- [ ] Components: consistent heights/radii/borders, all states present.
- [ ] States: loading skeletons, empty states, error banners designed.
- [ ] Responsive: 390 px and 1440 px both intentional, no overflow.
- [ ] Dark mode: designed values, not inverted; contrast re-checked.
- [ ] Accessibility: keyboard reachable, focus rings, labels, ≥ 40 px touch targets.
- [ ] Copy: labels are specific ("Gross Inventory Value" not "Value"), no placeholder text.
- [ ] Motion: subtle, purposeful, `prefers-reduced-motion` honoured.

---

*Design direction set by Ravi, Product Designer — 2 November 2026.*
*Reference: Grafana-calm / Linear-clean hybrid. No Figma file connected; tokens defined here are the source of truth until one is.*
