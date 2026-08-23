# @domain:   publisher
# @module:   cls_weekly_brief_store
# @loc:      gh_main
# @status:   stable
# @depends:  NONE

"""JSONL store for public weekly briefs (append-only persistence)."""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, Optional

from cls_weekly_brief.schemas import PublicWeeklyBrief


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class WeeklyBriefStore:
    """Thread-safe append-only JSONL store for PublicWeeklyBrief objects."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self._lock = threading.Lock()

    def save(self, brief: PublicWeeklyBrief, write_markdown: bool = True) -> dict:
        """Save a brief to JSONL and optionally write Markdown file.

        Args:
            brief: PublicWeeklyBrief to save
            write_markdown: If True, also write a .md file

        Returns:
            Written entry dict with written_at timestamp
        """
        entry = {**brief.to_dict(), "written_at": _now()}

        # Write JSONL
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(entry) + "\n")

        # Write Markdown if requested
        if write_markdown:
            from cls_weekly_brief.formatter import to_markdown

            md_dir = self.path.parent / "markdown"
            md_dir.mkdir(parents=True, exist_ok=True)
            md_path = md_dir / f"weekly_{brief.week_id}.md"

            md_content = to_markdown(brief)
            with md_path.open("w", encoding="utf-8") as fh:
                fh.write(md_content)

        return entry

    def read_all(self) -> Iterator[dict]:
        """Iterate over all brief records in insertion order."""
        if not self.path.exists():
            return
        with self.path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    continue

    def latest(self) -> Optional[dict]:
        """Return the most recently written brief record."""
        last = None
        for record in self.read_all():
            last = record
        return last

    def get_by_week_id(self, week_id: str) -> Optional[dict]:
        """Return brief for a specific ISO week (YYYY-W##)."""
        for record in self.read_all():
            if record.get("week_id") == week_id:
                return record
        return None

    def count(self) -> int:
        """Count total brief records."""
        return sum(1 for _ in self.read_all())

    def filter_by_date_range(
        self, start_date: str, end_date: str
    ) -> Iterator[dict]:
        """Iterate briefs where week_start is between dates (inclusive)."""
        for record in self.read_all():
            week_start = record.get("week_start", "")
            if start_date <= week_start <= end_date:
                yield record

    def filter_by_category(self, category: str) -> Iterator[dict]:
        """Iterate briefs that contain a section with the given category."""
        for record in self.read_all():
            sections = record.get("sections", [])
            for section in sections:
                if section.get("category") == category:
                    yield record
                    break
