"""Locate the pds workshop lib from anywhere.

Books' build.py:  import pds_bootstrap; ROOT = pds_bootstrap.init()
Search order: $PDS_HOME, then upward from this file for a dir containing
lib/typeset.py + AGENTS.md. Returns the workshop root path.
"""
import os
import pathlib
import sys


def find_root(start=None):
    env = os.environ.get("PDS_HOME")
    if env and (pathlib.Path(env) / "lib" / "typeset.py").exists():
        return pathlib.Path(env).resolve()
    p = pathlib.Path(start or __file__).resolve()
    for cand in [p.parent] + list(p.parents):
        if (cand / "lib" / "typeset.py").exists() and (cand / "AGENTS.md").exists():
            return cand
    raise SystemExit("pds workshop root not found (set PDS_HOME)")


def init():
    root = find_root()
    lib = str(root / "lib")
    if lib not in sys.path:
        sys.path.insert(0, lib)
    return root
