# Contributing to SPEC-1

SPEC-1 is proprietary (see [LICENSE](LICENSE)). Pull requests from outside
the project are not accepted.

## What helps

**Corrections.** If a published card, record or brief gets something wrong,
[open an issue](https://github.com/CLS-1000/spec-1/issues) with:

- the measure, record or brief ID,
- what SPEC-1 says,
- what the official source says, with a link.

Corrections to the underlying public data are recorded with the row they
fix, so the original stays visible.

**Bug reports.** Open an issue with the command you ran, what you expected
and what happened. Include the Python version and, for a cycle problem, the
relevant lines of `logs/llm_fallback.jsonl` or the gate log.

**Verification results.** If you ran `verify.py` against a published pack
and it did not pass, open an issue with the command and its output.

## Questions

Write to spec1_ops@proton.me.

## Development process

Work inside the project follows [CLAUDE.md](CLAUDE.md): agent work on
`claude/*` branches, pull requests into `develop`, releases from `develop`
to `Main`, the frozen core under `src/spec1_core/core/`, and the PR template
in [`.github/pull_request_template.md`](.github/pull_request_template.md).

Never commit `.env` or any file containing an API key. If a key may have
leaked, rotate it at <https://console.anthropic.com/settings/keys> first.
