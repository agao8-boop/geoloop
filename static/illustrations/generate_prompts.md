# GeoLoop UI Illustration Generation Guide

These prompts are ready to paste into **Claude.ai** (claude.ai has built-in image generation).
After generating, run `make_transparent.py` to strip the background for UI overlay use.

---

## How to use

1. Open [claude.ai](https://claude.ai) in a new chat
2. Upload the source photo listed for each prompt
3. Paste the full prompt block
4. Download the result → save to `static/illustrations/generated/`
5. Run `python3 make_transparent.py <generated_file> <output_file>`

---

## ILLUSTRATION 1 — Site & Building pages (stage1a, stage1b, stage1c)
**Source photo:** `../gshp_grass.jpg`
**Skill:** `travel-photo-abstraction` (abstract distillation)
**Upload:** `gshp_grass.jpg` as Image 1, and these 3 refs as Images 2–4:
- `~/.claude/skills/travel-photo-abstraction/assets/style-references/memory-reference-011.png`
- `~/.claude/skills/travel-photo-abstraction/assets/style-references/memory-reference-017.png`
- `~/.claude/skills/travel-photo-abstraction/assets/style-references/memory-reference-016.png`

**Prompt:**
```
Use case: visual distillation for UI illustration
Asset type: abstract lower panel ONLY — do not reproduce the photograph

Image 1 is the USER-UPLOADED CONTENT SOURCE ONLY — a photograph of a commercial office
building campus. A 2-story white rectangular building sits at center foreground on a green
lawn. Eight to twelve varied-height white rectangular buildings form a backdrop. A uniform
row of round-crown trees separates the foreground from the background zone. Sky with gentle
cumulus clouds at top.
Images 2–4 are BUNDLED LOWER-PANEL STYLE REFERENCES ONLY. Match their abstraction
vocabulary, editorial quiet, and poetic negative space.

Core method: DECONSTRUCT → ABSTRACT/DISTILL → RECONSTRUCT — NEVER STYLE TRANSFER.

Deconstruction:
- Foreground building: solid dark rectangle, centered, dominant (~12% of motif width)
- Background array: 8 varied-height thin rectangles at consistent baseline in upper zone
- Tree row: 10 small dots at consistent height between zones
- Lawn: flat horizontal field, lower portion

Reconstruction:
- Foreground building → one solid near-black rectangle, 10% panel width, centered
- Background buildings → 8 thin hairline rectangles graduated in height, 42% panel width,
  positioned above and behind the foreground building baseline
- Tree row → 8 small filled near-black dots, consistent baseline
- Lawn → flat muted sage-green horizontal field, lower 22% of panel

Layout: compact motif, center of lower panel. Motif: 38% panel width, 25% panel height max.
80% of panel is empty neutral-ivory space (#F3F0E8).
Surface: CLEAN. Perfectly uniform flat neutral-ivory background (#F3F0E8). No gradient,
no vignette, no grain, no texture, no bands anywhere.
Color: muted sage/olive green for lawn only; near-black for all building + dot marks.
Text: generate NO text whatsoever.
Avoid: photograph, scene redraw, style transfer, gradient background, texture, watercolor,
3D, full illustration.
```

---

## ILLUSTRATION 2 — Results pages (result_1, result_final)
**Source photo:** `../gshp_underground.jpg`
**Skill:** `travel-photo-abstraction` (abstract distillation)
**Upload:** `gshp_underground.jpg` as Image 1, and refs as Images 2–4:
- `~/.claude/skills/travel-photo-abstraction/assets/style-references/memory-reference-009.png`
- `~/.claude/skills/travel-photo-abstraction/assets/style-references/memory-reference-017.png`
- `~/.claude/skills/travel-photo-abstraction/assets/style-references/memory-reference-013.png`

**Prompt:**
```
Use case: visual distillation for UI illustration
Asset type: abstract lower panel ONLY

Image 1 is USER-UPLOADED CONTENT SOURCE ONLY — a photograph showing a commercial building
campus above ground AND a cross-section of the underground geothermal U-loop borehole array.
Eight paired vertical pipe runs (blue cold-return, warm-red supply) descend from a horizontal
ground-cut line into three horizontal soil strata layers. A 2-story white building sits above
the ground line, centered.
Images 2–4 are BUNDLED LOWER-PANEL STYLE REFERENCES ONLY.

Core method: DECONSTRUCT → ABSTRACT/DISTILL → RECONSTRUCT — NEVER STYLE TRANSFER.

Deconstruction:
- Primary: 8 U-shaped pipe loops, each a pair of vertical hairlines + semicircle at base;
  equally spaced across 45% horizontal width; blue (#2563EB) cold and red (#DC4A26) warm
- Ground line: thin horizontal separator at ~38% height from panel bottom
- 3 soil strata: three muted earth-tone horizontal bars spanning full width below ground line
- Building: small dark rectangle above ground line, centered

Reconstruction:
- 8 U-loops → 5 paired vertical hairlines + tiny U-semicircles at bottom; 32% panel width;
  cobalt-blue (#2563EB) and warm-red (#DC4A26) alternating; grouped at panel center
- Ground line → one thin horizontal hairline at 38% from bottom
- 3 soil strata → 3 thin horizontal earth-brown bars below ground line
- Building → one small solid dark-gray rectangle (6% panel width) just above ground line, centered

Layout: motif at center. Total motif: 35% panel width, 26% panel height. 78% empty ivory.
Surface: CLEAN. Uniform #F3F0E8 everywhere. No gradient, no bands, no texture.
Color: cobalt blue and warm red on U-loop hairlines ONLY; muted brown/tan for soil bars;
near-black for building. No other colors.
Text: NO text.
Avoid same standard list.
```

---

## ILLUSTRATION 3 — Borefield page (stage2)
**Source photo:** the driller/auger B&W photo you attached in chat
**Skill:** `gc-minimal-zine-poster` (editorial minimal poster)
**Upload:** driller photo as Image 1 (no style refs needed for this skill)

**Prompt:**
```
Tall vertical 3:5 aged-paper canvas, full frame. 84% plain cream paper. One isolated compact
vertical specimen at center of canvas, occupying about 10–14% of canvas area. No border,
no mockup frame.

One imageable subject: a small halftone-softened photocopy fragment of an auger drill bit —
showing a central vertical shaft with five flat circular disc-flanges at regular descending
intervals, each flange slightly tilted at approximately 15°. The flanges decrease in diameter
from top (largest) to bottom (smallest), suggesting perspective foreshortening. Below the
lowest flange, a small solid dark circle represents the borehole mouth. The whole specimen
is rendered as a xerox-soft grayscale halftone on the aged paper, roughly 8% canvas width.

Typography: typewriter font, very small, "VERTICAL BORE" in near-black at lower-left corner.
Tiny DD MON YYYY date in same font below the phrase. Both lines extremely small and
unobtrusive. Accent: one small fully saturated cobalt-blue flat risograph-ink rectangle
overlapping the lower third of the drill silhouette, about 0.8% of canvas area, flat and
opaque. Subtle xerox grain and light scan noise throughout.

Flat scanned-paper appearance. Matte absorbent cream paper. Diffuse soft light. Quiet,
archival, industrial memory. Mood: solitude, depth, precision.
Avoid: full-bleed scene, commercial headline, product ad, glossy mockup, 3D rendering,
cinematic lighting, hard shadows, neon, cute cartoon, dense scrapbook, long clean text.
```

---

## ILLUSTRATION 4 — Site & Building (alternate / zine style)
**Source:** `../gshp_grass.jpg` uploaded
**Skill:** `gc-minimal-zine-poster`

**Prompt:**
```
Tall vertical 3:5 aged-paper canvas, full frame. 85% plain aged paper. One compact
architectural cluster at canvas center, occupying about 12% of canvas. No border.

One imageable subject: a simplified 2-story flat-silhouette rectangular building as a
near-black specimen at canvas center, slightly below center. Behind and above it: eight
varied-height thin near-black vertical rectangles representing a background building array
(tallest ~1.8× foreground building height). Below the foreground building: a narrow
horizontal flat fully saturated pear-green (#84B347) risograph-ink bar spanning 40% canvas
width, representing the lawn ground plane.

Typography: tiny serif/typewriter "SITE SURVEY" at upper-right in near-black. Optional tiny
date microtext below. Pear-green bar is the accent: fully saturated, flat, opaque, about
1.2% of canvas. Slight letterpress ink bleed on building silhouette edges. Aged paper
mottling and scan noise throughout.

Flat scanned-paper appearance, matte, quiet, archival, distant.
Avoid: full-bleed, commercial poster, product ad, logo, glossy, 3D, neon, cartoon.
```

---

## After generating: make transparent

Run this after saving each generated image:

```bash
python3 static/illustrations/make_transparent.py <input.png> <output_transparent.png>
```

The script removes the paper/ivory background and saves with alpha channel.
Then reference in HTML as: `<img src="/static/illustrations/<name>_transparent.png">`
