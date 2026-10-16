// gp_verify.js: Gatepost gp-canon/1 chain verifier for the browser (and Node >= 20).
//
// A third independent implementation, after gpcanon/verify.py and spec/ref/gp_canon.mjs.
// The canonical-form, parser and schema code is carried over from spec/ref/gp_canon.mjs
// (written from CANON.md / SCHEMA.md); Node's Buffer/crypto are swapped for TextEncoder,
// WebCrypto SHA-256 and WebCrypto Ed25519. verifyChain() mirrors verify_chain() in
// gpcanon/verify.py rule for rule and returns the same codes and exit code
// (0 pass, 1 chain, 2 signature, 3 malformed, 4 key, 5 nothing pinned).
//
// No network, no dependencies. Exposes globalThis.GPVerify.
(function (root) {
  "use strict";
  const CANON_VERSION = "gp-canon/1";
  const GENESIS = "0".repeat(64);
  const SEAL_DOMAIN = "gatepost/seal/v1\n";
  const MAX = 9007199254740991n;
  const enc = new TextEncoder();
  const dec = new TextDecoder("utf-8", { fatal: true });

  class CanonError extends Error {
    constructor(code, detail = "") { super(detail ? `${code}: ${detail}` : code); this.code = code; }
  }

  // ---------------------------------------------------------------- strict parser
  function strictParse(text) {
    let i = 0;
    const fail = (code, d) => { throw new CanonError(code, d ?? `at ${i}`); };
    const ws = () => { while (i < text.length && " \t\n\r".includes(text[i])) i++; };
    function value() {
      ws();
      const c = text[i];
      if (c === "{") return object();
      if (c === "[") return array();
      if (c === '"') return string();
      if (c === "-" || (c >= "0" && c <= "9")) return number();
      for (const [lit, v] of [["true", true], ["false", false], ["null", null]]) {
        if (text.startsWith(lit, i)) { i += lit.length; return v; }
      }
      fail("bad_json");
    }
    function object() {
      i++; const o = new Map(); ws();
      if (text[i] === "}") { i++; return o; }
      for (;;) {
        ws(); if (text[i] !== '"') fail("bad_json");
        const k = string(); ws();
        if (text[i] !== ":") fail("bad_json"); i++;
        const v = value();
        if (o.has(k)) fail("dup_key", k);
        o.set(k, v); ws();
        if (text[i] === ",") { i++; continue; }
        if (text[i] === "}") { i++; return o; }
        fail("bad_json");
      }
    }
    function array() {
      i++; const a = []; ws();
      if (text[i] === "]") { i++; return a; }
      for (;;) {
        a.push(value()); ws();
        if (text[i] === ",") { i++; continue; }
        if (text[i] === "]") { i++; return a; }
        fail("bad_json");
      }
    }
    function string() {
      i++; let s = "";
      for (;;) {
        if (i >= text.length) fail("bad_json");
        const c = text[i];
        const cu = c.charCodeAt(0);
        if (c === '"') { i++; break; }
        if (cu < 0x20) fail("bad_json", "raw control character");
        if (c === "\\") {
          const e = text[i + 1];
          const map = { '"': '"', "\\": "\\", "/": "/", b: "\b", f: "\f", n: "\n", r: "\r", t: "\t" };
          if (e in map) { s += map[e]; i += 2; continue; }
          if (e === "u") {
            const h = text.slice(i + 2, i + 6);
            if (!/^[0-9a-fA-F]{4}$/.test(h)) fail("bad_json");
            s += String.fromCharCode(parseInt(h, 16)); i += 6; continue;
          }
          fail("bad_json");
        }
        s += c; i++;
      }
      return s;
    }
    function number() {
      const m = /^-?(0|[1-9][0-9]*)(\.[0-9]+)?([eE][+-]?[0-9]+)?/.exec(text.slice(i, i + 400));
      if (!m) fail("bad_json");
      i += m[0].length;
      if (m[2] || m[3]) fail("float", m[0]);
      if (m[0] === "-0") fail("neg_zero");
      const b = BigInt(m[0]);
      if (b > MAX || b < -MAX) fail("int_range", m[0]);
      return Number(b);
    }
    const v = value(); ws();
    if (i !== text.length) fail("bad_json", "trailing data");
    walkStrings(v);
    return v;
  }

  function checkStr(s) {
    for (let k = 0; k < s.length; k++) {
      const u = s.charCodeAt(k);
      if (u >= 0xd800 && u <= 0xdbff) {
        const n = s.charCodeAt(k + 1);
        if (!(n >= 0xdc00 && n <= 0xdfff)) throw new CanonError("lone_surrogate");
        k++;
      } else if (u >= 0xdc00 && u <= 0xdfff) throw new CanonError("lone_surrogate");
    }
    if (s.normalize("NFC") !== s) throw new CanonError("non_nfc", JSON.stringify(s));
  }
  function walkStrings(v) {
    if (typeof v === "string") checkStr(v);
    else if (Array.isArray(v)) v.forEach(walkStrings);
    else if (v instanceof Map) for (const [k, x] of v) { checkStr(k); walkStrings(x); }
  }

  // ---------------------------------------------------------------- canonical bytes
  function esc(s) {
    let o = '"';
    for (const ch of s) {
      const c = ch.codePointAt(0);
      if (ch === '"') o += '\\"';
      else if (ch === "\\") o += "\\\\";
      else if (c === 8) o += "\\b";
      else if (c === 12) o += "\\f";
      else if (c === 10) o += "\\n";
      else if (c === 13) o += "\\r";
      else if (c === 9) o += "\\t";
      else if (c < 0x20) o += "\\u" + c.toString(16).padStart(4, "0");
      else o += ch;
    }
    return o + '"';
  }
  function byUtf8(a, b) {
    const x = enc.encode(a), y = enc.encode(b);
    const n = Math.min(x.length, y.length);
    for (let k = 0; k < n; k++) if (x[k] !== y[k]) return x[k] - y[k];
    return x.length - y.length;
  }
  function canonStr(v) {
    if (v === null) return "null";
    if (v === true) return "true";
    if (v === false) return "false";
    if (typeof v === "number") {
      if (!Number.isSafeInteger(v) || Object.is(v, -0)) throw new CanonError("float", String(v));
      return String(v);
    }
    if (typeof v === "string") { checkStr(v); return esc(v); }
    if (Array.isArray(v)) return "[" + v.map(canonStr).join(",") + "]";
    const m = v instanceof Map ? v : new Map(Object.entries(v));
    const keys = [...m.keys()];
    keys.forEach(checkStr);
    keys.sort(byUtf8);
    return "{" + keys.map((k) => esc(k) + ":" + canonStr(m.get(k))).join(",") + "}";
  }
  const canon = (v) => enc.encode(canonStr(v));

  const hex = (buf) => Array.from(new Uint8Array(buf), (b) => b.toString(16).padStart(2, "0")).join("");
  const fromHex = (h) => {
    const out = new Uint8Array(h.length / 2);
    for (let k = 0; k < out.length; k++) out[k] = parseInt(h.substr(k * 2, 2), 16);
    return out;
  };
  const subtle = () => {
    const c = root.crypto && root.crypto.subtle;
    if (!c) throw new Error("This browser has no WebCrypto; use verify.py instead.");
    return c;
  };
  async function sha256hex(bytes) { return hex(await subtle().digest("SHA-256", bytes)); }
  function sameBytes(a, b) {
    if (a.length !== b.length) return false;
    for (let k = 0; k < a.length; k++) if (a[k] !== b[k]) return false;
    return true;
  }

  // ---------------------------------------------------------------- schema (SCHEMA §3-4)
  const COMMON = ["canon_version", "chain_id", "seq", "prev_hash", "kind", "recorded_at", "occurred_at"];
  const SHAPE = {
    intent: [...COMMON, "gate_id", "policy_id", "policy_version", "policy_digest", "subject", "action",
      "inputs_digest", "decision", "reason", "detail", "actor"],
    outcome: [...COMMON, "gate_id", "result", "detail", "actor"],
    failure: [...COMMON, "gate_id", "failure_code", "detail", "actor"],
    seal: [...COMMON, "key_id"],
    finding: [...COMMON, "actor", "subject", "finding_type", "claim", "evidence_digest", "detail"],
  };
  const MAYBE_NULL = new Set(["policy_version", "policy_digest", "inputs_digest", "detail"]);
  const DOTTED = /^[a-z0-9][a-z0-9_-]*(\.[a-z0-9][a-z0-9_-]*)+$/;
  const str = (v) => typeof v === "string";
  function timestampOk(v) {
    if (!str(v)) return false;
    const m = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})\.(\d{6})Z$/.exec(v);
    if (!m) return false;
    const [y, mo, d, h, mi, se] = m.slice(1, 7).map(Number);
    if (y < 1 || mo < 1 || mo > 12 || h > 23 || mi > 59 || se > 59) return false;
    const leap = (y % 4 === 0 && y % 100 !== 0) || y % 400 === 0;
    const dim = [31, leap ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][mo - 1];
    return d >= 1 && d <= dim;
  }
  const CHECK = {
    chain_id: (v) => str(v) && DOTTED.test(v),
    policy_id: (v) => str(v) && DOTTED.test(v),
    finding_type: (v) => str(v) && DOTTED.test(v),
    seq: (v) => typeof v === "number" && Number.isSafeInteger(v) && v >= 0,
    prev_hash: (v) => str(v) && /^[0-9a-f]{64}$/.test(v),
    kind: (v) => typeof v === "string" && Object.prototype.hasOwnProperty.call(SHAPE, v),
    recorded_at: timestampOk,
    occurred_at: timestampOk,
    gate_id: (v) => str(v) && /^[0-9a-f]{32}$/.test(v),
    policy_version: (v) => str(v) && /^[A-Za-z0-9._+-]{1,64}$/.test(v),
    policy_digest: (v) => str(v) && /^sha256:[0-9a-f]{64}$/.test(v),
    inputs_digest: (v) => str(v) && /^sha256:[0-9a-f]{64}$/.test(v),
    evidence_digest: (v) => str(v) && /^sha256:[0-9a-f]{64}$/.test(v),
    subject: (v) => str(v) && v.length > 0,
    action: (v) => str(v) && v.length > 0,
    actor: (v) => str(v) && v.length > 0,
    claim: (v) => str(v) && v.length > 0,
    decision: (v) => v === "allow" || v === "deny",
    reason: (v) => ["policy_allowed", "policy_denied", "policy_unknown", "policy_raised",
      "policy_prefix_mismatch", "inputs_invalid"].includes(v),
    detail: str,
    result: (v) => ["ok", "raised", "skipped"].includes(v),
    failure_code: (v) => v === "outcome_unwritten",
    key_id: (v) => str(v) && /^[0-9a-f]{16}$/.test(v),
  };
  function validateSealed(s) {
    if (!(s instanceof Map)) return ["bad_field"];
    if (!s.has("kind")) return ["missing_field"];
    const kind = s.get("kind");
    if (typeof kind !== "string" || !Object.prototype.hasOwnProperty.call(SHAPE, kind)) return ["bad_field"];
    const want = SHAPE[kind];
    const e = new Set();
    if (s.has("canon_version") && s.get("canon_version") !== CANON_VERSION) e.add("canon_version_unsupported");
    for (const f of want) if (!s.has(f)) e.add("missing_field");
    for (const f of s.keys()) if (!want.includes(f)) e.add("unknown_field");
    for (const f of want) {
      if (f === "canon_version" || !s.has(f)) continue;
      const v = s.get(f);
      if (v === null) { if (!MAYBE_NULL.has(f)) e.add("null_not_allowed"); continue; }
      if (!CHECK[f](v)) e.add("bad_field");
    }
    if (kind === "intent" && e.size === 0) {
      const g = (f) => s.get(f);
      if ((g("decision") === "allow") !== (g("reason") === "policy_allowed")) e.add("decision_reason_mismatch");
      const noPolicy = ["policy_unknown", "policy_prefix_mismatch"].includes(g("reason"));
      for (const f of ["policy_version", "policy_digest"]) {
        if (noPolicy && g(f) !== null) e.add("null_required");
        if (!noPolicy && g(f) === null) e.add("null_not_allowed");
      }
      const invalid = g("reason") === "inputs_invalid";
      if (invalid && g("inputs_digest") !== null) e.add("null_required");
      if (!invalid && g("inputs_digest") === null) e.add("null_not_allowed");
      const samePrefix = g("policy_id").split(".")[0] === g("chain_id").split(".")[0];
      if ((g("reason") === "policy_prefix_mismatch") === samePrefix) e.add("policy_prefix_mismatch");
    }
    if (kind === "finding" && e.size === 0) {
      if (s.get("finding_type").split(".")[0] !== s.get("chain_id").split(".")[0]) e.add("type_prefix_mismatch");
    }
    return [...e].sort();
  }

  // ---------------------------------------------------------------- seal signature
  async function sealVerify(pubHex, sealed, sigHex) {
    const key = await subtle().importKey("raw", fromHex(pubHex), { name: "Ed25519" }, false, ["verify"]);
    const body = canon(sealed);
    const dom = enc.encode(SEAL_DOMAIN);
    const msg = new Uint8Array(dom.length + body.length);
    msg.set(dom, 0); msg.set(body, dom.length);
    return subtle().verify({ name: "Ed25519" }, key, fromHex(sigHex), msg);
  }

  // ---------------------------------------------------------------- report (verify.py Report)
  const MALFORMED = new Set(["float", "neg_zero", "int_range", "dup_key", "non_nfc", "lone_surrogate", "bad_json",
    "bad_type", "line_key_invalid", "missing_field", "unknown_field", "bad_field",
    "null_not_allowed", "null_required", "decision_reason_mismatch", "policy_prefix_mismatch",
    "canon_version_unsupported", "torn_line", "type_prefix_mismatch"]);
  const CHAIN = new Set(["seal_backdated", "hash_mismatch", "prev_mismatch", "seq_gap", "seq_duplicate",
    "chain_id_mismatch", "line_not_canonical", "unpaired", "pairing_invalid", "policy_digest_mismatch",
    "truncated_tail", "anchor_mismatch", "evidence_mismatch"]);
  const SIGNATURE = new Set(["sig_missing", "sig_forbidden", "bad_signature"]);
  const KEY = new Set(["key_id_mismatch", "key_outside_window"]);
  const NOTICE = new Set(["unsealed_tail", "tail_unanchored", "unpinned", "dangling_intent", "notes_unverified",
    "seals_unverified", "evidence_absent"]);

  class Report {
    constructor() { this.findings = []; this.records = 0; this.seals = 0; this.lastSealSeq = null; this.head = null; }
    add(code, seq, detail = "") { this.findings.push({ code, seq, detail }); }
    codes() { return new Set(this.findings.map((f) => f.code)); }
    exitCode() {
      const c = this.codes();
      for (const [group, code] of [[MALFORMED, 3], [CHAIN, 1], [SIGNATURE, 2], [KEY, 4]]) {
        for (const x of c) if (group.has(x)) return code;
      }
      return c.has("unpinned") ? 5 : 0;
    }
  }

  async function keyIdOf(pubHex) { return (await sha256hex(fromHex(pubHex))).slice(0, 16); }

  // pack: { segments: [{name, bytes: Uint8Array}], evidence: Map<hex, Uint8Array> }
  // opts: { pubkeys: [hex], anchor: object|null, policies: {policy_id: Uint8Array}, chainId, allowUnpinned }
  async function verifyChain(pack, opts = {}) {
    const rep = new Report();
    const pubkeys = new Map();
    for (const p of opts.pubkeys || []) pubkeys.set(await keyIdOf(p), p);
    const policyDigests = new Map();
    for (const [pid, bytes] of Object.entries(opts.policies || {})) policyDigests.set(pid, "sha256:" + await sha256hex(bytes));
    let chainId = opts.chainId ?? null;
    const anchor = opts.anchor ?? null;
    let lastSealAt = null;
    let expectSeq = 0, prev = GENESIS;
    const hashes = new Map();
    let openIntent = null;

    const segs = [...pack.segments].filter((s) => /^seg-.*\.jsonl$/.test(s.name)).sort((a, b) => (a.name < b.name ? -1 : a.name > b.name ? 1 : 0));
    if (!segs.length) rep.add("bad_json", null, "no segments");
    for (const seg of segs) {
      const data = seg.bytes;
      const parts = [];
      let start = 0;
      for (let k = 0; k < data.length; k++) if (data[k] === 10) { parts.push(data.subarray(start, k)); start = k + 1; }
      const tail = data.subarray(start);
      if (tail.length) rep.add("torn_line", null, `${seg.name}: final line has no newline (crash mid-write?)`);
      for (const raw of parts) {
        let line;
        try { line = strictParse(dec.decode(raw)); } catch (e) {
          rep.add(e instanceof CanonError ? e.code : "bad_json", null, `${seg.name}: ${e.message}`);
          continue;
        }
        const keys = line instanceof Map ? [...line.keys()] : [];
        if (!(line instanceof Map) || !line.has("h") || !line.has("s") || !keys.every((k) => ["h", "s", "n", "sig"].includes(k))) {
          rep.add("line_key_invalid", null, `${seg.name}: keys ${keys.sort().join(",")}`);
          continue;
        }
        const s = line.get("s"), h = line.get("h");
        const seq = s instanceof Map ? s.get("seq") ?? null : null;
        rep.records += 1;
        const errs = validateSealed(s);
        for (const code of errs) rep.add(code, seq);
        if (errs.length) continue;
        if (!sameBytes(canon(line), raw)) rep.add("line_not_canonical", seq);
        if (await sha256hex(canon(s)) !== h) rep.add("hash_mismatch", seq, "record altered after it was written");
        if (chainId === null) chainId = s.get("chain_id");
        if (s.get("chain_id") !== chainId) rep.add("chain_id_mismatch", seq, `${s.get("chain_id")} in chain ${chainId}`);
        if (hashes.has(seq)) rep.add("seq_duplicate", seq);
        else if (seq !== expectSeq) rep.add("seq_gap", seq, `expected ${expectSeq}`);
        if (s.get("prev_hash") !== prev) rep.add("prev_mismatch", seq, "record deleted, inserted or reordered before this one");
        hashes.set(seq, h);
        prev = h; expectSeq = seq + 1;
        if (line.has("n")) rep.add("notes_unverified", seq, "notes sit outside the hash");

        const kind = s.get("kind");
        if (kind === "seal") {
          if (!line.has("sig")) rep.add("sig_missing", seq);
          else {
            rep.seals += 1; rep.lastSealSeq = seq;
            const sig = line.get("sig");
            if (!(typeof sig === "string" && /^[0-9a-f]{128}$/.test(sig))) rep.add("bad_signature", seq, "sig is not 128 lowercase hex");
            else if (pubkeys.size) {
              const pub = pubkeys.get(s.get("key_id"));
              if (pub === undefined) rep.add("key_id_mismatch", seq, `sealed by ${s.get("key_id")}, pinned ${[...pubkeys.keys()].sort().join(",")}`);
              else if (!(await sealVerify(pub, s, sig))) rep.add("bad_signature", seq, "seal signature does not verify");
            }
            if (lastSealAt && s.get("recorded_at") < lastSealAt) rep.add("seal_backdated", seq, `sealed at ${s.get("recorded_at")}, before an earlier seal (${lastSealAt})`);
            lastSealAt = lastSealAt && lastSealAt > s.get("recorded_at") ? lastSealAt : s.get("recorded_at");
          }
          if (openIntent) rep.add("pairing_invalid", seq, "seal written while an intent was open");
        } else if (line.has("sig")) rep.add("sig_forbidden", seq);

        if (kind === "intent") {
          if (openIntent) rep.add("unpaired", openIntent[2], "intent has no outcome before the next intent");
          openIntent = [s.get("gate_id"), s.get("decision"), seq];
          const pol = policyDigests.get(s.get("policy_id"));
          if (pol && s.get("policy_digest") !== null && s.get("policy_digest") !== pol) {
            rep.add("policy_digest_mismatch", seq, `${s.get("policy_id")}: recorded digest differs from given file`);
          }
        } else if (kind === "finding") {
          if (openIntent) rep.add("pairing_invalid", seq, "finding written while an intent was open");
          await checkEvidence(pack, s, rep);
        } else if (kind === "outcome" || kind === "failure") {
          if (!openIntent || openIntent[0] !== s.get("gate_id")) rep.add("pairing_invalid", seq, `${kind} without its intent`);
          else if (kind === "outcome") {
            const ok = { allow: ["ok", "raised"], deny: ["skipped"] }[openIntent[1]];
            if (!ok.includes(s.get("result"))) rep.add("pairing_invalid", seq, `${openIntent[1]} followed by result=${s.get("result")}`);
          }
          openIntent = null;
        }
      }
    }
    const last = expectSeq - 1;
    rep.head = last >= 0 ? { seq: last, h: prev } : null;
    if (openIntent) rep.add("dangling_intent", openIntent[2], "no outcome yet: action in progress or process died");
    if (rep.lastSealSeq === null || rep.lastSealSeq < last) {
      const n = last - (rep.lastSealSeq !== null ? rep.lastSealSeq : -1);
      if (n > 0) rep.add("unsealed_tail", last, `${n} record(s) after the last seal`);
    }
    if (anchor) {
      const aSeq = anchor.seq;
      if (anchor.chain_id !== chainId) rep.add("anchor_mismatch", aSeq, "anchor is for another chain");
      else if (!hashes.has(aSeq)) rep.add("truncated_tail", aSeq, `chain ends at seq ${last}, anchor is at ${aSeq}`);
      else if (hashes.get(aSeq) !== anchor.h) rep.add("anchor_mismatch", aSeq, "hash at the anchored seq differs");
    } else rep.add("tail_unanchored", last, `truncation after seq ${rep.lastSealSeq} not detectable`);
    const allow = !!opts.allowUnpinned;
    if (rep.seals === 0 && !allow) rep.add("unpinned", null, "no seals: nothing is signed, so the whole chain could be rewritten");
    else if (rep.seals && !pubkeys.size && !allow) rep.add("unpinned", null, "seals present but no key pinned: signatures NOT verified");
    else if (!pubkeys.size || rep.seals === 0) rep.add("seals_unverified", null, "allow-unpinned: integrity shown only against whoever can edit the files");
    return { exit: rep.exitCode(), records: rep.records, seals: rep.seals, head: rep.head, findings: rep.findings,
      notice: (code) => NOTICE.has(code) };
  }

  async function checkEvidence(pack, s, rep) {
    const digest = s.get("evidence_digest");
    const data = pack.evidence.get(digest.slice(7));
    if (!data) { rep.add("evidence_absent", s.get("seq"), "evidence file not in this pack; claim is bound but not inspectable"); return; }
    if ("sha256:" + await sha256hex(data) !== digest) {
      rep.add("evidence_mismatch", s.get("seq"), "evidence file does not match the digest in the record");
      return;
    }
    try {
      if (!sameBytes(canon(strictParse(dec.decode(data))), data)) rep.add("evidence_mismatch", s.get("seq"), "evidence file is not canonical");
    } catch (e) {
      rep.add("evidence_mismatch", s.get("seq"), `evidence file is not gp-canon/1 JSON: ${e.code || e.message}`);
    }
  }

  // ---------------------------------------------------------------- zip reader (stored + deflate)
  async function inflateRaw(bytes) {
    const ds = new DecompressionStream("deflate-raw");
    const out = new Response(new Blob([bytes]).stream().pipeThrough(ds));
    return new Uint8Array(await out.arrayBuffer());
  }
  async function readZip(buf) {
    const b = new Uint8Array(buf), dv = new DataView(b.buffer, b.byteOffset, b.byteLength);
    let eocd = -1;
    for (let k = b.length - 22; k >= Math.max(0, b.length - 65557); k--) if (dv.getUint32(k, true) === 0x06054b50) { eocd = k; break; }
    if (eocd < 0) throw new Error("not a zip file");
    const count = dv.getUint16(eocd + 10, true);
    let p = dv.getUint32(eocd + 16, true);
    const files = new Map();
    for (let n = 0; n < count; n++) {
      if (dv.getUint32(p, true) !== 0x02014b50) throw new Error("zip central directory is damaged");
      const method = dv.getUint16(p + 10, true), csize = dv.getUint32(p + 20, true);
      const nlen = dv.getUint16(p + 28, true), xlen = dv.getUint16(p + 30, true), clen = dv.getUint16(p + 32, true);
      const local = dv.getUint32(p + 42, true);
      const name = dec.decode(b.subarray(p + 46, p + 46 + nlen));
      p += 46 + nlen + xlen + clen;
      if (name.endsWith("/")) continue;
      const lstart = local + 30 + dv.getUint16(local + 26, true) + dv.getUint16(local + 28, true);
      const raw = b.subarray(lstart, lstart + csize);
      if (method === 0) files.set(name, raw.slice());
      else if (method === 8) files.set(name, await inflateRaw(raw));
      else throw new Error(`zip entry ${name} uses unsupported compression ${method}`);
    }
    return files;
  }
  // Turn {path: bytes} (from a zip or a folder) into a pack.
  function packFromFiles(files) {
    const segments = [], evidence = new Map();
    for (const [path, bytes] of files) {
      const parts = path.split("/"), base = parts[parts.length - 1];
      if (parts.length >= 2 && parts[parts.length - 2] === "evidence" && /^[0-9a-f]{64}\.json$/.test(base)) evidence.set(base.slice(0, 64), bytes);
      else if (/^seg-.*\.jsonl$/.test(base)) segments.push({ name: base, bytes });
    }
    return { segments, evidence };
  }

  root.GPVerify = { verifyChain, readZip, packFromFiles, strictParse, canon, validateSealed, sealVerify, sha256hex, keyIdOf, CanonError };
})(typeof window !== "undefined" ? window : globalThis);
