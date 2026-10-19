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

## The loop (triage → fix → converge → final sweep)

    triage ──► verify-claims ──► fix ──► verify-fixes
       ▲                                   │
       └────────── (next round) ◄──────────┘
                        │ round yields no new claims
                        ▼
                  final-sweep swarm ──► consensus clean ──► DONE
                        │ any new finding
                        └──► back to triage

**Done is not a feeling.** The primary may not declare completion; only
final-sweep consensus says so.

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
categories) yields ZERO new confirmed claims AND no pending fixes. A
round that only produces refuted hunches still counts as progress —
log it.

### 6. Final-sweep swarm — the ONLY thing that grants DONE
≥3 independent finders, each with a distinct charter (structural
correctness / visual parity via pagecmp+record audit / content
verbatim via strict extraction + record audit / notes-navigation &
links), each starting from the shipped PDF + scan provenance records,
NONE told what previous rounds fixed (no anchoring). A finder that
reports no findings must list what it re-derived (commands run) — an
empty verdict without receipts is VOID, re-spawn.
Any NEW confirmed claim → back to step 1, the sweep restarts.
DONE = all finders verdict-clean WITH receipts + zero ISSUES rows
open + operator gets a plain-English report (AGENTS ground rules).
Honest residue: perception has one channel by design — a claim
category with NO text proxy (the feel of an emphasis system, an
unusual artifact) is verified only as far as the primary's recorded
observations cohere and the operator's spot-checks reach. The protocol
removes hiding places for errors; it does not claim to remove the
primary's eyes from the critical path.

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
