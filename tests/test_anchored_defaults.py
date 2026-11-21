"""Default store/cache/log paths resolve against spec1_home(), never the working folder.

Each case runs with the cwd set to one temp dir and SPEC1_HOME set to another. A
default that still resolves against the cwd would land in ``cwd``; anchored ones
land in ``home``. Explicit arguments keep their meaning (relative to the cwd).
"""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def dirs(tmp_path, monkeypatch):
    home, cwd = tmp_path / "home", tmp_path / "cwd"
    home.mkdir()
    cwd.mkdir()
    monkeypatch.setenv("SPEC1_HOME", str(home))
    monkeypatch.chdir(cwd)
    for var in ("SPEC1_PUBLISH_LOG", "SPEC1_LEG_JUD_PATH", "SPEC1_LLM_LOG_PATH"):
        monkeypatch.delenv(var, raising=False)
    return home.resolve(), cwd.resolve()


def _defaults() -> dict[str, Path]:
    from cls_db.database import Database
    from cls_founder_brain.store import FounderBrainStore
    from cls_leads.store import LeadStore
    from cls_leg_jud.store import LegJudStore
    from cls_psyop.evidence import EvidenceStore
    from cls_psyop.pipeline import PipelineConfig
    from cls_psyop.store import PsyopStore
    from cls_research.store import DossierStore
    from cls_research.topics import topic_profile_path
    from cls_world_brief.store import BriefStore

    from cls_db import publish_log

    world = BriefStore()
    return {
        "Database": Database().path,
        "FounderBrainStore": FounderBrainStore().path,
        "LeadStore": LeadStore().path,
        "LegJudStore": LegJudStore().path,
        "EvidenceStore": EvidenceStore().path,
        "PipelineConfig.store_path": PipelineConfig().store_path,
        "PsyopStore": PsyopStore().path,
        "DossierStore": DossierStore().base_dir,
        "topic_profile_path": topic_profile_path("t").parent,
        "BriefStore.jsonl_path": world.jsonl_path,
        "BriefStore.briefs_dir": world.briefs_dir,
        "publish_log": publish_log._log_path(),
    }


def test_defaults_resolve_under_spec1_home(dirs):
    home, cwd = dirs
    for name, path in _defaults().items():
        assert path.is_absolute(), f"{name} default is relative: {path}"
        assert path.is_relative_to(home), f"{name} default {path} is not under SPEC1_HOME"
        assert not path.is_relative_to(cwd), f"{name} default {path} follows the working folder"


def test_titan_cache_defaults_to_spec1_home(dirs):
    home, _ = dirs
    from titan.sources.olis import OlisAdapter
    from titan.sources.orestar import OrestarAdapter

    for adapter in (OlisAdapter(), OrestarAdapter()):
        assert adapter._cache_dir == home / "cache" / "pdx1"


def test_explicit_relative_path_keeps_cwd_meaning(dirs):
    _, cwd = dirs
    from cls_leg_jud.store import LegJudStore

    store = LegJudStore("mine.jsonl")
    assert store.path.resolve() == cwd / "mine.jsonl"


def test_env_value_relative_to_spec1_home(dirs, monkeypatch):
    home, _ = dirs
    monkeypatch.setenv("SPEC1_PUBLISH_LOG", "logs/publish.jsonl")
    from cls_db import publish_log

    assert publish_log._log_path() == home / "logs" / "publish.jsonl"
