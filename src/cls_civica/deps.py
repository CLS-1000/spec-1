# @domain:   civica
# @module:   civica_deps
# @status:   mvp

"""Locate the sibling CLS-1000 repo this module builds on, and load the vendored gpcanon.

proc_track (stdlib scripts, by design not a package) is found on disk:

  SPEC1_PROC_TRACK_HOME   path to a CLS-1000/proc_track checkout (default ../proc_track)

gpcanon (Gatepost's gp-canon/1 writer and verifier) is vendored under
cls_civica/vendor/, so no gatepost checkout is needed. SPEC1_GATEPOST_HOME is
read only by the vendor parity test, to compare the copy against upstream.
"""

from __future__ import annotations

import hashlib
import importlib
import os
import sys
from pathlib import Path
from types import ModuleType

_REPO_ROOT = Path(__file__).resolve().parents[2]


class MissingDependency(RuntimeError):
    pass


def _home(env: str, sibling: str, marker: str) -> Path:
    raw = os.environ.get(env)
    candidates = [Path(raw)] if raw else [_REPO_ROOT.parent / sibling, _REPO_ROOT / sibling]
    for c in candidates:
        if (c / marker).exists():
            return c.resolve()
    tried = ", ".join(str(c) for c in candidates)
    raise MissingDependency(
        f"{sibling} not found (tried {tried}). Clone github.com/CLS-1000/{sibling} "
        f"next to spec-1 or set {env}."
    )


def proc_track_home() -> Path:
    return _home("SPEC1_PROC_TRACK_HOME", "proc_track", "replay_harness.py")


def gatepost_home() -> Path:
    """A gatepost checkout, for the vendor parity test only. The runtime never needs one."""
    return _home("SPEC1_GATEPOST_HOME", "gatepost", "gpcanon/writer.py")


def replay_harness() -> ModuleType:
    """proc_track's replay_harness module (mapping rules + transition graph)."""
    home = str(proc_track_home())
    if home not in sys.path:
        sys.path.insert(0, home)
    return importlib.import_module("replay_harness")


def gpcanon_writer() -> ModuleType:
    """The vendored gp-canon/1 writer (cls_civica/vendor/gpcanon)."""
    return importlib.import_module("cls_civica.vendor.gpcanon.writer")


def gpcanon_verify() -> ModuleType:
    """The vendored gp-canon/1 verifier (stdlib only)."""
    return importlib.import_module("cls_civica.vendor.gpcanon.verify")


def verify_bundle() -> Path:
    """The single-file verifier recipients run (gatepost bin/verify.py, vendored unchanged)."""
    from cls_civica.vendor import VERIFY_BUNDLE

    return VERIFY_BUNDLE


def ruleset_digest() -> str:
    """sha256 of the proc_track rules a replay was validated against.

    proc_track's own rule: records are mutable, so a transition is stamped with
    the rule set it was checked under rather than recomputed later.
    """
    h = hashlib.sha256()
    home = proc_track_home()
    for rel in ("replay_harness.py",):
        h.update(rel.encode() + b"\0" + (home / rel).read_bytes())
    return "sha256:" + h.hexdigest()


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return "sha256:" + h.hexdigest()
