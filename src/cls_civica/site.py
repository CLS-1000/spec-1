# @domain:   civica
# @module:   civica_site
# @status:   mvp

"""Render the public site: one self-contained, accessible index.html.

Accessibility choices (the Governor's "understood and accessible"):
  - plain words, short sentences, outcomes named the way a resident would say them
  - semantic landmarks, skip link, labelled controls, live result count,
    visible focus, 18px base type, AA contrast in light and dark, no motion
  - works without the network: data is embedded, no external fonts or scripts
Every card shows the Gatepost record it was sealed in, and the page explains
how anyone can check the whole site offline.
"""

from __future__ import annotations

import html
import json
from pathlib import Path

from cls_civica import labels as L


def _compact(card: dict) -> dict:
    rec = card.get("record", {})
    return {
        "m": card["measure"],
        "id": card["measure_id"],
        "t": card.get("title") or "",
        "o": card["outcome"],
        "h": card["headline"],
        "c": [c["text"] for c in card["claims"]],
        "tl": [[s["when"], s["text"]] for s in card["timeline"]],
        "tp": card["topics"],
        "v": card["verified"],
        "d": card["last_action_date"],
        "u": card["public_url"],
        "s": card["source_url"],
        "n": card["row_count"],
        "r": [rec.get("finding_seq"), (rec.get("finding_hash") or "")[:16], rec.get("evidence_digest", "")[7:23]],
    }


def render_site(site_dir: Path, cards: list[dict], summary: dict, res) -> Path:
    data = [_compact(c) for c in cards]
    o = summary["outcomes"]
    ca = summary["constitutional_amendments"]
    session = summary["session"]
    year = session[:4]
    stopped = o.get(L.OUTCOME_STOPPED, 0)
    ballot_line = (
        f"None of the {ca['proposed']} proposed changes to the Oregon Constitution passed, "
        f"so none of them will be on your ballot."
        if not ca["passed"] else
        f"{len(ca['passed'])} of {ca['proposed']} proposed changes to the Oregon Constitution passed "
        f"and go to voters: {', '.join(ca['passed'])}."
    )
    demo_banner = (
        '<div class="demo" role="note"><strong>Preview.</strong> This copy is sealed with a throwaway '
        'demo key, so its seal proves nothing about who published it. The real site is sealed with the '
        'publisher\'s own key, published separately.</div>' if res.demo_key else ""
    )
    page = (Path(__file__).parent / "templates" / "site.html").read_text(encoding="utf-8")
    repl = {
        "{{SESSION}}": html.escape(session),
        "{{YEAR}}": html.escape(year),
        "{{TOTAL}}": f"{summary['measures_published']:,}",
        "{{LAW}}": f"{o.get(L.OUTCOME_LAW, 0):,}",
        "{{VETOED}}": f"{o.get(L.OUTCOME_VETOED, 0):,}",
        "{{STOPPED}}": f"{stopped:,}",
        "{{ROWS}}": f"{summary['rows_in_cache']:,}",
        "{{BALLOT_LINE}}": html.escape(ballot_line),
        "{{CA_PROPOSED}}": str(ca["proposed"]),
        "{{CA_PASSED}}": str(len(ca["passed"])),
        "{{KEY_ID}}": html.escape(res.key_id),
        "{{KEY_SOURCE}}": html.escape(L.PUBLISHED_KEY_SOURCE),
        "{{PUBKEY}}": html.escape(res.public_key_hex),
        "{{ANCHOR_SEQ}}": str(res.anchor["seq"]),
        "{{ANCHOR_H}}": html.escape(res.anchor["h"]),
        "{{UNVERIFIED}}": str(len(summary["unverified"])),
        "{{WITHHELD}}": str(summary["measures_withheld"]),
        "{{CACHE_SHA}}": html.escape(summary["history_cache"]["sha256"][7:23]),
        "{{BUILT}}": html.escape(summary["built_at"]),
        "{{DEMO_BANNER}}": demo_banner,
        "{{DATA}}": json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/"),
        "{{LABELS}}": json.dumps({"o": L.OUTCOME_LABELS, "t": L.TOPIC_LABELS}),
    }
    for k, v in repl.items():
        page = page.replace(k, v)
    out = site_dir / "index.html"
    out.write_text(page, encoding="utf-8")
    return out
