"""gp-canon/1 chain writer and gate (SCHEMA §1, §2, §5–7). Producer side.

Only sealing needs a third-party package (`cryptography`); everything else is stdlib.

Deviation from SCHEMA §6, deliberate: the chain lock is held from the intent
through the outcome, not released while the body runs. With the lock released,
a concurrent gate() on the same chain sees the in-flight intent as dangling
(§5.4) and writes `outcome_unwritten` for an action that is still running, and
its own intent lands between another intent and its outcome (breaking §4
pairing). Holding the lock serialises actions per chain, which is what one
chain per consumer action already implies.
"""
from __future__ import annotations

import errno
import fcntl
import getpass
import hashlib
import os
import socket
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from .canon import CANON_VERSION, GENESIS, CanonError, canon, digest, file_digest, parse, record_hash
from .schema import ID_RE, utc_ts

SEAL_DOMAIN = b"gatepost/seal/v1\n"


class GateError(RuntimeError):
    """The gate could not record a decision, so the action must not run (SCHEMA §5.2)."""


class GateLockTimeout(GateError):
    pass


@dataclass(frozen=True)
class Policy:
    """policy_id -> version, source file (hashed into policy_digest), and the decision function.

    fn(inputs) returns (allow: bool, detail: str | None). Raising is recorded as policy_raised.
    """
    version: str
    source: str
    fn: Callable[[object], tuple[bool, str | None]]


@dataclass
class Gate:
    gate_id: str
    decision: str
    reason: str
    detail: str | None
    seq: int

    @property
    def allowed(self) -> bool:
        return self.decision == "allow"


def now_ts() -> str:
    return utc_ts(datetime.now(timezone.utc))


def default_actor() -> str:
    return f"{getpass.getuser()}@{socket.gethostname()}"


def key_id_of(public_raw: bytes) -> str:
    return hashlib.sha256(public_raw).hexdigest()[:16]


class Chain:
    def __init__(self, chain_dir: str | os.PathLike, chain_id: str, actor: str | None = None,
                 lock_timeout: float = 10.0, max_segment_bytes: int = 64 * 1024 * 1024):
        if not ID_RE.match(chain_id):
            raise ValueError(f"bad chain_id {chain_id!r}")
        self.dir = Path(chain_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.chain_id = chain_id
        self.consumer = chain_id.split(".")[0]
        self.actor = actor or default_actor()
        self.lock_timeout = lock_timeout
        self.max_segment_bytes = max_segment_bytes
        self._lock_fd = None

    # ---- locking -------------------------------------------------------------------

    @contextmanager
    def _locked(self):
        if self._lock_fd is not None:              # already held by this object (gate -> seal)
            yield
            return
        fd = os.open(self.dir / ".lock", os.O_RDWR | os.O_CREAT, 0o644)
        deadline = time.monotonic() + self.lock_timeout
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError as e:
                if e.errno not in (errno.EAGAIN, errno.EACCES):
                    os.close(fd)
                    raise GateError(f"lock failed: {e}") from e
                if time.monotonic() >= deadline:
                    os.close(fd)
                    raise GateLockTimeout(f"{self.chain_id}: lock not acquired in {self.lock_timeout}s")
                time.sleep(0.02)
        self._lock_fd = fd
        try:
            yield
        finally:
            self._lock_fd = None
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)

    # ---- segments ------------------------------------------------------------------

    def segments(self) -> list[Path]:
        return sorted(self.dir.glob("seg-*.jsonl"))

    def _tail(self):
        """(next_seq, prev_hash, last_sealed_zone). Repairs a torn final line (crash mid-write)."""
        segs = self.segments()
        if not segs:
            return 0, GENESIS, None
        path = segs[-1]
        data = path.read_bytes()
        if data and not data.endswith(b"\n"):
            cut = data.rfind(b"\n") + 1
            with open(path, "r+b") as f:
                f.truncate(cut)
                f.flush()
                os.fsync(f.fileno())
            data = data[:cut]
        lines = data.splitlines()
        if not lines:
            if len(segs) == 1:
                return 0, GENESIS, None
            prev = segs[-2].read_bytes().splitlines()[-1]
            rec = parse(prev)
            return rec["s"]["seq"] + 1, rec["h"], rec["s"]
        rec = parse(lines[-1])
        return rec["s"]["seq"] + 1, rec["h"], rec["s"]

    def _append(self, sealed: dict, notes: dict | None = None, sig: str | None = None) -> str:
        h = record_hash(sealed)
        line = {"h": h, "s": sealed}
        if notes is not None:
            line["n"] = notes
        if sig is not None:
            line["sig"] = sig
        data = canon(line) + b"\n"
        segs = self.segments()
        if not segs or segs[-1].stat().st_size >= self.max_segment_bytes:
            path = self.dir / f"seg-{sealed['seq']:012d}.jsonl"
            new = True
        else:
            path, new = segs[-1], False
        fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
        try:
            os.write(fd, data)
            os.fsync(fd)
        finally:
            os.close(fd)
        if new:
            dfd = os.open(self.dir, os.O_RDONLY)
            try:
                os.fsync(dfd)
            finally:
                os.close(dfd)
        return h

    def _base(self, kind: str, seq: int, prev: str, occurred_at: str) -> dict:
        return {"canon_version": CANON_VERSION, "chain_id": self.chain_id, "seq": seq,
                "prev_hash": prev, "kind": kind, "recorded_at": now_ts(), "occurred_at": occurred_at}

    def _resolve_dangling(self):
        seq, prev, last = self._tail()
        if last is not None and last["kind"] == "intent":
            s = self._base("failure", seq, prev, now_ts())
            s.update(gate_id=last["gate_id"], actor=self.actor,
                     detail="process ended before the outcome was written", failure_code="outcome_unwritten")
            prev = self._append(s)
            seq += 1
        return seq, prev

    # ---- the gate ------------------------------------------------------------------

    def _decide(self, policy_id: str, inputs, registry: dict[str, Policy]):
        """(decision, reason, detail, policy_version, policy_digest, inputs_digest). Never raises for a
        recordable fault; raises GateError only when no schema-valid record could describe it."""
        def inputs_digest():
            try:
                return digest(inputs), None
            except CanonError as e:
                return None, e.reason

        if not ID_RE.match(policy_id):
            raise GateError(f"policy_id {policy_id!r} is not a valid id; nothing can be recorded")
        if policy_id.split(".")[0] != self.consumer:
            d, bad = inputs_digest()
            if d is None:
                raise GateError(f"prefix mismatch and invalid inputs ({bad}): no valid record exists")
            return "deny", "policy_prefix_mismatch", f"{policy_id} belongs to another consumer", None, None, d
        pol = registry.get(policy_id)
        pol_digest = None
        if pol is not None:
            try:
                pol_digest = file_digest(pol.source)
            except OSError as e:
                pol = None
                unreadable = f"policy source unreadable: {type(e).__name__}"
        if pol is None:
            d, bad = inputs_digest()
            if d is None:
                raise GateError(f"unknown policy and invalid inputs ({bad}): no valid record exists")
            detail = unreadable if pol_digest is None and policy_id in registry else "no policy registered"
            return "deny", "policy_unknown", detail, None, None, d
        d, bad = inputs_digest()
        if d is None:
            return "deny", "inputs_invalid", bad, pol.version, pol_digest, None
        try:
            ok, detail = pol.fn(inputs)
        except Exception as e:                      # the policy raised: recorded deny, never allow
            return "deny", "policy_raised", type(e).__name__, pol.version, pol_digest, d
        if ok is True:
            return "allow", "policy_allowed", detail, pol.version, pol_digest, d
        return "deny", "policy_denied", detail, pol.version, pol_digest, d

    @contextmanager
    def gate(self, policy_id: str, subject: str, action: str, inputs, registry: dict[str, Policy],
             notes: dict | None = None):
        """Decide, record the intent, run the body only if allowed, record the outcome.

        Every recordable fault is a recorded deny. If the intent cannot be written, GateError is
        raised before the body runs. An exception in the body is recorded as result=raised and re-raised.
        """
        with self._locked():
            try:
                seq, prev = self._resolve_dangling()
                decided_at = now_ts()
                decision, reason, detail, pver, pdig, idig = self._decide(policy_id, inputs, registry)
                g = Gate(uuid.uuid4().hex, decision, reason, detail, seq)
                s = self._base("intent", seq, prev, decided_at)
                s.update(gate_id=g.gate_id, actor=self.actor, detail=detail, policy_id=policy_id,
                         subject=subject, action=action, decision=decision, reason=reason,
                         policy_version=pver, policy_digest=pdig, inputs_digest=idig)
                prev = self._append(s, notes)
            except GateError:
                raise
            except Exception as e:                  # could not record the intent: fail closed
                raise GateError(f"intent not recorded: {type(e).__name__}: {e}") from e

            result, out_detail = "skipped", detail
            try:
                if g.allowed:
                    yield g
                    result, out_detail = "ok", g.detail
                else:
                    yield g
            except BaseException as e:
                if g.allowed:
                    result, out_detail = "raised", type(e).__name__
                self._write_outcome(g, seq + 1, prev, result, out_detail)
                raise
            self._write_outcome(g, seq + 1, prev, result, out_detail)

    def _write_outcome(self, g: Gate, seq: int, prev: str, result: str, detail: str | None) -> None:
        s = self._base("outcome", seq, prev, now_ts())
        s.update(gate_id=g.gate_id, actor=self.actor, detail=detail, result=result)
        self._append(s)

    # ---- findings ------------------------------------------------------------------

    def record_finding(self, subject: str, finding_type: str, claim: str, evidence,
                       detail: str | None = None, occurred_at: str | None = None) -> dict:
        """Append a `finding`: a sourced claim that is not a gated action (proc_track, pdx-1i).

        `evidence` is any canonical value. It is written to <chain_dir>/evidence/<hex>.json in
        canonical form (fsynced before the record), and the record binds it by evidence_digest.
        Raises CanonError if the evidence is not canonical and ValueError for a malformed type;
        nothing is written in either case.
        """
        if not ID_RE.match(finding_type) or finding_type.split(".")[0] != self.consumer:
            raise ValueError(f"finding_type {finding_type!r} must be a dotted id under {self.consumer!r}")
        if not subject or not claim:
            raise ValueError("subject and claim must be non-empty")
        body = canon(evidence)                        # raises CanonError before anything is written
        ev_digest = "sha256:" + hashlib.sha256(body).hexdigest()
        ev_dir = self.dir / "evidence"
        ev_dir.mkdir(exist_ok=True)
        ev_path = ev_dir / f"{ev_digest[7:]}.json"
        if not ev_path.exists():
            tmp = ev_dir / f".{ev_digest[7:]}.tmp"
            with open(tmp, "wb") as f:
                f.write(body)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, ev_path)
            dfd = os.open(ev_dir, os.O_RDONLY)
            try:
                os.fsync(dfd)
            finally:
                os.close(dfd)
        with self._locked():
            seq, prev = self._resolve_dangling()
            s = self._base("finding", seq, prev, occurred_at or now_ts())
            s.update(actor=self.actor, subject=subject, finding_type=finding_type, claim=claim,
                     evidence_digest=ev_digest, detail=detail)
            h = self._append(s)
        return {"seq": seq, "h": h, "evidence_digest": ev_digest}

    # ---- sealing -------------------------------------------------------------------

    def seal(self, private_key) -> dict:
        """Append a signed seal (Ed25519 via `cryptography`), update HEAD, return the anchor to publish."""
        from cryptography.hazmat.primitives import serialization

        pub = private_key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
        with self._locked():
            seq, prev = self._resolve_dangling()
            s = self._base("seal", seq, prev, now_ts())
            s["key_id"] = key_id_of(pub)
            sig = private_key.sign(SEAL_DOMAIN + canon(s)).hex()
            h = self._append(s, sig=sig)
            head = canon({"h": h, "s": s, "sig": sig}) + b"\n"
            tmp = self.dir / "HEAD.tmp"
            with open(tmp, "wb") as f:
                f.write(head)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, self.dir / "HEAD")
            return {"chain_id": self.chain_id, "seq": seq, "h": h, "sig": sig}


def load_private_key(path: str | os.PathLike):
    from cryptography.hazmat.primitives import serialization
    return serialization.load_pem_private_key(Path(path).read_bytes(), password=None)


def generate_key(path: str | os.PathLike) -> tuple[str, str]:
    """Write a new Ed25519 private key (PEM, 0600). Returns (key_id, public key hex)."""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    k = Ed25519PrivateKey.generate()
    pem = k.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                          serialization.NoEncryption())
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(pem)
    pub = k.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    return key_id_of(pub), pub.hex()
