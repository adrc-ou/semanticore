#!/usr/bin/env python
"""comfy_probe.py — ComfyUI capability gate. Stdlib-only, zero defaults.

The project makes no assumption about whether ComfyUI exists, where it lives,
or how it is reached: the harness declares that, per environment. This script
turns the declaration into a re-runnable verdict so every agent downstream can
re-derive it (docs/verification-protocol.md) instead of trusting a note, and so
"no ComfyUI here" is a clean, supported answer rather than a mysterious failure.

Verdicts (printed as `COMFYUI: <VERDICT>`; exit code in parentheses):
  AVAILABLE (0)     reachable, image I/O present, >=1 generative model loaded
  PARTIAL (1)       reachable, but restoration cannot run as designed
                    (no models, or required node classes missing)
  ABSENT (3)        nothing declared in this environment -> do not use ComfyUI
  UNREACHABLE (4)   declared but no usable answer (down / net / auth / proxy)
  (2)               configuration is ambiguous — several endpoint-like names
                    are declared and the probe cannot tell which one the
                    harness means; pass --url after re-reading the harness.

Discovery order: --url, then --from-json, then environment variables whose
NAME mentions comfy plus a location word (url/endpoint/host/port/addr). One
match is used; several require an explicit --url (names are listed, values are
not). A bearer token and TLS CA bundle are picked up the same way, from names
mentioning comfy+token / comfy+ca, and are never echoed.

Offline evidence (--from-json) accepts whatever the harness's own ComfyUI
tooling reports — a dict of node_class -> object_info entry, or a list of such
dicts — so a session that can only reach ComfyUI through a harness helper can
still produce the same verdict and the same ledger record.

  ./bin/comfy_probe.py --json | tee /tmp/agent-state/comfy-probe.json
  ./bin/comfy_probe.py --from-json snapshot.json
"""
import argparse, json, os, re, ssl, sys, urllib.error, urllib.request

# Node classes the restoration pipelines in docs/comfyui-ops.md are built on.
REQUIRED_NODES = ["LoadImage", "SaveImage", "ImageScale", "VAEEncode",
                  "VAEDecode", "CheckpointLoaderSimple", "KSampler",
                  "UpscaleModelLoader", "ImageUpscaleWithModel"]
OPTIONAL_NODES = ["LoraLoader", "ControlNetApplyAdvanced", "IPAdapterUnifiedLoader",
                  "InpaintModelConditioning", "VAELoader", "TextEncodeQwenImageEditPlus"]
# Loader class -> the input field that lists what is actually installed.
MODEL_FIELDS = {"CheckpointLoaderSimple": "ckpt_name", "UpscaleModelLoader": "model_name",
                "VAELoader": "vae_name", "LoraLoader": "lora_name", "UnetLoader": "unet_name"}

def _env(names):
    """First env var whose name matches pattern -> (name, value)."""
    for k in sorted(os.environ):
        if re.search(names, k, re.I):
            return k, os.environ[k]
    return None, None

def endpoint(args):
    if args.url:
        return args.url, "--url"
    # A name whose segments are exactly a qualifier (…_UI_URL, …_WEB_URL, …) is a
    # viewing link, not the API endpoint; those must never be probed as if they were.
    qual = ("ui", "web", "browser", "dash", "dashboard", "console", "viewer", "vnc")
    def loc(k):
        segs = [s.lower() for s in k.split("_")]
        if not re.search("comfy", k, re.I) or any(s in qual for s in segs):
            return None
        if re.search(r"url|endpoint", k, re.I):
            return "url"
        if re.search(r"host|addr|port", k, re.I):
            return "host"
        return None
    kind = {k: loc(k) for k in os.environ}
    hits = {k: os.environ[k] for k, v in kind.items() if v}
    urls = {k: v for k, v in hits.items() if kind[k] == "url"}
    if len(urls) == 1:
        return list(urls.values())[0], "$" + list(urls)[0]
    if len(urls) > 1:
        sys.stderr.write("comfy_probe: several endpoint-like variables declared (%s); "
                         "pass the one the harness means with --url. ABORT.\n"
                         % ", ".join("$" + k for k in sorted(urls)))
        raise SystemExit(2)
    hosts = {k: v for k, v in hits.items() if re.search("host|addr", k, re.I)}
    if len(hosts) == 1:
        _, port = _env("comfy.*port|port.*comfy")
        return "http://%s%s" % (list(hosts.values())[0], ":" + port if port else ""), "$" + list(hosts)[0]
    return None, None

def get(base, path, tok, ca, timeout):
    ctx = ssl.create_default_context(cafile=ca) if ca else ssl.create_default_context()
    req = urllib.request.Request(base.rstrip("/") + path)
    if tok:
        req.add_header("Authorization", "Bearer " + tok)
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
        return json.load(r)

def object_info(base, tok, ca, timeout):
    info = {}
    for cls in REQUIRED_NODES + OPTIONAL_NODES:
        try:
            info.update(get(base, "/object_info/" + cls, tok, ca, timeout) or {})
        except Exception:
            pass
    return info

def models_of(info):
    out = {}
    for cls, field in MODEL_FIELDS.items():
        req = (info.get(cls) or {}).get("input", {}).get("required", {}) or {}
        val = req.get(field)
        names = val[0] if isinstance(val, list) and val and isinstance(val[0], list) else []
        out[cls] = [n for n in names if isinstance(n, str)]
    return out

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", help="endpoint the harness declares (scheme://host[:port])")
    ap.add_argument("--from-json", help="node object_info snapshot from the harness's own tooling")
    ap.add_argument("--timeout", type=float, default=20.0)
    ap.add_argument("--json", action="store_true", help="emit the record as JSON")
    a = ap.parse_args()

    rec = {"verdict": None, "declared_by": None, "reachable": False, "auth": None,
           "tls_ca": None, "nodes_missing": [], "nodes_optional_present": [],
           "models": {}, "generative_models": 0, "note": ""}

    if a.from_json:
        raw = json.load(open(a.from_json))
        parts = raw if isinstance(raw, list) else [raw]
        info = {}
        for p in parts:
            info.update(p.get("nodes", p) if isinstance(p, dict) else {})
        rec["declared_by"] = "--from-json"
        rec["reachable"] = True
    else:
        base, src = endpoint(a)
        rec["declared_by"] = src
        if not base:
            rec["verdict"] = "ABSENT"
            rec["note"] = ("no ComfyUI endpoint declared by the environment; the harness is the "
                           "authority on whether ComfyUI exists here. Use the non-diffusion ladder "
                           "rungs (live text > vector > crop) — see docs/comfyui-ops.md §1.")
            print(json.dumps(rec, indent=1) if a.json else "COMFYUI: ABSENT\n" + rec["note"])
            return 3
        tk, tv = _env("comfy.*token|token.*comfy")
        ck, cv = _env("comfy.*(_|^)ca(_|$)|(_|^)ca(_|$).*comfy")
        rec["auth"] = "bearer $%s" % tk if tk else "none"
        rec["tls_ca"] = "$%s" % ck if ck else "system default"
        try:
            get(base, "/system_stats", tv, cv, a.timeout)
            rec["reachable"] = True
        except (urllib.error.HTTPError, urllib.error.URLError, OSError, ValueError) as e:
            rec["verdict"] = "UNREACHABLE"
            rec["note"] = "%s: %s (endpoint declared by %s; %s)" % (
                type(e).__name__, e, src, "credential material is never printed")
            print(json.dumps(rec, indent=1) if a.json else "COMFYUI: UNREACHABLE\n" + rec["note"])
            return 4
        info = object_info(base, tv, cv, a.timeout)

    rec["nodes_missing"] = [c for c in REQUIRED_NODES if c not in info]
    rec["nodes_optional_present"] = [c for c in OPTIONAL_NODES if c in info]
    rec["models"] = models_of(info)
    rec["generative_models"] = len(rec["models"].get("CheckpointLoaderSimple", [])) + \
        len(rec["models"].get("UnetLoader", []))

    if rec["nodes_missing"]:
        rec["verdict"] = "PARTIAL"
        rec["note"] = "node classes the pipelines need are not installed: %s" % ", ".join(rec["nodes_missing"])
        code = 1
    elif rec["generative_models"] == 0:
        rec["verdict"] = "PARTIAL"
        rec["note"] = ("reachable, and the graph machinery is there, but no generative model is "
                       "installed, so diffusion restoration cannot run. Image I/O, resizing and "
                       "any installed upscale model still work. Ask the operator/harness whether "
                       "models may be added; otherwise use the non-diffusion rungs.")
        code = 1
    else:
        rec["verdict"] = "AVAILABLE"
        rec["note"] = "restoration pipelines may run; confirm per-class capability with the harness tooling."
        code = 0
    if a.json:
        print(json.dumps(rec, indent=1))
    else:
        print("COMFYUI: %s" % rec["verdict"])
        print("  declared by : %s" % (rec["declared_by"] or "-"))
        print("  auth / tls  : %s / %s" % (rec["auth"] or "-", rec["tls_ca"] or "-"))
        print("  nodes       : %s" % ("all %d required present" % len(REQUIRED_NODES)
                                      if not rec["nodes_missing"] else "missing " + ", ".join(rec["nodes_missing"])))
        print("  extras seen : %s" % (", ".join(rec["nodes_optional_present"]) or "-"))
        for cls, names in rec["models"].items():
            print("  %-20s %d installed" % (cls, len(names)))
        print("  note        : %s" % rec["note"])
        print("  (record the verdict, never the endpoint, in project files)")
    return code

if __name__ == "__main__":
    sys.exit(main())
