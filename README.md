# SPEC-1

**Status:** Beta · **Version:** 0.6.0 · EVASTARARCANA LLC, Portland, Oregon

SPEC-1 reads public sources on a schedule, decides which items deserve a closer look, and writes up what it found. Every decision it makes along the way is written down, including the decision to throw something out.

That last part is the point. Most monitoring software tells you what it surfaced. SPEC-1 also tells you what it discarded, which test the item failed, the score it received and the score it needed. The record is kept in an append-only file that the system never rewrites.

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

**Investigate, verify, analyze.** Items that pass become hypotheses, which a language model checks and classifies as Corroborated, Escalate, Investigate, Monitor, Conflicted or Archive, with a confidence score. The analyzer blends that result with the source's weight into a final record.

**Store.** Records are appended to a JSONL file, which is the system of record, and mirrored into SQLite so they can be queried. Nothing is updated in place. If the SQLite copy is lost, it can be rebuilt from the JSONL.

---

## Which model does what

Every model call goes through one client, and each task follows its own route: an ordered list of backends to try.

| Backend | What it is |
|---|---|
| `claude` | Anthropic's API (`ANTHROPIC_API_KEY`) |
| `local` | A model on your own machine: Ollama, or any server that speaks the OpenAI chat API, such as llama.cpp, vLLM or LM Studio |
| `mock` | Deterministic rules. No model, no network, always available |

With no routing configured, every task tries Claude, then the local model, then the rules. A common arrangement sends the cycle's analysis to the local model and leaves Claude to write the brief:

```bash
SPEC1_LLM_ROUTE_ANALYZE=local,mock
SPEC1_LOCAL_BACKEND=ollama          # or "openai" for llama.cpp, vLLM, LM Studio
OLLAMA_MODEL=qwen2.5:7b
```

Under that route, analysis falls back to rules, never to Claude. Reasoning models that wrap their answers in `<think>` blocks are handled: the blocks are stripped before the answer is read.

Every call is logged to `logs/llm_fallback.jsonl` with its task and the backend that answered, so a weak result can be traced to the model that produced it. When no model is available, the cycle still finishes and the brief says so on its first line: *Rule-based brief generated from cycle data.*

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
| `SPEC1_LOCAL_URL`, `SPEC1_LOCAL_MODEL` | Address and model name for the `openai` backend | none |
| `OLLAMA_MODEL`, `SPEC1_OLLAMA_URL` | Model and address for the `ollama` backend | `llama3` with 8 GB of RAM or more, otherwise `mistral`; `localhost:11434` |
| `SPEC1_STORE_PATH` | The JSONL system of record | `spec1_intelligence.jsonl` |
| `SPEC1_GATE_LOG_PATH` | The gate log | `<store>_gate_decisions.jsonl` |
| `SPEC1_API_KEY` | Turns on API authentication | unset |

The full list is in [.env.example](.env.example).

---

## Rules the code keeps

The machine sorts; a person decides. SPEC-1 filters, scores and drafts. What runs, what is cut and how it is framed are left to the person reading the draft.

Records are written once. Signals, records, verdicts and gate decisions are appended and never overwritten.

Thresholds change only by hand. The calibration report can show that a gate is too loose or too tight. Only an operator can change it.

A failure is recorded, not hidden. A stage that cannot run logs the error and the cycle continues. A brief written without a model says so.

---

## Tests

1,665 tests across 75 files. Two suites, `test_olis_live.py` and `test_orestar_resolver.py`, call live government services and are skipped in offline runs. The Civica tests expect the [proc_track](https://github.com/CLS-1000/proc_track) repository beside this one, or at `SPEC1_PROC_TRACK_HOME`.

```bash
pytest tests/ --ignore=tests/test_olis_live.py --ignore=tests/test_orestar_resolver.py
```
