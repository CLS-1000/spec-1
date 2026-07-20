from __future__ import annotations

from cls_congress.models import Affiliation


def build_graph_data(affiliations: list[Affiliation]) -> dict:
    nodes: dict[str, dict] = {}
    edges: list[dict] = []
    for aff in affiliations:
        nodes.setdefault(aff.member_id, {"id": aff.member_id, "kind": "member"})
        nodes.setdefault(aff.entity_id, {"id": aff.entity_id, "kind": "entity"})
        edges.append({"source": aff.member_id, "target": aff.entity_id, "edge_type": aff.edge_type.name})
    return {"nodes": list(nodes.values()), "edges": edges}
