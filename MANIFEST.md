# Research Mode — file drop

> **Status: integrated.** All files listed below have been merged into `CLS-1000/spec-1`.
> This document is kept as a reference for what was added in the Research Mode batch.

These files mirror their exact path in `CLS-1000/spec-1` (develop branch),
as of base commit `3d1d5f9`. Unzip this into your repo root and the folders
land in the right place.

## New files — safe to just drop in

```
docs/research_mode.md
research/topics/topic_dprk_missile_indigenization.json
research/topics/topic_portland_metro_housing_levy_implementation.json
src/cls_research/__init__.py
src/cls_research/collector.py
src/cls_research/dossier.py
src/cls_research/expansion.py
src/cls_research/formatter.py
src/cls_research/pipeline.py
src/cls_research/schemas.py
src/cls_research/store.py
src/cls_research/topics.py
src/spec1_core/tools/run_research.py
tests/test_research.py
```

## Modified files — check for drift before overwriting

These already exist in your repo. If `develop` has moved since `3d1d5f9`
(check with `git log --oneline -1`), someone may have touched these same
files in the meantime — overwriting blind could clobber unrelated changes.
Diff before replacing:

```
.env.example          — added two SPEC1_RESEARCH_* env var lines
.gitignore            — added research/dossiers/ to the generated-artifacts block
Makefile              — added the `research` target + .PHONY entry + help line
README.md             — added a Research Mode bullet + use case
mcp_server.py         — added tool_run_research() + its TOOLS dict entry + docstring line
memory/context.md     — added cls_research to Active Modules + Agent Write Surfaces
memory/decisions.md   — added ADR-009
src/spec1_labels.py   — added RESEARCH_STATUS_*, RESEARCH_GAP_MARKER, EXPANSION_RULE_*, ResearchStatusT, is_valid_research_status
```

If your local `develop` is still at `3d1d5f9` (the base these were generated
from), these are safe to overwrite outright. Otherwise, open each one
side-by-side and merge the additions in manually — they're all small,
additive edits, not rewrites of existing logic.

## After copying

```bash
git add -A
git commit -m "feat: add Research Mode (cls_research) — analyst-defined topic dossiers"
git push origin develop
```

Then verify: `PYTHONPATH=src pytest tests/test_research.py -v` (33 tests,
all passing in the original sandbox run) and `PYTHONPATH=src python -m
spec1_core.tools.run_research --list-topics`.
