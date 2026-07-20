from __future__ import annotations

import importlib
from datetime import datetime, timezone

from fastapi.testclient import TestClient

from cls_congress.models import Chamber, Issue, IssueSection, Member
from cls_congress.api.main import create_app as create_congress_app
from cls_congress.pipeline import CycleResult
from spec1_api.main import create_app

congress_api_router = importlib.import_module("cls_congress.api.router")


def _now() -> datetime:
    return datetime.now(timezone.utc)


class _FakePipeline:
    def __init__(self, member_id: str) -> None:
        self._member_id = member_id

    def run_cycle(self) -> CycleResult:
        issue = Issue(
            issue_id=Issue.make_id(1, _now()),
            issue_number=1,
            title="Congress Brief #1",
            published_at=_now(),
            sections=[IssueSection(title="Section", body="According to source: test", section_type="signal", source_uri="https://example.com")],
        )
        result = CycleResult(issue=issue)
        return result


def test_congress_cycle_and_brief_routes(monkeypatch):
    member = Member(member_id=Member.make_id("Ron Wyden", Chamber.SENATE, "OR", None), name="Ron Wyden", chamber=Chamber.SENATE, state="OR")
    congress_api_router._registry._members = [member]
    congress_api_router._registry._members_by_id = {member.member_id: member}
    congress_api_router._pipeline = _FakePipeline(member.member_id)

    monkeypatch.setattr("spec1_api.main.start_scheduler", lambda: None)
    monkeypatch.setattr("spec1_api.main.stop_scheduler", lambda: None)
    monkeypatch.setattr("spec1_api.main.maybe_run_on_start", lambda: None)

    app = create_app()
    with TestClient(app) as client:
        cycle = client.post("/api/v1/congress_brief/cycle")
        assert cycle.status_code == 200

        brief = client.get("/api/v1/congress_brief/brief")
        assert brief.status_code == 200

        member_response = client.get(f"/api/v1/congress_brief/member/{member.member_id}")
        assert member_response.status_code == 200

        anomalies = client.get("/api/v1/congress_brief/anomalies")
        assert anomalies.status_code == 200


def test_congress_standalone_app(monkeypatch):
    member = Member(member_id=Member.make_id("Ron Wyden", Chamber.SENATE, "OR", None), name="Ron Wyden", chamber=Chamber.SENATE, state="OR")
    congress_api_router._registry._members = [member]
    congress_api_router._registry._members_by_id = {member.member_id: member}
    congress_api_router._pipeline = _FakePipeline(member.member_id)

    app = create_congress_app()
    with TestClient(app) as client:
        cycle = client.post("/api/v1/congress_brief/cycle")
        assert cycle.status_code == 200

        brief = client.get("/api/v1/congress_brief/brief")
        assert brief.status_code == 200
