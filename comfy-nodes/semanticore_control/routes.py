"""HTTP control surface for the Semanticore workshop: status + graceful self-restart.

Stdlib only. Node registration happens while ComfyUI starts up, so an agent that
has just placed a pack in `custom_nodes/` needs one process restart to get it
loaded; this module is how every restart *after* that first one happens.

  GET  /semanticore/control          readiness + queue state (no side effects)
  POST /semanticore/reboot           replace the process in place (see guards below)
        ?preview=1           report what would run, do not restart
        ?force=1             allow reboot with a non-empty queue
        header X-Semanticore-Confirm: reboot   required, and blocks simple-form POSTs

The restart primitive is `os.execv(sys.executable, argv)`: same interpreter, same
arguments, new process, so no supervisor or shell access is required. It is
destructive to in-flight work, hence the idle-queue guard and the explicit
confirm header.
"""

import os
import sys

from server import PromptServer

routes = PromptServer.instance.routes

VERSION = "1.0"
CONFIRM_HEADER = "X-Semanticore-Confirm"
CONFIRM_VALUE = "reboot"
SIMPLE_FORM_TYPES = ("text/plain", "application/x-www-form-urlencoded",
                     "multipart/form-data")


def _json(payload, status=200):
    from aiohttp import web

    return web.json_response(payload, status=status)


def queue_state():
    """(busy, detail). Unknown queue state counts as busy — safer for a reboot."""
    try:
        running, pending = PromptServer.instance.prompt_queue.get_queue()
        return (bool(running or pending),
                {"running": len(running), "pending": len(pending)})
    except Exception as exc:  # pragma: no cover - depends on server internals
        return True, {"unknown": "%s: %s" % (type(exc).__name__, exc)}


def restart_argv(argv=None, executable=None):
    """The argv execv() needs, mirroring how the process was actually launched."""
    argv = list(sys.argv if argv is None else argv)
    executable = executable or sys.executable
    if argv and str(argv[0]).endswith("__main__.py"):  # launched as -m package
        module = os.path.basename(os.path.dirname(str(argv[0])))
        return [executable, "-m", module] + argv[1:]
    argv = [a for a in argv if a != "--windows-standalone-build"]
    return [executable] + argv


def reboot_plan(force=False, confirmed=False, content_type=""):
    """Decision for a reboot request: (allowed, http_status, body)."""
    if not confirmed or content_type.lower().split(";")[0] in SIMPLE_FORM_TYPES:
        return False, 403, {"status": "refused",
                           "reason": "missing or unconfirmed %s: %s header"
                                     % (CONFIRM_HEADER, CONFIRM_VALUE)}
    busy, detail = queue_state()
    if busy and not force:
        return False, 409, {"status": "refused", "reason": "queue not idle",
                            "queue": detail, "hint": "retry with ?force=1"}
    return True, 200, {"status": "rebooting", "queue": detail,
                       "argv": restart_argv(), "pid": os.getpid()}


def _do_exec():
    os.execv(sys.executable, restart_argv())


@routes.get("/semanticore/control")
async def control_status(request):
    busy, detail = queue_state()
    try:
        import folder_paths

        version = getattr(folder_paths, "COMFYUI_VERSION", None)
    except Exception:  # pragma: no cover
        version = None
    return _json({"loaded": True, "semanticore_control_version": VERSION,
                  "comfyui_version": version, "python": sys.version.split()[0],
                  "platform": sys.platform, "reboot_enabled": True,
                  "queue_busy": busy, "queue": detail})


@routes.post("/semanticore/reboot")
async def reboot(request):
    force = request.query.get("force", "") not in ("", "0", "false")
    preview = request.query.get("preview", "") not in ("", "0", "false")
    allowed, status, body = reboot_plan(
        force=force,
        confirmed=request.headers.get(CONFIRM_HEADER, "") == CONFIRM_VALUE,
        content_type=request.headers.get("Content-Type", ""))
    if not allowed or preview:
        if preview and allowed:
            body = dict(body, status="preview", would_reboot=True)
        return _json(body, status=status)
    import asyncio

    # Flush this response before replacing the process.
    asyncio.get_running_loop().call_later(0.5, _do_exec)
    return _json(body, status=200)
