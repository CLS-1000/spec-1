# @domain:   publisher
# @module:   store
# @loc:      gh_main
# @status:   stable
# @depends:  NONE

"""WorldBrief persistence — JSONL index + dated Markdown files, with optional SQLite dual-write."""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from spec1_core.intelligence.store import anchor_to_home
from typing import Iterator, Optional

from cls_world_brief.formatter import to_markdown
from cls_world_brief.schemas import WorldBrief


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class BriefStore:
    """Persists WorldBrief objects to JSONL + Markdown files, with optional SQLite dual-write.

    Modes:
    - **JSONL-only** (default) — append-only file; Markdown files written per brief.
    - **Dual-write** (``BriefStore(..., db=database)``) — additionally mirrors every
      entry to the ``briefs`` SQLite table via :class:`cls_db.dual_write.DualWriter`.
      JSONL remains the source of truth; SQLite failures are non-fatal.
    """

    def __init__(
        self,
        jsonl_path: Path | str | None = None,
        briefs_dir: Path | str | None = None,
        db: Optional["Database"] = None,  # noqa: F821
    ) -> None:
        self.jsonl_path = Path(jsonl_path) if jsonl_path is not None else anchor_to_home("world_briefs.jsonl")
        self.briefs_dir = Path(briefs_dir) if briefs_dir is not None else anchor_to_home("briefs")
        self._lock = threading.Lock()
        self._dual_writer = None
        if db is not None:
            from cls_db.dual_write import DualWriter

            self._dual_writer = DualWriter(
                jsonl_path=self.jsonl_path,
                db=db,
                table="briefs",
                pk_field="brief_id",
            )

    def save(self, brief: WorldBrief, write_markdown: bool = True) -> dict:
        """Save a WorldBrief to JSONL index and optionally to a Markdown file.

        Returns the JSONL entry dict.
        """
        record_dict = brief.to_dict()

        # Dual-write path: DualWriter handles JSONL + SQLite atomically
        if self._dual_writer is not None:
            entry = self._dual_writer.write(record_dict)
        else:
            entry = {**record_dict, "written_at": _now()}
            with self._lock:
                self.jsonl_path.parent.mkdir(parents=True, exist_ok=True)
                with self.jsonl_path.open("a", encoding="utf-8") as fh:
                    fh.write(json.dumps(entry) + "\n")

        # Write Markdown file (always outside the dual_writer path — markdown is not SQLite)
        if write_markdown:
            with self._lock:
                self.briefs_dir.mkdir(parents=True, exist_ok=True)
                md_path = self.briefs_dir / f"{brief.date}.md"
                latest_path = self.briefs_dir / "latest.md"
                md_content = to_markdown(brief)
                md_path.write_text(md_content, encoding="utf-8")
                latest_path.write_text(md_content, encoding="utf-8")

        return entry

    def read_all(self) -> Iterator[dict]:
        """Iterate over all brief records from the JSONL index."""
        if not self.jsonl_path.exists():
            return
        with self.jsonl_path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    continue

    def latest(self) -> Optional[dict]:
        """Return the most recently saved brief dict."""
        last = None
        for record in self.read_all():
            last = record
        return last

    def get_by_date(self, date: str) -> Optional[dict]:
        """Return the brief for a specific date (YYYY-MM-DD)."""
        for record in self.read_all():
            if record.get("date") == date:
                return record
        return None

    def count(self) -> int:
        return sum(1 for _ in self.read_all())

    def clear(self) -> None:
        if self.jsonl_path.exists():
            self.jsonl_path.unlink()

    def list_markdown_files(self) -> list[Path]:
        """Return sorted list of brief Markdown files."""
        if not self.briefs_dir.exists():
            return []
        return sorted(self.briefs_dir.glob("*.md"))
