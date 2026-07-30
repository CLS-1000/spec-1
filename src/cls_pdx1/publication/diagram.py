# @domain:   citizens_source
# @module:   publication_diagram
# @loc:      gh_main
# @status:   stable
# @depends:  NONE

"""D3 force-directed graph exporter for Metro Citizens Brief.

Produces a self-contained HTML file with embedded D3.js and graph data.
The diagram is regenerated on each publish cycle (or diagram trigger) and
saved as a static asset alongside the issue PDF/markdown.

The graph models:
  nodes: officials (blue), entities (orange), districts (green)
  links: affiliation edges, weighted by confidence tier
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from cls_pdx1.models import Affiliation, ConfidenceTier, EdgeType, Entity, Official

logger = logging.getLogger(__name__)

# D3 colour scheme
_COLOUR = {
    "official": "#4a90d9",
    "entity": "#e07b39",
    "district": "#5cb85c",
}

_EDGE_COLOUR = {
    EdgeType.DONATION: "#e74c3c",
    EdgeType.BOARD_SEAT: "#9b59b6",
    EdgeType.CONTRACT: "#f39c12",
    EdgeType.LOBBYING: "#1abc9c",
    EdgeType.EMPLOYMENT: "#3498db",
    EdgeType.CO_MENTION: "#bdc3c7",
    EdgeType.ENDORSEMENT: "#e91e63",
    EdgeType.FAMILY_TIE: "#795548",
}

_TEMPLATE = """\
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>Metro Citizens Brief — Political Ties Graph</title>
  <style>
    body {{ margin: 0; background: #1a1a2e; color: #eee; font-family: sans-serif; }}
    svg {{ width: 100vw; height: 100vh; }}
    .node text {{ font-size: 11px; fill: #eee; pointer-events: none; }}
    .link {{ stroke-opacity: 0.5; }}
    .tooltip {{ position: absolute; background: rgba(0,0,0,0.85); color: #fff;
                padding: 8px 12px; border-radius: 4px; font-size: 12px;
                pointer-events: none; display: none; }}
    #legend {{ position: fixed; top: 16px; right: 16px; background: rgba(0,0,0,0.7);
               padding: 12px; border-radius: 6px; font-size: 12px; }}
    .legend-dot {{ display: inline-block; width: 10px; height: 10px;
                   border-radius: 50%; margin-right: 6px; }}
  </style>
</head>
<body>
<div id="legend">
  <b>Node types</b><br>
  <span class="legend-dot" style="background:{off}"></span>Official<br>
  <span class="legend-dot" style="background:{ent}"></span>Entity<br>
  <span class="legend-dot" style="background:{dis}"></span>District<br>
  <hr style="border-color:#555;margin:6px 0">
  <b>Edge types</b><br>
  {edge_legend}
</div>
<div class="tooltip" id="tooltip"></div>
<svg></svg>
<script src="https://d3js.org/d3.v7.min.js"></script>
<script>
const graph = {graph_json};

const svg = d3.select("svg");
const width = window.innerWidth, height = window.innerHeight;
const tooltip = document.getElementById("tooltip");

const sim = d3.forceSimulation(graph.nodes)
  .force("link", d3.forceLink(graph.links).id(d => d.id).distance(120))
  .force("charge", d3.forceManyBody().strength(-300))
  .force("center", d3.forceCenter(width / 2, height / 2))
  .force("collision", d3.forceCollide(30));

const link = svg.append("g")
  .selectAll("line")
  .data(graph.links)
  .join("line")
  .attr("class", "link")
  .attr("stroke", d => d.colour)
  .attr("stroke-width", d => Math.max(1, d.weight));

const node = svg.append("g")
  .selectAll("g")
  .data(graph.nodes)
  .join("g")
  .attr("cursor", "pointer")
  .call(d3.drag()
    .on("start", (e, d) => {{ if (!e.active) sim.alphaTarget(0.3).restart(); d.fx=d.x; d.fy=d.y; }})
    .on("drag",  (e, d) => {{ d.fx=e.x; d.fy=e.y; }})
    .on("end",   (e, d) => {{ if (!e.active) sim.alphaTarget(0); d.fx=null; d.fy=null; }}));

node.append("circle")
  .attr("r", d => d.radius)
  .attr("fill", d => d.colour)
  .attr("stroke", "#222").attr("stroke-width", 1.5);

node.append("text")
  .attr("dx", 14).attr("dy", 4)
  .text(d => d.label);

node.on("mouseover", (e, d) => {{
    tooltip.style.display = "block";
    tooltip.style.left = (e.pageX + 12) + "px";
    tooltip.style.top  = (e.pageY - 8) + "px";
    tooltip.textContent = d.tooltip || d.label;
}}).on("mouseout", () => {{ tooltip.style.display = "none"; }});

sim.on("tick", () => {{
  link.attr("x1", d => d.source.x).attr("y1", d => d.source.y)
      .attr("x2", d => d.target.x).attr("y2", d => d.target.y);
  node.attr("transform", d => `translate(${{d.x}},${{d.y}})`);
}});
</script>
</body>
</html>
"""


def _edge_legend_html() -> str:
    lines = []
    for et, colour in _EDGE_COLOUR.items():
        lines.append(
            f'<span class="legend-dot" style="background:{colour}"></span>{et.name.title()}<br>'
        )
    return "\n  ".join(lines)


def build_graph_data(
    officials: list[Official],
    entities: list[Entity],
    affiliations: list[Affiliation],
) -> dict[str, Any]:
    """Convert PDX-1i records to D3 node/link format."""
    nodes = []
    links = []
    seen_ids: set[str] = set()

    for off in officials:
        if off.official_id not in seen_ids:
            seen_ids.add(off.official_id)
            nodes.append(
                {
                    "id": off.official_id,
                    "label": off.name,
                    "kind": "official",
                    "colour": _COLOUR["official"],
                    "radius": 12,
                    "tooltip": f"{off.name} — {off.role} ({off.jurisdiction.name})",
                }
            )

    for ent in entities:
        if ent.entity_id not in seen_ids:
            seen_ids.add(ent.entity_id)
            nodes.append(
                {
                    "id": ent.entity_id,
                    "label": ent.canonical_name,
                    "kind": "entity",
                    "colour": _COLOUR["entity"],
                    "radius": 10,
                    "tooltip": f"{ent.canonical_name} ({ent.kind})",
                }
            )

    for aff in affiliations:
        if aff.official_id in seen_ids and aff.entity_id in seen_ids:
            weight = {
                ConfidenceTier.HARD_RECORD: 2.5,
                ConfidenceTier.REPORTED: 1.5,
                ConfidenceTier.INFERRED: 0.8,
            }.get(aff.confidence, 1.0)
            links.append(
                {
                    "source": aff.official_id,
                    "target": aff.entity_id,
                    "colour": _EDGE_COLOUR.get(aff.edge_type, "#999"),
                    "weight": weight,
                    "label": aff.edge_type.name,
                }
            )

    return {"nodes": nodes, "links": links}


def write_diagram(
    officials: list[Official],
    entities: list[Entity],
    affiliations: list[Affiliation],
    output_dir: Path,
    filename: str = "mcb_graph.html",
) -> Path:
    """Write self-contained D3 HTML diagram to output_dir."""
    output_dir.mkdir(parents=True, exist_ok=True)
    graph_data = build_graph_data(officials, entities, affiliations)
    graph_json = json.dumps(graph_data, default=str)

    html = _TEMPLATE.format(
        off=_COLOUR["official"],
        ent=_COLOUR["entity"],
        dis=_COLOUR["district"],
        edge_legend=_edge_legend_html(),
        graph_json=graph_json,
    )

    path = output_dir / filename
    path.write_text(html, encoding="utf-8")
    logger.info("MCB diagram written: %s (%d nodes, %d links)", path, len(graph_data["nodes"]), len(graph_data["links"]))
    return path
