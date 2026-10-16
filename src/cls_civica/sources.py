# @domain:   civica
# @module:   civica_sources
# @status:   mvp

"""Official Oregon data, via proc_track.

History rows come from proc_track's session cache (cache/<SESSION>.json),
which proc_track pulls from the Legislature's OData `MeasureHistoryActions`.
To refresh: `python <proc_track>/scripts/fetch_session.py 2025R1` (network).

Measure titles are optional. proc_track does not cache them; `fetch_titles`
pulls CatchLine/RelatingTo from the `Measures` entity when the network allows
and caches the raw response next to the history cache. Without titles, cards
still work; the elections topic filter needs them.
"""

from __future__ import annotations

import json
import logging
import urllib.parse
import urllib.request
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from cls_civica import deps
from cls_civica import labels as L

logger = logging.getLogger(__name__)


@dataclass
class Session:
    session: str
    cache_file: Path
    cache_sha256: str
    rows_by_measure: dict[str, list[dict]]
    closed: bool
    titles: dict[str, str]
    titles_file: Optional[Path]
    titles_sha256: Optional[str]

    @property
    def row_total(self) -> int:
        return sum(len(v) for v in self.rows_by_measure.values())


def cache_path(session: str, cache_dir: Optional[Path] = None) -> Path:
    base = cache_dir or (deps.proc_track_home() / "cache")
    return base / f"{session}.json"


def load_session(session: str, cache_dir: Optional[Path] = None, titles_path: Optional[Path] = None) -> Session:
    path = cache_path(session, cache_dir)
    if not path.exists():
        raise FileNotFoundError(
            f"no cached history for {session} at {path}. "
            f"Run: python {deps.proc_track_home() / 'scripts' / 'fetch_session.py'} {session}"
        )
    rows = json.loads(path.read_text(encoding="utf-8"))
    by: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        if r.get("SessionKey") != session:
            continue
        by[f"{r['MeasurePrefix']}{r['MeasureNumber']}"].append(r)
    # proc_track rule: ActionDate is the only defensible sort key; MeasureHistoryId contradicts it.
    for k in by:
        by[k].sort(key=lambda r: (r["ActionDate"], r["MeasureHistoryId"]))
    closed = any("upon adjournment" in (r.get("ActionText") or "").lower() for r in rows)

    titles: dict[str, str] = {}
    tpath = titles_path or path.with_name(f"{session}.titles.json")
    tsha = None
    if tpath.exists():
        for m in json.loads(tpath.read_text(encoding="utf-8")):
            mid = f"{m['MeasurePrefix']}{m['MeasureNumber']}"
            titles[mid] = (m.get("CatchLine") or m.get("RelatingTo") or "").strip()
        tsha = deps.file_sha256(tpath)
    return Session(session, path, deps.file_sha256(path), dict(by), closed, titles,
                   tpath if tpath.exists() else None, tsha)


def fetch_titles(session: str, out: Path, timeout: int = 60) -> int:
    """Page the Measures entity (titles only) into `out`. Returns count. Network required."""
    params = {
        "$filter": f"SessionKey eq '{session}'",
        "$select": "SessionKey,MeasurePrefix,MeasureNumber,CatchLine,RelatingTo",
        "$format": "json",
    }
    url: Optional[str] = f"{L.OLIS_API}/Measures?" + urllib.parse.urlencode(params)
    got: list[dict] = []
    while url:
        req = urllib.request.Request(url, headers={"Accept": "application/json",
                                                   "User-Agent": "spec1-civica/0.1"})
        # URL is always built from the fixed https OLIS host above.
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # nosec B310
            page = json.loads(resp.read().decode("utf-8"))
        got.extend(page.get("value", []))
        url = page.get("odata.nextLink") or page.get("@odata.nextLink")
        if url and not url.startswith("http"):
            url = f"{L.OLIS_API}/{url}"
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".tmp")
    tmp.write_text(json.dumps(got, ensure_ascii=False), encoding="utf-8")
    tmp.replace(out)
    logger.info("titles: %d measures for %s -> %s", len(got), session, out)
    return len(got)


def replay(measure_id: str, rows: list[dict]):
    """proc_track replay. Returns (states, history, halt)."""
    h = deps.replay_harness()
    item, halt, _gaps = h.replay(measure_id, rows)
    return dict(item.states), list(item.history), halt
