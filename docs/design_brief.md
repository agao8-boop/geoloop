# GeoSite Advisor — Design Brief

> Created: 2026-07-09. Update this file as the design evolves.

---

## Design Philosophy

**Core tension:** The asset is invisible. A building owner commits serious money to something 100 m underground they cannot see or touch. Every design choice answers one question: *How do we make invisible geology feel credible?*

**Design metaphor: Strata.** Geological cross-sections have clean, legible surfaces over enormous depth. The UI mirrors this — simple, approachable above the fold; deep methodology and data underneath.

**Design character:** Mission-control-adjacent. Satellite geology + premium SaaS. Serious, technical, but beautiful. Not a toy.

---

## Reference Inspiration

- **Grassfeld (grassfeld.com)** — hero composition: Mac + iPhone device mockup centered on dark background, bold editorial headline, ambient radial glow, minimal nav, single CTA.
- Awwwards: https://www.awwwards.com/sites/grassfeld#score
- Key takeaways:
  - Mac + iPhone at slight angle/float animation
  - Dark (#070D18-range) background
  - Single strong green/brand-accent CTA with glow box-shadow
  - Centered layout, headline + sub + CTA above devices
  - Stats bar beneath devices
  - Grain noise overlay for premium feel
  - Glassmorphism nav (backdrop-filter blur)

---

## Color Palette

| Token | Hex | Use |
|-------|-----|-----|
| `--bg` | `#070D18` | Page background — deep geological dark |
| `--surface` | `#0D1A26` | Cards, panels |
| `--surface-2` | `#102031` | Hover state, elevated surface |
| `--border` | `rgba(255,255,255,0.07)` | Default border |
| `--border-light` | `rgba(255,255,255,0.12)` | Stronger border |
| `--text` | `#F0F6FF` | Primary text |
| `--text-muted` | `#6B8299` | Secondary text |
| `--text-faint` | `#3D5166` | Disabled, placeholder |
| `--green` | `#10B981` | Primary accent — geothermal emerald |
| `--green-glow` | `rgba(16,185,129,0.15)` | Glow halos |
| `--green-soft` | `rgba(16,185,129,0.1)` | Badge backgrounds |
| `--amber` | `#F59E0B` | Warning, secondary accent |

**Tool (light theme):** Unchanged — `--bg: #f6f8fa`, `--accent: #0e7c5b`. The landing page uses a separate dark design system.

---

## Typography

| Role | Size | Weight | Notes |
|------|------|--------|-------|
| Hero H1 | `clamp(48px, 7vw, 88px)` | 800 | letter-spacing: -0.03em, line-height 1.0 |
| Section H2 | `clamp(32px, 4vw, 48px)` | 800 | letter-spacing: -0.02em |
| Badge/label | 11px | 700 | UPPERCASE, letter-spacing 0.08em |
| Body | 14–16px | 400 | line-height 1.6–1.65 |
| CTA button | 15–16px | 600 | — |

**Font:** `Inter` — existing Google Fonts load. No additional font dependency.

---

## Component Patterns

### Nav
- `position: fixed` with `backdrop-filter: blur(20px)` glassmorphism
- Logo left: `GeoSite` + `Advisor` (green)
- Links center: Features, Methodology, Dev Dashboard
- CTA right: pill button, green fill, "Open Tool →"

### Hero
- `min-height: 100vh`, flex column, centered
- Radial glow: `900px × 600px` radial at 30% vertical, `rgba(16,185,129,0.12)`
- Grain noise: SVG feTurbulence as `::before` pseudo-element, opacity 0.4
- Badge → H1 → sub → CTAs → devices → stats bar

### Device Mockup Composition
- Mac: CSS-only laptop frame, `max-width: 900px`, 16px border-radius lid, dark aluminum gradient
  - Screen: `aspect-ratio: 16/10`, shows mini-version of the tool's sidebar + form + result
- iPhone: `width: 180px`, `border-radius: 30px`, `position: absolute; bottom: -24px; right: -20px`
  - Shows feasibility score (74/100) + key stats
- Float animation: both devices animate with `translateY` loop (5s, 0.5s offset for iPhone)

### CTA Buttons
- Primary: `background: #10B981`, `color: #000`, `border-radius: 100px`, `box-shadow: 0 0 30px rgba(16,185,129,0.3)` glow
- Ghost: `border: 1px solid rgba(255,255,255,0.12)`, `color: var(--text-muted)`, hover lightens border

### Feature Cards
- 3×2 grid on desktop, stacked on mobile
- `background: var(--surface)`, `border: 1px solid var(--border)`
- `border-radius: 20px`
- Hover: border-color → `rgba(16,185,129,0.3)` + `translateY(-4px)`
- Icon: 44×44px emoji-in-container with green-soft background

### Stats Bar
- 4 stats: 3,221 counties · 100m depth · 7 stages · 379 tests
- Divided by `border-right: 1px solid var(--border)`
- Number: 24px, weight 800; label: 12px, text-muted

---

## Page Architecture

| URL | Template | Purpose |
|-----|----------|---------|
| `/` | `index.html` | Tool (original, unchanged) |
| `/landing` | `landing.html` | Marketing hero page |
| `/tool` | `index.html` | Tool (alias — for CTA links from landing) |

> **To make landing the homepage:** swap `/` to serve `landing.html` and `/tool` for `index.html`. Confirm with user before doing this.

---

## Open Questions / Next Steps

- [ ] Replace CSS device mockup screens with real screenshots once tool UI is stable
- [ ] Add scroll-triggered section fade-in animations (Intersection Observer, no lib needed)
- [ ] Add a brief "How it works" step section between hero and features
- [ ] Consider a `/why-gshp` page explaining geothermal fundamentals for non-engineers
- [ ] Mobile nav: hamburger menu for nav-links on < 768px
- [ ] Dark/light toggle for the tool itself (currently light-only)
- [ ] Testimonials / professor quote section once review feedback exists
- [ ] Optimize grain texture: replace SVG filter with a real PNG noise texture for crispness

---

## Files Changed

| File | Change |
|------|--------|
| `templates/landing.html` | NEW — marketing landing page with hero, features, footer |
| `app.py` | Added `/landing` route + `/tool` alias |
| `docs/design_brief.md` | NEW — this file |
