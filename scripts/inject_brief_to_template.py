#!/usr/bin/env python3
"""inject_brief_to_template.py

Reads the latest SPEC-1 brief (briefs/spec1_brief_latest.md) and a
Notitia Civica print template, converts the Markdown content to HTML,
and injects it into the template to produce a publication-ready HTML file.

Usage:
    python scripts/inject_brief_to_template.py \
        --brief    briefs/spec1_brief_latest.md \
        --template <path-to>/notitia-civica/templates/print/civic-intelligence-brief.html \
        --out      <path-to>/notitia-civica/published/civic-intelligence-brief_YYYY-MM-DD.html \
        [--date    2026-08-31]   # defaults to today
        [--run-id  run-abc123]   # optional run ID for metadata display

Exit codes: 0 = success, 1 = error (missing input files, write failure).
"""

from __future__ import annotations

import argparse
import html
import re
import sys
from datetime import date, datetime, timezone
from pathlib import Path


# ---------------------------------------------------------------------------
# Minimal Markdown → HTML converter (no external deps)
# ---------------------------------------------------------------------------

def _escape(text: str) -> str:
    return html.escape(text, quote=False)


def _md_inline(text: str) -> str:
    """Convert inline Markdown (bold, italic, code, links) to HTML."""
    # Bold **text** or __text__
    text = re.sub(r"\*\*(.+?)\*\*", lambda m: f"<strong>{_escape(m.group(1))}</strong>", text)
    text = re.sub(r"__(.+?)__", lambda m: f"<strong>{_escape(m.group(1))}</strong>", text)
    # Italic *text* or _text_
    text = re.sub(r"\*(.+?)\*", lambda m: f"<em>{_escape(m.group(1))}</em>", text)
    text = re.sub(r"(?<!\w)_(.+?)_(?!\w)", lambda m: f"<em>{_escape(m.group(1))}</em>", text)
    # Inline code `code`
    text = re.sub(r"`(.+?)`", lambda m: f"<code>{_escape(m.group(1))}</code>", text)
    # Links [text](url)
    text = re.sub(
        r"\[(.+?)\]\((.+?)\)",
        lambda m: f'<a href="{_escape(m.group(2))}">{_escape(m.group(1))}</a>',
        text,
    )
    return text


def md_to_html(md: str) -> str:
    """Convert Markdown text to an HTML fragment suitable for injection."""
    lines = md.splitlines()
    out: list[str] = []
    in_ul = False
    in_ol = False
    in_pre = False
    pre_buf: list[str] = []
    i = 0

    def close_lists() -> None:
        nonlocal in_ul, in_ol
        if in_ul:
            out.append("</ul>")
            in_ul = False
        if in_ol:
            out.append("</ol>")
            in_ol = False

    while i < len(lines):
        line = lines[i]

        # Fenced code block
        if line.strip().startswith("```"):
            if in_pre:
                out.append(f"<pre><code>{_escape(chr(10).join(pre_buf))}</code></pre>")
                pre_buf = []
                in_pre = False
            else:
                close_lists()
                in_pre = True
            i += 1
            continue
        if in_pre:
            pre_buf.append(line)
            i += 1
            continue

        stripped = line.strip()

        # Blank line
        if not stripped:
            close_lists()
            i += 1
            continue

        # ATX headings
        m = re.match(r"^(#{1,6})\s+(.*)", stripped)
        if m:
            close_lists()
            level = len(m.group(1))
            text = _md_inline(m.group(2))
            out.append(f"<h{level}>{text}</h{level}>")
            i += 1
            continue

        # Horizontal rule
        if re.match(r"^[-*_]{3,}$", stripped):
            close_lists()
            out.append("<hr>")
            i += 1
            continue

        # Unordered list
        m_ul = re.match(r"^[-*+]\s+(.*)", stripped)
        if m_ul:
            if not in_ul:
                close_lists()
                out.append("<ul>")
                in_ul = True
            out.append(f"<li>{_md_inline(m_ul.group(1))}</li>")
            i += 1
            continue

        # Ordered list
        m_ol = re.match(r"^\d+\.\s+(.*)", stripped)
        if m_ol:
            if not in_ol:
                close_lists()
                out.append("<ol>")
                in_ol = True
            out.append(f"<li>{_md_inline(m_ol.group(1))}</li>")
            i += 1
            continue

        # Blockquote (CLAUDE PROMPT blocks / investigation prompts)
        if stripped.startswith(">"):
            close_lists()
            content = re.sub(r"^>\s?", "", stripped)
            out.append(f"<blockquote>{_md_inline(content)}</blockquote>")
            i += 1
            continue

        # Plain paragraph
        close_lists()
        out.append(f"<p>{_md_inline(stripped)}</p>")
        i += 1

    close_lists()
    if in_pre and pre_buf:
        out.append(f"<pre><code>{_escape(chr(10).join(pre_buf))}</code></pre>")

    return "\n".join(out)


# ---------------------------------------------------------------------------
# Brief parsing helpers
# ---------------------------------------------------------------------------

def _parse_brief_metadata(brief_md: str) -> dict:
    """Extract run metadata from the SPEC-1 brief header."""
    meta: dict = {
        "run_id": "—",
        "signals_harvested": "—",
        "records_stored": "—",
        "date_str": date.today().strftime("%d %b %Y").upper(),
    }
    for line in brief_md.splitlines():
        if line.startswith("**Run:**"):
            meta["run_id"] = line.split("**Run:**")[-1].strip()
        elif line.startswith("**Signals harvested:**"):
            meta["signals_harvested"] = line.split("**Signals harvested:**")[-1].strip()
        elif line.startswith("**Records stored:**"):
            meta["records_stored"] = line.split("**Records stored:**")[-1].strip()
        elif re.match(r"\*\*Completed:\*\*", line):
            raw = re.sub(r"\*\*Completed:\*\*\s*", "", line).strip()
            try:
                dt = datetime.fromisoformat(raw)
                meta["date_str"] = dt.strftime("%d %b %Y").upper()
            except ValueError:
                pass
    return meta


def _split_sections(brief_md: str) -> dict[str, str]:
    """Split brief into named sections by ## headings."""
    sections: dict[str, str] = {"_preamble": ""}
    current = "_preamble"
    buf: list[str] = []

    for line in brief_md.splitlines():
        m = re.match(r"^##\s+(.*)", line)
        if m:
            sections[current] = "\n".join(buf).strip()
            current = m.group(1).strip()
            buf = []
        else:
            buf.append(line)
    sections[current] = "\n".join(buf).strip()
    return sections


# ---------------------------------------------------------------------------
# Template injection
# ---------------------------------------------------------------------------

_PLACEHOLDER_PATTERNS = [
    # Exec summary lede paragraph
    (
        r'<p class="lede">\s*This issue\'s coverage window[^<]*</p>',
        None,  # replaced dynamically
    ),
    # Summary points ul
    (
        r'<ul class="summary-points">.*?</ul>',
        None,
    ),
    # Issue metadata box grid
    (
        r'(<div class="box-grid">)\s*<div><span class="k">Signals Ingested</span> 000</div>.*?</div>\s*</div>',
        None,
    ),
    # Signals section articles
    (
        r'<!-- ={10,} 02 SIGNALS ={10,} -->.*?<!-- ={10,} 03 SIGNAL ASSESSMENT',
        None,
    ),
    # Assessment prose
    (
        r'<div class="assessment">.*?</div>\s*<div class="confidence-note">',
        None,
    ),
    # Story leads
    (
        r'<!-- ={10,} 05 STORY LEADS ={10,} -->.*?<!-- ={10,} 06',
        None,
    ),
]


def _build_exec_summary_html(meta: dict, brief_text: str) -> str:
    """Build the Executive Summary block from brief text."""
    lede = (
        f"SPEC-1 cycle <code>{meta['run_id']}</code> ingested "
        f"<strong>{meta['signals_harvested']}</strong> signals, of which "
        f"<strong>{meta['records_stored']}</strong> passed composite gating and are "
        f"reported below. All findings are anchored to the cited public record and should "
        f"be treated as provisional pending independent verification."
    )
    return f'<p class="lede">{lede}</p>'


def _build_signals_section_html(sections: dict[str, str]) -> str:
    """Build Section 02 Signals + Section 03 Assessment from brief sections."""
    signals_html_parts: list[str] = []
    sig_num = 1

    for title, body in sections.items():
        # Skip metadata/preamble sections
        if title.startswith("_") or title.upper().startswith("SPEC-1"):
            continue
        if not body.strip():
            continue

        sig_id = f"SIG-{sig_num:03d}"
        body_html = md_to_html(body)
        signals_html_parts.append(
            f"""    <article class="signal">
      <div class="signal-head">
        <span class="signal-id">{sig_id}</span>
        <span class="signal-title">{_escape(title)}</span>
        <span class="signal-verdict">SPEC-1 Output</span>
      </div>
      <div class="signal-body">
        {body_html}
      </div>
      <div class="signal-src">SPEC-1 Intelligence Engine · Automated OSINT Pipeline</div>
      <div class="gates"><span>Assessment</span><span>Machine-Assisted</span></div>
    </article>"""
        )
        sig_num += 1

    if not signals_html_parts:
        signals_html_parts.append(
            '    <p><em>No gated signals recorded for this cycle.</em></p>'
        )

    return "\n".join(signals_html_parts)


def _build_meta_box_grid_html(meta: dict) -> str:
    return (
        f'<div class="box-grid">'
        f'<div><span class="k">Signals Ingested</span> {meta["signals_harvested"]}</div>'
        f'<div><span class="k">Passed Gates</span> {meta["records_stored"]}</div>'
        f'<div><span class="k">Published</span> {meta["records_stored"]}</div>'
        f'<div><span class="k">Held</span> 0</div>'
        f'<div><span class="k">Run ID</span> {_escape(meta["run_id"])}</div>'
        f'<div><span class="k">Methodology Ver.</span> v0.6</div>'
        f"</div>"
    )


def _update_issue_line(template_html: str, meta: dict, today: date) -> str:
    """Update the issue-line metadata strip with live run data."""
    coverage_start = today.replace(day=max(1, today.day - 7)).strftime("%d %b").upper()
    coverage_end = today.strftime("%d %b").upper()
    new_issue_line = (
        f'<div class="issue-line">\n'
        f'      <div class="cell"><span class="k">Date</span>'
        f'<span class="v">{today.strftime("%d %b %Y").upper()}</span></div>\n'
        f'      <div class="cell"><span class="k">Run ID</span>'
        f'<span class="v">{_escape(meta["run_id"])}</span></div>\n'
        f'      <div class="cell"><span class="k">Signals</span>'
        f'<span class="v">{meta["signals_harvested"]}</span></div>\n'
        f'      <div class="cell"><span class="k">Coverage Window</span>'
        f'<span class="v">{coverage_start} – {coverage_end}</span></div>\n'
        f"    </div>"
    )
    return re.sub(
        r'<div class="issue-line">.*?</div>\s*</div>\s*<div class="dist-banner">',
        new_issue_line + '\n    <div class="dist-banner">',
        template_html,
        flags=re.DOTALL,
    )


def inject_brief_into_template(
    brief_md: str,
    template_html: str,
    output_date: date,
) -> str:
    """Return a publication-ready HTML string with SPEC-1 brief content injected."""
    meta = _parse_brief_metadata(brief_md)
    sections = _split_sections(brief_md)

    result = template_html

    # 1. Update issue-line metadata strip
    result = _update_issue_line(result, meta, output_date)

    # 2. Update <title> date
    result = re.sub(
        r"<title>NOTITIA CIVICA[^<]*</title>",
        f"<title>NOTITIA CIVICA — Civic Intelligence Brief — {output_date.strftime('%d %b %Y').upper()}</title>",
        result,
    )

    # 3. Replace exec summary lede paragraph
    exec_html = _build_exec_summary_html(meta, brief_md)
    result = re.sub(
        r'<p class="lede">.*?</p>',
        exec_html,
        result,
        count=1,
        flags=re.DOTALL,
    )

    # 4. Replace summary-points list with cycle stats
    summary_points = (
        f'<ul class="summary-points">\n'
        f'  <li>Signals ingested this cycle: <strong>{meta["signals_harvested"]}</strong>.</li>\n'
        f'  <li>Records passing all 4 gates: <strong>{meta["records_stored"]}</strong>.</li>\n'
        f"  <li>All findings are open-source. Internal scoring weights are not published.</li>\n"
        f"</ul>"
    )
    result = re.sub(
        r'<ul class="summary-points">.*?</ul>',
        summary_points,
        result,
        count=1,
        flags=re.DOTALL,
    )

    # 5. Replace meta-box grid (signals ingested / passed gates)
    new_grid = _build_meta_box_grid_html(meta)
    result = re.sub(
        r'<div class="box-grid">.*?</div>(?=\s*</div>)',
        new_grid,
        result,
        count=1,
        flags=re.DOTALL,
    )

    # 6. Replace the Signals section articles (02) with live signal cards
    signals_html = _build_signals_section_html(sections)
    # Replace placeholder article blocks between section 02 head and section 03 head
    result = re.sub(
        r'(<!-- ={5,} 02 SIGNALS ={5,} -->.*?<span class="tag">Gated · Ranked</span>\s*</div>)'
        r'.*?'
        r'(<!-- ={5,} 03 SIGNAL ASSESSMENT)',
        lambda m: m.group(1) + "\n\n" + signals_html + "\n\n  " + m.group(2),
        result,
        count=1,
        flags=re.DOTALL,
    )

    # 7. Replace assessment prose — use the full brief as the analytic body
    full_brief_html = md_to_html(brief_md)
    new_assessment = (
        f'<div class="assessment">\n'
        f"{full_brief_html}\n"
        f"</div>\n"
        f'      <div class="confidence-note">'
    )
    result = re.sub(
        r'<div class="assessment">.*?</div>\s*<div class="confidence-note">',
        new_assessment,
        result,
        count=1,
        flags=re.DOTALL,
    )

    # 8. Add SPEC-1 generation note in footer seal
    date_stamp = output_date.strftime("%Y-%m-%d")
    result = re.sub(
        r'(<div class="seal">)',
        f'<div class="spec1-stamp" style="text-align:center;font-family:var(--mono);'
        f'font-size:7pt;letter-spacing:.3em;color:var(--ink-faint);margin-top:10px;">'
        f"GENERATED BY SPEC-1 · {date_stamp} · OPEN SOURCES ONLY</div>\n  \\1",
        result,
        count=1,
    )

    return result


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--brief", default="briefs/spec1_brief_latest.md",
                        help="Path to SPEC-1 brief Markdown file (default: briefs/spec1_brief_latest.md)")
    parser.add_argument("--template", required=True,
                        help="Path to Notitia Civica print template HTML")
    parser.add_argument("--out", required=True,
                        help="Output path for the rendered publication HTML")
    parser.add_argument("--date", default=None,
                        help="Publication date (YYYY-MM-DD, default: today)")
    parser.add_argument("--run-id", default=None,
                        help="Optional SPEC-1 run ID for metadata display")
    args = parser.parse_args(argv)

    brief_path = Path(args.brief)
    template_path = Path(args.template)
    out_path = Path(args.out)

    if not brief_path.exists():
        print(f"[inject] ERROR: brief not found: {brief_path}", file=sys.stderr)
        return 1
    if not template_path.exists():
        print(f"[inject] ERROR: template not found: {template_path}", file=sys.stderr)
        return 1

    output_date = date.today()
    if args.date:
        try:
            output_date = date.fromisoformat(args.date)
        except ValueError:
            print(f"[inject] ERROR: invalid --date '{args.date}' (expected YYYY-MM-DD)", file=sys.stderr)
            return 1

    brief_md = brief_path.read_text(encoding="utf-8")
    template_html = template_path.read_text(encoding="utf-8")

    # Optionally override run_id in brief metadata
    if args.run_id:
        brief_md = f"**Run:** {args.run_id}\n" + brief_md

    result_html = inject_brief_into_template(brief_md, template_html, output_date)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(result_html, encoding="utf-8")

    file_size_kb = out_path.stat().st_size // 1024
    print(f"[inject] Written: {out_path} ({file_size_kb} KB, date={output_date})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
