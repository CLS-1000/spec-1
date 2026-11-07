from pathlib import Path
import re


WORKFLOW = (
    Path(__file__).resolve().parents[1]
    / ".github"
    / "workflows"
    / "notitia_civica_publish.yml"
)


def _step(workflow, name):
    match = re.search(
        rf"(?ms)^      - name: {re.escape(name)}\n(.*?)(?=^      - name: |\Z)",
        workflow,
    )
    assert match, f"workflow step not found: {name}"
    return match.group(1)


def test_notitia_publication_requires_eligible_brief():
    workflow = WORKFLOW.read_text(encoding="utf-8")
    guard = _step(workflow, "Check publication eligibility")

    assert "id: publish_guard" in guard
    assert 'echo "publishable=false" >> "$GITHUB_OUTPUT"' in guard
    assert 'echo "publishable=true" >> "$GITHUB_OUTPUT"' in guard
    assert "spec1_core.briefing.writer --check" in guard

    for name in (
        "Checkout notitia-civica",
        "Inject SPEC-1 brief into Notitia Civica print template",
        "Copy brief Markdown files to notitia-civica",
        "Commit and push to notitia-civica",
    ):
        assert (
            "steps.publish_guard.outputs.publishable == 'true'"
            in _step(workflow, name)
        )
