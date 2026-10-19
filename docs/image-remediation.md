# Image remediation — policy, restoration protocol, selection rubric

Restoration policy: diffusion restoration via ComfyUI is authorized for
degraded scans; accessibility wins ties; no creative embellishment; verify own
outputs; bounded attempts then choose-best-and-move-on. ComfyUI is an
*environment* capability: whether it exists here, and how it is reached, comes
from the harness, and the ladder's restoration rung applies only where the
capability gate (docs/comfyui-ops.md §1) says it does. Storage budget likewise
belongs to the project: a hard 150 GB ceiling over models, inputs and outputs
(docs/comfyui-ops.md §7).

## 1. Preserve-first ladder (apply top-down; descend only when the level
above cannot represent the content faithfully + accessibly)

1. **Live text**: anything readable as text in the source (labels, plate
   numbers, axis values, text on banners) → real tagged text in the PDF,
   never baked into an image. Artwork under it is restored with that text
   region excluded via mask (the hole gets background/line continuation
   only — no invented glyphs).
2. **Vectorizable line art** (simple diagrams): optional redraw path as PDF
   vector paths in an artifact-marked content sequence + Figure semantics;
   default remains image, redraw only when diffusion cannot hold geometry.
3. **Restored raster** (diffusion): halftone photos, plates, decorations,
   charts-as-art. Restore tone/line fidelity; kill scan damage (show-through,
   speckle, blur, banding, skew artifacts) — NOT the artwork's own style.
4. **Faithful crop** as-is when already clean enough (do no harm).

## 2. Fidelity rules (diffusion discipline)

- Match style + content of the source as closely as possible. Every
  restored element must be justifiable against the source crop ("visible
  or unambiguously implied"). No embellishment, no added objects, no
  "improved" faces/maps, no text substitution.
- Preserve composition: crop frame, aspect, margins, position, and the
  silhouette of the artwork (its non-rectangular outline matters for wrap —
  see §4). Halftone screens: preserve the ART, descreen to continuous
  tone (period dot patterns are print medium, not content); line screens
  stay sharp lines.
- Palette: derive from the source (imgctl measure); restoration may
  denoise/lighten but may not recolor outside the observed family.
- Handwriting/marginalia: excluded (per original brief) unless the book's
  own printed content (caption inside the art block = content, keep/restore).

## 3. Accessibility (non-negotiable, and it WINS ties)

- Every image = `/Figure` structure element: `/Alt` (concise identity+
  function, written from the verified restored image + source context),
  `/Lang en-US`, `/Placement /Block`, correct `/BBox`, MCID in reading
  order. Validators: validate_pdf --expect Figure=N; alt present enforced.
- Data figures (charts, graphs, diagrams with information): `/Alt` short +
  a **long description** as real adjacent text in the tree (visible
  caption if the book has one; else `P` "Description: …" immediately after
  the figure, in the Figure's Sect). Numbers transcribed accurately from
  the source — this is text work, not generation.
- Decorative-only art: `/Artifact /Type /Layout /Subtype /Decoration` (no
  tree node, no alt). Classify honestly: chapter openers/vignettes are
  usually semantic (set the tone = function) → Figure + brief alt.
- WCAG 1.4.3/1.4.6/1.4.11: body text over any image-derived background →
  effective contrast ≥ 4.5:1 (3:1 for ≥18.66px-equivalent "large"); UI-ish
  marks in figures ≥3:1. Remediation order: (a) restore the underlying art
  lighter/darker, (b) artifact background patch under the text zone (solid
  or matched, subtle), (c) document the deviation. The original's exact
  look yields to the rule; make the compromise tasteful.
- Reading order: figure bands sit between text lines exactly where printed;
  wraps preserve logical paragraph order (see §4); no content hidden
  behind images (z-order: backgrounds artifact-first, text last).

## 4. Wrap geometry (irregular text flow around illustrations)

Source truth is the LINE TABLE (playbook page model): the transcription
already records each line's true visual extent. Engine contract:
- `page["figures"]`: {id, bbox:[x,top,w,h] pt (from column box), shape
  "rect|silhouette", alt, longdesc?, class, src_crop, out_png, status}.
- `block["widths"]`: optional per-line available width (pt). Missing =
  full column. Transcription measures wrap indent per line from the scan
  (imgctl strips) → wrap replicates exactly, including tapered edges
  (approximate the silhouette with per-line min width; never less readable
  than source).
- `kind:"figure"` blocks consume ceil(h/pitch) grid rows when inline-band;
  side-by-side wrap uses widths instead (no figure block in the stream).
- Gate: rendered line table vs source strip — line ends must visually
  agree (checked in P6 montage); reading order gate: /Figure MCID position
  matches its printed position (validate_pdf + pdf_probe dump).

## 5. Restoration attempt protocol (bounded, logged — never a loop)

0. Gate: run `./bin/comfy_probe.py` this session (docs/comfyui-ops.md §1).
   Its verdict decides whether steps 2–5 below can happen at all; ABSENT or
   UNREACHABLE → skip to the fallback order (comfyui-ops §6) and ledger the
   verdict. Never assume the rung exists because a past session used it.
1. Prep: source crop (native res), palette/geometry measure, classify
   (rubric class), pick pipeline (comfyui-ops §5), note mask needs
   (text holes, wrap silhouette, gutter shadows to avoid).
2. Generate K=4 seeds/attempt-round. Each round: escalate TECHNIQUE once
   on a specific failure (mask tighter / controlnet weight / lower denoise
   / recursive edit on failing region), don't just re-roll seeds. The
   analogous budgets for *engineering* attempts — installs, custom nodes,
   novel pipelines, model hunts — are comfyui-ops §12: state what counts as
   working and what means stop, then pivot with a written note.
3. Verify EVERY candidate personally (ReadMediaFile native-res or contact
   sheet + objective pre-scores via imgctl score). Never accept unseen.
4. Score with rubric (§6): hard gates first (instant reject), then weighted
   score. If best ≥ accept threshold (default 1.6/2.0 weighted, all gates
   pass) → ACCEPT, discard siblings (ledger keeps the score record +
   chosen + one "best failure" for pattern learning until the book ships).
5. Else rounds 2–3 (max 3; ≈12 images). Still failing → pick highest-
   scoring + open ISSUES.md row with contact sheet path + question
   (e.g., "is the faint third signature authentic content?"). Escalate to
   user, don't grind past the cap.
6. Ledger EVERY figure: per-book `IMAGES.md` (imgctl
   ledger appends): id, class, source, rounds, per-candidate scores,
   chosen, notes, storage bytes.

## 6. Selection rubric (standardized, class-parameterized)

Machine-readable: `images/rubrics/base.json` + class overrides
(`images/rubrics/<class>.json`). Judge = agent (vision) with objective
pre-scores from `bin/imgctl.py score` as tie-breakers/evidence, never as
the verdict alone.

Dimensions (weights per class, each scored 0/1/2 with anchors):
- content_fidelity: elements, count, placement, poses vs source
- style_fidelity: period, medium, linework/hatching character, tonal curve
- artifact_absence: hallucinated detail, texture mush, halftone→plastic,
  seams, speckle kept, scan-bleed kept, extra text/glyphs
- geometry_preserve: crop, aspect, margins, silhouette/wrap boundary,
  straight lines straight, chart axis geometry unmoved
- legibility (text-in-figure class): surviving printed labels crisp & correct
- tone_color: palette distance within source family (objective-assisted)

Hard gates (instant reject regardless of score):
- invented content or missing source content
- wrong words/letters generated or lost where source is decisive
- aspect/crop change; silhouette changed so wrap/adjacency breaks
- style register error (photo→cartoon, engraving→flat vector)
- residual scan damage mistaken as content (or vice versa), when material

Final score = Σ w_d · s_d / Σ w_d ∈ [0,2]. Accept ≥1.6 + gates clean.
Tie-break: higher content_fidelity, then artifact_absence, then lower
denoise/less processed. Record the numeric sheet in IMAGES.md.

Class list (starter): lineart_diagram, halftone_photo, duotone_plate,
chart_figure, decorative_vignette, map_figure, text_on_art (special:
text-hole masking + contrast adjudication), mixed_page_element.
New class = copy base, reweight, add ≤3 class questions; commit to
images/rubrics/ with a line in the book STYLE-GUIDE.md.

## 7. What is NOT yet proven (mark of honesty)

- The restoration rung has never carried a real figure end to end: the gate
  and the transport are proven, model inventories and rubric weights are not
  (docs/comfyui-ops.md §8). Capability is environment-specific — the probe
  answers it per session, and "no ComfyUI here" is a normal answer, not a
  defect to route around.
- rubric weights are priors tuned from general practice; recalibrate per
  book in the ledger (note drift in STYLE-GUIDE, not here).
- The engine supports band-figures + per-line widths NOW (tested);
  silhouette-per-line wrap from a supplied mask map (imgctl wrapmap) is
  the only automated wrap path; anything fancier = human transcription.
