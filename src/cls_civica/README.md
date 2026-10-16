# cls_civica — Oregon Legislature, Verified

**Notitia Civica's public layer.** Every Oregon bill, in plain language, with a
record anyone can check offline. Built for the Governor's two asks: the
legislature *understood and accessible*, and the public record *secure*.

It joins the three CLS-1000 projects:

| Repo | Role here |
|---|---|
| **proc_track** | Replays each bill's official action history (Oregon OData `MeasureHistoryActions`) and proves every step was a legal move under chamber procedure. Anything it can't explain halts. |
| **SPEC-1** (`cls_civica`) | Turns each replay into a plain-language card: what happened, when, where it stands. Every sentence cites the official rows it rests on. |
| **Gatepost** (`gpcanon`, vendored in `vendor/`, pinned to gatepost `d2efca9`) | Records each card as a `finding` with the exact rows as evidence, runs the publication gate, and seals the chain (Ed25519). `verify.py` checks the whole site offline without trusting the publisher. |

## Run it

```bash
# proc_track next to spec-1 (or set SPEC1_PROC_TRACK_HOME); gpcanon is vendored in vendor/
git clone https://github.com/CLS-1000/proc_track ../proc_track
pip install cryptography

# preview with a throwaway key
PYTHONPATH=src python -m cls_civica build --session 2025R1 --out out/civica_2025R1 --demo-key

# real build with your Gatepost operator key (python3 ../gatepost/tools/gp_operator.py keygen)
PYTHONPATH=src python -m cls_civica build --session 2025R1 --out out/civica_2025R1 --key ~/.gatepost/op_key.pem

# check it (what any recipient does)
PYTHONPATH=src python -m cls_civica verify out/civica_2025R1 --pubkey <your published public key hex>

# optional, needs network: measure titles, which turn on the Elections & voting topic
PYTHONPATH=src python -m cls_civica titles --session 2025R1
```

Fresh data: `python ../proc_track/scripts/fetch_session.py 2025R1`, then
`python ../proc_track/scripts/check.py` (must exit 0) before building.

Output: `out/<name>/site/` is the whole public site (one `index.html`, per-bill
JSON in `cards/`, and the verification kit in `verify/`). `out/<name>/chain/`
is the sealed record. The chain is append-only: build into a new directory.

## The chain (`civica.publish`, gp-canon/1)

Per measure: `finding civica.measure_card` (card + official rows + replay
result + the proc_track rule-set digest) → `intent civica.publish_card`
(allow/deny under `policy.py`) → `outcome` (card written, or withheld). Then a
`civica.session_summary` finding and a seal. A denied card is recorded and
listed as withheld, never dropped silently.

`policy.py` is the publication gate. It checks accountability only (every
claim cites rows present in the sealed evidence; source is the official API;
unverified histories are labelled as such). It does not check tone
(DESIGN_INTENT §4). Its file hash is in every intent, so loosening it is
detectable (`--policy civica.publish_card=policy.py`).

## What it does not do

It proves the site matches what was recorded from the Legislature's public
data and that nothing changed afterward. It does not prove the Legislature's
data is error-free (see gatepost/docs/CASE_STUDY_OREGON.md), and it is not part
of casting or counting ballots, which county elections offices and the
Secretary of State run.

## 2025R1 results (demo build, 2026-10-14)

3,466 measures · 10,400 records · 0 withheld · 0 unverified ·
633 became law · 7 vetoed (matches the Gatepost veto pack exactly) ·
56 proposed constitutional amendments, none passed, so none reach the ballot.
Tamper checks (edited claim, altered evidence, loosened policy, deleted tail,
wrong key) all fail verification as they should.
