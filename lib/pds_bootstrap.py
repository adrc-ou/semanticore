"""Locate the pds workshop lib from anywhere.

typeset.py calls find_root() (lib is already on sys.path from the build
script). init() is a convenience for callers that have bootstrapped lib
onto sys.path; it is NOT importable before that. Search order: $PDS_HOME, then upward from this file for a dir containing
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
