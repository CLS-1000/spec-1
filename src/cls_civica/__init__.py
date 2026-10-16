# @domain:   civica
# @module:   cls_civica
# @loc:      gh_main
# @status:   mvp
# @depends:  proc_track (replay), gpcanon (sealing; vendored from gatepost)

"""NOTITIA CIVICA — Oregon Legislature, Verified.

Joins the three CLS-1000 projects into one public product:

  proc_track  replays every bill's official action history and proves each step
              was a legal move under chamber procedure (fail closed on anything
              it cannot explain).
  SPEC-1      turns each replayed history into a plain-language card a resident
              can read: what happened, when, and where it stands.
  Gatepost    records every card as a sourced `finding` (with the exact official
              rows as evidence), runs the publication gate on it, and seals the
              chain with the operator's Ed25519 key. Anyone can check the whole
              site offline with bin/verify.py without trusting the publisher.

Entry point: ``python -m cls_civica build --help``.
"""

__all__ = ["__version__"]
__version__ = "0.1.0"
