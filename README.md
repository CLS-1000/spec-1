# SPEC-1

**Status:** Beta · **Version:** 0.6.0 · EVASTARARCANA LLC, Portland, Oregon

SPEC-1 reads public sources on a schedule, decides which items deserve a closer look, and writes up what it found. Every decision it makes along the way is written down, including the decision to throw something out.

That last part is the point. Most monitoring software tells you what it surfaced. SPEC-1 also tells you what it discarded, which test the item failed, the score it received and the score it needed. The record is kept in an append-only file that the system never rewrites.

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

## What happens in a cycle

A cycle runs in seven steps: harvest, parse, score, investigate, verify, analyze, store.

**Harvest.** The default cycle pulls ten RSS feeds: War on the Rocks, The Cipher Brief, Just Security, RAND, the Atlantic Council, Defense One, 38 North, NK News, CSIS's Korea Chair and Yonhap. The feed list is a single dictionary in `src/spec1_core/signal/harvester.py`.

**Score.** Each item is measured against four gates. It must clear all four to go on.

| Gate | What it measures | Must reach |
|---|---|---|
| Credibility | The source's weight in the operator's credibility table. Unlisted sources get 0.60. | 0.65 |
| Volume | Length, in tiers from under 30 words to over 500 | 0.30 (about 30 words) |
| Velocity | Age. The score steps down from 1.0 (under six hours) to 0.75, 0.50, 0.25 and finally 0.10 (over a week). | 0.50 (under 72 hours) |
| Novelty | The number of terms that signal something new: arrests, charges, classified material, corruption and similar | 1 term |

Because the credibility gate sits just above the default weight, a source that is not in the table does not get through. The thresholds live in one file, `src/spec1_core/config/calibration.py`. A person sets them. The system does not adjust them.

**Log.** Every scored item, passed or blocked, gets one line in the gate log: the decision, the gates it failed, and each gate's measured value beside its threshold. The file sits next to the intelligence store as `<store>_gate_decisions.jsonl`, or wherever `SPEC1_GATE_LOG_PATH` points.

**Investigate, verify, analyze.** Items that pass become hypotheses. A language model reads the hypothesis together with the article's own text and classifies it as Corroborated, Escalate, Investigate, Monitor, Conflicted or Archive, with a confidence score. The analyzer blends that result with the source's weight into a final record. Each record keeps an excerpt of the article and the model's stated reasoning, so a classification can be checked against what the model was shown.

**Store.** Records are appended to a JSONL file, which is the system of record, and mirrored into SQLite so they can be queried. Nothing is updated in place. If the SQLite copy is lost, it can be rebuilt from the JSONL.

---

## Which model does what

Every model call goes through one client, and each task follows its own route: an ordered list of backends to try.

| Backend | What it is |
|---|---|
| `claude` | Anthropic's API (`ANTHROPIC_API_KEY`) |
| `local` | A model on your own machine: Ollama, or any server that speaks the OpenAI chat API, such as llama.cpp, vLLM or LM Studio |
| `mock` | Deterministic rules. No model, no network, always available |

With no routing configured, every task tries Claude, then the local model, then the rules. To send the cycle's analysis to a local model:

```bash
SPEC1_LLM_ROUTE_ANALYZE=local,mock
SPEC1_LOCAL_BACKEND=openai           # llama.cpp, vLLM, LM Studio; or "ollama"
SPEC1_LOCAL_URL=http://localhost:8080/v1
SPEC1_LOCAL_MODEL=<model name>
```

Under that route, analysis falls back to rules, never to Claude. Reasoning models that wrap their answers in `<think>` blocks are handled: the blocks are stripped before the answer is read.

Every call is logged to `logs/llm_fallback.jsonl` with its task and the backend that answered, so a weak result can be traced to the model that produced it. When no model is available, the cycle still finishes and the brief says so on its first line: *Rule-based brief generated from cycle data.*

**Writing the brief without an API key.** Each cycle also writes `briefs/spec1_handoff_<date>.md` (and a copy at `briefs/spec1_handoff_latest.md`). It holds the same instructions and run data the API would send, plus the format every story lead must follow. Hand the file to Claude in a chat and ask for the brief. The local model does the analysis at no cost, and a person reviews what Claude writes.

---

## What comes out

**A daily brief.** A structured first draft built from the stored records. Confidence is stated as a tier, such as *confirmed by two independent sources*, *single-source unconfirmed* or *insufficient signal*, rather than left to adjectives. A person edits it before it goes anywhere.

**Leads.** Records worth pursuing, each with the anomaly that flagged it, the records that support it, and a drafted list of documents to request.

**Influence-pattern scoring.** Fourteen named framing patterns, among them fear amplification, manufactured consensus, coordinated amplification and whataboutism, checked across a cycle's harvest.

**Research mode.** A standing dossier on a topic you define by keywords, entities and questions. Each run adds to it. Research mode skips the gates and makes no model calls.

**PDX-1i, the Portland metro module.** Campaign finance from ORESTAR and Washington's Public Disclosure Commission, bills from Oregon's legislative API, statements of economic interest, and watchers on seven local institutions: OHSU, the Portland Police Bureau, TriMet, PGE, NW Natural, Schnitzer and the Water Bureau. Officials are tracked as seats rather than as named people, and a section cannot be published unless it cites records the system holds.

**The legislative and judicial desk.** Federal and state legislative records, FARA filings and court records, with a section that sets each measure's stated purpose beside who benefits from it.

**Verdicts.** Anyone reviewing a record can mark it correct, incorrect, partial or unclear. The calibration report shows where the system's confidence and the verdicts disagree. It proposes threshold changes and applies none of them.

---

## Rules the code keeps

The machine sorts; a person decides. SPEC-1 filters, scores and drafts. What runs, what is cut and how it is framed are left to the person reading the draft.

Records are written once. Signals, records, verdicts and gate decisions are appended and never overwritten.

Thresholds change only by hand. The calibration report can show that a gate is too loose or too tight. Only an operator can change it.

A failure is recorded, not hidden. A stage that cannot run logs the error and the cycle continues. A brief written without a model says so.

---

## Corrections and issues

If a published card, record or brief gets something wrong, [open an issue](https://github.com/CLS-1000/spec-1/issues) with the measure or record ID and what the official source says. Bug reports are welcome the same way. Pull requests are not accepted; see [CONTRIBUTING.md](CONTRIBUTING.md).

SPEC-1 is proprietary. All rights reserved; see [LICENSE](LICENSE).

---

## Running it

SPEC-1 needs Python 3.11 or newer.

```bash
git clone https://github.com/CLS-1000/spec-1.git
cd spec-1
pip install -e ".[dev]"
cp .env.example .env        # add ANTHROPIC_API_KEY, or leave it out and run on rules
```

```bash
make cycle      # one full cycle
make run        # the HTTP API
make mcp        # the MCP server (17 tools)
make test       # the test suite
```

The API serves records, leads, briefs, verdicts and calibration under `/api/v1/`, with a browser form for filing verdicts at `/verdicts/`. Authentication is off until `SPEC1_API_KEY` is set.

[docs/quickstart.md](docs/quickstart.md) walks through a first run. [docs/runbook.md](docs/runbook.md) covers deployment.

### Settings you are most likely to change

| Variable | What it does | Default |
|---|---|---|
| `ANTHROPIC_API_KEY` | Enables the `claude` backend | unset |
| `SPEC1_LLM_ROUTE_<TASK>` | Route for one task, such as `ANALYZE` | `claude,local,mock` |
| `SPEC1_LOCAL_BACKEND` | `ollama`, or `openai` for other local servers | `ollama` |
| `SPEC1_LOCAL_URL`, `SPEC1_LOCAL_MODEL` | Address and model name for the `openai` backend | `http://localhost:5272/v1`; no model |
| `SPEC1_LOCAL_API_KEY` | Bearer token for the `openai` backend, if the server wants one | unset |
| `SPEC1_LOCAL_TIMEOUT` | Seconds to wait for a local reply | `120` |
| `OLLAMA_MODEL`, `SPEC1_OLLAMA_URL` | Model and address for the `ollama` backend | `llama3` with 8 GB of RAM or more, otherwise `mistral`; `localhost:11434` |
| `SPEC1_STORE_PATH` | The JSONL system of record | `spec1_intelligence.jsonl` |
| `SPEC1_GATE_LOG_PATH` | The gate log | `<store>_gate_decisions.jsonl` |
| `SPEC1_PROC_TRACK_HOME` | Where `cls_civica` finds proc_track | `../proc_track` |
| `SPEC1_API_KEY` | Turns on API authentication | unset |

The full list is in [.env.example](.env.example).

---

## Tests

1,716 tests across 78 files. Two suites, `test_olis_live.py` and `test_orestar_resolver.py`, call live government services and are left out of offline runs. The Civica tests expect the [proc_track](https://github.com/CLS-1000/proc_track) repository beside this one, or at `SPEC1_PROC_TRACK_HOME`.

```bash
pytest tests/ --ignore=tests/test_olis_live.py --ignore=tests/test_orestar_resolver.py
```
