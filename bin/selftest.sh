#!/usr/bin/env bash
# Workshop self-test — run after ANY lib/ or bin/ change.
# Anchored on books/canary: a SYNTHETIC fixture exercising every engine path
# (continuation/indents, run-in heading, list+disc, soft & real hyphens,
# Em/Strong/E spans, band/float/artifact figures, wrap widths, collision
# guard). No document content lives in the repo or this harness.
#
# Intentional, approved engine-output changes: inspect the stream diff, then
#   ./bin/selftest.sh --update-goldens   (and say WHY in the commit message)
# NEVER re-seize to silence an unexplained failure.
set -e; cd "$(dirname "$0")/.."
K=books/canary
[ -x venv/bin/python ] || { echo "missing venv: run bin/setup_env.sh"; exit 1; }
SEMANTICORE_HOME=$PWD ./venv/bin/python $K/build.py >/dev/null
SEMANTICORE_HOME=$PWD UA_PART=1 ./venv/bin/python $K/build.py >/dev/null
export UPDATE="${1:-}"
./venv/bin/python - <<'PY'
import pikepdf, hashlib, json, os
gf = "books/canary/golden_streams.json"
cur = {}
for tag, f in (("ua2", "books/canary/out/canary.pdf"),
               ("ua1", "books/canary/out/canary-ua1.pdf")):
    p = pikepdf.open(f)
    cur[tag] = [hashlib.sha256(pg.Contents.read_bytes()).hexdigest()
                for pg in p.pages]
if os.environ.get("UPDATE") == "--update-goldens":
    old = json.load(open(gf)) if os.path.exists(gf) else None
    json.dump(cur, open(gf, "w"), indent=1)
    print("goldens RE-SEIZED" if old != cur else "goldens already current")
else:
    g = json.load(open(gf))
    assert cur == g, ("canary stream drift vs golden. If the engine change is "
                      "APPROVED, review the diff then: ./bin/selftest.sh "
                      "--update-goldens. Unapproved drift: FIX THE CODE.")
    print("golden streams: OK")
PY
./venv/bin/python bin/validate_pdf.py $K/out/canary.pdf --profile 2 --book $K \
    --expect Em=4 --expect Strong=2 --expect H1=1 --expect Figure=2 \
    --expect FENote=2 --expect Table=1 --expect-soft-hyphens 3 | tail -1
./venv/bin/python bin/validate_pdf.py $K/out/canary-ua1.pdf --profile 1 --book $K \
    --expect Em=0 --expect Strong=0 --expect Figure=2 --expect Table=1 \
    --expect-soft-hyphens 3 | tail -1
# collision guard negative test
cp $K/pages/p002.json /tmp/p002.harness.json
./venv/bin/python - <<'PY'
import json, pathlib
p = pathlib.Path("books/canary/pages/p002.json"); pg = json.loads(p.read_text())
for x in pg["blocks"]:
    if x["id"] == "k-wrap": x["widths"] = [None]*10
p.write_text(json.dumps(pg))
PY
if SEMANTICORE_HOME=$PWD ./venv/bin/python $K/build.py 2>&1 | grep -q "LAYOUT COLLISION"; then
    echo "collision guard: OK"; else echo "collision guard: BROKEN"; cp /tmp/p002.harness.json $K/pages/p002.json; exit 1; fi
cp /tmp/p002.harness.json $K/pages/p002.json
SEMANTICORE_HOME=$PWD ./venv/bin/python $K/build.py >/dev/null
./venv/bin/python -c "import pikepdf; assert pikepdf.Job(['qpdf','--check','books/canary/out/canary.pdf']).run() in (None,0)"
echo "qpdf: OK"
if [ -f tools/vp/bin/cli-1.30.3.jar ]; then
    export PATH=$PWD/tools/jdk-17.0.20.1+1-jre/bin:$PATH
    java -jar tools/vp/bin/cli-1.30.3.jar -f ua2 --format text $K/out/canary.pdf 2>/dev/null | tail -1
    java -jar tools/vp/bin/cli-1.30.3.jar -f ua1 --format text $K/out/canary-ua1.pdf 2>/dev/null | tail -1
else
    echo "veraPDF SKIP (run bin/setup_env.sh) — REQUIRED before shipping any book"
fi
# template out-of-tree smoke
rm -rf /tmp/semanticore_smokebook && cp -r books/TEMPLATE /tmp/semanticore_smokebook
cp $K/pages/*.json /tmp/semanticore_smokebook/pages/
cp -r $K/assets /tmp/semanticore_smokebook/assets
rm -rf /tmp/semanticore_smokebook/__pycache__
SEMANTICORE_HOME=$PWD ./venv/bin/python /tmp/semanticore_smokebook/build.py >/dev/null
./venv/bin/python bin/validate_pdf.py /tmp/semanticore_smokebook/out/remediated.pdf --profile 2 \
    --book /tmp/semanticore_smokebook | tail -1
rm -rf /tmp/semanticore_smokebook /tmp/p002.harness.json
echo "selftest: ALL OK"
