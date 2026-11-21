# @domain:   product
# @module:   tools_run_research
# @loc:      gh_main
# @status:   stable
# @depends:  NONE

"""CLI: run Research Mode for one topic profile.

Usage:
    PYTHONPATH=src python -m spec1_core.tools.run_research \\
        --topic research/topics/topic_dprk_missile_indigenization.json \\
        --dossiers-dir research/dossiers

    # List all topic profiles known to the system
    PYTHONPATH=src python -m spec1_core.tools.run_research --list-topics

Reads:  one TopicProfile JSON file (--topic)
Writes: research/dossiers/<topic_id>.jsonl (new dossier version, appended)
        research/dossiers/<topic_id>/dossier_v<N>.md
        research/dossiers/<topic_id>/dossier_latest.md

Exit code 0 on success, 1 if the topic file is missing/invalid.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from spec1_core.intelligence.store import anchor_to_home

from cls_research.pipeline import run_research
from cls_research.store import DossierStore
from cls_research.topics import DEFAULT_TOPICS_DIR, list_topic_profiles, load_topic_profile


def build_argparser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="spec1_core.tools.run_research")
    p.add_argument(
        "--topic",
        help="Path to a TopicProfile JSON file (see research/topics/ for examples)",
    )
    p.add_argument(
        "--dossiers-dir",
        default=str(anchor_to_home(os.environ.get("SPEC1_RESEARCH_DOSSIERS_DIR", "research/dossiers"))),
        help="Directory for the dossier JSONL store + Markdown output (default research/dossiers)",
    )
    p.add_argument(
        "--topics-dir",
        default=os.environ.get("SPEC1_RESEARCH_TOPICS_DIR", str(DEFAULT_TOPICS_DIR)),
        help="Directory to scan with --list-topics (default research/topics)",
    )
    p.add_argument(
        "--list-topics",
        action="store_true",
        help="List every topic profile found in --topics-dir and exit",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_argparser().parse_args(argv)

    if args.list_topics:
        profiles = list_topic_profiles(Path(args.topics_dir))
        if not profiles:
            print(f"No topic profiles found in {args.topics_dir}", file=sys.stderr)
            return 0
        for p in profiles:
            print(f"{p.topic_id}\t{p.name}\t{p.core_question}")
        return 0

    if not args.topic:
        print("error: --topic is required (or pass --list-topics)", file=sys.stderr)
        return 1

    topic_path = Path(args.topic)
    if not topic_path.exists():
        print(f"error: topic profile not found: {topic_path}", file=sys.stderr)
        return 1

    profile = load_topic_profile(topic_path)
    dossiers_dir = Path(args.dossiers_dir)
    store = DossierStore(base_dir=dossiers_dir)

    artifact = run_research(profile, dossier_store=store, markdown_dir=dossiers_dir)

    print(
        f"topic={profile.topic_id} version={artifact.version} "
        f"items={len(artifact.collected_items)} "
        f"findings={len(artifact.notable_findings)} "
        f"gaps={len(artifact.unresolved_questions)} "
        f"-> {dossiers_dir / profile.topic_id / f'dossier_v{artifact.version}.md'}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
