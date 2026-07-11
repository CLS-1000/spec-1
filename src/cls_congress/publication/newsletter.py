from __future__ import annotations

from cls_congress.models import Issue


def render_markdown(issue: Issue) -> str:
    lines = [f"# {issue.title}", "", f"Published: {issue.published_at.isoformat()}", ""]
    for section in issue.sections:
        lines.extend([f"## {section.title}", section.body, ""])
    return "\n".join(lines).strip() + "\n"
