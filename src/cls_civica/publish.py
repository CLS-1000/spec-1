# @domain:   civica
# @module:   civica_publish
# @status:   mvp

"""Build the verified site: replay -> card -> finding -> gate -> publish -> seal.

Chain `civica.publish` (gp-canon/1), per measure:
  finding  civica.measure_card   the card + the exact official rows, as evidence
  intent   civica.publish_card   policy decision on that card (allow/deny)
  outcome                        ok (card written to the site) or skipped (withheld)
then one civica.session_summary finding and a seal signed with the operator key.

The gate and the record are the same act: a card file is written only inside an
allowed gate, after its evidence and decision are on the chain. A denied card is
recorded and listed as withheld, never silently dropped.
"""

from __future__ import annotations

import json
import logging
import re
import shutil
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional

from cls_civica import deps, policy, sources
from cls_civica import labels as L
from cls_civica.plain import build_card

logger = logging.getLogger(__name__)

_PREFIX_ORDER = ["HB", "SB", "HJR", "SJR", "HJM", "SJM", "HCR", "SCR", "HR", "SR"]


@dataclass
class BuildResult:
    out_dir: Path
    session: str
    published: int = 0
    withheld: list[dict] = field(default_factory=list)
    outcomes: Counter = field(default_factory=Counter)
    unverified: int = 0
    anchor: Optional[dict] = None
    key_id: str = ""
    public_key_hex: str = ""
    demo_key: bool = False


def _sort_key(mid: str):
    m = re.match(r"([A-Z]+)(\d+)$", mid)
    p, n = m.group(1), int(m.group(2))
    return (_PREFIX_ORDER.index(p) if p in _PREFIX_ORDER else 99, p, n)


def _public_key(private_key) -> tuple[str, str]:
    from cryptography.hazmat.primitives import serialization

    W = deps.gpcanon_writer()
    raw = private_key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    return W.key_id_of(raw), raw.hex()


class KeyPolicyError(RuntimeError):
    """The signing key failed a precaution; nothing was built."""


def _inside_git_repo(path: Path) -> Optional[Path]:
    """The working tree containing `path`, if any. A private key must never live in one."""
    p = Path(path).expanduser().resolve()
    for parent in [p.parent, *p.parent.parents]:
        if (parent / ".git").exists():
            return parent
    return None


def check_key(key_path: Path, demo_key: bool, expect_key_id: Optional[str]) -> None:
    """Precautions before anything is written.

    Real builds: the key must sit outside every git repository (so it cannot be
    committed), be readable only by its owner, and match the published key
    (L.PUBLISHED_KEY_ID) unless the operator names a new key id while rotating.
    Demo builds skip the identity check; they are labelled as demos on the page.
    """
    key_path = Path(key_path).expanduser()
    if demo_key:
        return
    repo = _inside_git_repo(key_path)
    if repo is not None:
        raise KeyPolicyError(f"refusing a signing key inside a git repository ({repo}). "
                             "Keep it in ~/.gatepost/ and back it up offline.")
    try:
        mode = key_path.stat().st_mode & 0o077
    except OSError as e:
        raise KeyPolicyError(f"cannot read key {key_path}: {e}") from e
    if mode:
        raise KeyPolicyError(f"{key_path} is readable by other users; run: chmod 600 {key_path}")
    W = deps.gpcanon_writer()
    key_id, _ = _public_key(W.load_private_key(key_path))
    want = expect_key_id or L.PUBLISHED_KEY_ID
    if key_id != want:
        raise KeyPolicyError(
            f"key {key_id} is not the published operator key {want} ({L.PUBLISHED_KEY_SOURCE}). "
            "Use the published key, or publish the new key first and pass --expect-key-id <new id> while rotating.")


def make_demo_key(path: Path) -> Path:
    """Throwaway key for previews. Never publish a real site sealed with it."""
    W = deps.gpcanon_writer()
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        W.generate_key(path)
    return path


def build(
    session: str,
    out_dir: Path,
    key_path: Path,
    *,
    cache_dir: Optional[Path] = None,
    titles_path: Optional[Path] = None,
    measures: Optional[Iterable[str]] = None,
    limit: Optional[int] = None,
    demo_key: bool = False,
    expect_key_id: Optional[str] = None,
) -> BuildResult:
    check_key(key_path, demo_key, expect_key_id)
    out_dir = Path(out_dir)
    chain_dir = out_dir / "chain"
    if chain_dir.exists() and any(chain_dir.iterdir()):
        raise FileExistsError(f"{chain_dir} already holds a chain; build into a new directory (append-only)")
    site_dir = out_dir / "site"
    cards_dir = site_dir / "cards"
    cards_dir.mkdir(parents=True, exist_ok=True)

    W = deps.gpcanon_writer()
    priv = W.load_private_key(key_path)
    key_id, pub_hex = _public_key(priv)

    sess = sources.load_session(session, cache_dir, titles_path)
    ruleset = deps.ruleset_digest()
    ids = sorted(sess.rows_by_measure, key=_sort_key)
    if measures:
        wanted = {m.replace(" ", "").upper() for m in measures}
        ids = [m for m in ids if m in wanted]
    if limit:
        ids = ids[:limit]

    chain = W.Chain(chain_dir, L.CHAIN_ID, actor=f"cls_civica:{W.default_actor()}")
    registry = {L.POLICY_PUBLISH_CARD: W.Policy(policy.POLICY_VERSION, policy.__file__, policy.decide)}
    res = BuildResult(out_dir=out_dir, session=session, key_id=key_id, public_key_hex=pub_hex, demo_key=demo_key)
    index: list[dict] = []

    for mid in ids:
        rows = sess.rows_by_measure[mid]
        states, history, halt = sources.replay(mid, rows)
        card = build_card(session, mid, rows, history, states, halt,
                          title=sess.titles.get(mid) or None, session_closed=sess.closed)
        cd = card.to_dict()
        evidence = {
            "card": cd,
            "rows": rows,
            "source_query": card.source_url,
            "history_cache": {"file": sess.cache_file.name, "sha256": sess.cache_sha256},
            "titles_cache": ({"file": sess.titles_file.name, "sha256": sess.titles_sha256}
                             if sess.titles_file else None),
            "ruleset": ruleset,
            "replay": {"states": states, "halt": halt},
        }
        f = chain.record_finding(card.subject, L.FINDING_MEASURE_CARD, claim=card.headline, evidence=evidence)
        inputs = {
            "card": cd,
            "evidence_digest": f["evidence_digest"],
            "source_row_ids": [int(r["MeasureHistoryId"]) for r in rows],
        }
        with chain.gate(L.POLICY_PUBLISH_CARD, card.subject, L.ACTION_PUBLISH, inputs, registry) as g:
            if g.allowed:
                published = dict(cd)
                published["record"] = {
                    "chain_id": L.CHAIN_ID,
                    "finding_seq": f["seq"],
                    "finding_hash": f["h"],
                    "evidence_digest": f["evidence_digest"],
                    "gate_id": g.gate_id,
                    "gate_seq": g.seq,
                }
                (cards_dir / f"{mid}.json").write_text(json.dumps(published, ensure_ascii=False, indent=1),
                                                       encoding="utf-8")
                index.append(published)
            else:
                res.withheld.append({"measure": card.measure, "reason": g.detail, "gate_id": g.gate_id})
        if g.allowed:
            res.published += 1
            res.outcomes[card.outcome] += 1
            res.unverified += 0 if card.verified else 1

    summary = _summary(sess, index, res)
    sf = chain.record_finding(f"or_legislature/{session}", L.FINDING_SESSION_SUMMARY,
                              claim=summary["headline"], evidence=summary)
    res.anchor = chain.seal(priv)
    _write_verify_kit(site_dir, chain_dir, res, summary, sf)
    from cls_civica.site import render_site

    render_site(site_dir, index, summary, res)
    return res


def _summary(sess: "sources.Session", index: list[dict], res: BuildResult) -> dict:
    outcomes = Counter(c["outcome"] for c in index)
    jr = [c for c in index if c["measure_id"][:3] in L.JOINT_RESOLUTIONS]
    jr_passed = [c["measure"] for c in jr if c["outcome"] in (L.OUTCOME_ADOPTED, L.OUTCOME_PASSED)]
    vetoed = [c["measure"] for c in index if c["outcome"] == L.OUTCOME_VETOED]
    headline = (f"Oregon {sess.session}: {len(index)} measures published, "
                f"{outcomes.get(L.OUTCOME_LAW, 0)} became law, {len(vetoed)} vetoed")
    return {
        "headline": headline,
        "session": sess.session,
        "session_closed": sess.closed,
        "measures_published": len(index),
        "measures_withheld": len(res.withheld),
        "rows_in_cache": sess.row_total,
        "outcomes": dict(sorted(outcomes.items())),
        "unverified": [c["measure"] for c in index if not c["verified"]],
        "constitutional_amendments": {"proposed": len(jr), "passed": jr_passed},
        "vetoed": vetoed,
        "history_cache": {"file": sess.cache_file.name, "sha256": sess.cache_sha256},
        "built_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def _write_verify_kit(site_dir: Path, chain_dir: Path, res: BuildResult, summary: dict, sf: dict) -> None:
    """Everything a stranger needs to check the site offline, in site/verify/."""
    vdir = site_dir / "verify"
    vdir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(deps.verify_bundle(), vdir / "verify.py")
    shutil.copy2(policy.__file__, vdir / "civica_publish_card_policy.py")
    (vdir / "anchor.json").write_text(json.dumps(res.anchor, indent=1), encoding="utf-8")
    (vdir / "PUBLIC_KEY.txt").write_text(
        f"key_id {res.key_id}\npublic_key_hex {res.public_key_hex}\n"
        + ("DEMO KEY: throwaway preview key. Do not trust a site sealed with it.\n" if res.demo_key else ""),
        encoding="utf-8")
    archive = shutil.make_archive(str(vdir / "chain"), "zip", root_dir=chain_dir.parent, base_dir=chain_dir.name)
    (site_dir / "summary.json").write_text(
        json.dumps({**summary, "summary_finding_seq": sf["seq"], "anchor": res.anchor,
                    "key_id": res.key_id, "public_key_hex": res.public_key_hex,
                    "demo_key": res.demo_key, "withheld": res.withheld,
                    "chain_zip": Path(archive).name}, indent=1),
        encoding="utf-8")


def verify(out_dir: Path, public_key_hex: str) -> int:
    """Run Gatepost's verifier against a built site. Returns its exit code (0 = pass)."""
    V = deps.gpcanon_verify()
    out_dir = Path(out_dir)
    return V.main([
        str(out_dir / "chain"),
        "--pubkey", public_key_hex,
        "--anchor", str(out_dir / "site" / "verify" / "anchor.json"),
        "--policy", f"{L.POLICY_PUBLISH_CARD}={policy.__file__}",
    ])
