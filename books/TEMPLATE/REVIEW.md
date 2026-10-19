# REVIEW ledger — <job-id>

Triage/consensus ledger per docs/verification-protocol.md. One row per
claim; verifiers append verdict lines under the row they checked.
Claim text must be a single falsifiable sentence; evidence must be
re-runnable (a command with args, or a file+region) — no naked
opinions. Keep rows after resolution (audit trail); never edit a
verifier's verdict line, append arbitration below it.

## Claim format

    C-<n> | page(s) | category | state | evidence | claim
    → verdict: CONFIRM|REFUTE|UNSURE — <re-run excerpt + one-line reason>

Categories: AGENTS.md "What to be alert for" (1–8).
States: unverified → confirmed|refuted|disputed|escalated; then
fixed-verified|fixed-refuted.

## Claims

(none yet)
