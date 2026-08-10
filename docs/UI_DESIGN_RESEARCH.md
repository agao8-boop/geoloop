# GeoLoop UI Design Research — v2
_Updated after second design review. Grayed matcha primary system. Red/blue accent-only._

---

## 1. COLOR SYSTEM — Grayed Matcha Philosophy

### Why gray-down the matcha
GeoLoop communicates sustainability and engineering trust. Fully-saturated matcha reads as "health app" or "food brand". Desaturating the green by 60-75% shifts it toward Japanese wabi-sabi earthiness — quiet, professional, responsible. Red and blue are reserved as **small data-encoding accents only** (icons, dots, value text), not for large surfaces.

### Rule: accent-only for red and blue
- Red (`#c1314d`) and blue (`#2e4efe`) appear ONLY as:
  - Small colored dot (`8px`) before "Heating dominant" / "Cooling dominant" labels
  - Icon fill color (16-20px icons)
  - Data value text color inside a result row
  - Tiny badge/pill (max 24px tall)
- Never: buttons, card backgrounds, large fills, section headers

### Three grayed matcha variants (pick one for the whole app)

```
SAGE — HSL 82° 12% — most muted, almost stone gray
--sg1:  #f4f5f0   ← page bg option
--sg2:  #e0e2da
--sg3:  #c9cbc2
--sg4:  #b2b5ab
--sg5:  #9a9e94
--sg6:  #83877d   ← interactive default
--sg7:  #6b6f66   ← hover
--sg8:  #545750   ← anchor
--sg9:  #3c3f38
--sg10: #23261f   ← near-black

MOSS — HSL 82° 22% — balanced, earthy (RECOMMENDED)
--mm1:  #f2f5eb
--mm2:  #dce3cf
--mm3:  #c4cdb3
--mm4:  #aab897
--mm5:  #90a37c
--mm6:  #778c62   ← interactive default
--mm7:  #5f724e   ← hover
--mm8:  #48583b   ← anchor
--mm9:  #323e28
--mm10: #1b2214   ← near-black

FERN — HSL 83° 35% — most color, still muted
--fm1:  #f1f6e6
--fm2:  #d8e7c2
--fm3:  #bcd49e
--fm4:  #a0c17b
--fm5:  #84ad58
--fm6:  #6c9242   ← interactive default
--fm7:  #557434   ← hover
--fm8:  #3f5726   ← anchor
--fm9:  #293a18
--fm10: #131d0b
```

**Recommendation:** Use **Moss** for the full app. Sage is too close to pure gray. Fern is more expressive but still subdued.

### Warm grayscale (unchanged from v1)
```
--gray0: #faf9f7  --gray1: #f5f3f0  --gray2: #eeecea  --gray3: #e0ddd9
--gray4: #c8c4be  --gray5: #a09c97  --gray6: #7a7570
--gray7: #4a4540  --gray8: #2e2a26  --gray9: #1a1814
```

### Accent (keep from landing.html — used sparingly)
```
--red:  #c1314d  (heating, danger, key CTA only)
--blue: #2e4efe  (cooling, info, secondary link)
```

---

## 2. REACT BITS — Detailed Component Review

All components reviewed from source at github.com/DavidHDev/react-bits. Difficulty = effort to port to vanilla JS/CSS.

### A. Already implemented in GeoLoop (keep)
| Component | Type | Notes |
|---|---|---|
| **SpecularButton** | Animations | WebGL specular ring on button — already on welcome.html. Keep. |
| **SpotlightCard** | Components | Mouse-tracked radial glow. Already in design preview. |
| **StarBorder** | Animations | CSS rotating glow border on button. Easy to reuse. |

### B. High-value, easy to port (CSS + minimal JS)

| # | Component | Effect | GeoLoop use | Port complexity |
|---|---|---|---|---|
| 1 | **ShinyText** | CSS gradient shine sweep over text | Score label, section headings | Easy — pure CSS animation |
| 2 | **GlareHover** | Single glare sweep on hover | Stat cards in result_report | Easy — CSS `background-position` |
| 3 | **BorderGlow** | Gradient border appears on hover (mouse-edge proximity) | Result detail cards, save card | Medium — CSS + mouse tracking JS |
| 4 | **ElectricBorder** | CSS conic-gradient border rotates around card | Active/focused card highlight | Easy — CSS `@property` |
| 5 | **Counter / CountUp** | Number rolls up from 0 on enter | Score display, stat values | Medium — RAF loop |
| 6 | **AnimatedList** | List items stagger-enter on scroll | FAQ, feature list | Easy — IntersectionObserver |
| 7 | **FadeContent** | Fade + optional blur on scroll enter | Each section | Easy — IntersectionObserver |
| 8 | **Stepper** | Wizard progress rail | Top of onboarding wizard | Easy — CSS only |

### C. High-value, harder to port (needs canvas or GSAP)

| # | Component | Effect | GeoLoop use | Port complexity |
|---|---|---|---|---|
| 9 | **FuzzyText** | Canvas renders text with noise/fuzz, hover intensifies | Score "85" large display | Hard — canvas text rendering |
| 10 | **MagicBento** | Dark card grid, per-card particle glow on hover | Result overview grid | Medium — JS mouse tracking |
| 11 | **PixelCard** | Canvas pixel-dissolve reveal on hover | Result card reveal | Hard — canvas pixel scatter |
| 12 | **DecayCard** | SVG turbulence displacement on mouse move | Score card mouse interaction | Hard — SVG filter + GSAP |
| 13 | **GlassSurface** | SVG `feDisplacementMap` glass refraction | Modal overlay, panel | Hard — SVG filter |

### D. Background components (WebGL — use CSS approximations)

| # | Component | Effect | CSS approximation | Notes |
|---|---|---|---|---|
| 14 | **Threads** | 40 flowing Perlin noise lines | Canvas sine waves | Good match |
| 15 | **Topography** | WebGL contour elevation map | CSS repeating radial gradients | Approximate only |
| 16 | **DotGrid** | CSS dot grid + optional mouse glow | Exact CSS match | Easy |
| 17 | **Aurora / SoftAurora** | Animated radial gradient blobs | CSS `radial-gradient` + keyframes | Good match |
| 18 | **Particles** | Canvas floating connected dots | Canvas (already implemented) | Good match |

### E. Text animations (require GSAP SplitText — skip unless GSAP loaded)

| # | Component | Notes |
|---|---|---|
| 19 | **SplitText** | Per-character animate-in. Needs GSAP SplitText plugin. |
| 20 | **ScrambledText** | Mouse-proximity scramble. Needs GSAP ScrambleText. |
| 21 | **VariableProximity** | Font variation weight changes near cursor. Needs variable font. |

### F. Not recommended for GeoLoop (too decorative)
- **BlobCursor, GhostCursor, SwarmCursor** — distracting on a decision tool
- **LogoLoop, MetaBalls, MetallicPaint** — too heavy/visual for dashboard
- **TiltedCard** — needs webcam for ReflectiveCard; TiltedCard is playful, not tool-like
- **ChromaGrid** — portrait grid, wrong use case
- **DecayCard** — interesting but heavy; only if GSAP already loaded

---

## 3. COMPONENT VARIATIONS — Selection Matrix

For each UI component, show multiple options and pick one to implement.

### Score card
| Variant | Background | Number color | Use case |
|---|---|---|---|
| **A — Dark gradient** | mm10 → mm8 gradient | White | Main score display in result_report |
| **B — Sage surface** | --sg1 / --mm1 | mm8 | Embedded in wizard confirmation |
| **C — White outlined** | white | mm8 | Inside light sections |
| **D — Dark ink** | --gray9 | White | Landing.html aesthetic, dark hero |

### Stat/data card
| Variant | Style | When |
|---|---|---|
| **A — SpotlightCard dark** | Dark bg + mouse spotlight | Dark section, feature highlight |
| **B — GlareHover** | Gradient dark bg + glare sweep | Dark metrics grid |
| **C — Flat light** | White + moss left-border | Inside light wizard steps |
| **D — ElectricBorder** | Rotating CSS conic border | Active/selected item |

### Button
| Variant | Style | When |
|---|---|---|
| **A — Moss filled** | Background mm7, white text | Primary action |
| **B — Outlined moss** | Border mm6, mm7 text | Secondary action |
| **C — StarBorder** | Dark bg + rotating glow | Landing/welcome CTA only |
| **D — Ghost** | Transparent, mm6 text | Tertiary / destructive |
| **E — With red dot** | Outlined + small red dot accent | "New" or "Alert" badge |

### Form input
| Variant | Style | When |
|---|---|---|
| **A — Rounded, moss focus** | Border-radius 10px, focus glow mm3 | Standard inputs |
| **B — Underline** | No border, only bottom border | Compact/inline inputs |
| **C — Filled** | Slight mm1 bg fill | Dense data entry |

### Section header / eyebrow
| Variant | Style | When |
|---|---|---|
| **A — Text + rule** | Uppercase 10px + horizontal line | Standard section break |
| **B — Left accent bar** | 3px mm6 left border | Sub-section heading |
| **C — ShinyText** | Shine sweep animation | Landing / hero section label |
| **D — Red/blue dot** | Small colored dot prefix | "Heating load" / "Cooling load" labels |

### Background
| Variant | When |
|---|---|
| **A — Plain paper** (--gray1) | Wizard steps, form pages |
| **B — Dot grid dark** | Dark sections, hero bg |
| **C — Topography CSS** | Loading states, welcome bg |
| **D — Aurora blobs** | Intro / landing section |
| **E — Canvas particles** | Dark stats section |

---

## 4. ACCENT ICON USAGE PATTERNS

How to incorporate red/blue without making them dominant:

```
Pattern 1 — Data dot
  ● Heating load   148 kW    ← 8px red dot prefix
  ● Cooling load   112 kW    ← 8px blue dot prefix
  ● Balanced       N/A       ← 8px moss dot prefix

Pattern 2 — Icon fill
  [🌡 red icon] 148 kW peak heating
  [❄ blue icon] 112 kW peak cooling

Pattern 3 — Value text color only
  Heating Load   [148 kW ← red text]
  Cooling Load   [112 kW ← blue text]
  Score          [85 ← white/moss text]

Pattern 4 — Tag/pill with color
  [● Heating] [● Cooling] [● Balanced]
  pills with 4px colored left border only, gray background
```

---

## 5. ANIMATIONS PRIORITY (updated)

| Priority | Change | Effort | Notes |
|---|---|---|---|
| P0 | Grayed matcha tokens (Moss) in `design-tokens.css` | 1h | Foundation |
| P0 | Form field focus glow (CSS, mm3) | 20min | Immediate feel |
| P1 | CountUp on score number | 45min | First impression |
| P1 | FadeContent scroll reveal per section | 1h | IntersectionObserver |
| P1 | Factor bar fill animation | 30min | Score section |
| P1 | Score donut SVG (animated arc) | 1h | Replace static card |
| P2 | ElectricBorder on active/selected card | 1h | CSS @property only |
| P2 | ShinyText on score label or section eyebrow | 30min | CSS only |
| P2 | Stepper progress rail in wizard | 1h | CSS only |
| P3 | GlareHover on stat cards | 45min | CSS |
| P3 | Stagger list on results | 45min | JS |
| P4 | MagicBento result grid | 2h | JS mouse tracking |
| P4 | PixelCard on score card | 3h | Canvas — skip unless needed |

---

## 6. REACT BITS IMPLEMENTATION NOTES (vanilla JS ports)

### ElectricBorder — CSS @property conic gradient
```css
@property --angle {
  syntax: '<angle>';
  initial-value: 0deg;
  inherits: false;
}
.electric-wrap {
  padding: 1.5px;
  border-radius: 18px;
  background: conic-gradient(
    from var(--angle),
    transparent 20%, rgba(122,140,98,.7) 40%,
    rgba(193,49,77,.3) 55%,
    rgba(122,140,98,.6) 70%, transparent 80%
  );
  animation: elec 2.5s linear infinite;
}
@keyframes elec { to { --angle: 360deg; } }
```

### FuzzyText — canvas approximation
Core idea: draw text to canvas, then on each frame add random offset per character using `ctx.fillText(char, x + noise, y)`. Intensity ramps up on hover.

### VariableProximity — requires variable font
Only works if the loaded font has `wght` axis (Sora does: 300-800). Use `font-variation-settings: 'wght' ${weight}` updated via JS on mousemove.

### ShinyText — pure CSS
```css
.shiny {
  background: linear-gradient(90deg, var(--mm8) 30%, white 50%, var(--mm8) 70%);
  background-size: 250% 100%;
  -webkit-background-clip: text; -webkit-text-fill-color: transparent;
  animation: shine 3s linear infinite;
}
@keyframes shine { from { background-position: 150% 0 } to { background-position: -150% 0 } }
```

---

## 7. TYPOGRAPHY ADDITIONS

- **Sora** (existing, 300–800): UI text, labels, values
- **DM Serif Display** (from landing.html): welcome page hero only
- **JetBrains Mono** (existing): all numeric technical values

Font size scale: 10 / 11 / 12 / 13 / 14 / 17 / 22 / 28 / 36 / 48px

---

## Sources consulted (v2 additions)
- github.com/DavidHDev/react-bits — source code for all 165+ components
- landing.html — color tokens (#c1314d, #2e4efe, --ink, --paper)
- Japanese wabi-sabi color references for low-saturation green palettes
