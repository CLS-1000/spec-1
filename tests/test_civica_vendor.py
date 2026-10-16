# @domain:   civica
# @module:   test_civica_vendor
# @status:   testing

"""The vendored gpcanon copy matches its recorded digest, and upstream when available.

Same pattern as pdx-1i's RULES_VERSION parity test: editing the copy without
updating GPCANON_DIGEST fails here. If SPEC1_GATEPOST_HOME (or a sibling
../gatepost) is present, the copy must also be byte-identical to that checkout;
without one, only the recorded digest is checked.
"""

from __future__ import annotations

import subprocess
import sys

from cls_civica import deps, vendor


def test_vendored_copy_matches_recorded_digest():
    got = vendor.digest()
    assert got == vendor.GPCANON_DIGEST, (
        f"vendored gpcanon changed (digest {got}, recorded {vendor.GPCANON_DIGEST}). "
        f"Re-copy from {vendor.UPSTREAM_REPO} unchanged, then update GPCANON_DIGEST and UPSTREAM_COMMIT."
    )


def test_vendored_copy_matches_upstream_when_present():
    try:
        home = deps.gatepost_home()
    except deps.MissingDependency:
        assert vendor.digest() == vendor.GPCANON_DIGEST  # no checkout: the recorded digest is the check
        return
    upstream = vendor.digest(home, vendor.FILES)
    assert upstream == vendor.digest(), (
        f"vendored gpcanon differs from {home} (upstream {upstream}, vendored {vendor.digest()}). "
        "Re-copy the files listed in cls_civica/vendor/__init__.py."
    )


def test_runtime_uses_vendored_package():
    assert deps.gpcanon_writer().__name__ == "cls_civica.vendor.gpcanon.writer"
    assert deps.gpcanon_verify().__name__ == "cls_civica.vendor.gpcanon.verify"


def test_verify_bundle_is_stdlib_only_and_runs():
    # The bundle runs on a bare interpreter. (Upstream quirk: its --help prints "None", because
    # bundling drops the module docstring; it still exits 3, the usage code.) The full check
    # against a real chain is test_civica_e2e.py::test_verify_kit_runs_standalone.
    r = subprocess.run([sys.executable, "-I", str(deps.verify_bundle()), "--help"], capture_output=True, text=True)
    assert r.returncode == 3, r.stdout + r.stderr
    imports = [ln.split()[1].split(".")[0] for ln in deps.verify_bundle().read_text().splitlines()
               if ln.startswith(("import ", "from ")) and not ln.startswith("from __future__")]
    stdlib = set(sys.stdlib_module_names)
    assert all(m in stdlib for m in imports), sorted(set(imports) - stdlib)
