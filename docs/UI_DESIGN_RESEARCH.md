# GeoLoop UI Design Research
_Deep research for color system, animations, interactive components, and illustration integration._
_Compiled Aug 2026. Review before implementation sprint._

---

## 1. COLOR PALETTE — Recommended System

### Why single-hue + grayscale works for GeoLoop
Engineering tools need trust and precision. A monochromatic system anchored in **forest green** (earthy, geothermal, sustainable) with a warm grayscale reads as scientific but human. Neon accents are for SaaS dashboards; GeoLoop needs *depth*, not flash.

### Proposed token set

```
BASE HUE: #1a5c38  (forest green, HSL 150° 55% 23%)

Greens (primary scale, 10 steps)
--green-1:  #f0f9f3   ← backgrounds, subtle fills
--green-2:  #d4eddf
--green-3:  #a8d9bc
--green-4:  #7cc49a
--green-5:  #50af78
--green-6:  #2d9a5a   ← primary interactive (buttons, links)
--green-7:  #1e7a48   ← hover, focus ring
--green-8:  #1a5c38   ← anchor, brand
--green-9:  #123d25
--green-10: #0a1f12   ← near-black for dark text

Warm grayscale (neutrals, 10 steps)
--gray-0:  #faf9f7   ← page background
--gray-1:  #f5f3f0   ← card background (current --bg)
--gray-2:  #eeecea   ← subtle borders
--gray-3:  #e0ddd9   ← dividers (current --border)
--gray-4:  #c8c4be
--gray-5:  #a09c97   ← faint text (current --faint)
--gray-6:  #7a7570   ← muted text (current --muted)
--gray-7:  #4a4540
--gray-8:  #2e2a26
--gray-9:  #1a1814   ← primary text (current --text)

Heat accent (cooling/heating indicator, 8 steps)
--heat-1: #fff8f0
--heat-4: #f97316   ← heating mode
--heat-8: #7c2d12

Cool accent
--cool-1: #eff6ff
--cool-4: #3b82f6   ← cooling mode
--cool-8: #1e3a5f

Earth accent (subsurface / soil data)
--earth-1: #fdf8f0
--earth-4: #b45309   ← soil thermal warning
--earth-8: #451a03
```

**WCAG compliance:**
- --green-7 on white: ratio ~4.8:1 → passes AA (normal text)
- --green-8 on white: ratio ~7.2:1 → passes AAA
- --gray-9 on --gray-1: ratio ~15:1 → passes AAA

### 10 reference color systems studied

| # | Source / Product | Approach | Key insight for GeoLoop |
|---|---|---|---|
| 1 | **Stripe** (stripe.com) | Single purple hue, 9 steps, warm white bg | Semantic aliases (--color-primary-action) over raw hex |
| 2 | **Vercel** design system | Near-monochrome, accent only on interactive | Less is more; color reserved for state, not decoration |
| 3 | **Linear** | Dark-mode primary, single accent, grayscale | Spacing and typography carry hierarchy, not color |
| 4 | **Anthropic Claude** | Warm beige base + terracotta accent | Warm neutrals feel more human than cold grays |
| 5 | **ENERG (Dribbble)** | Forest green ROI calculator | Dark pine → pistachio gradient, earthy feel for energy tools |
| 6 | **Oak meditation app** | Soft greens + muted browns | Low-saturation greens reduce anxiety; good for decision-support tools |
| 7 | **US Web Design System** | Tonal palette with consistent perceptual lightness | Grade system: same lightness = same weight across hue families |
| 8 | **Accessible Palette tool** | LCh-based palette generation | LCh ensures perceptually uniform steps; pure HSL is uneven |
| 9 | **Tailwind CSS** | 10-step per-hue scales, warm gray (zinc/stone) | Warm gray (stone) + green matches GeoLoop's existing `--bg` |
| 10 | **Material Design 3** | Tonal surface + primary container pattern | Surface-variant approach prevents "flat card soup" |

**Recommendation:** Extend current `design-tokens.css` — the foundation is correct. Add missing mid-tones (--green-3, --green-4, --green-5) and semantic aliases (`--color-interactive`, `--color-interactive-hover`, `--color-surface-raised`).

---

## 2. ANIMATIONS & MICRO-INTERACTIONS

### Principles from research
- **Functional motion only.** Every animation should communicate state, not decorate. SaaS products that used clarity-focused motion saw 15% higher task completion vs splash animations.
- **Duration budget:** enter 200-300ms, exit 150ms, page transitions 350ms max.
- **Easing:** `cubic-bezier(0.2, 0, 0, 1)` for entrances (fast out), `ease-in` for exits.
- **Respect `prefers-reduced-motion`** — wrap all transitions in a media query.

### 10 patterns relevant to GeoLoop

| # | Pattern | Where to use | Implementation |
|---|---|---|---|
| 1 | **Number counter roll** | Score card (0→85), NB/H/L results | CSS `counter` + JS `requestAnimationFrame`, count up over 600ms |
| 2 | **Progress shimmer** | Loading skeleton while API runs | CSS gradient animation `background-position` sweep |
| 3 | **Stat card entrance** | Result cards slide up on first render | `transform: translateY(16px) → 0`, `opacity: 0 → 1`, staggered 80ms |
| 4 | **Canvas draw-on** | Borehole layout canvas | Draw paths incrementally over 800ms using `requestAnimationFrame` |
| 5 | **Button specular ring** | Already implemented (WebGL SpecularButton) | Extend to green color: LINE_COL `#1e7a48`, BASE_COL `#2d9a5a` |
| 6 | **Pill selection pulse** | onboarding_1 role pills | `transform: scale(1.05)` + brief green ring on select |
| 7 | **Form field focus glow** | ZIP, floor area inputs | `box-shadow: 0 0 0 3px var(--green-2)` on `:focus` (CSS only) |
| 8 | **FAQ accordion unfurl** | result_report.html FAQ | Max-height transition: `0 → auto` via JS-measured pixel height |
| 9 | **Score bar fill** | Factor bars in score card | Width transition from 0% → final%, delay 200ms after card visible |
| 10 | **Page slide transition** | Stage1a → Stage1b → etc. | Translate X ±20px + opacity, triggered on navigation |

### CSS boilerplate (respects prefers-reduced-motion)
```css
@media (prefers-reduced-motion: no-preference) {
  .stat-card-enter {
    animation: slideUp 280ms cubic-bezier(0.2, 0, 0, 1) both;
  }
  @keyframes slideUp {
    from { opacity: 0; transform: translateY(16px); }
    to   { opacity: 1; transform: translateY(0); }
  }

  .factor-bar { transition: width 600ms cubic-bezier(0.2, 0, 0, 1); }
  .shimmer    { animation: shimmer 1.4s linear infinite; }
  @keyframes shimmer {
    from { background-position: -400px 0; }
    to   { background-position: 400px 0; }
  }
}
```

---

## 3. INTERACTIVE COMPONENTS

### 10 components to add / upgrade

| # | Component | Current state | Upgrade |
|---|---|---|---|
| 1 | **Soil quality gauge** | Text label ("Moderate") | Semi-circle SVG gauge, color = heat/cool/earth scale, animates on load |
| 2 | **Borehole depth slider** | `<input type="range">` default | Custom thumb with live value bubble, green track fill |
| 3 | **Building type card grid** | Plain radio pills | Cards with small SVG icon per type, selected = green border + checkmark |
| 4 | **Score donut** | Static colored card | SVG donut, arc length proportional to score (0–100), animates fill |
| 5 | **Climate zone map** | Text ("Zone 5A") | Small inline SVG US map, zone highlighted in green-4 |
| 6 | **Cost comparison bar** | Two numbers in table | Horizontal stacked bar: GSHP cost vs conventional, animated width |
| 7 | **Load profile sparkline** | Not shown | 24h sparkline SVG (heating negative, cooling positive), color-coded |
| 8 | **Borehole perimeter preview** | Canvas (existing) | Add CSS `transition: opacity` on load; canvas draws in over 1s |
| 9 | **Tooltip system** | `title` attribute | Custom floating tooltip with green arrow, 200ms fade |
| 10 | **Stepper progress bar** | None | Top of wizard: 5-step dot rail, current = green, done = green-8 checkmark |

---

## 4. WATERCOLOR ILLUSTRATION INTEGRATION

### What you have
Low-contrast, single-hue watercolor sketches (similar to welcome page). Warm tones, soft edges, architectural/geological subject matter.

### Integration patterns studied

| # | Technique | How it works | Fits GeoLoop? |
|---|---|---|---|
| 1 | **Hero bleed** | Full-bleed watercolor bg behind hero text, text on white card overlay | Yes — welcome page already does this |
| 2 | **Section divider splash** | Watercolor texture strip between sections, 80px tall, faded top+bottom | Yes — between wizard stages |
| 3 | **Card corner accent** | Small watercolor ink stroke in top-right corner of result cards | Yes — light, decorative |
| 4 | **Loading state illustration** | Replaces spinner with a small watercolor building sketch during API calls | Yes — charming, on-brand |
| 5 | **Empty state art** | Watercolor borehole cross-section when no results yet | Yes — better than "No data" |
| 6 | **Background texture layer** | `mix-blend-mode: multiply` + low opacity over solid bg | Possible — test at 8-12% opacity |
| 7 | **SVG + raster composite** | Ink sketch as `<img>`, data visualization as SVG overlay | Good for soil profile visualization |
| 8 | **Parallax layer** | Background sketch scrolls slower than content | Avoid — too distracting for a tool |
| 9 | **Print export header** | Watercolor illustration header on PDF export | Yes — elevates the report output |
| 10 | **Icon sketch style** | Replace solid icons with ink-sketch-style SVGs matching watercolor feel | Possible — needs new icon set |

**Recommended approach for GeoLoop:**
1. Use illustrations as **loading state backgrounds** (most impactful, least intrusive)
2. Add a **section-divider watercolor strip** on the welcome page between hero and stage list
3. Use as **PDF report header** (already a strong branding moment)
4. Keep illustrations OUT of the functional wizard steps — they add noise during decision-making

---

## 5. ICONS

### Recommended icon sources (MCP-accessible)
The VSCode Iconify extension + MCP gives access to:
- **Phosphor Icons** (`ph:`) — duotone variants work beautifully with green tint
- **Lucide** (`lucide:`) — clean, consistent 24px stroke icons
- **Tabler Icons** (`tabler:`) — largest open set, engineering-friendly symbols

### Specific icon recommendations per page

| Page | Icon | Source |
|---|---|---|
| ZIP / Location | `ph:map-pin-duotone` | Phosphor |
| Building type | `ph:buildings-duotone` | Phosphor |
| Borehole depth | `ph:arrow-down-duotone` | Phosphor |
| Soil thermal k | `ph:thermometer-duotone` | Phosphor |
| Climate zone | `lucide:cloud-sun` | Lucide |
| Cost | `ph:currency-dollar-duotone` | Phosphor |
| Hybrid system | `ph:git-branch-duotone` | Phosphor |
| Save project | `ph:floppy-disk-duotone` | Phosphor |
| Score/grade | `ph:seal-check-duotone` | Phosphor |
| FAQ | `ph:question-duotone` | Phosphor |

---

## 6. DECISION MATRIX — What to build first

| Priority | Change | Effort | Impact |
|---|---|---|---|
| P0 | Extend color tokens (add mid-tones, semantic aliases) | 1h | High — enables all other changes |
| P0 | Form field focus glow (CSS only) | 30min | High — immediate tactile improvement |
| P1 | Stat card entrance animation (CSS) | 1h | High — score card feels alive |
| P1 | Factor bar fill animation | 1h | High — score section most-viewed |
| P1 | Score donut SVG | 2h | High — replaces most-ugly element |
| P2 | Building type card grid (icons) | 2h | Medium — onboarding feels premium |
| P2 | Watercolor loading state | 1h | Medium — brand moment |
| P2 | Stepper progress bar | 1.5h | Medium — spatial orientation |
| P3 | Custom tooltip system | 2h | Medium |
| P3 | Cost comparison bar chart | 2h | Medium |
| P3 | Load profile sparkline | 3h | Lower — advanced |

---

## Sources consulted

- [Green Tech Design Trends](https://beetroot.co/greentech/top-design-trends-shaping-green-tech-and-clean-energy-mobile-apps/)
- [Color Psychology in UI 2025](https://mockflow.com/blog/color-psychology-in-ui-design)
- [IxDF UI Color Palette 2026](https://ixdf.org/literature/article/ui-color-palette)
- [ENERG — Green Energy ROI Calculator (Dribbble)](https://dribbble.com/shots/26048547-ENERG-UI-UX-Design-for-Green-energy-ROI-calculator)
- [Dashboard Design Patterns](https://dashboarddesignpatterns.github.io/patterns.html)
- [Dashboard Design Trends 2025](https://rosalie24.medium.com/dashboard-design-trends-you-cant-ignore-in-2025-8c882f0328b5)
- [SaaS Design Trends 2026](https://www.designstudiouiux.com/blog/top-saas-design-trends/)
- [Micro-Interactions vs Animations](https://medium.com/@hashbyt/micro-interactions-vs-animations-saas-ux-conversions-927b9e5ac151)
- [Accessible Palette Tool](https://accessiblepalette.com/)
- [Forest Green Palette Reference](https://colorpalettegenerator.io/palette/forest-green-color-palette)
- [Design Tokens & Theming 2025](https://materialui.co/blog/design-tokens-and-theming-scalable-ui-2025)
- [USWDS Color Token System](https://designsystem.digital.gov/design-tokens/color/overview/)
