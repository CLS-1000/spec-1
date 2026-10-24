# @domain:   spec-1
# @module:   spec1_professional
# @loc:      gh_main
# @status:   stable
# @depends:  NONE

"""Out-of-process PDF renderer for SPEC-1 briefs.

Invoked as a subprocess from spec1_engine.briefing.writer.write_brief_pdf so
the API/engine processes never have to import weasyprint or its native deps.

Usage:
    python -m spec1_engine.tools.pdf_render --brief-md path/in.md --out path/out.pdf
"""

from __future__ import annotations

import argparse
from pathlib import Path


_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>WORLD STATE BRIEF</title>
<style>
    @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@300;400;500;600&display=swap');
    * {{ margin: 0; padding: 0; box-sizing: border-box; }}
    body {{
        font-family: 'IBM Plex Mono', 'Courier New', monospace;
        background: #ffffff;
        color: #000000;
        line-height: 1.6;
        max-width: 800px;
        margin: 0 auto;
        padding: 60px 40px;
    }}
    .masthead {{
        border: 2px solid #000000;
        padding: 40px;
        margin-bottom: 60px;
        position: relative;
    }}
    .masthead::before, .masthead::after {{
        content: '';
        position: absolute;
        width: 20px;
        height: 20px;
        border: 2px solid #000000;
    }}
    .masthead::before {{ top: -2px; left: -2px; border-right: none; border-bottom: none; }}
    .masthead::after  {{ bottom: -2px; right: -2px; border-left: none; border-top: none; }}
    .masthead-title    {{ font-size: 40px; font-weight: 600; letter-spacing: 6px; text-align: center; margin-bottom: 8px; }}
    .masthead-subtitle {{ font-size: 11px; font-weight: 300; letter-spacing: 3px; text-align: center; margin-bottom: 30px; }}
    .masthead-date     {{ font-size: 10px; font-weight: 400; letter-spacing: 2px; text-align: center;
                         padding-top: 20px; border-top: 1px solid #000000; }}
    /* Markdown h1 becomes the brief date line — hidden; masthead carries it */
    .brief-body h1 {{ display: none; }}
    /* h2 → section divider */
    .brief-body h2 {{
        font-size: 14px; font-weight: 600; letter-spacing: 4px;
        margin: 50px 0 20px 0; padding-bottom: 10px;
        border-bottom: 2px solid #000000;
        text-transform: uppercase;
    }}
    /* h3 → item headline */
    .brief-body h3 {{
        font-size: 15px; font-weight: 600; letter-spacing: 1px;
        margin: 20px 0 6px 0;
    }}
    /* h4 → sub-label (Watch List items, lead titles) */
    .brief-body h4 {{
        font-size: 11px; font-weight: 600; letter-spacing: 3px;
        margin: 16px 0 4px 0; text-transform: uppercase;
    }}
    .brief-body p {{
        font-size: 12px; font-weight: 400; line-height: 1.8;
        margin-bottom: 10px; text-align: justify;
    }}
    .brief-body ul, .brief-body ol {{
        margin: 10px 0 16px 0; padding-left: 0; list-style: none;
    }}
    .brief-body li {{
        font-size: 11px; line-height: 1.7; margin-bottom: 6px;
        padding-left: 16px; position: relative;
    }}
    .brief-body li::before {{ content: '▸'; position: absolute; left: 0; }}
    /* blockquote → assessment / trajectory box */
    .brief-body blockquote {{
        border: 1px solid #000000; padding: 14px 16px; margin: 16px 0;
        font-size: 11px; line-height: 1.7;
        background: repeating-linear-gradient(
            90deg, transparent, transparent 2px,
            rgba(0,0,0,0.02) 2px, rgba(0,0,0,0.02) 4px
        );
    }}
    .brief-body blockquote p {{ font-size: 11px; margin-bottom: 4px; text-align: left; }}
    /* strong in running text */
    .brief-body strong {{ font-weight: 600; }}
    /* horizontal rule → bar separator */
    .brief-body hr {{
        border: none; border-top: 1px solid #000000;
        margin: 40px 0;
    }}
    /* code / pre — signal IDs, run IDs */
    .brief-body code {{
        font-family: inherit; font-size: 10px;
        background: rgba(0,0,0,0.05); padding: 1px 4px;
    }}
    .brief-body pre {{
        font-size: 10px; border: 1px solid #000000;
        padding: 12px; margin: 16px 0; overflow-x: auto;
        white-space: pre-wrap; word-break: break-word;
    }}
    .footer {{
        margin-top: 60px; padding-top: 20px;
        border-top: 1px solid #000000;
        font-size: 10px; font-weight: 300;
        text-align: center; letter-spacing: 1px;
    }}
    @media print {{ body {{ padding: 40px; }} }}
</style>
</head>
<body>
    <div class="masthead">
        <div class="masthead-title">WORLD STATE BRIEF</div>
        <div class="masthead-subtitle">GEOPOLITICAL INTELLIGENCE &middot; DAILY ANALYSIS</div>
        <div class="masthead-date">{date_line}</div>
    </div>
    <div class="brief-body">
        {body}
    </div>
    <div class="footer">
        <p>WORLD STATE BRIEF &mdash; SPEC-1 INTELLIGENCE ENGINE</p>
        <p>Analysis aggregates open-source intelligence. Not investment or policy advice.</p>
    </div>
</body>
</html>"""


def build_argparser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="spec1_engine.tools.pdf_render")
    p.add_argument("--brief-md", required=True, help="Path to markdown brief")
    p.add_argument("--out", required=True, help="Path to output PDF")
    return p


def render_brief_html(md_text: str) -> str:
    """Wrap rendered markdown in the WORLD STATE BRIEF HTML template."""
    import re
    from markdown import markdown

    # Extract date from the first H1/H2 line (e.g. "## SPEC-1 DAILY BRIEF — 2026-04-11")
    m = re.search(r"(?:#+ .*?)(20\d\d-\d\d-\d\d)", md_text)
    if m:
        from datetime import datetime
        try:
            dt = datetime.strptime(m.group(1), "%Y-%m-%d")
            date_line = dt.strftime("%A, %B %-d, %Y").upper()
        except ValueError:
            date_line = m.group(1)
    else:
        from datetime import datetime, timezone
        date_line = datetime.now(timezone.utc).strftime("%A, %B %-d, %Y").upper()

    html_body = markdown(md_text, extensions=["tables", "fenced_code"])
    return _HTML_TEMPLATE.format(date_line=date_line, body=html_body)


def render_pdf_from_markdown(md_text: str) -> bytes:
    """Convert markdown brief to PDF bytes via WeasyPrint.

    weasyprint is imported lazily so importing this module does not force
    the API/engine processes to load it.
    """
    html = render_brief_html(md_text)
    from weasyprint import HTML  # type: ignore

    return HTML(string=html).write_pdf()


def main(argv: list[str] | None = None) -> int:
    args = build_argparser().parse_args(argv)

    brief_md_path = Path(args.brief_md).expanduser().resolve()
    out_path = Path(args.out).expanduser().resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    md_text = brief_md_path.read_text(encoding="utf-8")
    pdf_bytes = render_pdf_from_markdown(md_text)
    out_path.write_bytes(pdf_bytes)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
