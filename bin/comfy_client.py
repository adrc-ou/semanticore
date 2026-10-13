#!/usr/bin/env python
"""comfy_client.py — THIN ComfyUI API client. UNTESTED: no server yet.

Validate on arrival (docs/comfyui-ops.md §6) before real use.
Stdlib-only. Subcommands:
  submit WORKFLOW.json --set node.FIELD=VALUE ... [--out DIR]
  history [PROMPT_ID]        poll/list
  view PROMPT_ID NODE        fetch a produced image to --out
  upload IMAGE               register an input image, print its upload name
Env: COMFY_HOST (default 127.0.0.1), COMFY_PORT (default 8188).
Workflow JSON = ComfyUI saved format ({"nodes":[...],"links":[...]} OR the
API prompt map {node_id:{class_type,inputs}}). `submit` auto-detects the
API-prompt form; for graph form, convert in the UI and export API format.
"""
import argparse, json, os, sys, urllib.request, urllib.parse, uuid

def _url(path): return "http://%s:%s%s" % (os.environ.get("COMFY_HOST","127.0.0.1"),
                                           os.environ.get("COMFY_PORT","8188"), path)
def _get(path):  return json.load(urllib.request.urlopen(_url(path), timeout=60))

def _post_json(path, obj):
    data = json.dumps(obj).encode()
    req = urllib.request.Request(_url(path), data=data,
                                 headers={"Content-Type":"application/json"})
    return json.load(urllib.request.urlopen(req, timeout=60))

def _prompt_map(wf):
    if isinstance(wf, dict) and "nodes" in wf:
        sys.exit("workflow is UI-graph format; export API format (curl examples "
                 "in ComfyUI) or apply node->inputs flattening here. ABORT.")
    return wf

def apply_sets(pm, sets):
    for spec in sets:
        node, rest = spec.split(".", 1)
        field, val = rest.split("=", 1)
        cur = pm[node]["inputs"]; parts = field.split(".")
        for p in parts[:-1]: cur = cur[p]
        try: cur[parts[-1]] = json.loads(val)
        except Exception: cur[parts[-1]] = val
    return pm

def main():
    ap=argparse.ArgumentParser(); sub=ap.add_subparsers(dest="c",required=True)
    sm=sub.add_parser("submit"); sm.add_argument("wf"); sm.add_argument("--set",action="append",default=[])
    sm.add_argument("--client-id",default=uuid.uuid4().hex); sm.add_argument("--dry-run",action="store_true")
    hi=sub.add_parser("history"); hi.add_argument("pid",nargs="?")
    vw=sub.add_parser("view"); vw.add_argument("pid"); vw.add_argument("node")
    vw.add_argument("--out",required=True); vw.add_argument("--subfolder",default="")
    vw.add_argument("--filename",default="output.png"); vw.add_argument("--type",default="output")
    up=sub.add_parser("upload"); up.add_argument("image")
    a=ap.parse_args()
    if a.c=="submit":
        pm=_prompt_map(json.load(open(a.wf)))
        if a.set: pm=apply_sets(pm,a.set)
        if a.dry_run: print(json.dumps({"prompt":pm},indent=1)[:1500]); return 0
        r=_post_json("/prompt", {"prompt":pm,"client_id":a.client_id})
        print(json.dumps(r)); return 0
    if a.c=="history":
        print(json.dumps(_get("/history/"+(a.pid or "")))); return 0
    if a.c=="view":
        q=urllib.parse.urlencode({"subfolder":a.subfolder,"filename":a.filename,"type":a.type})
        with urllib.request.urlopen(_url("/view?"+q),timeout=120) as f, open(a.out,"wb") as g:
            g.write(f.read())
        print("saved",a.out); return 0
    if a.c=="upload":
        import mimetypes
        boundary=uuid.uuid4().hex; fn=os.path.basename(a.image)
        body=b""
        body+=("--%s\r\nContent-Disposition: form-data; name=\"image\"; "
               "filename=\"%s\"\r\nContent-Type: %s\r\n\r\n"
               % (boundary,fn,mimetypes.guess_type(fn)[0] or "image/png")).encode()
        body+=open(a.image,"rb").read()
        body+=("\r\n--%s--\r\n"%boundary).encode()
        req=urllib.request.Request(_url("/upload/image"),data=body,
            headers={"Content-Type":"multipart/form-data; boundary="+boundary})
        print(json.load(urllib.request.urlopen(req,timeout=120))); return 0

if __name__=="__main__": sys.exit(main())
