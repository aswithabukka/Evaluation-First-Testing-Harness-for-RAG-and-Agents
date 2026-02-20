# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

---

## Commands

### Start the full stack
```bash
cp .env.example .env    # add OPENAI_API_KEY
make up                 # starts api, worker, db, redis, frontend
make migrate            # runs Alembic migrations (required on first start)
```

### Backend development
```bash
make test-backend                              # run all tests with coverage
docker compose exec api pytest tests/path/to/test_file.py::test_function -v  # single test
make lint                                      # ruff check
make format                                    # ruff format + autofix
make shell-api                                 # open bash in api container
make seed                                      # seed the database with demo data
make eval-local                                # run an evaluation locally (no Docker)
```

### Frontend development
```bash
make type-check-frontend                       # tsc --noEmit
cd frontend && npm run dev                     # run Next.js dev server locally
cd frontend && npm run lint
```

### CLI (evaluation runner)
```bash
# Trigger a run and wait for completion
# Writes the resulting run ID to .rageval_run_id for use by subsequent commands
python -m runner.cli run \
  --config rageval.yaml \
  --test-set <UUID> \
  --timeout 300 \
  --pipeline-version "v1.2.3" \
  --commit-sha <sha> \
  --branch main \
  --pr-number 42

# Check gate (exits non-zero if blocked or regression detected)
python -m runner.cli gate --config rageval.yaml --fail-on-regression
# --run-id <id>  (optional; defaults to reading .rageval_run_id)

# Print report
python -m runner.cli report --format console
python -m runner.cli report --format json --output eval-report.json --diff
```

---

## Architecture

Five layers communicate in sequence:

```
rageval CLI (runner/cli.py)
    ↓  POST /api/v1/runs (httpx)
FastAPI Backend (backend/app/main.py, port 8000)
    ↓  apply_async() to "evaluations" queue
Celery Worker (backend/app/workers/tasks/evaluation_tasks.py)
    ↓  reads/writes
PostgreSQL  ←→  Redis (broker: db1, results: db2)
    ↑
Next.js Dashboard (frontend/, port 3000)  ← polls API via SWR
```

**Run lifecycle:** `PENDING → RUNNING → COMPLETED | GATE_BLOCKED | FAILED`

When `create_run()` is called, a threshold snapshot is stored immutably on the run row — the gate is always evaluated against thresholds at run creation time, not current config.

### Key services

| Service | Code | Description |
|---------|------|-------------|
| Test Set Manager | `backend/app/services/test_set_service.py`, `test_case_service.py` | CRUD for test sets and cases; bumps test set version on every case mutation |
| Evaluation Service | `backend/app/services/evaluation_service.py` | Creates run records, dispatches Celery task |
| Release Gate | `backend/app/services/release_gate_service.py` | Compares `summary_metrics` against `gate_threshold_snapshot`; computes regression diff vs last passing run |
| Metrics Service | `backend/app/services/metrics_service.py` | Reads from `metrics_history` for trend charts |
| Celery Task | `backend/app/workers/tasks/evaluation_tasks.py` | Runs Ragas + rule evaluator per case; writes `EvaluationResult` and `MetricsHistory` rows; updates run status |

### Adapter pattern

Any RAG pipeline plugs in by subclassing `runner/adapters/base.py:RAGAdapter`:

```python
class MyPipeline(RAGAdapter):
    def setup(self): ...         # called once before the run
    def run(self, query, context) -> PipelineOutput: ...  # called per test case
    def teardown(self): ...      # called once after the run
```

`PipelineOutput` carries `answer`, `retrieved_contexts`, `tool_calls`, and `turn_history` (for multi-turn). The adapter class and config kwargs are loaded dynamically from `rageval.yaml` by `runner/config_loader.py` using `importlib`.

Pre-built adapters: `runner/adapters/langchain_adapter.py`, `runner/adapters/llamaindex_adapter.py`.

### Evaluators

| Evaluator | File | Description |
|-----------|------|-------------|
| `RagasEvaluator` | `runner/evaluators/ragas_evaluator.py` | Runs Ragas metrics (faithfulness, answer_relevancy, context_precision, context_recall) using an LLM judge (OpenAI). Batches test cases. |
| `RuleEvaluator` | `runner/evaluators/rule_evaluator.py` | Interprets `failure_rules` JSONB per test case (see table below). Returns `{passed, details}` per rule. |
| `LLMJudgeEvaluator` | `runner/evaluators/llm_judge_evaluator.py` | Uses GPT-4o to score free-form responses against configurable criteria. Returns score (0–1) and reasoning string. |
| `MultiTurnAgentEvaluator` | `runner/multi_turn/agent_evaluator.py` | Evaluates multi-turn conversations. Returns `AgentEvalResult` with `passed`, `turn_results` (list of `TurnResult`), `goal_completed`, and `failure_reason`. |

`MetricScores` (returned by evaluators): `faithfulness`, `answer_relevancy`, `context_precision`, `context_recall`, `custom` (dict for plugin scores).

### Failure rule engine

`runner/evaluators/rule_evaluator.py` interprets the `failure_rules` JSONB field on each test case. Supported rule types:

| Type | Checks |
|------|--------|
| `must_not_contain` / `must_contain` | Substring presence in output |
| `must_call_tool` / `must_not_call_tool` | Named tool in `tool_calls` list |
| `regex_must_match` / `regex_must_not_match` | Regex on output |
| `max_hallucination_risk` | Faithfulness score >= `threshold` |
| `must_refuse` | Output contains any phrase in `REFUSAL_PHRASES` list (~13 standard phrases) |
| `custom` | Delegates to `plugin_class` via `runner/plugins/plugin_loader.py` |

Each rule returns `(passed: bool, reason: str)`. The run-level `rules_passed` is `False` if any rule fails and blocks the gate regardless of metric scores.

### Reporters

| Reporter | File | CLI flag |
|----------|------|----------|
| `ConsoleReporter` | `runner/reporters/console_reporter.py` | `--format console` |
| `JsonReporter` | `runner/reporters/json_reporter.py` | `--format json --output <file>` |
| `DiffReporter` | `runner/reporters/diff_reporter.py` | `--diff` flag; shows regressions vs last baseline |

### Database schema

Five tables (migration in `backend/alembic/versions/001_initial_schema.py`):

- **test_sets** — name, description, version (bumped on every case change)
- **test_cases** — query, expected_output, ground_truth, `context JSONB`, `failure_rules JSONB`, `tags JSONB`
- **evaluation_runs** — status enum, git metadata, `gate_threshold_snapshot JSONB` (immutable), `summary_metrics JSONB` (cached aggregates)
- **evaluation_results** — per-case float scores, `rules_detail JSONB`, raw_output, raw_contexts
- **metrics_history** — append-only; indexed on `(test_set_id, metric_name, recorded_at)` for trend queries

`metrics_history` is intentionally separate from `evaluation_results` so trend chart queries don't have to aggregate across result rows.

### Async vs sync

- FastAPI uses `asyncpg` (async SQLAlchemy sessions via `AsyncSessionLocal`)
- Celery workers use sync `psycopg2` (`SYNC_DATABASE_URL`); the URL replacement of `+asyncpg` → `` is done in `alembic/env.py` and the task file

### API routes (prefix `/api/v1`)

```
GET  /health

# Test sets
POST /test-sets                                      ← 201
GET  /test-sets                                      ← paginated list
GET/PUT/DELETE /test-sets/{id}
GET  /test-sets/{id}/export                          ← download JSON

# Test cases
POST /test-sets/{id}/cases                           ← create single
POST /test-sets/{id}/cases/bulk                      ← bulk import
GET/PUT/DELETE /test-sets/{id}/cases/{cid}

# Evaluation runs
POST /runs                                           ← 202; accepts pipeline_version, notes, triggered_by, git metadata
GET  /runs?test_set_id=&status=&git_branch=&git_commit_sha=
GET  /runs/{id}
GET  /runs/{id}/status                               ← lightweight CI poller (overall_passed, status only)
GET  /runs/{id}/diff                                 ← regression diff vs last passing baseline (metric_deltas, regressions, improvements)
POST /runs/{id}/cancel                               ← 202

# Results
GET  /results?run_id=&passed=                        ← filterable by run and pass/fail
GET  /results/summary?run_id=                        ← aggregated metrics for a run
GET  /results/{id}

# Metrics & gate
GET  /metrics/trends?test_set_id=&metric=&days=
GET  /metrics/thresholds/{test_set_id}
PUT  /metrics/thresholds/{test_set_id}
GET  /metrics/gate/{run_id}                          ← evaluates gate; returns overall_passed, per-metric results, block reason
```

### Dashboard pages

| Route | Content |
|-------|---------|
| `/dashboard` | 4 stat cards (Total Runs 24h, Gate Pass Rate, Active Blocks, Test Sets) via `SummaryCards`; `RecentRunsTable` showing last 10 runs (SWR polling every 10s) |
| `/test-sets` | 3-column grid of test set cards, each showing name, version, description, case count, last run status, and a hover-reveal "Quick Run" button |
| `/test-sets/[id]` | Cases table with columns: Query, Ground Truth, Tags (blue badges), Rules (count badge), Created, Actions; inline add-case form (green-tinted row); edit/delete per row; `TriggerRunModal` for launching a run with pipeline version, "what changed" notes, and triggered-by fields |
| `/test-sets/new` | Create form with Name (required) and Description fields |
| `/runs` | All evaluation runs table: Status badge, Pass Rate, Cases (passed/total), Branch, Commit (7-char SHA), Version, Triggered by, Started; refreshes every 8s |
| `/runs/[id]` | `MetricGauge` cards per metric (label, %, progress bar); regression diff table with `ScoreRow` (current vs baseline side-by-side); `ResponseDiffPanel` (raw output with coloured diff sections vs baseline); per-case results; auto-refreshes while run is pending/running |
| `/metrics` | Recharts `LineChart` per metric with threshold `ReferenceLine`; 7/30/90d selector; test-set dropdown when multiple exist; each card shows a colored dot, `▲ Passing` / `▼ Failing` pill badge, bold percentage, and a description callout (light gray bg + ⓘ icon) explaining what the metric measures |

### GitHub Actions

`.github/workflows/evaluate.yml` — triggers on push/PR to `main`/`develop` and `workflow_dispatch`. Steps:
1. Start Postgres 15 + Redis 7 services
2. Install Python 3.11 deps, run `alembic upgrade head`
3. Start FastAPI on port 8000 (health-checked) and Celery worker (2 concurrency, `evaluations` queue) in background
4. `python -m runner.cli run` — passes `--commit-sha`, `--branch`, `--pr-number`, `--pipeline-version`; writes run ID to `.rageval_run_id`
5. `python -m runner.cli gate --fail-on-regression` — exits non-zero if gate blocked
6. `python -m runner.cli report --format json --output eval-report.json --diff`
7. Upload report as artifact (90-day retention)
8. Post (or update) a PR comment with a formatted Markdown table showing: run ID, commit, branch, metrics table, gate status, and up to 10 regressions. Uses `GITHUB_TOKEN` to find and update existing comment on re-run.

`.github/workflows/release-gate.yml` — queries `GET /runs?git_commit_sha=<sha>` for `overall_passed`; sets a GitHub commit status (`success` / `failure`) using the GitHub Statuses API.

---

## Environment variables

| Variable | Required | Default |
|----------|----------|---------|
| `OPENAI_API_KEY` | Yes (for Ragas/DeepEval scoring) | — |
| `DATABASE_URL` | Yes | `postgresql+asyncpg://postgres:postgres@db:5432/rageval` |
| `SYNC_DATABASE_URL` | Yes | `postgresql://postgres:postgres@db:5432/rageval` |
| `CELERY_BROKER_URL` | Yes | `redis://redis:6379/1` |
| `CELERY_RESULT_BACKEND` | Yes | `redis://redis:6379/2` |
| `OPENAI_MODEL` | No | `gpt-4o` |
| `EVAL_LLM_PROVIDER` | No | `openai` |
| `DEFAULT_FAITHFULNESS_THRESHOLD` | No | `0.7` |
| `DEFAULT_ANSWER_RELEVANCY_THRESHOLD` | No | `0.7` |
| `DEFAULT_CONTEXT_PRECISION_THRESHOLD` | No | `0.6` |
| `DEFAULT_CONTEXT_RECALL_THRESHOLD` | No | `0.6` |
| `DEFAULT_PASS_RATE_THRESHOLD` | No | `0.8` |
| `GITHUB_TOKEN` | No | — (required only for PR comment posting in CI) |

---

## Extending the system

**New rule type:** Add to `RuleType` enum and a branch in `RuleEvaluator._evaluate_rule()` in `runner/evaluators/rule_evaluator.py`.

**New metric:** Add to `RagasEvaluator.SUPPORTED_METRICS` and the `metric_obj_map` in `runner/evaluators/ragas_evaluator.py`. Add a corresponding column to the `evaluation_results` table via a new Alembic migration.

**Custom plugin:** Implement `evaluate(self, output, tool_calls, rule) -> tuple[bool, str]` and reference via `{"type": "custom", "plugin_class": "my_module.MyClass"}` in failure rules.

**New adapter:** Subclass `runner/adapters/base.py:RAGAdapter`, implement `run()`, place in `runner/adapters/`, reference from `rageval.yaml`.

---

## Frontend UI conventions

### Metric cards (`frontend/src/app/metrics/page.tsx`)

Each metric is defined in the `METRICS` array with `key`, `label`, `color`, `threshold`, and `description`. The `MetricChart` component renders:

- **Header:** colored dot (matching chart line) + metric name on the left; `▲ Passing` / `▼ Failing` pill badge + bold percentage on the right
- **Description callout:** light gray `bg-gray-50` box with an `ⓘ` SVG icon and human-readable explanation of what the metric means and what high/low scores imply — always shown above the chart
- **Chart:** Recharts `LineChart` with a dashed red `ReferenceLine` for the threshold

Metric descriptions:

| Metric | What it measures |
|--------|-----------------|
| Faithfulness | Whether the answer uses only facts from retrieved context (no hallucination) |
| Answer Relevancy | Whether the answer directly addresses the question asked |
| Context Precision | Whether retrieved chunks are actually useful (targeted retrieval) |
| Context Recall | Whether retrieval surfaced all chunks needed to answer fully |
| Pass Rate | % of test cases where all metric thresholds and failure rules passed |

To add a new metric, append an entry to the `METRICS` array in `metrics/page.tsx` and ensure the backend exposes it via `GET /metrics/trends`.

### Shared UI components (`frontend/src/components/`)

| Component | Location | Purpose |
|-----------|----------|---------|
| `Sidebar` | `layout/Sidebar.tsx` | Fixed left nav with logo, links (Dashboard / Test Sets / Eval Runs / Metrics), and `v1.0.0` footer |
| `Badge` | `ui/Badge.tsx` | Color variants: `green`, `red`, `yellow`, `blue`, `orange`, `gray` |
| `Card`, `CardHeader`, `CardBody` | `ui/Card.tsx` | White rounded card with shadow; header has bottom border |
| `LoadingSpinner`, `PageLoader` | `ui/LoadingSpinner.tsx` | Inline spinner and full-page centered loader |
| `SummaryCards` | `dashboard/SummaryCards.tsx` | 4 `StatCard` tiles: Total Runs (24h), Gate Pass Rate, Active Blocks, Test Sets |
| `RecentRunsTable` | `dashboard/RecentRunsTable.tsx` | Last 10 runs, SWR 10s refresh |
