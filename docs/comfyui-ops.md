# ComfyUI operations — harness-first, environment-agnostic

ComfyUI is a general-purpose graph execution engine, not just a diffusion
button. The project treats it as standing instrumentation + generation capacity
whose value the agent is expected to invent: the image ladder's restoration rung
is only the most obvious use.

What lives where: whether ComfyUI exists, where it runs, and how it is reached
are facts about the *environment* and belong to the harness. What we ask it to
do, what we install into it, and how we prove the result are this project's
business, and they travel.

## 0. Who owns what

| Owned by the harness / operator | Owned by the agent (autonomy granted) |
|---|---|
| whether ComfyUI exists, endpoint, transport, auth, helper tooling | deciding *whether* ComfyUI is the right tool for a task at all |
| loading the **first** node pack in an environment: the restart that picks it up (every later restart is ours — §13) | placing/cloning packs into the deployment's custom-node directory, auditing their source, and rebooting the process once a control route exists |
| **Python packages for the server runtime** — usually outside the agent's filesystem reach | discovering, vetting, downloading and organising model *weights* (see §4.1) |
| the deployment's storage/compute/time budget and licence ceiling | designing and iterating workflows; authoring bespoke nodes when nodes are insufficient |
| policy disputes (is licence X acceptable, is this spend worth it) | running the gate, the budgets (§12), and the acceptance bar (§11) |

Precedence rule: **if this file and the harness disagree about how to talk to
ComfyUI, the harness is right.** Never commit an endpoint, token, helper-tool
path, host name, or capacity number here — that is the note that goes stale and
then misleads the next session (`docs/pitfalls.md` #58).

Two actions are *not* agent-side in practice and must be requested once, plainly,
then waited for: restarting ComfyUI so new node code loads, and adding a Python
package to the server's own environment. Requesting them repeatedly, or routing
around them by starting a second stack, is prohibited.

## 1. Capability gate — first command of any ComfyUI work, every session

    ./bin/comfy_probe.py            # human verdict
    ./bin/comfy_probe.py --json     # ledger-shaped record

- `AVAILABLE` — go.
- `PARTIAL` — reachable, but something is missing. **Read which.** Missing
  *weights* is the agent's own to-do (§4.1: provision them); missing *node
  packs* is a one-line request to the operator (§0); missing *capabilities* you
  did not expect is a research prompt, not a stop sign.
- `ABSENT` — supported configuration, not a failure. The ladder stops at
  `live text > vector > crop`, `bin/imgctl.py` carries the figure, and nothing
  gets installed or guessed. Ledger the verdict; open `ISSUES.md` for any figure
  that really needed the rung.
- `UNREACHABLE` — environment fault: report once with the probe output, fall
  back as for `ABSENT`, do not widen concurrency or start a parallel stack.

The gate is re-runnable evidence: verifiers re-run it instead of trusting the
transcript, and the verdict belongs in the book's `IMAGES.md`.

## 2. Establishing a new environment (ask the harness, then measure)

From the harness: reach, auth, helper surface, restart process, dependency
policy, declared budget. From the running server, without asking anyone: device
class and memory headroom (`stats`), installed node packs (§1 `--json` output),
installed weights per loader, version. Measure rather than remember — the answer
changes between sessions and proves nothing carried over.

### 2.1 The workspace `comfyui/` mount

When the harness provides ComfyUI it also adds a `comfyui/` directory to the
workspace, mapping onto the running deployment's own folders. It is untracked
(see `.gitignore`) — it is runtime state, not project content. It is the control
surface for everything file-shaped; the API is the control surface for
everything job-shaped.

| dir | what it is | how the agent uses it |
|---|---|---|
| `custom_nodes/` | installed node packs, one subfolder each | add/remove packs after reading their source (§10); discovered only at startup (§13) |
| `models/` | weight store, with class subfolders (`checkpoints/`, `vae/`, `upscale_models/`, `clip/`, `unet/`, `loras/`, …) | provision weights (§4.1); the running server sees new files without a restart |
| `input/` | where the upload route writes, and what `LoadImage` reads | place source crops here, or upload and use the returned name |
| `output/` | what `SaveImage` writes, and what the download route serves | read results; prune per §7 |
| `temp/` | transient/preview scratch | disposable; do not store anything you need |
| `user/` | per-user state: `default/` settings, `workflows/`, logs | keep a workflow here only when a human UI session needs to open it; never edit another user's state |

Prove the mapping before relying on it — write and observe from the server's
side (`docs/pitfalls.md` #61): upload through the API and look in `input/`, or
drop a placeholder under `models/vae/` and query that loader. Where the mount is
absent, nothing else changes: jobs still run through the API, but provisioning
becomes an operator action.

### 2.2 Discovering the server's Python environment (steps, not answers)

Node packs import into the *server's* interpreter, which is usually not the one
in this container. Never assume which is which, and never record what you find
here — that belongs to the session.

1. Ask the harness's tooling for system/device stats: the backend family (CUDA /
   MPS / ROCm / CPU) tells you which torch build the server actually uses.
2. Read the reported launch `argv`: listen/port, `--disable-auto-launch`, and
   the directory flags show where its code, models and user state really live.
3. Infer importable-from-the-box from `/object_info` (§1): a pack needs its deps
   already present, and what loaders exist bounds what you can address.
4. Look for an interpreter *identical* to the server's — a venv/conda dir or a
   ComfyUI checkout reachable through the mount. If found, read its `pyvenv.cfg`
   / `conda-meta` and its `site-packages` listing: that is the only dependable
   dependency census, and it is per-environment.
5. If no such interpreter is reachable (typical when the server runs outside the
   sandbox), dependency changes are the operator's: state the exact pin, request
   it once (§0), and prefer packs needing nothing beyond ComfyUI core.
6. Never install into an interpreter you have not proven is the one serving
   jobs, and never into a host machine's system interpreter.

## 3. Project-side invariants (true in every environment)

- Real generation runs from **API-format workflow JSONs** in `images/workflows/`
  — one file per pipeline, small, versioned; parameters are substituted into
  them, never hand-built per image. Reproducible unit = (workflow, seed, inputs).
- Source crops enter at native resolution; nothing is downsampled before the
  first look.
- Nothing generated is accepted unseen (§11).
- Structure stays structure: alt text, live text over art, and contrast audits
  live in the PDF, never in pixels; contrast is measured on the rendered page.
- Anything the engine learns about the deployment goes in the session, not the
  repo; anything it learns about *method* goes in this file.

## 4. Model plan — capabilities, not product names

Ask for classes and take what the deployment can run — no licence ceiling
exists for this project (it is MIT-licensed, and acquiring whatever tool helps is
in scope), with one hard rule: **nothing that requires payment.** No paid
software, no per-seat licences, no trials, no metered API calls on someone's
bill. Free tiers that need no purchase are fine if their terms allow this use.
Prefer the smallest thing that clears the rubric: an image-to-image / inpainting generative model; a structure-control
mechanism (edge/line/depth conditioning, or an instruction-editing model); a
style/content reference mechanism; an upscale mechanism; optional pretrained
adapters for recurring media in the book at hand (halftone/descreen, engraving,
aged paper). Model *size* is chosen from what §2 measured, never from a
remembered spec.

### 4.1 Provisioning weights autonomously

Agents are expected to obtain their own models rather than report them missing.
The mechanical shape (re-prove it per environment — it is a property of the
deployment, not of this file):

1. Confirm the deployment's model root is agent-writable: write a temp file
   under the mapped `models/` tree, then check whether it appears in a loader's
   live listing. On a mapped mount, ComfyUI rescans weight folders at query
   time — a dropped file shows up in seconds with no restart. (Code is
   different: custom nodes load only at startup.)
2. Discover candidates from primary sources: the Hub's public search/metadata
   API, the model card, the upstream repo, and the ComfyUI registry/templates —
   unauthenticated for public data. Web research is expected when the right tool
   for a media class is not obvious.
3. Vet before fetching: terms allow this use and cost nothing (no paid
   software, no trials, no metered endpoints — §4); the architecture matches a
   node that actually exists in this install; the file size fits inside the
   remaining storage ceiling; provenance is the canonical repo, not a re-upload
   of unclear origin.
4. Fetch with integrity: preflight the byte count, resume on failure, verify a
   checksum (upstream-provided, or record one yourself at first fetch so later
   sessions can detect drift), place it in the correct class subfolder, and
   re-query the loader listing to prove the server can see it.
5. Ledger it in `images/storage.md` (path, size, class, terms, retention) and
   record the (repo, revision, file) provenance in the book's `IMAGES.md`
   alongside the workflows that use it. Prune anything no kept workflow
   references.
6. Gated repositories need a human, and only when they are actually needed.
   Provision from ungated sources first; when a specific gated artifact is the
   right tool and no credential is present (`hf auth whoami` errors), pause
   *that item*, keep working everything else, and ask the operator to open a
   shell in the container and run `hf auth login` themselves — never ask them to
   paste a token, and never read, print, copy or commit one. Then wait for their
   confirmation, re-check with `hf auth whoami`, record the verdict, and resume
   the fetch exactly where it stopped: keep the pending repo, revision, file,
   checksum and destination in the session notes or the book's IMAGES.md so the
   pause costs nothing to pick up. Expect to ask again after a container rebuild
   (the token file defaults to a home cache that may be tmpfs); a `HF_HOME` or
   `HF_TOKEN` pointed at persistent storage is the operator's choice to make it
   stick. If the operator is unavailable and an ungated equivalent clears the
   rubric, take it — the goal is the finished book, not the credential.

A weight you cannot vet, fetch, or load is a `PARTIAL` finding to record and
route around under §12, not a reason to stall the book.

## 5. Pipelines by class (starting recipes; invent better ones)

- `lineart_diagram`: crop → upscale → work resolution → structure control at
  high weight + source as reference → img2img at low denoise (0.30–0.45) →
  edge-overlap geometry gate → on failure mask the failing junctions and recurse.
- `halftone_photo`: crop → descreen toward the source tone curve → img2img
  0.35–0.50, identity-preserving, no face/hand "enhancement" → tone histogram vs
  source.
- `chart_figure`: prefer the **non-diffusion** path (labels and axes rebuilt
  live/vector; generation only for a masked paper-or-ink underlay) — the rubric
  gate forbids data-geometry drift. If generation must touch geometry, drive it
  from the vector skeleton alone.
- `text_on_art`: mask text pixels out (live text covers them) → fill holes with
  background continuation → contrast audit on the rendered page.
- `decorative_vignette` / `duotone_plate` / `map_figure`: per class rubric notes;
  maps additionally get a toponym verification pass at native res.

Recursive-edit pattern: accept-round → localise failing regions by diffing
against the source (`imgctl score --diffmap`) → mask → second pass at lower
denoise on the masked region only → rescore.

## 6. When a capability is missing

Degradation order, chosen so a book never stalls on an absent integration: full
recipe → drop the optional mechanism (reference/adapter/LoRA) and keep what is
installed → obtain what is obtainable (§4.1) → drop generation entirely and
rebuild the figure on the vector/live-text rungs → ship the best-scoring
candidate with an `ISSUES.md` row naming what could not be attempted. Record
which rung you landed on so a later session can tell what to redo.

## 7. Storage hygiene — hard 150 GB ceiling

Project-wide cap: **everything this deployment holds for us — models, inputs,
outputs — stays under 150 GB.** That is a ceiling, not a target: leave headroom,
check free space before any fetch (weights are gigabytes each), and treat the
ledger as the enforcement mechanism, since nothing downstream will stop us for
you. `images/storage.md` counts persistent artifacts (path, size, class,
licence, retention). Prune aggressively and continuously: intermediate upscales
and per-round discards right after ledgering, weights no retained workflow uses,
and full re-encodes of originals (keep crops instead). Cleanup is part of the
job — an unbounded artifact set on a shared host is someone else's outage.

VRAM is *not* a budget to enforce from here: use what the machine gives, let
ComfyUI and the host OS do their own paging and eviction, and only react to an
actual failure the run reports.

## 8. Per-environment checklist

- [ ] gate run this session; verdict + `--json` in `IMAGES.md`
- [ ] transport/auth confirmed from the harness (not from this file)
- [ ] accelerator class and free storage measured from the running deployment
- [ ] node and weight inventory read; gaps either provisioned (§4.1) or escalated once
- [ ] upload → run → fetch round trip proven with a throwaway workflow
- [ ] one full line-art restoration and one halftone through the whole loop
      (generate → verify → score → ledger); these two calibrate rubric weights
- [ ] `text_on_art` contrast audit proven on a rendered page
- [ ] storage ledger initialized; cleanup hook proven

Nothing on this list is inherited from a previous session, and none of it is
closed project-wide yet: the two calibration runs (one line-art restoration and
one halftone, end to end) have never been performed, so every rubric weight in
`images/rubrics/` is still a prior, not a measurement.

## 9. Non-diffusion uses — experiment deliberately

Generation is one use of a graph engine, not the whole of it. Consider it as
batch, reproducible, node-composable image machinery: mask construction and
boolean region algebra; compositing and silhouette/wrap derivation; colour and
tonal transforms measured against source curves; geometric corrections (dewarp,
perspective, crop-register); tile pyramids and multi-resolution exports; format
and bit-depth normalisation for the PDF writer; scan-chain diagnostics rendered
as visible overlays (edge maps, ink coverage, registration marks) that make a
page's defects legible to the reviewer; and **measurement nodes that emit
numbers** — a node that outputs statistics into the history JSON is an
*instrument* in the protocol sense, whose evidence any verifier can re-run.
Novel pipelines are in scope; the acceptance bar is unchanged, and the cost of a
failed experiment is bounded by §12. Prefer a boring graph you can reproduce over
a clever one you cannot.

## 10. Custom nodes: write them, but read them first

Existing nodes are the default; authoring a node is legitimate when the task is
real and the machinery is genuinely missing (an unusual measurement, an
odd-format export, a book-specific region algebra). Modify an existing pack only
in targeted, minimal ways and keep the provenance; prefer a small own node over
forking a large one. Because node code is executable: audit the source and its
dependency metadata before it is loaded, pin exact versions, and treat a third-
party pack as untrusted input. New or changed node code needs the operator's
restart to load (§0) — so batch node work into one request rather than a
drip, and keep workflows that depend on unloaded nodes out of `images/workflows/`
until they run.

## 11. Acceptance bar — every ComfyUI output gets looked at

Nothing an engine produced is accepted on the strength of the graph that
produced it, and that includes non-generative outputs: a mask, a composite, a
deskew, an upscale, a crop-register correction, or a number emitted by a
measurement node all get read by a multimodal agent at the resolution the
judgment requires, against the source. Diffusion output additionally goes through
the class rubric with its hard gates first (`docs/image-remediation.md` §6).

Perception and consensus have different channels here, and both are mandatory:

- **Eyes:** the primary (or another multimodal reviewer, or the operator for a
  genuine dispute) is the only one who looks. Subagent contexts carry no images,
  ever (`docs/pitfalls.md` #57).
- **Text:** the looking must be *written down* — file paths, what was compared,
  the objective pre-scores (`imgctl score`, tone histogram, edge overlap), the
  gate outcomes, the verdict — so that it becomes a claim others can attack.
- **Consensus loop applies unchanged.** ComfyUI work is triage → claim → fix →
  converge, not a side activity: independent verifiers RE-DERIVE the claim by
  re-running the probe, the workflow submission, the instruments and the ledger
  audit; a "the graph said success" line is never a finding; a multi-round
  experiment, a model choice, a node authoring decision, and every accepted
  asset all enter that loop, and the book's checklist re-validation re-checks the image
  claims with the same scepticism as the text claims. Skating the loop because
  the work felt exploratory is the failure mode this section exists to name.

## 12. Attempt budgets and getting out of the way

The point of remediation is the finished book, not the defeated experiment.
Before starting anything with a cost (a download, a training-free pipeline, a
custom node, a model hunt), state in one line what would count as working and
what would mean stop. Then:

- **Bounded attempts.** Generative figures: the existing protocol (4 seeds ×
  ≤3 rounds, escalating *technique*, not luck). Installs and downloads: 3 tries
  per artifact with a diagnosed change between them (different source, mirror,
  revision, size class) — a fourth identical retry is prohibited. Bespoke node
  or novel pipeline: timebox the spike, and prefer proving it on one figure
  before generalising it to a class.
- **Recognise stuck.** Repeated `PARTIAL` on the same cause, the same error
  twice after "fixing" it, consensus failing on the same claim twice, or the
  best score moving the wrong way across rounds = stuck, whatever your
  confidence says.
- **Cost of persistence is not paid from the book's main goal.** If an
  experiment is consuming the turns a page still needs, it has already failed
  even if it might have succeeded.
- **Back out cleanly.** Record a pivot note in `ISSUES.md` (or the book's
  `IMAGES.md` for a figure): hypothesis, what was tried with the evidence
  pointers, what was ruled out, the fallback rung taken, and what a future
  session should try instead. Prune the dead experiment's artifacts and unload
  the things it needed. A pivot is a completion, not a defeat — shipping a
  slightly-less-restored figure with an honest row beats shipping nothing after
  eleven hacks.
- **Never** weaken a gate, a rubric threshold, a validator, or a verifier to let
  an experiment pass. Lower the ambition, not the bar.

## 13. Getting new node code loaded — the restart problem

Custom nodes are imported once, while ComfyUI starts. Core serves no route that
reloads them and no route that restarts the process — established by enumerating
the served route surface and the shipped frontend bundle, whose restart control
is wired to a *node pack's* route, not to core. Consequence: the first node-pack
install in an environment costs one human restart, and everything after that is
agent-driven, because whatever restarts ComfyUI is itself a loaded pack.

Order of preference:

1. **A control route already answers.** `GET /semanticore/control` — this project's own
   `comfy-nodes/semanticore_control` pack (stdlib-only, no dependencies) — reports
   version, queue state and whether reboot is enabled. To restart: confirm the
   queue is idle (`GET /queue`), `POST /semanticore/reboot?preview=1` to see the exact
   exec plan, then `POST /semanticore/reboot` with the `X-Semanticore-Confirm: reboot` header,
   and re-probe after a pause.
2. **ComfyUI-Manager**, if its routes answer (`/v2/manager/reboot`, and its
   registry/model/snapshot install routes). Prefer it whenever the job is more
   than restarting — it installs packs and models server-side. Its own Python
   dependencies have to exist in the *server's* environment, which §2.2 shows how
   to probe; whether they do is answered empirically by whether its routes come
   up after a restart.
3. **Nothing answers.** Place the pack (§13 "where to place", below), then ask
   the operator for the single restart: one request, with the reason and a note
   that the queue is idle. Do not poll, do not re-ask, do not start a second
   server in the meantime — carry on with the non-node work.

Placement is an environment fact, not a repo fact. The harness maps
`comfyui/custom_nodes`, but whether the *running* server imports from that path
must be proven after the restart: look for the pack's marker node in
`GET /object_info/SemanticoreImageStats`, and read the startup log (`GET
/internal/logs/raw` on deployments that serve it, otherwise the operator's
console), which names the directories it scanned and prints import failures. If
the marker is absent, hand the operator the log line naming the import directory
and ask for the pack to be moved there — one request, same rule as above.

Restart hygiene — it is a shared process, so:

- idle queue first; a reboot kills in-flight jobs and anything held only in RAM
  (history and outputs are on disk and survive);
- treat the dropped connection as expected, re-probe once after a pause instead
  of hammering retries;
- if the goal is memory rather than new code, `POST /free` unloads models with no
  restart at all;
- the reboot route is privileged: call it only as part of node work you are
  actually doing, and say so in the session notes, because it interrupts anyone
  else using that server.

