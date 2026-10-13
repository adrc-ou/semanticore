# ComfyUI operations (design — UNVERIFIED until the box exists)

Host: separate machine, ~80 GB VRAM, ComfyUI server + HF token provided.
Budget: ≤150 GB persistent storage on that host; clean up after yourself.
Everything here is a PLAN; the validate-on-arrival checklist (§6) upgrades
items to proven as they pass, and results get pinned into this file with
dates. Do not treat model names/versions below as verified facts — they're
a shortlist to check against current releases + licenses at setup time.

## 1. Connection contract

- Client exists: `bin/comfy_client.py` (stdlib-only; submit/history/view/
  upload; `--dry-run` + parameter-set paths are offline-tested; HTTP paths
  are UNTESTED). Confirm API shape on arrival; adapt there first.
- All generation is driven from WORKFLOW JSONs kept in `images/workflows/`
  (one file per pipeline, versioned in-repo, small). API prompts are built
  by parameter substitution into these saved workflows — never hand-built
  payloads, so every image is reproducible from (workflow, seed, inputs).

## 2. Model plan (shortlist; pick smallest sufficient; licenses must allow
   the user's use; prefer open-weight)

- Base img2img/inpaint: an SDXL inpainting-capable checkpoint and/or a
  FLUX-dev class model IF VRAM allows fp8 — decide by first benchmark.
- ControlNets: canny, lineart, tile, depth (union-style acceptable) —
  for line-art/diagram geometry lock.
- Adapters/cond: IP-Adapter (style/content reference from the source crop),
  attention masking via native inpaint nodes.
- Upscalers: Real-ESRGAN class + SwinIR class for 2–4x before detail pass;
  tile-based hires pass for >2048px page crops.
- Optional pretrained LoRAs ONLY (no training): e.g., halftone/descreen,
  engraving/pen-and-ink, aged-paper texture — justify each in the ledger;
  cap: what measurably beats base+controlnet on the rubric for this book.
- VAE/tile VAE for big images. Record every downloaded file + bytes in
  images/storage.md ledger (target steady-state ≤120 GB to leave headroom).

## 3. Pipelines by class (initial designs)

- lineart_diagram: crop → 2–4x upscale (SwinIR) → downsample to work res →
  ControlNet canny+lineart (high weight) + source as IP-Adapter ref →
  img2img denoise 0.30–0.45, tile hires pass → geometry verify (edge
  overlap gate) → if fail: MASK failing junctions, recursive edit round.
- halftone_photo: crop → descreen via upscale+blur target from source tone
  curve → img2img denoise 0.35–0.5, NO face/hand enhancement prompts;
  identity-preservation weighting; compare tone histogram to source.
- chart_figure: prefer NON-diffusion path: vector/labels rebuilt live +
  diffusion only for paper/ink texture underlay (masked), because rubric
  gate forbids any data-geometry drift. If diffusion must touch geometry:
  ControlNet from vector skeleton only.
- text_on_art: text pixels excluded via mask (live text covers them);
  inpaint holes with background continuation; contrast audit via
  `bin/imgctl.py contrast` on final PDF render, not on the raw asset.
- decorative_vignette / duotone_plate / map: per class rubric notes; maps
  get a toponym verification pass at native res before accept.

Recursive-edit pattern (all classes): accept-round → localize failing
regions via diff vs source (imgctl score --diffmap) → mask → second pass
at lower denoise on masked region only → rescore. Budget per protocol §5
of image-remediation.md.

## 4. Verification loop (non-negotiable)

Every candidate is viewed (contact sheets of ≤6 at native crops; full view
for finalists), scored on the class rubric with imgctl objective
pre-scores attached, and recorded in the book's IMAGES.md ledger before
anything is chosen. Chosen asset + workflow JSON + seed + scores are the
reproducible unit. Failed candidates pruned after accept (keep best
failure per figure until book ships, then prune to ledger refs only).

## 5. Storage hygiene

- images/storage.md: running table {host path, GB, class, retention}.
- Prune: intermediate upscales, per-round discards (after ledger), model
  shortlist rejects. Checkpoint dir only holds models referenced by kept
  workflows.
- Never store originals' full re-encodes; crops only.

## 6. Validate-on-arrival checklist (convert PLAN→PROVEN)

- [ ] server reachable, API shape matches §1; comfy_client.py written+tested
- [ ] GPU/VRAM confirmed; model size decisions made; licenses recorded
- [ ] controlnet canny/lineart/tile install + single-image smoke
- [ ] IP-Adapter node works with our ComfyUI version (or substitute)
- [ ] upscalers benchmarked on 300-dpi book crops
- [ ] one full line-art restoration + one halftone through the WHOLE loop
      (generate→verify→score→ledger) — these two calibrate rubric weights
- [ ] storage ledger initialized; cleanup hook proven
- [ ] text_on_art contrast audit path (imgctl contrast on rendered page)

Pin date + findings under "PROVEN LOG" at the bottom as each lands.

## PROVEN LOG
(empty — first contact pending)
