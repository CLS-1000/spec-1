
import json, sys, asyncio
sys.path.insert(0, "/home/mjlak/spec-1")
from spec1_api.db.signals import insert_signal

P1 = "/home/mjlak/pdx-1i/pdx1_signals.jsonl"

# Transparent jurisdiction/source attribution to the 34-node registry.
# NOT verified person-specific links -- a dev seed over REAL pdx-1i data.
ENTITY_TO_NODE = {
    "portland": "city_admin", "port": "city_admin", "ppb": "police",
    "washco": "county", "multco": "county", "clackco": "county",
    "nike": "business_tax", "ohsu": "business_tax", "pge": "business_tax",
    "prosper": "housing",
}
SOURCE_TO_NODE = {"ORESTAR": "ethics", "WA_PDC": "ethics", "PORTLAND_PRESS": "city_admin"}

def pick_node(rec):
    for e in (rec.get("entity_ids") or []):
        if e in ENTITY_TO_NODE:
            return ENTITY_TO_NODE[e]
    if rec.get("source") in SOURCE_TO_NODE:
        return SOURCE_TO_NODE[rec["source"]]
    return None

count = written = 0
with open(P1) as fh:
    for line in fh:
        try:
            rec = json.loads(line)
        except Exception:
            continue
        node = pick_node(rec)
        if not node:
            continue
        conf = float(rec.get("confidence") or 0)
        if conf < 0.5:
            continue
        sig_id = rec.get("signal_id") or rec.get("record_id") or f"seed-{count}"
        # tags passed as a LIST so _insert's json.dumps encodes exactly once
        row = {
            "signal_id": sig_id,
            "node_id": node,
            "run_id": rec.get("run_id", "seed-run"),
            "headline": (rec.get("pattern") or "")[:160],
            "summary": rec.get("pattern") or "",
            "source_url": rec.get("url") or f"https://pdx-1i.local/{sig_id}",
            "source_domain": rec.get("source", "pdx-1i"),
            "published_at": rec.get("published_at") or rec.get("created_at"),
            "retrieved_at": rec.get("created_at") or rec.get("published_at"),
            "gate_status": "PASS",
            "gate_credibility": round(conf, 4),
            "gate_volume": 0.6, "gate_velocity": 0.6, "gate_novelty": 0.6,
            "signal_age_hours": 24.0,
            "freshness_label": "fresh",
            "analyst_voice": None, "conflict_score": None,
            "tags": rec.get("tags") or [],
        }
        try:
            if asyncio.run(insert_signal(row)):
                written += 1
        except Exception as e:
            print("err", e)
        count += 1
print(f"scanned {count}, wrote {written} PASS rows")
