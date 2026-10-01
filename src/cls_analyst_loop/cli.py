# @domain:   handler
# @module:   cli
# @loc:      gh_main
# @status:   stable
# @depends:  cls_db

"""Command-line interface for analyst workflow chain of custody.

Commands:
  new-case        Create a new case from a lead
  submit-output   File analyst output for a case
  run-audit       Run LLM audit on analyst output
  file-verdict    File verdict on case (routes to publication)
  list-cases      List cases with optional filtering
  show            Display case + output + audit + verdict chain
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import click

from cls_analyst_loop.audit import run_audit
from cls_analyst_loop.schemas import (
    AnalystCase,
    AnalystOutput,
    AnalystVerdict,
)
from cls_analyst_loop.store import AnalystLoopStore

logger = logging.getLogger(__name__)


def _get_store(store_path: str = "analyst_loop") -> AnalystLoopStore:
    """Get or create the store."""
    return AnalystLoopStore(base_path=Path(store_path))


@click.group()
@click.option("--store-path", default="analyst_loop", help="Path to analyst_loop storage")
@click.pass_context
def cli(ctx: click.Context, store_path: str) -> None:
    """Analyst workflow chain of custody logging."""
    ctx.ensure_object(dict)
    ctx.obj["store"] = _get_store(store_path)


@cli.command("new-case")
@click.option("--lead-id", required=True, help="Lead ID")
@click.option("--run-id", required=True, help="Originating run ID")
@click.option("--lead-text", required=True, help="Full lead content")
@click.option("--feed-prompt", required=True, help="Feed prompt for analyst")
@click.option("--analyst", default="anonymous", help="Analyst identifier")
@click.pass_context
def new_case(
    ctx: click.Context,
    lead_id: str,
    run_id: str,
    lead_text: str,
    feed_prompt: str,
    analyst: str,
) -> None:
    """Create a new case from a lead."""
    store = ctx.obj["store"]
    now = datetime.now(timezone.utc)
    case_id = AnalystCase.make_id(lead_id, analyst, now)
    case = AnalystCase(
        case_id=case_id,
        run_id=run_id,
        lead_id=lead_id,
        lead_text=lead_text,
        feed_prompt=feed_prompt,
        analyst_id=analyst,
        created_at=now,
    )
    store.save_case(case)
    click.echo(f"Created case: {case_id}")
    click.echo(json.dumps(case.to_dict(), indent=2))


@cli.command("submit-output")
@click.option("--case-id", required=True, help="Case ID")
@click.option("--file", "output_file", required=True, type=click.File("r"), help="Report file")
@click.option("--source-data", default="", help="Source data used by analyst")
@click.pass_context
def submit_output(
    ctx: click.Context,
    case_id: str,
    output_file: object,
    source_data: str,
) -> None:
    """Submit analyst output for a case."""
    store = ctx.obj["store"]
    case = store.get_case(case_id)
    if not case:
        click.echo(f"Error: case {case_id} not found", err=True)
        sys.exit(1)

    raw_output = output_file.read()
    now = datetime.now(timezone.utc)
    output_id = AnalystOutput.make_id(case_id, now)
    output = AnalystOutput(
        output_id=output_id,
        case_id=case_id,
        raw_output=raw_output,
        source_data=source_data,
        submitted_at=now,
    )
    store.save_output(output)
    click.echo(f"Submitted output: {output_id}")
    click.echo(json.dumps(output.to_dict(), indent=2))


@cli.command("run-audit")
@click.option("--output-id", required=True, help="Output ID to audit")
@click.option("--llm", default="claude", help="LLM to use (claude)")
@click.pass_context
def run_audit_cmd(ctx: click.Context, output_id: str, llm: str) -> None:
    """Run LLM audit on analyst output."""
    store = ctx.obj["store"]
    output = store.get_output(output_id)
    if not output:
        click.echo(f"Error: output {output_id} not found", err=True)
        sys.exit(1)

    case = store.get_case(output["case_id"])
    if not case:
        click.echo(f"Error: case {output['case_id']} not found", err=True)
        sys.exit(1)

    click.echo(f"Running audit on {output_id}...")
    audit = run_audit(
        output_id=output_id,
        raw_output=output["raw_output"],
        source_data=output["source_data"],
        audit_llm=llm,
    )
    store.save_audit(audit)
    click.echo(f"Audit complete: {audit.audit_id}")
    audit_data = json.loads(audit.audit_output)
    click.echo(f"  Confirmed: {audit.claims_confirmed}")
    click.echo(f"  Flagged: {audit.claims_flagged}")
    click.echo(f"  Dropped: {audit.claims_dropped}")
    click.echo(f"  Confidence: {audit.confidence:.2f}")
    if audit_data.get("findings"):
        click.echo(f"  Findings: {len(audit_data['findings'])}")
        for finding in audit_data["findings"]:
            click.echo(f"    [{finding['severity']}] {finding['claim'][:60]}")


@cli.command("file-verdict")
@click.option("--case-id", required=True, help="Case ID")
@click.option("--output-id", required=True, help="Output ID")
@click.option("--kind", required=True, type=click.Choice(["confirmed", "partial", "flagged", "rejected"]), help="Verdict kind")
@click.option("--audit-id", default=None, help="Optional audit ID")
@click.option("--reviewer", default="anonymous", help="Reviewer identifier")
@click.option("--notes", default="", help="Reviewer notes")
@click.option("--publish", is_flag=True, default=False, help="Route to publication")
@click.pass_context
def file_verdict(
    ctx: click.Context,
    case_id: str,
    output_id: str,
    kind: str,
    audit_id: str | None,
    reviewer: str,
    notes: str,
    publish: bool,
) -> None:
    """File verdict on analyst output."""
    store = ctx.obj["store"]
    case = store.get_case(case_id)
    if not case:
        click.echo(f"Error: case {case_id} not found", err=True)
        sys.exit(1)

    output = store.get_output(output_id)
    if not output:
        click.echo(f"Error: output {output_id} not found", err=True)
        sys.exit(1)

    now = datetime.now(timezone.utc)
    verdict_id = AnalystVerdict.make_id(case_id, reviewer, now)
    verdict = AnalystVerdict(
        verdict_id=verdict_id,
        case_id=case_id,
        output_id=output_id,
        audit_id=audit_id,
        kind=kind,
        reviewer=reviewer,
        notes=notes,
        published=publish,
        filed_at=now,
    )
    store.save_verdict(verdict)
    click.echo(f"Filed verdict: {verdict_id}")
    click.echo(f"  Kind: {kind}")
    click.echo(f"  Published: {publish}")
    if notes:
        click.echo(f"  Notes: {notes}")


@cli.command("list-cases")
@click.option("--lead-id", default=None, help="Filter by lead ID")
@click.option("--analyst", default=None, help="Filter by analyst ID")
@click.pass_context
def list_cases(ctx: click.Context, lead_id: str | None, analyst: str | None) -> None:
    """List cases with optional filtering."""
    store = ctx.obj["store"]
    cases = store.list_cases(lead_id=lead_id, analyst_id=analyst)
    if not cases:
        click.echo("No cases found")
        return

    for case in cases:
        outputs = store.outputs_for_case(case["case_id"])
        verdicts = store.verdicts_for_case(case["case_id"])
        click.echo(
            f"{case['case_id']} | lead={case['lead_id']} | analyst={case['analyst_id']} | "
            f"outputs={len(outputs)} | verdicts={len(verdicts)}"
        )


@cli.command("show")
@click.option("--case-id", required=True, help="Case ID")
@click.pass_context
def show_case(ctx: click.Context, case_id: str) -> None:
    """Display case + output + audit + verdict chain."""
    store = ctx.obj["store"]
    case = store.get_case(case_id)
    if not case:
        click.echo(f"Error: case {case_id} not found", err=True)
        sys.exit(1)

    click.echo("=== CASE ===")
    click.echo(json.dumps(case, indent=2))

    outputs = store.outputs_for_case(case_id)
    if outputs:
        click.echo("\n=== OUTPUTS ===")
        for output in outputs:
            click.echo(f"\n{output['output_id']}:")
            click.echo(output["raw_output"][:500] + "..." if len(output["raw_output"]) > 500 else output["raw_output"])

            audits = store.audits_for_output(output["output_id"])
            if audits:
                click.echo(f"\n  === AUDITS ({len(audits)}) ===")
                for audit in audits:
                    pass  # audit_output available as audit["audit_output"]
                    click.echo(f"    {audit['audit_id']}")
                    click.echo(f"      Confirmed: {audit['claims_confirmed']}")
                    click.echo(f"      Flagged: {audit['claims_flagged']}")
                    click.echo(f"      Confidence: {audit['confidence']:.2f}")

    verdicts = store.verdicts_for_case(case_id)
    if verdicts:
        click.echo("\n=== VERDICTS ===")
        for verdict in verdicts:
            click.echo(f"{verdict['verdict_id']}: {verdict['kind']} (published={verdict['published']})")
            if verdict["notes"]:
                click.echo(f"  {verdict['notes']}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    cli()
