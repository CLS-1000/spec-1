# Contributing to SPEC-1

> SPEC-1 is proprietary (see [LICENSE](LICENSE)). External contributions are
> not accepted by default; this document describes the development process
> the author and authorized collaborators follow. Reach out at
> lakampmatt@gmail.com before opening a PR.

SPEC-1 is a portfolio-grade OSINT engine; the bar for changes is "do not
break the deterministic, legible pipeline." This guide is the short version
of [CLAUDE.md](CLAUDE.md) — read that for the full governance contract.

## Ground rules

1. **The frozen core is frozen.** `src/spec1_core/core/` (schemas, IDs,
   logging, prompts) cannot change without explicit approval and a `MAJOR`
   version bump. Import from it; don't edit it.
2. **No stubs.** Every function body must be implemented. No `pass` placeholders,
   no `pytest.skip`, no `raise NotImplementedError`.
3. **Calibration is descriptive.** It surfaces drift — humans tune thresholds.
   Do not add auto-tuning.
4. **Briefing must never crash on LLM error.** Always fall back to the rule-based
   brief.
5. **Dual-write everything.** Stores append to JSONL *and* SQLite via
   `cls_db.dual_write`. Don't add a write path that bypasses one.
6. **Import labels from `spec1_labels`.** Never hard-code enum/label strings.

## Branches and PRs

| Branch       | Use                                                      |
|--------------|----------------------------------------------------------|
| `main`       | Human-curated, stable. PRs only — never push direct.     |
| `dev`        | Integration. Merge agent branches here first.            |
| `claude/*`   | Agent / automation work.                                 |
| `agent/*`    | Same.                                                    |
| topic-named  | Human-led changes (`docs/...`, `fix/...`, `feat/...`).   |

Every PR uses [`.github/pull_request_template.md`](.github/pull_request_template.md)
and must declare:

1. A summary of the change.
2. The version bump (`MAJOR` / `MINOR` / `PATCH`) and why.
3. Confirmation that `/core` was not modified, or the justification if it was.
4. Test status — `pytest` and `flake8` clean.

### Version bumps

| Bump  | When                                                        |
|-------|-------------------------------------------------------------|
| MAJOR | Breaking change to `/core` contracts or schemas             |
| MINOR | New module, scorer, adapter, prompt surface, or API route   |
| PATCH | Bug fix, CI, infra, tests, docs                             |

Bumps go in `pyproject.toml` and a one-line entry in `CHANGELOG.md`.

## Local setup

```bash
bash scripts/setup_dev.sh      # one-shot: venv + editable install + dev deps
cp .env.example .env           # then set ANTHROPIC_API_KEY
make test                      # pytest + flake8
```

## Tests

- Use `tmp_path` fixtures; mock all external network and Anthropic calls.
- New modules need a matching `tests/test_<module>.py`.
- Don't lower coverage. The suite is the contract.

## Secrets

Never commit `.env`, `.bashrc`, or any file containing an API key. The
`.gitignore` covers the obvious ones — if you add a new init/config file,
add it there too. If you suspect a key was leaked, rotate it at
<https://console.anthropic.com/settings/keys> before doing anything else.

## Style

- Internal models: `dataclasses`. API schemas: `pydantic`.
- Run `flake8` before opening a PR. The CI gate is the same.
- Keep functions small enough that a reviewer can hold them in their head.
