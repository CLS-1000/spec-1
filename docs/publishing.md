# Publishing the daily brief

How a brief gets from the daily cycle to the publication repo, and what has to
be configured for that to happen.

## The path

```
run-cycle.yml (13:00 UTC daily)
  └─ python -m spec1_engine.app.cycle
       └─ writes briefs/spec1_brief_YYYY-MM-DD.md
  └─ upload-artifact                     ← always, even on failure
  └─ check_brief_publishable.py          ← fails the run if the brief is not real
  └─ publish_brief.sh                    ← opens a PR on notitia-civica
```

## Why there is a gate

`generate_brief()` never raises. When `ANTHROPIC_API_KEY` is missing or the API
call fails, it returns `_fallback_brief()` — a stub that interpolates the entire
`cycle_stats` dict — and the cycle writes it to disk and **exits 0**.

That means a green cycle run does not tell you a brief was produced. This is not
hypothetical: the 2026-08-04 run reported success and wrote a 32,971-word file
whose contents were `[Brief generation failed. Raw stats: {...}]`. The word count
had grown from 31 in April to 33k in August purely because the record count grew
— the same failure the whole time, in a bigger wrapper.

`check_brief_publishable.py` closes that gap. It rejects a brief that:

- contains the `[Brief generation failed.` marker
- is below `--min-words` (default 200) — a stub
- is above `--max-words` (default 10000) — beyond what `MAX_TOKENS` permits, so
  a data dump rather than a brief

A rejected brief fails the workflow. That is the point: the run should go red
when no brief was generated.

Run it by hand against any brief:

```bash
python .github/scripts/check_brief_publishable.py briefs/spec1_brief_latest.md
```

## Required secrets

Both are set in **Settings → Secrets and variables → Actions** on `CLS-1000/spec-1`.

| Secret | Purpose | Without it |
|---|---|---|
| `ANTHROPIC_API_KEY` | Generating the brief | Every run produces a fallback stub and now **fails the gate**, turning the daily run red |
| `NOTITIA_PUBLISH_TOKEN` | Opening the PR on the publication repo | The brief is generated and gated but not published; the run logs a warning and stays green |

`NOTITIA_PUBLISH_TOKEN` needs `contents: write` and `pull_requests: write` on
`CLS-1000/notitia-civica`. A fine-grained PAT scoped to that single repository is
enough — it does not need any access to `spec-1` itself.

## Why a pull request and not a push

`notitia-civica/methodology/editorial-standard.md` places editorial
responsibility with a human, and the README states that SPEC-1 "supports source
monitoring and signal organization. Editorial responsibility remains human."

Pushing generated output straight into the publication surface would contradict
that. The gate establishes only that a brief was *generated*; it makes no
judgement about whether the content is fit to publish. A person still decides
that, by merging or closing the PR.

## Behaviour worth knowing

- **Re-runs are safe.** If `brief/YYYY-MM-DD` already exists on the publication
  repo, the script exits without opening a second PR.
- **The index is append-only.** Only the entries matching the brief's own date
  are appended to `briefs/brief_index.jsonl`; the publication repo's existing
  history is never rewritten.
- **The clone pins its base branch** (`--branch main`). Relying on the remote's
  default HEAD risks checking out a tree with no `briefs/`, in which case the
  append silently becomes a fresh file that drops every prior entry. The script
  also refuses to publish into a tree with no `briefs/` directory.
- **Artifacts upload before the gate**, with 90-day retention, so a failed run's
  output is still recoverable for diagnosis.

## Overrides

| Variable | Default | Use |
|---|---|---|
| `PUBLICATION_REPO` | `CLS-1000/notitia-civica` | Target a different publication repo |
| `BASE_BRANCH` | `main` | Base the PR on a different branch |
