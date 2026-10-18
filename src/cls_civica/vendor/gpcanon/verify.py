"""verify — offline verifier for gp-canon/1 chains. Stdlib only.

usage: python3 verify.py CHAIN_DIR [--pubkey HEX]... [--keyring FILE] [--allow-unpinned]
                         [--anchor FILE] [--policy POLICY_ID=PATH]... [--chain-id ID] [--json]

Exit codes (same meaning as gatepost/v1):
  0  verified; every seal checked against a pinned key (or --allow-unpinned given)
  1  chain broken: altered, deleted, reordered or spliced records; pairing violated;
     truncated against an anchor; policy file differs from the recorded digest
  2  signature failure: forged seal, sig missing on a seal or present on a non-seal
  3  malformed: not gp-canon/1 JSON, bad line keys, schema violation
  4  a seal is signed by a key that is not pinned, or outside that key's validity window

Keyring (key rotation): a JSON file {"keys": [{"key_id", "public_key_hex", "effective_from",
"retired_at"}]}, timestamps in the record format, retired_at may be null. A seal must be
made (recorded_at) inside its key's window. Get the keyring from somewhere the chain does
not control, the same as --pubkey.
  5  hashes and pairing check out but nothing is pinned: either no --pubkey was given
     (seals were not verified) or the chain has no seals at all (nothing is signed).
     Pin with --pubkey, using a key obtained from somewhere the chain does not control.

A pass proves the records were not changed after they were written and that each
gated action was recorded as decided. It does not prove the records are true.
Without --anchor, deletion of the tail (including its seals) is not detectable, and
the report says so.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

from .canon import GENESIS, CanonError, canon, parse, record_hash
from .ed25519_verify import verify as ed25519_verify
from .schema import FORMAT, validate_sealed

SEAL_DOMAIN = b"gatepost/seal/v1\n"

MALFORMED = {"float", "neg_zero", "int_range", "dup_key", "non_nfc", "lone_surrogate", "bad_json",
             "bad_type", "line_key_invalid", "missing_field", "unknown_field", "bad_field",
             "null_not_allowed", "null_required", "decision_reason_mismatch", "policy_prefix_mismatch",
             "canon_version_unsupported", "torn_line", "type_prefix_mismatch"}
CHAIN = {"seal_backdated", "hash_mismatch", "prev_mismatch", "seq_gap", "seq_duplicate", "chain_id_mismatch",
         "line_not_canonical", "unpaired", "pairing_invalid", "policy_digest_mismatch",
         "truncated_tail", "anchor_mismatch", "evidence_mismatch"}
SIGNATURE = {"sig_missing", "sig_forbidden", "bad_signature"}
KEY = {"key_id_mismatch", "key_outside_window"}
NOTICE = {"unsealed_tail", "tail_unanchored", "unpinned", "dangling_intent", "notes_unverified",
          "seals_unverified", "evidence_absent"}


class Report:
    def __init__(self):
        self.findings: list[dict] = []
        self.records = 0
        self.seals = 0
        self.last_seal_seq = None
        self.head = None

    def add(self, code: str, seq, detail: str = "") -> None:
        self.findings.append({"code": code, "seq": seq, "detail": detail})

    def codes(self) -> set[str]:
        return {f["code"] for f in self.findings}

    def exit_code(self) -> int:
        c = self.codes()
        for group, code in ((MALFORMED, 3), (CHAIN, 1), (SIGNATURE, 2), (KEY, 4)):
            if c & group:
                return code
        return 5 if "unpinned" in c else 0


def _lines(chain_dir: Path, rep: Report):
    segs = sorted(chain_dir.glob("seg-*.jsonl"))
    if not segs:
        rep.add("bad_json", None, "no segments")
    for seg in segs:
        data = seg.read_bytes()
        parts = data.split(b"\n")
        if parts and parts[-1] != b"":
            rep.add("torn_line", None, f"{seg.name}: final line has no newline (crash mid-write?)")
        for raw in parts[:-1]:
            yield seg.name, raw


def _check_evidence(chain_dir: Path, s: dict, rep: "Report") -> None:
    """A finding's evidence file, if the pack includes it, must hash to evidence_digest."""
    path = chain_dir / "evidence" / f"{s['evidence_digest'][7:]}.json"
    if not path.exists():
        rep.add("evidence_absent", s["seq"], "evidence file not in this pack; claim is bound but not inspectable")
        return
    data = path.read_bytes()
    if "sha256:" + hashlib.sha256(data).hexdigest() != s["evidence_digest"]:
        rep.add("evidence_mismatch", s["seq"], "evidence file does not match the digest in the record")
        return
    try:
        if canon(parse(data)) != data:
            rep.add("evidence_mismatch", s["seq"], "evidence file is not canonical")
    except CanonError as e:
        rep.add("evidence_mismatch", s["seq"], f"evidence file is not gp-canon/1 JSON: {e.reason}")


def load_keyring(path) -> tuple[dict[str, bytes], dict[str, tuple]]:
    """Parse a keyring file into (pubkeys, windows). Raises ValueError on any inconsistency."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    pubkeys, windows = {}, {}
    for k in data["keys"]:
        raw = bytes.fromhex(k["public_key_hex"])
        if len(raw) != 32:
            raise ValueError(f"keyring: {k.get('key_id')}: public key must be 32 bytes")
        kid = hashlib.sha256(raw).hexdigest()[:16]
        if kid != k["key_id"]:
            raise ValueError(f"keyring: key_id {k['key_id']} does not match its public key ({kid})")
        start, end = k.get("effective_from"), k.get("retired_at")
        for ts in (start, end):
            if ts is not None and not FORMAT["recorded_at"](ts):
                raise ValueError(f"keyring: {kid}: bad timestamp {ts!r}")
        pubkeys[kid] = raw
        windows[kid] = (start, end)
    return pubkeys, windows


def verify_chain(chain_dir, pubkeys: dict[str, bytes] | None = None, allow_unpinned: bool = False,
                 anchor: dict | None = None, policies: dict[str, str] | None = None,
                 chain_id: str | None = None, windows: dict[str, tuple] | None = None) -> Report:
    rep = Report()
    pubkeys = pubkeys or {}
    windows = windows or {}
    last_seal_at = None
    policy_digests = {}
    for pid, path in (policies or {}).items():
        policy_digests[pid] = "sha256:" + hashlib.sha256(Path(path).read_bytes()).hexdigest()

    expect_seq, prev = 0, GENESIS
    hashes: dict[int, str] = {}
    open_intent = None                  # (gate_id, decision, seq)
    for seg, raw in _lines(Path(chain_dir), rep):
        try:
            line = parse(raw)
        except CanonError as e:
            rep.add(e.reason, None, f"{seg}: {e}")
            continue
        if not isinstance(line, dict) or not {"h", "s"} <= set(line) or not set(line) <= {"h", "s", "n", "sig"}:
            rep.add("line_key_invalid", None, f"{seg}: keys {sorted(line) if isinstance(line, dict) else type(line).__name__}")
            continue
        s, h = line["s"], line["h"]
        seq = s.get("seq") if isinstance(s, dict) else None
        rep.records += 1
        errs = validate_sealed(s)
        for code, detail in errs:
            rep.add(code, seq, detail)
        if errs:
            continue
        if canon(line) != raw:
            rep.add("line_not_canonical", seq)
        if record_hash(s) != h:
            rep.add("hash_mismatch", seq, "record altered after it was written")
        if chain_id is None:
            chain_id = s["chain_id"]
        if s["chain_id"] != chain_id:
            rep.add("chain_id_mismatch", seq, f"{s['chain_id']} in chain {chain_id}")
        if seq in hashes:
            rep.add("seq_duplicate", seq)
        elif seq != expect_seq:
            rep.add("seq_gap", seq, f"expected {expect_seq}")
        if s["prev_hash"] != prev:
            rep.add("prev_mismatch", seq, "record deleted, inserted or reordered before this one")
        hashes[seq] = h
        prev, expect_seq = h, seq + 1
        if "n" in line:
            rep.add("notes_unverified", seq, "notes sit outside the hash")

        kind = s["kind"]
        if kind == "seal":
            if "sig" not in line:
                rep.add("sig_missing", seq)
            else:
                rep.seals += 1
                rep.last_seal_seq = seq
                sig = line["sig"]
                if not (isinstance(sig, str) and len(sig) == 128 and all(c in "0123456789abcdef" for c in sig)):
                    rep.add("bad_signature", seq, "sig is not 128 lowercase hex")
                elif pubkeys:
                    pub = pubkeys.get(s["key_id"])
                    if pub is None:
                        rep.add("key_id_mismatch", seq, f"sealed by {s['key_id']}, pinned {sorted(pubkeys)}")
                    elif not ed25519_verify(pub, SEAL_DOMAIN + canon(s), bytes.fromhex(sig)):
                        rep.add("bad_signature", seq, "seal signature does not verify")
                    else:
                        start, end = windows.get(s["key_id"], (None, None))
                        at = s["recorded_at"]           # fixed-width UTC strings compare in time order
                        if (start and at < start) or (end and at >= end):
                            rep.add("key_outside_window", seq,
                                    f"{s['key_id']} sealed at {at}, valid {start or '-'} to {end or 'now'}")
                if last_seal_at and s["recorded_at"] < last_seal_at:
                    rep.add("seal_backdated", seq, f"sealed at {s['recorded_at']}, before an earlier seal ({last_seal_at})")
                last_seal_at = max(last_seal_at or "", s["recorded_at"])
            if open_intent:
                rep.add("pairing_invalid", seq, "seal written while an intent was open")
        elif "sig" in line:
            rep.add("sig_forbidden", seq)

        if kind == "intent":
            if open_intent:
                rep.add("unpaired", open_intent[2], "intent has no outcome before the next intent")
            open_intent = (s["gate_id"], s["decision"], seq)
            pol = policy_digests.get(s["policy_id"])
            if pol and s["policy_digest"] is not None and s["policy_digest"] != pol:
                rep.add("policy_digest_mismatch", seq, f"{s['policy_id']}: recorded digest differs from given file")
        elif kind == "finding":
            if open_intent:
                rep.add("pairing_invalid", seq, "finding written while an intent was open")
            _check_evidence(Path(chain_dir), s, rep)
        elif kind in ("outcome", "failure"):
            if not open_intent or open_intent[0] != s["gate_id"]:
                rep.add("pairing_invalid", seq, f"{kind} without its intent")
            elif kind == "outcome":
                ok = {"allow": ("ok", "raised"), "deny": ("skipped",)}[open_intent[1]]
                if s["result"] not in ok:
                    rep.add("pairing_invalid", seq, f"{open_intent[1]} followed by result={s['result']}")
            open_intent = None

    last = expect_seq - 1
    rep.head = {"seq": last, "h": prev} if last >= 0 else None
    if open_intent:
        rep.add("dangling_intent", open_intent[2], "no outcome yet: action in progress or process died")
    if rep.last_seal_seq is None or rep.last_seal_seq < last:
        n = last - (rep.last_seal_seq if rep.last_seal_seq is not None else -1)
        if n > 0:
            rep.add("unsealed_tail", last, f"{n} record(s) after the last seal")
    if anchor:
        a_seq = anchor.get("seq")
        if anchor.get("chain_id") != chain_id:
            rep.add("anchor_mismatch", a_seq, "anchor is for another chain")
        elif a_seq not in hashes:
            rep.add("truncated_tail", a_seq, f"chain ends at seq {last}, anchor is at {a_seq}")
        elif hashes[a_seq] != anchor.get("h"):
            rep.add("anchor_mismatch", a_seq, "hash at the anchored seq differs")
    else:
        rep.add("tail_unanchored", last, f"truncation after seq {rep.last_seal_seq} not detectable")
    if rep.seals == 0 and not allow_unpinned:
        rep.add("unpinned", None, "no seals: nothing is signed, so the whole chain could be rewritten")
    elif rep.seals and not pubkeys and not allow_unpinned:
        rep.add("unpinned", None, "seals present but no --pubkey given: signatures NOT verified")
    elif not pubkeys or rep.seals == 0:
        rep.add("seals_unverified", None, "--allow-unpinned: integrity shown only against whoever can edit the files")
    return rep


def _summary(rep: Report, exit_code: int) -> str:
    verdict = {0: "OK", 1: "FAIL (chain)", 2: "FAIL (signature)", 3: "FAIL (malformed)",
               4: "FAIL (key)", 5: "NOT A PASS (unpinned)"}[exit_code]
    lines = [f"{verdict}: {rep.records} records, {rep.seals} seals, head "
             f"{rep.head['seq'] if rep.head else '-'}"]
    for f in rep.findings:
        mark = "·" if f["code"] in NOTICE else "✗"
        seq = f" seq {f['seq']}" if f["seq"] is not None else ""
        lines.append(f"  {mark} {f['code']}{seq}{': ' + f['detail'] if f['detail'] else ''}")
    return "\n".join(lines)


def main(argv=None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] in ("-h", "--help"):
        print(__doc__)
        return 3
    chain_dir, pubkeys, policies, anchor, chain_id, windows = None, {}, {}, None, None, {}
    allow_unpinned = as_json = False
    it = iter(args)
    try:
        for a in it:
            if a == "--pubkey":
                raw = bytes.fromhex(next(it))
                pubkeys[hashlib.sha256(raw).hexdigest()[:16]] = raw
            elif a == "--keyring":
                kp, kw = load_keyring(next(it))
                pubkeys.update(kp)
                windows.update(kw)
            elif a == "--allow-unpinned":
                allow_unpinned = True
            elif a == "--anchor":
                anchor = json.loads(Path(next(it)).read_text())
            elif a == "--policy":
                pid, path = next(it).split("=", 1)
                policies[pid] = path
            elif a == "--chain-id":
                chain_id = next(it)
            elif a == "--json":
                as_json = True
            elif chain_dir is None and not a.startswith("--"):
                chain_dir = a
            else:
                raise ValueError(f"unexpected argument {a!r}")
        if chain_dir is None:
            raise ValueError("CHAIN_DIR required")
        rep = verify_chain(chain_dir, pubkeys, allow_unpinned, anchor, policies, chain_id, windows)
    except (ValueError, StopIteration, OSError) as e:
        print(f"usage error: {e}", file=sys.stderr)
        return 3
    code = rep.exit_code()
    if as_json:
        print(json.dumps({"exit": code, "records": rep.records, "seals": rep.seals, "head": rep.head,
                          "findings": rep.findings}, ensure_ascii=False))
    else:
        print(_summary(rep, code))
    return code


if __name__ == "__main__":
    sys.exit(main())
