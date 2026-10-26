# SPEC-1

**Status:** Beta · **Version:** 0.8.0 · Python 3.11+ · Proprietary · EVASTARARCANA LLC, Portland, Oregon

SPEC-1 is an open-source intelligence engine that runs on a single laptop. It reads public sources on a schedule, decides which items deserve a closer look, checks them with a language model running on your own machine, and drafts what it found for a person to edit.

Every decision is written down, including the decision to throw something out. Nothing reaches publication unless a real model checked every record behind it.

| | |
|---|---|
| **Sources** | 10 national-security RSS feeds; Oregon's legislative API (bills and interim committees); OpenStates / LegiScan; FARA; Congress; courts; Portland campaign finance and seven local institutions |
| **Filtering** | 4 gates (credibility, volume, velocity, novelty). Every pass *and* every rejection is logged with its score and the score it needed |
| **Models** | Local first: Qwen 2.5 on Ollama does the analysis and writes the brief. Claude is the fallback, deterministic rules the floor. The cycle never crashes for lack of a model |
| **Publishing** | A brief is publishable only if every record behind it is `llm_verified`. Rule-based output is refused by the publisher, not just labelled |
| **Integrity** | Append-only records; published findings sealed in an Ed25519 chain anyone can verify offline |
| **Surfaces** | HTTP API, Triage Desk UI, MCP server (17 tools), CLIs |
| **Tests** | 1,718 tests across 80 files |

---

## Check it yourself

You don't have to trust SPEC-1's output. Its published findings are sealed, and anyone can check them offline with one file and the Python standard library.

The first published finding is about Oregon's legislative data. The Legislature's public data service carries a `Vetoed` field on every bill. On 27 September 2026 it was false on 26 of the 27 measures whose own histories record "Governor vetoed.", including all seven vetoes of 2025. The gap was reported to the Legislature on 28 September; by 29 September the field was true on all 27, and the Legislature confirmed the numbers and the update. The write-up is [Oregon's Veto Field](https://github.com/CLS-1000/pdx-1i/blob/main/ui/oregon-veto-field.html) (Notitia Civica, issue OR-001).

The evidence pack was sealed on 1 October and lives in [notitia-civica/evidence](https://github.com/CLS-1000/notitia-civica/tree/main/evidence). To check it:

```bash
git clone https://github.com/CLS-1000/notitia-civica
cd notitia-civica/evidence
python3 verify.py or_veto_pack_2026-10-01/chain \
  --pubkey c7dbbf86b2e014fad70190276f4e20969743d2fa2bc7c13e48c95fdd91a7d0ad \
  --anchor or_veto_pack_2026-10-01/anchor.json
```

It prints `OK: 56 records, 1 seals, head 55` and exits 0. The public key and anchor are published in [OPERATOR_KEY.md](https://github.com/CLS-1000/notitia-civica/blob/main/evidence/OPERATOR_KEY.md).

A pass shows the records have not changed since they were sealed. It does not show the records were true when they were written. That part is checked by reading them.

---

## Oregon Legislature, Verified

**Live: [Oregon Legislature, Verified — 2025 session](https://cls-1000.github.io/notitia-civica/oregon/2025R1/)**, every bill of the 2025 regular session, sealed and checkable. Its anchor is published in [OPERATOR_KEY.md](https://github.com/CLS-1000/notitia-civica/blob/main/evidence/OPERATOR_KEY.md).

`src/cls_civica/` turns every bill in an Oregon legislative session into a plain-language card: what happened, when, and where it stands. Every sentence cites the official rows it rests on.

1. [proc_track](https://github.com/CLS-1000/proc_track) replays each bill's official action history from the Legislature's API and checks that every step was a legal move under chamber procedure. Anything it can't explain halts the build.
2. `cls_civica` writes the card from the replay.
3. A publication gate checks that every claim cites rows in the sealed evidence. A card that fails is recorded as withheld, never dropped.
4. Every card and its evidence go into a sealed, append-only chain (Ed25519). The site ships with the same offline verifier as above.

The 2025 regular session (2025R1): 3,466 measures, all published, none withheld or unverified. 633 became law, 7 were vetoed, 66 resolutions were adopted, 1 measure failed and 2,759 stopped short. Edited claims, altered evidence, a loosened gate, deleted records and the wrong key all fail verification.

The site proves it matches what was recorded from the Legislature's public data and that nothing changed afterward. It does not prove the Legislature's data is free of errors, and it has nothing to do with casting or counting ballots.

```bash
git clone https://github.com/CLS-1000/proc_track ../proc_track   # or set SPEC1_PROC_TRACK_HOME
PYTHONPATH=src python -m cls_civica build --session 2025R1 --out out/civica_2025R1 --demo-key
PYTHONPATH=src python -m cls_civica verify out/civica_2025R1 --pubkey <public key hex from the build>
```

`--demo-key` seals with a throwaway key for a preview. [src/cls_civica/README.md](src/cls_civica/README.md) covers real builds and the chain format.

---

## Two desks, one pipeline

`python -m spec1_core.app.cycle` runs a desk end to end: collect, parse, score, investigate, verify, analyze, store, brief.

### The standard desk (default)

**Harvest.** Ten RSS feeds: War on the Rocks, The Cipher Brief, Just Security, RAND, the Atlantic Council, Defense One, 38 North, NK News, CSIS's Korea Chair and Yonhap. The list is one dictionary in `src/spec1_core/signal/harvester.py`. Items already in the store are skipped.

**Score.** Each item must clear all four gates.

| Gate | What it measures | Must reach |
|---|---|---|
| Credibility | The source's weight in the operator's credibility table. Unlisted sources get 0.60. | 0.65 |
| Volume | Length, in tiers from under 30 words to over 500 | 0.30 (about 30 words) |
| Velocity | Age. Steps down from 1.0 (under six hours) to 0.75, 0.50, 0.25 and 0.10 (over a week). | 0.50 (under 72 hours) |
| Novelty | Terms that signal something new: arrests, charges, classified material, corruption and similar | 1 term |

Because the credibility gate sits just above the default weight, a source not in the table does not get through. The thresholds live in one file, `src/spec1_core/config/calibration.py`. A person sets them; the system never adjusts them.

**Log.** Every scored item, passed or blocked, gets one line in the gate log: the decision, the gates it failed, and each gate's measured value beside its threshold. The file sits next to the store as `<store>_gate_decisions.jsonl`, or wherever `SPEC1_GATE_LOG_PATH` points.

**Investigate, verify, analyze.** Items that pass become hypotheses. The model reads the hypothesis together with the article's own text and classifies it as Corroborated, Escalate, Investigate, Monitor, Conflicted or Archive, with a confidence score. The analyzer blends that with the source's weight into a final record. Each record keeps an excerpt of the article, the model's stated reasoning, and its `analysis_tier`: `llm_verified` only if a real model answered, `rule_based` otherwise.

Small local models sometimes return almost-JSON (an unescaped quote inside the reasoning, say). The verifier recovers the fields instead of demoting the record to `rule_based`.

**Store.** Records are appended to JSONL, the system of record, and mirrored into SQLite for queries. Nothing is updated in place. If the SQLite copy is lost, it can be rebuilt from the JSONL.

### The Legislative & Judicial Desk (`--desk legislative`)

```bash
python -m spec1_core.app.cycle --desk legislative --since-days 90 --max-signals 25
```

Legislative work doesn't look like news. Bills move over months, and Oregon's Legislature spends most of the year in interim committees. This desk collects:

- **Oregon measures** from the Legislature's OData API whose last action falls in the window
- **Oregon interim committee meetings** with their agendas: who is testifying, on what, and which bills are named. Past meetings and the next 14 days of scheduled hearings are both in scope
- **Other states' bills** from OpenStates or LegiScan (needs `OPENSTATES_API_KEY`). If both services fail, the adapter's synthetic sample bills are discarded, never stored

The four gates are evaluated and recorded on every item but not enforced. A state agency is not a weighted news source, and a bill signed in August is not 72-hour news. The window and a per-run cap (25 by default, since each item costs one local-model verification) take their place. Priority comes from the bill's status: signed or passed is ELEVATED, in committee is STANDARD, everything else MONITOR.

Each item is verified on the local model like any other record. Records go to `spec1_legislative.jsonl`, tagged `domain = state_leg.<state>.<kind>`. The desk writes two briefs: a model-written `briefs/spec1_legislative_<date>.md` with its own provenance sidecar, and the rule-based desk view in `leg_jud_briefs.jsonl`, served at `/api/v1/leg_jud/brief`. Neither touches the daily brief or the index the publisher reads.

First live run (25 October 2026, 90-day window): 16 measures and 51 interim committee meetings in range. 10 were taken and all 10 came back `llm_verified` from Qwen 2.5 (3B) on a 7 GB WSL machine.

---

## Models: local first

Every model call goes through one client, and each task follows its own route: an ordered list of backends.

| Backend | What it is |
|---|---|
| `local` | A model on your own machine: Ollama, or any server that speaks the OpenAI chat API (llama.cpp, vLLM, LM Studio) |
| `claude` | Anthropic's API (`ANTHROPIC_API_KEY`) |
| `mock` | Deterministic rules. No model, no network, always available |

**The brief is local-first.** It is written by Qwen 2.5 on Ollama. If Ollama can't answer, Claude writes it (when a key is set). If neither can, a rule-based brief is written and says so under its title: *AI brief unavailable — … Rule-based brief generated from cycle data.* The cycle records which one wrote it (`brief_backend`).

**Analysis follows the task route.** With nothing configured, analysis tries Claude, then local, then rules. To keep analysis on your machine:

```bash
SPEC1_LLM_ROUTE_ANALYZE=local,mock
```

Under that route, analysis falls back to rules, never to Claude.

**Defaults sized for a laptop.** `qwen2.5:3b` is the brief model and, on machines under 8 GB, the analysis model. It runs CPU-only in about 2 GB, at roughly 10–20 seconds per verification and a few minutes per brief. `OLLAMA_MODEL` overrides both. 7B/8B models need more than 4.5 GiB free; on a smaller machine Ollama refuses them and the cycle falls back to rules.

Reasoning models that wrap answers in `<think>` blocks are handled: the blocks are stripped before the answer is read. Every call is logged to `logs/llm_fallback.jsonl` with its task and the backend that answered, so a weak result can be traced to the model that produced it.

**Writing the brief by hand.** Each cycle also writes `briefs/spec1_handoff_<date>.md`. It holds the same instructions and run data the model gets, plus the format every story lead must follow. Hand it to Claude in a chat and ask for the brief. `python -m spec1_core.briefing.writer --mark-hand-written <brief>` records that, and the brief stays publishable only if its records were `llm_verified`.

---

## What gets published, and what can't be

Rule-based output is never analysis, so it is never published.

- **Every brief gets a provenance sidecar,** `<brief>.meta.json`: the run, the tier of its records (`llm_verified` / `rule_based`), and who wrote it (`model`, `rule_fallback`, `hand_written`).
- **The publisher refuses** anything without a sidecar, or whose sidecar is not `llm_verified`. The check runs in three places: `notitia_civica_publish.yml`, `scripts/inject_brief_to_template.py` and `python -m spec1_core.briefing.writer --check <brief>`. One rule-based record makes the whole brief unpublishable.
- **GitHub Actions has no model, so it runs triage only.** `run-cycle.yml` (13:00 UTC daily) runs `--triage-only`: harvest, the four gates and Tier 3 rules, with no brief, handoff, PDF or case research. It commits state to the `data` branch. Real analysis runs locally with `make cycle`.

---

## What comes out

**A daily brief.** A structured first draft built from the stored records. Confidence is stated as a tier, such as *confirmed by two independent sources*, *single-source unconfirmed* or *insufficient signal*, rather than left to adjectives. A person edits it before it goes anywhere.

**A legislative brief.** The Legislative & Judicial Desk's model-written brief, plus a rule-based desk view in fixed sections: federal members, lobbying and FARA, judicial activity, state legislatures, stated purpose against observed beneficiary, geopolitical context and story leads.

**Leads.** Records worth pursuing, each with the anomaly that flagged it, the records that support it, and a drafted list of documents to request. The analyst loop (`python -m cls_analyst_loop`) tracks a lead from dispatch through an analyst's write-up, an audit and a filed verdict.

**Influence-pattern scoring.** Fourteen named framing patterns, among them fear amplification, manufactured consensus, coordinated amplification and whataboutism, checked across a cycle's harvest, with evidence chains back to the source text.

**Research mode.** A standing dossier on a topic you define by keywords, entities and questions. Each run adds to it. Research mode skips the gates and makes no model calls.

**PDX-1i, the Portland metro module.** Campaign finance from ORESTAR and Washington's Public Disclosure Commission, bills from Oregon's legislative API, statements of economic interest, and watchers on seven local institutions: OHSU, the Portland Police Bureau, TriMet, PGE, NW Natural, Schnitzer and the Water Bureau. Officials are tracked as seats rather than as named people, and a section cannot be published unless it cites records the system holds.

**Verdicts and calibration.** Anyone reviewing a record can mark it correct, incorrect, partial or unclear. The calibration report shows where the system's confidence and the verdicts disagree. It proposes threshold changes and applies none of them.

---

## Rules the code keeps

**The machine sorts; a person decides.** SPEC-1 filters, scores and drafts. What runs, what is cut and how it is framed are left to the person reading the draft.

**Records are written once.** Signals, records, verdicts and gate decisions are appended and never overwritten.

**Thresholds change only by hand.** The calibration report can show that a gate is too loose or too tight. Only an operator can change it.

**Only model-checked work is published.** `analysis_tier` travels with every record and every brief, and the publisher enforces it.

**A failure is recorded, not hidden.** A source, model or stage that cannot run logs the error and the cycle continues. A brief written without a model says so.

---

## Running it

```bash
git clone https://github.com/CLS-1000/spec-1.git
cd spec-1
pip install -e ".[dev]"
cp .env.example .env            # ANTHROPIC_API_KEY is optional

ollama pull qwen2.5:3b          # the local model; ollama serve must be running
```

| Command | What it does |
|---|---|
| `make cycle` | One full standard cycle: analysis, brief, handoff, PDF |
| `make triage` | Harvest + gates + rules only, no model (what Actions runs) |
| `python -m spec1_core.app.cycle --desk legislative` | The Legislative & Judicial Desk |
| `make run` | The HTTP API |
| `make mcp` | The MCP server (17 tools) |
| `make brief` · `make leads` · `make psyop` · `make research` | Operator tools for one run |
| `make calibration` | Calibration report from filed verdicts |
| `make test` | The test suite |

**HTTP API.** Records, leads, briefs, psyop scores, FARA, verdicts, calibration, publications, workspace cases, the legislative desk and run history are served under `/api/v1/`; `/health` and `/metrics` (Prometheus) sit at the root. Browser views: the Triage Desk (a run index and record inspector) at `/`, the original console at `/console/`, the verdict form at `/verdicts/`, and with `SPEC1_POLITICAL_WEB=true` the Portland political web at `/portland-web`. Authentication is off until `SPEC1_API_KEY` is set. A completed cycle can POST `cycle.completed` to webhooks, HMAC-signed if you set a secret.

**MCP.** `mcp_server.py` exposes 17 tools to Claude: running a cycle, scoring a single signal against the gates, reading signals, intel, leads, briefs, psyop scores, FARA, stats, verdicts and calibration, filing a verdict, and generating briefs, leads, psyop analyses and research dossiers.

[docs/quickstart.md](docs/quickstart.md) walks through a first run. [docs/runbook.md](docs/runbook.md) covers operations; [docs/deployment.md](docs/deployment.md) covers hosting.

### Settings you are most likely to change

| Variable | What it does | Default |
|---|---|---|
| `OLLAMA_MODEL` | Local model for analysis and the brief | `qwen2.5:3b` (analysis uses `llama3` on 8 GB+ machines) |
| `SPEC1_OLLAMA_URL` | Ollama address | `http://localhost:11434` |
| `SPEC1_LOCAL_CHAT_TIMEOUT` | Seconds the local model gets to write a brief | `600` |
| `SPEC1_LLM_ROUTE_<TASK>` | Route for one task, such as `ANALYZE` | `claude,local,mock` |
| `ANTHROPIC_API_KEY` | Enables the `claude` backend | unset |
| `SPEC1_LOCAL_BACKEND` | `ollama`, or `openai` for other local servers | `ollama` |
| `SPEC1_LOCAL_URL`, `SPEC1_LOCAL_MODEL` | Address and model for the `openai` backend | `http://localhost:5272/v1`; no model |
| `SPEC1_LOCAL_TIMEOUT` | Seconds to wait for a local verification | `120` |
| `SPEC1_TRIAGE_ONLY` | Same as `--triage-only` | unset |
| `OPENSTATES_API_KEY` | Other states' bills on the legislative desk | unset (Oregon only) |
| `SPEC1_STORE_PATH` | The JSONL system of record | `spec1_intelligence.jsonl` |
| `SPEC1_GATE_LOG_PATH` | The gate log | `<store>_gate_decisions.jsonl` |
| `SPEC1_PROC_TRACK_HOME` | Where `cls_civica` finds proc_track | `../proc_track` |
| `SPEC1_API_KEY` | Turns on API authentication | unset |

The full list is in [.env.example](.env.example).

---

## Where it stands

This is a beta, and these are its known limits as of 0.8.0:

- **A 3B model writes a serviceable brief, not a polished one.** In the first legislative run it named the bills in the executive summary but left the state-legislature section empty. A larger local model, or Claude, writes noticeably better briefs.
- **The verifier's prompt is written for news.** It asks whether an item is "a significant intelligence development", so routine appropriations bills mostly come back as Monitor. A desk-specific prompt is planned.
- **The legislative desk is Oregon-only without an OpenStates key.**
- **Desk-specific fields stay in the JSONL.** `domain`, `title` and the bill metadata are not mirrored to SQLite.

---

## Tests

1,718 tests across 80 files. Two suites, `test_olis_live.py` and `test_orestar_resolver.py`, call live government services and are left out of offline runs. No test reaches a real model: the Claude API and Ollama are blocked in `tests/conftest.py`. The Civica tests expect the [proc_track](https://github.com/CLS-1000/proc_track) repository beside this one, or at `SPEC1_PROC_TRACK_HOME`.

```bash
pytest tests/ --ignore=tests/test_olis_live.py --ignore=tests/test_orestar_resolver.py
```

CI runs ruff, a hard-coded-label check, bandit (no HIGH findings allowed) and the suite on Python 3.11 and 3.12, plus CodeQL and a fresh-clone install check.

---

## Corrections and issues

If a published card, record or brief gets something wrong, [open an issue](https://github.com/CLS-1000/spec-1/issues) with the measure or record ID and what the official source says. Bug reports are welcome the same way. Pull requests are not accepted; see [CONTRIBUTING.md](CONTRIBUTING.md).

SPEC-1 is proprietary. All rights reserved; see [LICENSE](LICENSE).
