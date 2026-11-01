"""Metro Citizens Narrative publication layer.

Produces: markdown text, PDF (ReportLab), and D3 diagram snapshot per issue.
"""

from titan.publication.builder import IssueBuilder

__all__ = ["IssueBuilder"]
