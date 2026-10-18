# @domain:   civica
# @module:   test_civica_e2e
# @status:   testing

"""End to end: real proc_track replay + Gatepost sealing + offline verify + tamper.

Needs CLS-1000/proc_track and CLS-1000/gatepost checked out next to spec-1 (or
SPEC1_PROC_TRACK_HOME / SPEC1_GATEPOST_HOME) and the `cryptography` package.
CI checks both out (see python-package.yml). Uses a tiny session cache built in
tmp_path, so no network and no dependency on proc_track's cached sessions.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from cls_civica import deps, publish

ROWS = [
    # SB 1: passes both chambers, signed into law
    (1, "SB", 1, "S", "2025-01-13T08:00:00", "Introduction and first reading. Referred to President's desk."),
    (2, "SB", 1, "S", "2025-01-15T08:00:00", "Referred to Judiciary."),
    (3, "SB", 1, "S", "2025-02-10T13:00:00", "Public Hearing held."),
    (4, "SB", 1, "S", "2025-03-01T13:00:00", "Work Session held."),
    (5, "SB", 1, "S", "2025-03-05T09:00:00", "Recommendation: Do pass."),
    (6, "SB", 1, "S", "2025-03-06T09:00:00", "Second reading."),
    (7, "SB", 1, "S", "2025-03-10T11:00:00", "Third reading. Carried by Smith G. Passed."),
    (8, "SB", 1, "H", "2025-03-11T08:00:00", "First reading. Referred to Speaker's desk."),
    (9, "SB", 1, "H", "2025-03-12T08:00:00", "Referred to Judiciary."),
    (10, "SB", 1, "H", "2025-04-01T13:00:00", "Recommendation: Do pass."),
    (11, "SB", 1, "H", "2025-04-02T09:00:00", "Second reading."),
    (12, "SB", 1, "H", "2025-04-07T11:00:00", "Third reading. Carried by Lee. Passed."),
    (13, "SB", 1, "S", "2025-04-10T09:00:00", "President signed."),
    (14, "SB", 1, "H", "2025-04-11T09:00:00", "Speaker signed."),
    (15, "SB", 1, "S", "2025-05-01T09:00:00", "Governor signed."),
    # SJR 2: proposed constitutional amendment, dies in committee
    (16, "SJR", 2, "S", "2025-01-13T08:00:00", "Introduction and first reading. Referred to President's desk."),
    (17, "SJR", 2, "S", "2025-01-15T08:00:00", "Referred to Rules."),
    (18, "SJR", 2, "S", "2025-06-27T12:00:00", "In committee upon adjournment."),
]


def _cache(tmp: Path) -> Path:
    rows = [{"MeasureHistoryId": i, "SessionKey": "2025R1", "MeasurePrefix": p, "MeasureNumber": n,
             "Chamber": c, "ActionDate": d, "ActionText": t, "VoteText": None, "CreatedDate": d,
             "ModifiedDate": None, "PublicNotification": False} for i, p, n, c, d, t in ROWS]
    cdir = tmp / "cache"
    cdir.mkdir()
    (cdir / "2025R1.json").write_text(json.dumps(rows), encoding="utf-8")
    return cdir


def _build(tmp: Path):
    cdir = _cache(tmp)
    out = tmp / "out"
    key = publish.make_demo_key(tmp / "k.pem")
    return publish.build("2025R1", out, key, cache_dir=cdir, demo_key=True), out


def test_build_seals_and_verifies(tmp_path):
    res, out = _build(tmp_path)
    assert res.published == 2 and not res.withheld
    assert dict(res.outcomes) == {"law": 1, "stopped": 1}
    assert publish.verify(out, res.public_key_hex) == 0
    card = json.loads((out / "site" / "cards" / "SB1.json").read_text())
    assert card["headline"] == "SB 1 became law"
    assert card["record"]["evidence_digest"].startswith("sha256:")
    summary = json.loads((out / "site" / "summary.json").read_text())
    assert summary["constitutional_amendments"] == {"proposed": 1, "passed": []}
    html = (out / "site" / "index.html").read_text()
    assert "Oregon Legislature, Verified" in html and "None of the 1 proposed changes" in html
    for f in ("verify.py", "anchor.json", "chain.zip", "PUBLIC_KEY.txt", "civica_publish_card_policy.py"):
        assert (out / "site" / "verify" / f).exists()


def test_chain_is_append_only(tmp_path):
    _res, out = _build(tmp_path)
    try:
        publish.build("2025R1", out, tmp_path / "k.pem", cache_dir=tmp_path / "cache", demo_key=True)
    except FileExistsError:
        return
    raise AssertionError("rebuilding into an existing chain must be refused")


def test_edited_claim_is_detected(tmp_path):
    res, out = _build(tmp_path)
    seg = sorted((out / "chain").glob("seg-*.jsonl"))[0]
    seg.write_text(seg.read_text().replace("SB 1 became law", "SB 1 was vetoed"), encoding="utf-8")
    assert publish.verify(out, res.public_key_hex) == 1


def test_altered_evidence_is_detected(tmp_path):
    res, out = _build(tmp_path)
    ev = next(p for p in (out / "chain" / "evidence").glob("*.json") if b"Governor signed" in p.read_bytes())
    ev.write_bytes(ev.read_bytes().replace(b"Governor signed", b"Governor vetoed"))
    assert publish.verify(out, res.public_key_hex) == 1


def test_wrong_key_is_rejected(tmp_path):
    _res, out = _build(tmp_path)
    assert publish.verify(out, "ab" * 32) == 4


def test_verify_kit_runs_standalone(tmp_path):
    """What a stranger does: only the files in site/verify, no SPEC-1, no Gatepost checkout."""
    import subprocess
    import sys
    import zipfile

    res, out = _build(tmp_path)
    kit = tmp_path / "stranger"
    shutil.copytree(out / "site" / "verify", kit)
    zipfile.ZipFile(kit / "chain.zip").extractall(kit)
    r = subprocess.run([sys.executable, "-I", str(kit / "verify.py"), str(kit / "chain"),
                        "--pubkey", res.public_key_hex, "--anchor", str(kit / "anchor.json"),
                        "--policy", f"civica.publish_card={kit / 'civica_publish_card_policy.py'}"],
                       capture_output=True, text=True, cwd=kit)
    assert r.returncode == 0, r.stdout + r.stderr


def test_ruleset_digest_is_stamped(tmp_path):
    _res, out = _build(tmp_path)
    ev = [json.loads(p.read_text()) for p in (out / "chain" / "evidence").glob("*.json")]
    stamps = {e["ruleset"] for e in ev if "ruleset" in e}
    assert stamps == {deps.ruleset_digest()}


# ---- key precautions -------------------------------------------------------------

def _real_key(tmp: Path, name: str = "op_key.pem") -> tuple[Path, str]:
    """A key outside any git repo, mode 600 (generate_key writes 0600)."""
    W = deps.gpcanon_writer()
    home = tmp / "keyhome"
    home.mkdir(exist_ok=True)
    path = home / name
    key_id, _pub = W.generate_key(path)
    return path, key_id


def _expect_refused(fn, needle: str):
    try:
        fn()
    except publish.KeyPolicyError as e:
        assert needle in str(e), str(e)
        return
    raise AssertionError("key precaution did not fire")


def test_refuses_key_that_is_not_the_published_one(tmp_path):
    key, _kid = _real_key(tmp_path)
    _expect_refused(lambda: publish.check_key(key, demo_key=False, expect_key_id=None),
                    "is not the published operator key")


def test_accepts_matching_key_while_rotating(tmp_path):
    key, kid = _real_key(tmp_path)
    publish.check_key(key, demo_key=False, expect_key_id=kid)


def test_refuses_key_inside_a_git_repo(tmp_path):
    repo = tmp_path / "somerepo"
    (repo / ".git").mkdir(parents=True)
    W = deps.gpcanon_writer()
    key = repo / "op_key.pem"
    W.generate_key(key)
    _expect_refused(lambda: publish.check_key(key, demo_key=False, expect_key_id=None),
                    "inside a git repository")


def test_refuses_world_readable_key(tmp_path):
    key, kid = _real_key(tmp_path)
    key.chmod(0o644)
    _expect_refused(lambda: publish.check_key(key, demo_key=False, expect_key_id=kid), "chmod 600")


def test_wrong_key_refused_before_anything_is_written(tmp_path):
    key, _kid = _real_key(tmp_path)
    out = tmp_path / "out"
    _expect_refused(lambda: publish.build("2025R1", out, key, cache_dir=_cache(tmp_path)),
                    "is not the published operator key")
    assert not out.exists()


def test_site_points_readers_to_published_key_page(tmp_path):
    from cls_civica import labels as L

    _res, out = _build(tmp_path)
    assert L.PUBLISHED_KEY_SOURCE in (out / "site" / "index.html").read_text()
