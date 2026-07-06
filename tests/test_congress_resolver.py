from __future__ import annotations

from cls_congress.models import Chamber, Entity, Member
from cls_congress.resolver import EntityResolver


def _member(name: str) -> Member:
    return Member(
        member_id=Member.make_id(name, Chamber.SENATE, "OR", None),
        name=name,
        chamber=Chamber.SENATE,
        state="OR",
    )


def _entity(name: str, aliases: list[str] | None = None) -> Entity:
    return Entity(entity_id=Entity.make_id(name), canonical_name=name, kind="pac", aliases=aliases or [])


def test_exact_match_member():
    resolver = EntityResolver(members=[_member("Ron Wyden")])
    result = resolver.resolve("Ron Wyden")
    assert result is not None
    assert result.kind == "member"


def test_token_sort_match():
    resolver = EntityResolver(members=[_member("Elizabeth Warren")])
    result = resolver.resolve("Warren Elizabeth")
    assert result is not None
    assert result.confidence == 0.9


def test_alias_match_entity():
    resolver = EntityResolver(entities=[_entity("Example PAC", aliases=["EX PAC"])])
    result = resolver.resolve("EX PAC")
    assert result is not None
    assert result.canonical_name == "Example PAC"


def test_unknown_returns_none():
    resolver = EntityResolver(members=[_member("Ron Wyden")])
    assert resolver.resolve("Unknown Person") is None
