# @domain:   civica
# @module:   civica_vendor
# @status:   mvp

"""Vendored copy of Gatepost's gp-canon/1 package, so cls_civica runs without a
gatepost checkout (CLS-1000/gatepost may be private).

**This is a copy.** The format is defined and tested in CLS-1000/gatepost; edit
there first, then re-copy every file below unchanged:

    gatepost/gpcanon/{__init__,canon,schema,ed25519_verify,writer,verify}.py -> vendor/gpcanon/
    gatepost/bin/verify.py                                                   -> vendor/verify_bundle.py

``GPCANON_DIGEST`` covers those files. ``tests/test_civica_vendor.py`` recomputes
it, so editing the copy without updating the constant fails the suite. That
detects drift; it does not prevent it (same rule as pdx-1i's RULES_VERSION).
When ``SPEC1_GATEPOST_HOME`` points at a gatepost checkout, the same test also
checks the copy is byte-identical to it.

The verifier half is stdlib-only and already public (CLS-1000/notitia-civica
``evidence/verify.py``). The writer needs ``cryptography`` only to sign seals.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

UPSTREAM_REPO = "CLS-1000/gatepost"
UPSTREAM_COMMIT = "d2efca9"
GPCANON_DIGEST = "b908874a0cffac06"

VENDOR_DIR = Path(__file__).resolve().parent
VERIFY_BUNDLE = VENDOR_DIR / "verify_bundle.py"

# vendored path -> path in the gatepost repo
FILES = {
    "gpcanon/__init__.py": "gpcanon/__init__.py",
    "gpcanon/canon.py": "gpcanon/canon.py",
    "gpcanon/schema.py": "gpcanon/schema.py",
    "gpcanon/ed25519_verify.py": "gpcanon/ed25519_verify.py",
    "gpcanon/writer.py": "gpcanon/writer.py",
    "gpcanon/verify.py": "gpcanon/verify.py",
    "verify_bundle.py": "bin/verify.py",
}


def digest(root: Path = VENDOR_DIR, mapping: dict[str, str] | None = None) -> str:
    """First 16 hex of sha256 over (vendored name, bytes) for every file, in sorted order."""
    h = hashlib.sha256()
    for vendored in sorted(FILES):
        source = (mapping or {}).get(vendored, vendored)
        h.update(vendored.encode() + b"\0" + (root / source).read_bytes())
    return h.hexdigest()[:16]
