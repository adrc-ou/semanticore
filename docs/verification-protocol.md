# Verification protocol — consensus loops

The agent is the driver; instruments are the ruler. This protocol turns
"trust the LLM" into something defensible WITHOUT piling on procedural
guardrails: every claim and every fix is validated by independent
agents that RE-DERIVE it from re-runnable evidence. Green checks never
substitute for triage; consensus never substitutes for looking (the
primary's job); re-derivation is what makes mistakes expensive to hide.

## Trust topology (read first)

| Channel | Owner | Why |
|---|---|---|
| Perception (reading scans, judging style/semantics) | MAIN agent only | Subagent windows fold under image load; folded agents hallucinate and livelock. Crops don't fix this and add selection bias (the primary framed the crop). |
| Measurement (geometry, text extraction, structure) | INSTRUMENTS, re-runnable | `pagecmp / validate_pdf / pdf_probe / scanctl / imgctl` convert the book into text that ANY agent can re-derive independently. |
| Verification (claims, fixes, DONE) | SWARMS — text-only | Verifiers re-run instruments and audit records. Cheap, parallel, safe with zero images. |
| Unresolvable disputes | OPERATOR via ISSUES.md | Genuinely perceptual disagreements do not get ground truth from instruments; escalate, don't grind. |

Practical rule: a verifier prompt contains file PATHS and CLAIM TEXT,
never image bytes, never the primary's scratch state, never a summary
of prior rounds. Fresh context or nothing.

## The loop (triage → fix → converge → checklist)

    triage ──► verify-claims ──► fix ──► verify-fixes
       ▲                                   │
       └────────── (next round) ◄──────────┘
                        │ round yields no new claims
                        ▼
          every CHECKLIST item closed ──► full re-validation of the list
                        │ an item fails, or a new gap appears
                        └──► back to triage (the gap becomes an item)
                        ▼
                       DONE  (§6)

**Done is not a feeling.** The primary may not declare completion; only the
book's checklist — adopted by consensus, closed item by item, then re-validated
in full — says so.

### 1. Triage (main agent)
Sweep the book against the defect categories (AGENTS.md). Record each
finding in `REVIEW.md` as a CLAIM row:

    C-<n> | page(s) | category | evidence pointer | claim text | state

State ∈ {unverified, confirmed, refuted, disputed, fixed-verified,
fixed-refuted, escalated}. Evidence pointer = the smallest re-runnable
check that shows it: a command (+args), a file region, an instrument
output line. A claim you cannot point at re-runnably is a HUNCH: mark
it hunch, and either find evidence or send it to ISSUES.md as a
question. No naked opinions enter the fix queue.

### 2. Verify-claims swarm (text-only)
For every `unverified` claim: spawn ≥2 independent verifiers (parallel
agents; different framings if you have them). Each verifier's task:

> Read <book>/REVIEW.md claim C-n. Independently re-derive the evidence
> pointer (run the instrument yourself — do not trust quoted output).
> Return exactly: VERDICT ∈ {CONFIRM, REFUTE, UNSURE} + your own re-run
> output excerpt + one sentence of reasoning.

All CONFIRM → `confirmed`. Any REFUTE → the primary does NOT argue; it
spawns ONE arbitration verifier with BOTH outputs visible (text only).
Arbitration REFUTE → claim dies (log it — a refuted claim is a finding
about your triage). Persistent split → `disputed` → ISSUES.md
(escalation), never silently dropped, never "fixed anyway".

### 3. Fix (main agent, single writer)
One claim or one coherent cluster at a time; model fixes, never guard
fixes (playbook). Record under the claim row: what changed, and the
re-run that proves the specific evidence pointer now shows the
OPPOSITE result (before/after pair). Engine output changes follow the
approved-drift ritual (selftest diff, reason, re-seize).

### 4. Verify-fixes swarm (text-only)
Two axes per fix, each independently re-derived:

- **Effectiveness**: does the claim's evidence pointer now pass?
- **Regression**: full instrument suite (validate_pdf incl. strict
  roundtrip + gates, pagecmp on touched pages, selftest if lib/bin
  changed) — output must be clean, and no OTHER page's pagecmp/claims
  may newly fail (scope drift is the classic partial-fix).
- **Side-effect audit**: verifiers get the fix description + the
  category list and hunt for collateral damage the primary didn't
  think to check (e.g., "spaces are copy" fixes must not break
  justified spacing; note-model fixes must not break the tree walk).

REFUTE on any axis → fix is REVERSED (git checkout / prior value — the
primary keeps fixes reversible by construction: one cluster per commit-
able step), and the claim re-enters the fix queue with the refutation
as new evidence. This retry loop is capped at 3 attempts per claim;
attempts must differ in HYPOTHESIS (what was learned from the last
refutation), not in effort. Cap hit → escalate.

### 5. Convergence
Loop 1–4 until a complete triage sweep (fresh eyes, whole book, all
categories) yields ZERO new confirmed claims AND no pending fixes; every new
confirmed claim is appended to the checklist as it lands. A
round that only produces refuted hunches still counts as progress —
log it.

### 6. DONE — the completion checklist, not a whole-book re-read

No verifier can judge "the whole book": a textbook is hundreds of pages, which
exceeds any subagent window, and an open-ended "is this done?" prompt earns an
agreeable answer. DONE is therefore granted by a bounded artifact on disk — the
book's `CHECKLIST.md` (shape in `books/TEMPLATE/CHECKLIST.md`) — and every
judgment stays small enough to re-derive.

1. **Draft (P0).** The primary writes the list from the operator brief, the
   defect categories, the phase gates, and its own first read of the book. One
   item = one falsifiable claim + its deciding evidence (a command and expected
   result, a stated page range for a visual check, or the record to be audited).
   Size items so one fresh agent can settle one in minutes: "nothing overflows,
   all 412 pages" is illegal; twelve items of ~35 pages each are legal.
2. **Adopt (consensus).** Verifiers audit **coverage**, not pages: is every
   applicable defect category present, every phase gate, every request in the
   brief, every ISSUES row? They mint missing items as claims; the primary adds
   them. Only then is the list official.
3. **Grow, never shrink.** Findings append items, each with the same coverage
   audit. Items are never deleted, merged away, or reworded to pass.
4. **Close per item.** Each closure runs the ordinary loop: independent
   verifiers re-derive that item's evidence. `visual` items are executed by the
   primary at the resolution the judgment needs and written into the row; on
   those, the swarm audits the *record* — page range fully covered, observations
   citing concrete pages, any numbers re-running — because verifiers never see
   images.
5. **Re-validate the whole list.** When every item is closed, the checklist is
   validated again in full: the primary re-reads each item and a consensus loop
   double-checks each one, in waves. A failing item reopens and the loop
   resumes; a gap found at this stage becomes a new item rather than a shrug.
6. **DONE** = every item `closed` by consensus + the full re-validation passed +
   the plain-English report to the operator. Anything the operator chooses to
   waive is recorded in their own words in the Waived section — agents cannot
   waive their own items.

Honest residue (unchanged): perception has one channel by design. A claim with no
text proxy is closed only as far as the primary's written observations cohere and
the operator's spot-checks reach. The checklist removes hiding places for errors;
it does not remove the primary's eyes from the critical path.

## Efficiency rules (anti-cycle-burn — the failure modes are known)

- NO agent re-verifies its own scratch state as a ritual. Verify = an
  independent consumer re-deriving, not the author re-checking.
- Verifiers are FRESH one-shot spawns for a bounded task, then
  discarded. Never "continue?" a verifier — that is how loops spin.
- Claims are small and falsifiable; big vague claims get decomposed at
  triage, not at verification.
- Parallelism is the default WITHIN a swarm wave (independent
  verifiers); it is banned for anything holding images, and for
  WRITING (single writer).
- Instruments earn their keep: every guard/check that fires must map to
  a claim category someone acts on; a check nobody's triage cites is
  cruft — delete it (operator standing concern: guardrail pile-up).
- Hunches are cheap to log and cheap to kill; the loop exists so you
  don't need to be right the first time — you need to converge.
