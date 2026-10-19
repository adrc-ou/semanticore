"""Build this book: edit book.json + pages/*.json, run `python build.py`.
Ships PDF/UA-2 only (the workshop's sole ship profile)."""
import os, pathlib, sys

_here = pathlib.Path(__file__).resolve()
root = pathlib.Path(os.environ.get("PDS_HOME", "") or "/nonexistent")
if not (root / "lib" / "typeset.py").exists():
    for cand in list(_here.parents):
        if (cand / "lib" / "typeset.py").exists():
            root = cand
            break
sys.path.insert(0, str(root / "lib"))
from typeset import build_book
build_book(_here.parent)
