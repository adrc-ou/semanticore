# ComfyUI-side storage ledger

Ceiling: **150 GB total** for everything the deployment holds for this project —
models, inputs and outputs combined. That is a hard project limit, not a
per-environment guess: check free space before any multi-gigabyte fetch, stay
under the cap with room to spare, and prune as you go. One row per persistent
artifact; populate on the first session that uses ComfyUI (leave empty where the
capability gate says it is absent).

| path | size | class | terms | retention | last checked |
|---|---|---|---|---|---|
