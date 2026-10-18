"""gp-canon/1 value model, strict parser and canonical bytes (CANON §1–3, §6–7). Stdlib only.

The verifier imports this module; it must never gain a third-party dependency.
"""
from __future__ import annotations

import hashlib
import json
import math
import unicodedata
from decimal import ROUND_HALF_EVEN, Decimal

CANON_VERSION = "gp-canon/1"
INT_MAX = 2**53 - 1
GENESIS = "0" * 64


class CanonError(ValueError):
    """Raised with one of the CANON §7 reason codes."""

    def __init__(self, reason: str, detail: str = ""):
        super().__init__(f"{reason}: {detail}" if detail else reason)
        self.reason = reason


# ---------- producer side: canonical bytes ------------------------------------------

_ESC = {'"': '\\"', "\\": "\\\\", "\b": "\\b", "\f": "\\f", "\n": "\\n", "\r": "\\r", "\t": "\\t"}


def _check_str(s: str) -> None:
    try:
        s.encode("utf-8")
    except UnicodeEncodeError:
        raise CanonError("lone_surrogate") from None
    if not unicodedata.is_normalized("NFC", s):
        raise CanonError("non_nfc", repr(s[:40]))


def _str(s: str) -> str:
    _check_str(s)
    out = []
    for ch in s:
        e = _ESC.get(ch)
        if e is not None:
            out.append(e)
        elif ord(ch) < 0x20:
            out.append(f"\\u{ord(ch):04x}")
        else:
            out.append(ch)
    return '"' + "".join(out) + '"'


def _ser(v, out: list) -> None:
    if v is None:
        out.append("null")
    elif v is True:
        out.append("true")
    elif v is False:
        out.append("false")
    elif isinstance(v, int):
        if not -INT_MAX <= v <= INT_MAX:
            raise CanonError("int_range", str(v))
        out.append(str(v))
    elif isinstance(v, float):
        raise CanonError("float", repr(v))
    elif isinstance(v, str):
        out.append(_str(v))
    elif isinstance(v, (list, tuple)):
        out.append("[")
        for i, x in enumerate(v):
            if i:
                out.append(",")
            _ser(x, out)
        out.append("]")
    elif isinstance(v, dict):
        for k in v:
            if not isinstance(k, str):
                raise CanonError("bad_type", f"object key {k!r}")
            _check_str(k)
        out.append("{")
        for i, k in enumerate(sorted(v, key=lambda k: k.encode("utf-8"))):   # code point order
            if i:
                out.append(",")
            out.append(_str(k))
            out.append(":")
            _ser(v[k], out)
        out.append("}")
    else:
        raise CanonError("bad_type", type(v).__name__)


def canon(v) -> bytes:
    out: list[str] = []
    _ser(v, out)
    return "".join(out).encode("utf-8")


def sha256_hex(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def record_hash(sealed: dict) -> str:
    return sha256_hex(canon(sealed))


def digest(v) -> str:
    """'sha256:' + hex of canon(v). Used for inputs_digest."""
    return "sha256:" + sha256_hex(canon(v))


def file_digest(path) -> str:
    with open(path, "rb") as f:
        return "sha256:" + hashlib.sha256(f.read()).hexdigest()


def decimal_from_float(x, places: int) -> str:
    """The one sanctioned float -> decimal-string conversion (CANON §6)."""
    if isinstance(x, bool) or not isinstance(x, (int, float)):
        raise CanonError("bad_type", type(x).__name__)
    if isinstance(x, float) and not math.isfinite(x):
        raise CanonError("non_finite", repr(x))
    if isinstance(places, bool) or not isinstance(places, int) or not 0 <= places <= 18:
        raise CanonError("bad_places", repr(places))
    d = Decimal(repr(x)) if isinstance(x, float) else Decimal(x)
    q = d.quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_EVEN)
    if q.is_zero():
        q = q.copy_abs()
    return format(q, "f")


def nfc(v):
    """Producer-boundary normalisation: NFC every string (keys and values), recursively.

    Call this on data you own before handing it to canon(). Verifiers must never call it.
    """
    if isinstance(v, str):
        return unicodedata.normalize("NFC", v)
    if isinstance(v, list):
        return [nfc(x) for x in v]
    if isinstance(v, dict):
        return {unicodedata.normalize("NFC", k): nfc(x) for k, x in v.items()}
    return v


# ---------- verifier side: strict parse --------------------------------------------

def _reject_float(s):
    raise CanonError("float", s)


def _parse_int(s: str) -> int:
    if s == "-0":
        raise CanonError("neg_zero")
    n = int(s)
    if not -INT_MAX <= n <= INT_MAX:
        raise CanonError("int_range", s)
    return n


def _reject_constant(s):
    raise CanonError("bad_json", s)


def _pairs(pairs):
    d = {}
    for k, v in pairs:
        if k in d:
            raise CanonError("dup_key", repr(k))
        d[k] = v
    return d


def _walk_strings(v):
    if isinstance(v, str):
        _check_str(v)
    elif isinstance(v, list):
        for x in v:
            _walk_strings(x)
    elif isinstance(v, dict):
        for k, x in v.items():
            _check_str(k)
            _walk_strings(x)


def parse(data: bytes | str):
    """Strict RFC 8259 parse into the gp-canon/1 value model, or CanonError with a CANON §2 reason."""
    if isinstance(data, bytes):
        if data.startswith(b"\xef\xbb\xbf"):
            raise CanonError("bad_json", "BOM")
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError as e:
            # UTF-8-encoded surrogates (ED A0..BF xx) are raw lone surrogates; anything else is bad JSON.
            bad = data[e.start:e.start + 2]
            if len(bad) == 2 and bad[0] == 0xED and 0xA0 <= bad[1] <= 0xBF:
                raise CanonError("lone_surrogate") from None
            raise CanonError("bad_json", "invalid UTF-8") from None
    else:
        text = data
        if text.startswith("﻿"):
            raise CanonError("bad_json", "BOM")
    try:
        v = json.loads(text, parse_float=_reject_float, parse_int=_parse_int,
                       parse_constant=_reject_constant, object_pairs_hook=_pairs)
    except CanonError:
        raise
    except (json.JSONDecodeError, RecursionError, ValueError) as e:
        raise CanonError("bad_json", str(e)[:80]) from None
    _walk_strings(v)
    return v
