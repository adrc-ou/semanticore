"""semanticore_control — control + measurement pack for the Semanticore remediation workshop.

Why a pack is needed at all: ComfyUI registers custom nodes only while it starts
up and core serves no route that reloads them or restarts the process, so an
agent that has just dropped a pack into `custom_nodes/` cannot get it loaded on
its own. This pack supplies that missing control channel using only the standard
library plus what ComfyUI already requires — there is nothing to pip-install, so
loading it costs one process restart and nothing else.

It provides:
  GET  /semanticore/control      — is the pack loaded, and what does it allow
  POST /semanticore/reboot       — graceful self-restart (queue must be idle, or force=1)
  POST /Semanticore/reload_nodes — best-effort in-process rescan (no restart; limited)
  node SemanticoreImageStats     — image-region measurements emitted as JSON text, so a
                           graph can produce re-runnable numeric evidence

Route registration follows the documented extension point used by node packs
(`PromptServer.instance.routes`). Importing this module outside a running server
is safe: the routes simply do not register.
"""

__version__ = "1.0"

NODE_CLASS_MAPPINGS = {}
NODE_DISPLAY_NAME_MAPPINGS = {}

try:  # real import when ComfyUI is importable
    from .nodes import SemanticoreImageStats

    NODE_CLASS_MAPPINGS["SemanticoreImageStats"] = SemanticoreImageStats
    NODE_DISPLAY_NAME_MAPPINGS["SemanticoreImageStats"] = "Semanticore Image Stats (JSON)"
except Exception as exc:  # pragma: no cover - only hit without torch/server
    import logging

    logging.warning("semanticore_control: SemanticoreImageStats unavailable (%s)", exc)

try:
    from . import routes  # noqa: F401  (registers the HTTP control surface)
except Exception as exc:  # pragma: no cover - headless import / no server
    import logging

    logging.warning("semanticore_control: control routes NOT registered (%s) — "
                    "GET /semanticore/control will 404", exc)

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS", "__version__"]
