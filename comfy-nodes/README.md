# comfy-nodes — our own ComfyUI node packs

Source for packs this project maintains itself, versioned and reviewable here and
*copied* into the deployment's `custom_nodes/` directory to run. A pack earns its
place by doing something core nodes cannot; everything else belongs in a workflow
JSON.

| pack | needs | gives |
|---|---|---|
| `semanticore_control/` | nothing beyond ComfyUI core (stdlib) | `GET /semanticore/control`, `POST /semanticore/reboot` (guarded self-restart so node work is not blocked on a human every time), and the `SemanticoreImageStats` measurement node (luma/ink/edge/saturation stats as JSON text) |

## Install

    cp -r comfy-nodes/semanticore_control <comfyui mount>/custom_nodes/

Then it needs a process restart before it registers — see
`docs/comfyui-ops.md` §13 for the restart ladder and how to prove the pack
actually loaded from the path you used.

## Verify / remove

- loaded: `GET /object_info/SemanticoreImageStats` returns a schema (not `{}`), and
  `GET /semanticore/control` answers.
- reboot wiring, without rebooting: `POST /semanticore/reboot?preview=1` prints the exec
  plan it would use.
- remove: delete the directory from `custom_nodes/` and restart; no uninstall
  state is written anywhere.

## Rules these packs follow

- stdlib + what ComfyUI already requires; no pip installs, no network at import,
  nothing that costs money;
- destructive routes are guarded: explicit confirm header, content-type check
  against simple-form POSTs, idle-queue requirement unless `force=1`;
- measurement nodes are deterministic (fixed strides, rounded, sorted keys) so
  two runs over one file agree and the number is citable evidence;
- no pack here reaches outside the directories ComfyUI already exposes.
