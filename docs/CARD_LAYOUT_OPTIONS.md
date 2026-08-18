# GeoLoop Card & Block Layout Options
_Design options for result pages. Pick one option per component._

**Problem:** Current cards are plain white rectangles with visible borders and vertical stacking.
**Goal:** Richer visual hierarchy, varied card treatments, layouts that use horizontal space.

---

## Color tokens reference (from palette)

```
Surface tiers (light → dark):
  S0  #f5f3f0   page bg (current)
  S1  #eeecea   card recessed / inset
  S2  #e0ddd9   divider / subtle fill
  S3  #c8c4be   muted accent

Matcha fills:
  M1  #f2f5eb   lightest matcha wash
  M2  #dce3cf   soft matcha
  M3  #c4cdb3   mid matcha
  M8  #48583b   dark matcha (text on light)
  M10 #1b2214   near-black matcha

Accent (data only):
  Heat  #c94030
  Cool  #2e64c8
  Moss  #557434
```

---

## 1. RESULT_1 — Site Analysis

Three `.result-card` blocks: Site & Soil (3-col), Building Loads (2-col), Borehole Capacity (text).

### Current
- White bg, 1.5px solid border, 16px radius, stacked vertically
- Values inside a CSS grid, all same size

### Option A — "Borderless Tiers" (RECOMMENDED)
- **Remove all borders.** Cards differentiated by background shade:
  - Site & Soil: `S1 #eeecea` bg
  - Building Loads: `M1 #f2f5eb` matcha wash bg
  - Borehole Capacity: transparent (just text, no card)
- Values use larger type (28px) with unit in smaller inline text
- Each stat is a mini-column: value on top (bold), label below (muted), separated by generous whitespace not borders
- Layout: Site & Soil and Building Loads side by side on desktop (2-column grid, 60/40 split), stacked on mobile

### Option B — "Inset Panels"
- Cards have no border but use `inset box-shadow` (`0 2px 8px rgba(0,0,0,0.04) inset`) for a subtle recessed feel
- Slightly darker bg (`S1`) than page
- Stats have a thin left accent bar (3px) in matcha color per category:
  - Soil stats: `M3` left bar
  - Load stats: Heat/Cool dots instead of bars
- Layout: all three cards in one row on desktop (3 equal columns)

### Option C — "Stat Tiles"
- No card wrapper at all. Each individual stat becomes its own tile:
  - 6 tiles total (soil k, ground T, climate zone, peak heat, peak cool, borehole range)
  - 3x2 grid on desktop, 2x3 on mobile
  - Each tile: `M1` bg, 14px radius, no border, 16px padding
  - Value centered, large (32px), label below (11px muted)
- Compact, dashboard-like feel

### Option D — "Dark Feature Card + Light Details"
- Site & Soil becomes a dark card (`M10` bg, white text) — it's the headline data
- Building Loads and Borehole stay light but borderless
- Creates visual hierarchy: dark = primary data, light = secondary

---

## 2. RESULT_STRATEGY — Hybrid Strategy

Heavy page: compare rows, equipment cards, scenario cards grid, charts, cost compare, breakdown tables.

### Current
- Everything white + border, stacked vertically
- Compare rows side-by-side but both look the same except `.hi` has darker border
- Scenario cards: 3-col grid of identical bordered boxes
- Charts in bordered white containers

### Option A — "Split Dashboard" (RECOMMENDED)
- **Top zone (dark):** Compare row becomes a dark strip (`M10` bg):
  - Two compare columns: the `.hi` one is slightly lighter (`M8` bg) with white text
  - The secondary one is semi-transparent overlay
  - Savings tag stays as-is (already dark pill)
- **Middle zone (light):** Equipment cards + scenario grid
  - Equipment cards: borderless, `M1` bg, with a large value and small label
  - Scenario cards: no individual borders; the grid itself has a single `S1` bg with internal dividers only (like a table, but rounded corners on the outer edge)
  - The `.hi` scenario gets a subtle matcha left bar instead of dark border
- **Chart zone:** Chart containers become borderless, just the canvas on the page bg with a faint `S2` top rule above
- **Cost compare:** Same dark/light split as compare row at top
- **Breakdown tables:** Alternate row shading (`S0`/`S1`) instead of dotted borders

### Option B — "Card Stack with Accents"
- Keep cards but remove all borders
- Each card type gets a distinct left accent:
  - Compare: 4px `M3` left bar
  - Equipment: 4px `M8` left bar
  - Cost: 4px moss left bar
- Cards have subtle shadow (`0 1px 3px rgba(0,0,0,0.06)`) instead of borders
- Scenario grid: pills/badges instead of bordered cards (dark text on `M2` bg, rounded)
- Charts: floating (no container at all, just canvas with title above)

### Option C — "Bento Grid"
- Entire page is one large bento-style grid (like the landing page)
- Cells of varying sizes:
  - Compare row: 2 cells spanning full width, 60/40
  - Chart: large cell (span 2 columns)
  - Equipment: 3 small cells in a row
  - Scenario: 3 cells below
  - Cost compare: 2 cells, same as compare row
- All cells: `S1` bg, no border, 16px radius, 20px padding
- The `.hi` cells get `M1` bg (matcha tint) as emphasis
- More visual interest from size variation than from color/border

### Option D — "Tabbed Sections"
- Group related data into collapsible tab sections:
  - Tab 1: "System Comparison" (compare + savings)
  - Tab 2: "Equipment" (equipment cards + scenario grid)
  - Tab 3: "Cost Analysis" (cost compare + breakdown + chart)
- Each tab is full-width, content inside uses the borderless tier approach
- Reduces vertical scroll, groups logically

---

## 3. RESULT_FINAL — Cost Benchmark / Borefield Sizing

Simpler page: borefield geometry card (stat grid), site plan canvas.

### Current
- One `.result-card` with 3-col then 2-col stat grids, bordered
- Canvas in bordered white container

### Option A — "Hero Stat Bar + Plan" (RECOMMENDED)
- **Hero bar:** Borefield stats displayed in a single horizontal strip:
  - Dark matcha bg (`M10`), white text
  - 3 primary stats (boreholes, depth, total length) as large numbers with labels below
  - Dividers between stats: 1px vertical line at 0.15 opacity
  - Secondary stats (footprint, spacing) in smaller text below, or as `M2` pills
- **Site plan:** Canvas fills full width, no border, slight `S1` bg behind it
  - Canvas label moves to overlay position (top-left, semi-transparent)

### Option B — "Stat Tiles + Floating Plan"
- Each stat is its own tile (same as Result_1 Option C)
  - 5 tiles: 3 on top row, 2 below
  - Matcha bg tones: boreholes `M1`, depth `M2`, length `M1`
  - No borders, generous padding
- Site plan: positioned to the right of tiles on desktop (side-by-side layout)

### Option C — "Spec Sheet Style"
- No cards at all. Stats displayed as a clean spec list:
  - Left-aligned labels, right-aligned values, dot leaders between (like result_report spec rows)
  - Horizontal rule separating primary from secondary stats
  - Canvas below, full-width, borderless
- Minimal, engineering-document feel

---

## 4. RESULT_REPORT — Full Report / PDF

Most complex: score card (colored bg), hero stats (3-col), spec sheet, borefield equation, building module, subsurface module (dark), config module, borehole slider.

### Current
- Score card: already has colored bg based on grade — this is GOOD, keep
- Hero stats: 3-col grid with right borders — functional but plain
- Spec rows: dot-leader pattern — clean, keep
- Modules: mix of white-bordered and one dark card (subsurface)
- Borefield equation: white bordered card with inline math

### Option A — "Report Blocks" (RECOMMENDED)
- **Score card:** Keep as-is (already has grade-colored bg). Possibly add subtle grain texture overlay for print quality.
- **Hero stats:** Remove right borders. Use matcha-tinted bgs instead:
  - Heating stat: very faint warm tint (`rgba(201,64,48,0.06)`)
  - Cooling stat: very faint cool tint (`rgba(46,100,200,0.06)`)
  - Borehole stat: `M1` tint
  - Each stat becomes a distinct tile with 12px radius, no border
- **Spec sheet:** Keep dot-leader pattern (clean). Add section grouping:
  - Group into "Site", "Building", "System" with subtle `S2` dividers between groups
  - Optional: alternate row shading
- **Borefield equation:** Remove border. Use `M1` bg with no border, or go dark (`M10` bg, white text) to match subsurface module aesthetic
- **Building module:** Remove border. Add `M3` left accent bar (4px). `S1` bg.
- **Subsurface module:** Keep dark. It already contrasts well. Possibly adjust to `M10` bg instead of `#1e1e1a` for palette consistency.
- **Config module:** Remove dashed border. Use `S1` bg, no border.
- **Slider:** Keep as-is (functional). Update thumb color to `M8` for palette alignment.

### Option B — "All-Dark Report"
- Flip the report to dark theme (like landing page):
  - Page bg: `M10`
  - All cards: slightly lighter dark (`#222b1a`)
  - Text: `#f5f3f0` (paper)
  - Score card: keep colored bg (pops more on dark)
  - Hero stats: dark tiles with colored value text
  - Spec rows: light text on dark, dot leaders in 0.15 alpha
- Print media query overrides to white for actual PDF output
- Dramatic, premium report feel

### Option C — "Modular Magazine"
- Each module becomes a full-width section with generous vertical spacing (48px between)
- No visible card containers at all
- Content differentiated by:
  - Typography scale (larger values, smaller labels)
  - Horizontal rules between sections
  - Occasional matcha wash bg for emphasis sections
- Score card: keep colored
- Hero stats: very large numbers (48px), inline with category dots
- Subsurface: full-width dark strip (edge to edge)
- Clean, editorial/magazine feel

---

## 5. CROSS-CUTTING LAYOUT PATTERNS

These apply to any option above:

### Border elimination strategies
| Instead of... | Use... |
|---|---|
| 1.5px solid border | No border + `S1` bg fill |
| Border + white bg | Subtle shadow `0 1px 4px rgba(0,0,0,0.05)` |
| Border between cards | 24px gap (whitespace as separator) |
| Dotted borders between rows | Alternate row shading `S0`/`S1` |
| `.hi` dark border for emphasis | Matcha left bar (4px `M3`) or `M1` bg tint |

### Layout patterns for data grids
| Pattern | When to use | Description |
|---|---|---|
| **Side-by-side split** | 2 comparison items | 60/40 or 50/50 grid, one dark one light |
| **Stat tiles** | 3-6 individual values | Equal-size tiles in 2x3 or 3x2 grid |
| **Hero bar** | Primary metric group | Full-width dark strip with big numbers |
| **Spec list** | 5+ key-value pairs | Dot-leader or alternating rows, no cards |
| **Bento** | Mixed-size content | Variable-span grid cells |
| **Accordion** | Dense data, optional depth | Collapsed sections user can expand |

### Value typography hierarchy
```
Primary value:   28-40px, weight 800, M10 color (or white on dark)
Secondary value: 18-22px, weight 700, text color
Tertiary value:  13-14px, weight 600, muted color
Label:           10-11px, weight 500, faint color, uppercase
Unit:            10-12px, weight 400, faint color, inline after value
```

---

## 6. RECOMMENDED COMBINATION

For consistency across all result pages, pick from the same family:

**"Borderless Matcha" (Option A across all pages):**
- Zero visible borders anywhere
- Cards differentiated by bg shade (S0/S1/M1)
- Dark hero bars for primary metrics
- Left accent bars (matcha) for emphasis cards
- Generous whitespace between sections
- Side-by-side layouts on desktop, stacked on mobile

This creates a calm, professional look that matches the grayed-matcha palette without looking like generic Bootstrap cards.

---

## 7. PAGES NOT INCLUDED (already good)

- stage1a, stage1b, stage1c, stage2: input forms, underline inputs, clean
- onboarding_1, onboarding_2: role selection + stage overview, redesigned
- welcome: particle text hero, single-purpose
- signup, account, contact: auth/info pages with gradient waves bg
