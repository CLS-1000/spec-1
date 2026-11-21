# @domain:   product
# @module:   store
# @loc:      gh_main
# @status:   stable
# @depends:  NONE

"""Dossier persistence — append-only JSONL store for ResearchArtifact.

Mirrors cls_leads.store.LeadStore: JSONL is the source of truth, one file
per topic, one line per dossier version, never rewritten in place. This is
the same append-only / single-writer convention used by every other
SPEC-1 store (ADR-003).

SQLite dual-write is not wired in this first pass (see docs/research_mode.md
"Next improvements") — JSONL alone is sufficient for a single analyst's
topic store, and adding the table/migration was judged out of scope for a
minimal first version. The constructor shape intentionally matches
LeadStore/PsyopStore so dual-write can be added later without changing the
call sites.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path
from spec1_core.intelligence.store import anchor_to_home
from typing import Iterator, Optional

from cls_research.schemas import ResearchArtifact

DEFAULT_DOSSIERS_DIR = Path("research/dossiers")


class DossierStore:
    """Thread-safe JSONL store for ResearchArtifact versions, one file per topic."""

    def __init__(self, base_dir: Path | str | None = None) -> None:
        self.base_dir = Path(base_dir) if base_dir is not None else anchor_to_home(DEFAULT_DOSSIERS_DIR)
        self._lock = threading.Lock()

    def _path_for(self, topic_id: str) -> Path:
        return self.base_dir / f"{topic_id}.jsonl"

    def save(self, artifact: ResearchArtifact) -> dict:
        """Append one dossier version to its topic's JSONL file."""
        path = self._path_for(artifact.topic_id)
        entry = artifact.to_dict()
        with self._lock:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(entry) + "\n")
        return entry

    def read_all(self, topic_id: str) -> Iterator[dict]:
        """Yield every stored dossier version dict for a topic, oldest first."""
        path = self._path_for(topic_id)
        if not path.exists():
            return
        with path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    continue

    def latest(self, topic_id: str) -> Optional[ResearchArtifact]:
        """Return the most recent dossier version for a topic, or None."""
        versions = list(self.read_all(topic_id))
        if not versions:
            return None
        latest_dict = max(versions, key=lambda d: d.get("version", 0))
        return ResearchArtifact.from_dict(latest_dict)

    def history(self, topic_id: str) -> list[ResearchArtifact]:
        """Return all dossier versions for a topic, oldest first."""
        return [ResearchArtifact.from_dict(d) for d in self.read_all(topic_id)]

    def list_topic_ids(self) -> list[str]:
        """Return every topic_id that has at least one stored dossier."""
        if not self.base_dir.exists():
            return []
        return sorted(p.stem for p in self.base_dir.glob("*.jsonl"))

    def count(self, topic_id: str) -> int:
        return sum(1 for _ in self.read_all(topic_id))
