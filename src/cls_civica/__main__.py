# @domain:   civica
# @module:   civica_cli
# @status:   mvp

"""python -m cls_civica <command>

  build    replay a session, gate + seal every card, render the site
  verify   check a built site with Gatepost's offline verifier
  titles   pull measure titles from the Legislature (network) to enable the elections topic

Examples
  # preview, throwaway key
  python -m cls_civica build --session 2025R1 --out out/civica_2025R1 --demo-key
  # real, your Gatepost operator key (python3 <gatepost>/tools/gp_operator.py keygen)
  python -m cls_civica build --session 2025R1 --out out/civica_2025R1 --key ~/.gatepost/op_key.pem
  python -m cls_civica verify out/civica_2025R1 --pubkey <your published public key hex>
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from cls_civica import deps, publish, sources
from cls_civica import labels as L


def _cmd_build(a) -> int:
    out = Path(a.out)
    if a.demo_key:
        key = publish.make_demo_key(out / "DEMO_KEY.pem")
    elif a.key:
        key = Path(a.key).expanduser()
    else:
        print("build: pass --key <operator key.pem> or --demo-key", file=sys.stderr)
        return 2
    try:
        res = publish.build(
            a.session, out, key,
            cache_dir=Path(a.cache_dir) if a.cache_dir else None,
            titles_path=Path(a.titles) if a.titles else None,
            measures=a.measures.split(",") if a.measures else None,
            limit=a.limit, demo_key=a.demo_key, expect_key_id=a.expect_key_id,
        )
    except (deps.MissingDependency, FileNotFoundError, FileExistsError, publish.KeyPolicyError) as e:
        print(f"build: {e}", file=sys.stderr)
        return 1
    print(json.dumps({
        "site": str(out / "site" / "index.html"),
        "published": res.published,
        "withheld": len(res.withheld),
        "unverified": res.unverified,
        "outcomes": dict(res.outcomes),
        "key_id": res.key_id,
        "public_key_hex": res.public_key_hex,
        "anchor": res.anchor,
        "demo_key": res.demo_key,
    }, indent=1))
    if a.demo_key:
        print("NOTE: sealed with a throwaway demo key. Rebuild with --key before publishing.", file=sys.stderr)
    code = publish.verify(out, res.public_key_hex)
    return 0 if code == 0 and not res.withheld else (code or 1)


def _cmd_verify(a) -> int:
    pub = a.pubkey or L.PUBLISHED_PUBKEY_HEX
    if not a.pubkey:
        print(f"pinning the published operator key {L.PUBLISHED_KEY_ID} ({L.PUBLISHED_KEY_SOURCE})", file=sys.stderr)
    return publish.verify(Path(a.out), pub)


def _cmd_titles(a) -> int:
    out = Path(a.out) if a.out else sources.cache_path(a.session).with_name(f"{a.session}.titles.json")
    n = sources.fetch_titles(a.session, out)
    print(f"{n} titles -> {out}")
    return 0 if n else 1


def main(argv=None) -> int:
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    p = argparse.ArgumentParser(prog="python -m cls_civica", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("build", help="build and seal the verified site")
    b.add_argument("--session", default="2025R1")
    b.add_argument("--out", required=True, help="new output directory (chain is append-only)")
    k = b.add_mutually_exclusive_group()
    k.add_argument("--key", help="Gatepost operator Ed25519 key (PEM)")
    k.add_argument("--demo-key", action="store_true", help="throwaway key, for previews only")
    b.add_argument("--expect-key-id", help="only while rotating: the NEW key id, already published")
    b.add_argument("--cache-dir", help="proc_track cache dir (default <proc_track>/cache)")
    b.add_argument("--titles", help="titles JSON from `titles` (default <cache>/<SESSION>.titles.json)")
    b.add_argument("--measures", help="comma list, e.g. SB976,HB2001")
    b.add_argument("--limit", type=int)
    b.set_defaults(fn=_cmd_build)

    v = sub.add_parser("verify", help="verify a built site offline")
    v.add_argument("out")
    v.add_argument("--pubkey", help="publisher's public key hex (default: the published operator key)")
    v.set_defaults(fn=_cmd_verify)

    t = sub.add_parser("titles", help="fetch measure titles (network)")
    t.add_argument("--session", default="2025R1")
    t.add_argument("--out")
    t.set_defaults(fn=_cmd_titles)

    a = p.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
