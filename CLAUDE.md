# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

---

## Commands

### Start the full stack
```bash
cp .env.example .env    # add OPENAI_API_KEY
make up                 # starts api, worker, db, redis, frontend
make migrate            # runs Alembic migrations (required on first start)
make seed               # seeds demo data for all 4 AI systems
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
cd frontend && npm run dev                     # run Next.js dev server locally (port 3001)
cd frontend && npm run lint
```

### CLI (evaluation runner)
```bash
# Trigger a run and wait for completion
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
Next.js Dashboard (frontend/, port 3000 Docker / 3001 dev)  ← polls API via SWR
```

**Run lifecycle:** `PENDING → RUNNING → COMPLETED | GATE_BLOCKED | FAILED`

When `create_run()` is called, a threshold snapshot is stored immutably on the run row — the gate is always evaluated against thresholds at run creation time, not current config.

### System types

The harness supports 9 AI system types via the `SystemType` enum:

| Type | Description | Key Metrics |
|------|-------------|-------------|
| `rag` | Retrieval-Augmented Generation | faithfulness, answer_relevancy, context_precision, context_recall |
| `agent` | Tool-using AI agents | tool_accuracy, goal_completion, faithfulness |
| `chatbot` | Multi-turn conversational AI | coherence, helpfulness, safety |
| `search` | Search/information retrieval | ndcg, mrr, map, precision_at_k |
| `code_gen` | Code generation systems | code_correctness, test_pass_rate |
| `classification` | Text classification | accuracy, f1_score, precision, recall |
| `summarization` | Text summarization | rouge_l, bleu, compression_ratio |
| `translation` | Language translation | bleu, translation_accuracy |
| `custom` | User-defined systems | configurable |

System type is stored on `test_sets.system_type` and drives metric selection, UI display, and evaluator behavior.

### Key services

| Service | Code | Description |
|---------|------|-------------|
| Test Set Manager | `backend/app/services/test_set_service.py`, `test_case_service.py` | CRUD for test sets and cases; bumps test set version on every case mutation |
| Evaluation Service | `backend/app/services/evaluation_service.py` | Creates run records, dispatches Celery task |
| Release Gate | `backend/app/services/release_gate_service.py` | Compares `summary_metrics` against `gate_threshold_snapshot`; computes regression diff vs last passing run |
| Metrics Service | `backend/app/services/metrics_service.py` | Reads from `metrics_history` for trend charts |
| Ingestion Service | `backend/app/services/ingestion_service.py` | Production traffic ingestion with configurable sampling; user feedback (thumbs up/down) with aggregated stats |
| Sampling Service | `backend/app/services/sampling_service.py` | Decides which production queries get sampled for evaluation |
| Alert Service | `backend/app/services/alert_service.py` | Slack/webhook alerts with Block Kit formatting for gate failures and run completions |
| Generation Service | `backend/app/services/generation_service.py` | LLM-powered test case generation via OpenAI with system-type-specific prompt templates |
| Celery Task (Eval) | `backend/app/workers/tasks/evaluation_tasks.py` | Runs evaluators per case; writes `EvaluationResult` and `MetricsHistory` rows; updates run status; dispatches alerts |
| Celery Task (Gen) | `backend/app/workers/tasks/generation_tasks.py` | Async test case generation; calls GenerationService, inserts TestCase rows, bumps test set version |

### Adapter pattern

Any AI pipeline plugs in by subclassing `runner/adapters/base.py:RAGAdapter`:

```python
class MyPipeline(RAGAdapter):
    def setup(self): ...         # called once before the run
    def run(self, query, context) -> PipelineOutput: ...  # called per test case
    def teardown(self): ...      # called once after the run
```

`PipelineOutput` carries `answer`, `retrieved_contexts`, `tool_calls`, `turn_history`, and `metadata`. The adapter class and config kwargs are loaded dynamically via `importlib` from `pipeline_config` on the evaluation run.

### Demo adapters (4 built-in AI systems)

| Adapter | File | System Type | Description |
|---------|------|-------------|-------------|
| `DemoRAGAdapter` | `runner/adapters/demo_rag.py` | `rag` | Embedding-based retrieval over ~30 knowledge chunks + GPT-4o-mini generation. Returns `answer` + `retrieved_contexts` with similarity scores. |
| `DemoToolAgentAdapter` | `runner/adapters/demo_tool_agent.py` | `agent` | OpenAI function-calling agent with 3 tools: `calculator`, `get_weather`, `unit_converter`. Returns `answer` + `tool_calls` (ToolCall objects) + tool result contexts. |
| `DemoChatbotAdapter` | `runner/adapters/demo_chatbot.py` | `chatbot` | TechStore customer support chatbot with system prompt, 10-item knowledge base, keyword-based retrieval. Maintains conversation history. Returns `answer` + `turn_history` + `retrieved_contexts`. |
| `DemoSearchAdapter` | `runner/adapters/demo_search.py` | `search` | Semantic search over 15-document developer knowledge base using OpenAI embeddings + cosine similarity. Returns ranked results with `metadata.scores` and `metadata.ranked_ids`. |

Pre-built framework adapters: `runner/adapters/langchain_adapter.py`, `runner/adapters/llamaindex_adapter.py`.

### Dynamic adapter loading

The Celery worker loads adapters dynamically from `pipeline_config` on the evaluation run:

```python
# In evaluation_tasks.py _load_adapter():
config = pipeline_config or {}
module_path = config.get("adapter_module", "runner.adapters.demo_rag")
class_name = config.get("adapter_class", "DemoRAGAdapter")
mod = importlib.import_module(module_path)
adapter_cls = getattr(mod, class_name)
# Extra config keys (excluding adapter_module/adapter_class) are passed as kwargs
return adapter_cls(**init_kwargs)
```

### Evaluators

| Evaluator | File | Description |
|-----------|------|-------------|
| `RagasEvaluator` | `runner/evaluators/ragas_evaluator.py` | Runs Ragas metrics (faithfulness, answer_relevancy, context_precision, context_recall) using an LLM judge (OpenAI). Batches test cases. |
| `RuleEvaluator` | `runner/evaluators/rule_evaluator.py` | Interprets `failure_rules` JSONB per test case (see table below). Returns `{passed, details}` per rule. |
| `LLMJudgeEvaluator` | `runner/evaluators/llm_judge_evaluator.py` | Uses GPT-4o to score free-form responses against configurable criteria. Returns score (0–1) and reasoning string. |
| `MultiTurnAgentEvaluator` | `runner/multi_turn/agent_evaluator.py` | Evaluates multi-turn conversations. Returns `AgentEvalResult` with `passed`, `turn_results`, `goal_completed`, and `failure_reason`. |
| `CodeEvaluator` | `runner/evaluators/code_evaluator.py` | Evaluates generated code: syntax check, test execution, linting. |
| `RankingEvaluator` | `runner/evaluators/ranking_evaluator.py` | Computes NDCG, MRR, MAP, precision@k for search/retrieval systems. |
| `SimilarityEvaluator` | `runner/evaluators/similarity_evaluator.py` | ROUGE-L, BLEU, cosine similarity for summarization/translation. |
| `ClassificationEvaluator` | `runner/evaluators/classification_evaluator.py` | Accuracy, F1, precision, recall for classification systems. |
| `ConversationEvaluator` | `runner/evaluators/conversation_evaluator.py` | Coherence, helpfulness, safety scoring for chatbots. |
| `AgentEvaluator` | `runner/evaluators/agent_evaluator.py` | Tool accuracy, goal completion, efficiency for agent systems. |
| `TranslationEvaluator` | `runner/evaluators/translation_evaluator.py` | BLEU, translation accuracy metrics. |

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

Tables (migrations in `backend/alembic/versions/`):

- **test_sets** — name, description, `system_type`, version (bumped on every case change)
- **test_cases** — query, expected_output, ground_truth, `context JSONB`, `failure_rules JSONB`, `tags JSONB`, `expected_labels JSONB`, `expected_ranking JSONB`, `conversation_turns JSONB`
- **evaluation_runs** — status enum, git metadata, `gate_threshold_snapshot JSONB` (immutable), `summary_metrics JSONB`, `pipeline_config JSONB`, notes
- **evaluation_results** — per-case float scores, `rules_detail JSONB`, raw_output, raw_contexts, `tool_calls JSONB`, duration_ms, `eval_cost_usd`, `tokens_used`, `extended_metrics JSONB`
- **metrics_history** — append-only; indexed on `(test_set_id, metric_name, recorded_at)` for trend queries
- **production_logs** — source, query, answer, status (received/sampled/skipped/evaluated), confidence_score, user_feedback

Migrations: 001 (initial) → 002 (notes, pipeline_config) → 003 (production_logs) → 004 (system_type, cost tracking, extended test_case fields)

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
POST /test-sets/{id}/generate                        ← 202; LLM test case generation (topic, count)

# Test cases
POST /test-sets/{id}/cases                           ← create single
POST /test-sets/{id}/cases/bulk                      ← bulk import
GET/PUT/DELETE /test-sets/{id}/cases/{cid}

# Evaluation runs
POST /runs                                           ← 202; accepts pipeline_config, pipeline_version, notes, triggered_by, git metadata
POST /runs/multi                                     ← 202; batch-trigger N runs with different configs; returns run_ids + compare_url
GET  /runs?test_set_id=&status=&git_branch=&git_commit_sha=
GET  /runs/{id}
GET  /runs/{id}/status                               ← lightweight CI poller (overall_passed, status only)
GET  /runs/{id}/diff                                 ← regression diff vs last passing baseline
POST /runs/{id}/cancel                               ← 202

# Results
GET  /results?run_id=&passed=                        ← filterable by run and pass/fail
GET  /results/summary?run_id=                        ← aggregated metrics for a run
GET  /results/export?run_id=&format=csv|json         ← download results as CSV or JSON
GET  /results/{id}

# Metrics & gate
GET  /metrics/trends?test_set_id=&metric=&days=
GET  /metrics/thresholds/{test_set_id}
PUT  /metrics/thresholds/{test_set_id}
GET  /metrics/gate/{run_id}                          ← evaluates gate; returns overall_passed, per-metric results

# Production ingestion
POST /ingest                                         ← 202; ingest single Q&A pair (API key protected)
POST /ingest/bulk                                    ← 202; bulk ingest
GET  /ingest/logs?source=&status=                    ← production log entries
GET  /ingest/logs/{id}
PATCH /ingest/logs/{id}/feedback                     ← update user feedback (thumbs_up/thumbs_down)
GET  /ingest/stats?source=                           ← sampling statistics per source
GET  /ingest/feedback-stats?source=                  ← aggregated feedback counts and positive rate

# Playground (interactive demo)
GET  /playground/systems                             ← metadata for all 4 demo AI systems
POST /playground/interact                            ← send query to a demo system, get response
POST /playground/reset-session?session_id=           ← reset chatbot conversation
```

### Dashboard pages

| Route | Content |
|-------|---------|
| `/dashboard` | 4 stat cards (Total Runs 24h, Gate Pass Rate, Active Blocks, Test Sets) via `SummaryCards`; `RecentRunsTable` showing last 10 runs (SWR polling every 10s) |
| `/systems` | AI Systems health dashboard — groups test sets by system_type, shows health badges (Healthy/Degraded/Failing), key metric bars, latest run info, and per-system test set links |
| `/playground` | **Interactive AI Playground** — tabbed interface to chat with all 4 demo systems. Two-column layout: chat + detail panel. Thumbs up/down feedback buttons on assistant messages. Per-system message persistence across tab switches. |
| `/test-sets` | 3-column grid of test set cards with system type badges, case count, last run status, and hover-reveal "Quick Run" button |
| `/test-sets/[id]` | Cases table with inline add/edit/delete; **3 action buttons**: "Generate Cases" (LLM-powered via GPT-4o), "Compare Models" (multi-run with different configs), "Run Evaluation" (trigger single run) |
| `/test-sets/new` | Create form with Name, Description, and System Type fields |
| `/runs` | All evaluation runs table with checkbox selection (max 4); floating "Compare N Runs" bar; refreshes every 8s |
| `/runs/[id]` | `MetricGauge` cards per metric; regression diff table; per-case results; **Export CSV/JSON** buttons; auto-refreshes while running |
| `/runs/compare` | **Side-by-side comparison** of 2–4 runs: summary cards with colored headers, metric comparison table (best values highlighted in green), per-case results grid |
| `/metrics` | Recharts `LineChart` per metric with threshold `ReferenceLine`; 7/30/90d selector; test-set dropdown |
| `/production` | Production Q&A logs, sampling statistics, **feedback stats card** (thumbs up/down counts, positive rate percentage) |

### Playground backend architecture

The playground endpoint (`backend/app/api/v1/endpoints/playground.py`) manages adapter lifecycle:

- **Stateless adapters** (RAG, Agent, Search): Cached as singletons in a module-level dict. `setup()` called once on first request. Thread-safe via `threading.Lock`.
- **Chatbot adapters**: One instance per `session_id` to maintain conversation history. 30-minute TTL with automatic eviction. Session ID returned in response for subsequent requests.
- **Execution**: Adapters run synchronously; `run_in_executor` prevents blocking the async event loop.
- **First request latency**: 2-5s for RAG/Search (embedding corpus). Subsequent requests are fast.

### Seed data

`backend/app/scripts/seed_demo_data.py` creates 4 test sets with 8 test cases each:

| Test Set | System Type | Adapter | Test Cases |
|----------|-------------|---------|------------|
| Demo RAG Pipeline | `rag` | `DemoRAGAdapter` | Geography, science, medical, tech, literature, physics, AI, safety/refusal questions |
| Demo Tool Agent | `agent` | `DemoToolAgentAdapter` | Calculator, weather, unit conversion, no-tool questions with `must_call_tool`/`must_not_call_tool` rules |
| Demo Chatbot | `chatbot` | `DemoChatbotAdapter` | Product inquiry, returns, order tracking, payment, warranty, shipping, safety guardrail questions |
| Demo Search Engine | `search` | `DemoSearchAdapter` | Python, JS, Docker, SQL, Git, REST, React, Redis queries with `expected_ranking` doc IDs |

Run with: `docker compose exec api python -m app.scripts.seed_demo_data` or `make seed`

### GitHub Actions

`.github/workflows/evaluate.yml` — triggers on push/PR to `main`/`develop` and `workflow_dispatch`. Steps:
1. Start Postgres 15 + Redis 7 services
2. Install Python 3.11 deps, run `alembic upgrade head`
3. Start FastAPI on port 8000 (health-checked) and Celery worker (2 concurrency, `evaluations` queue) in background
4. `python -m runner.cli run` — passes `--commit-sha`, `--branch`, `--pr-number`, `--pipeline-version`; writes run ID to `.rageval_run_id`
5. `python -m runner.cli gate --fail-on-regression` — exits non-zero if gate blocked
6. `python -m runner.cli report --format json --output eval-report.json --diff`
7. Upload report as artifact (90-day retention)
8. Post (or update) a PR comment with a formatted Markdown table showing: run ID, commit, branch, metrics table, gate status, and up to 10 regressions.

`.github/workflows/release-gate.yml` — queries `GET /runs?git_commit_sha=<sha>` for `overall_passed`; sets a GitHub commit status.

---

## Environment variables

| Variable | Required | Default |
|----------|----------|---------|
| `OPENAI_API_KEY` | Yes (for Ragas scoring + demo adapters) | — |
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
| `API_KEYS` | No | — (comma-separated keys for production ingestion endpoint) |
| `SAMPLING_RATE` | No | `0.2` (20% of production traffic sampled) |
| `SAMPLING_ERROR_RATE` | No | `1.0` (100% of error traffic sampled) |
| `ALERT_WEBHOOK_URL` | No | — (Slack/webhook URL for quality alerts) |
| `ALERT_ON_SUCCESS` | No | `False` (set `True` to alert on all completed runs, not just failures) |
| `CORS_ORIGINS` | No | `*` |
| `GITHUB_TOKEN` | No | — (required only for PR comment posting in CI) |

---

## Extending the system

**New rule type:** Add to `RuleType` enum and a branch in `RuleEvaluator._evaluate_rule()` in `runner/evaluators/rule_evaluator.py`.

**New metric:** Add to `RagasEvaluator.SUPPORTED_METRICS` and the `metric_obj_map` in `runner/evaluators/ragas_evaluator.py`. Add a corresponding column to the `evaluation_results` table via a new Alembic migration.

**Custom plugin:** Implement `evaluate(self, output, tool_calls, rule) -> tuple[bool, str]` and reference via `{"type": "custom", "plugin_class": "my_module.MyClass"}` in failure rules.

**New adapter:** Subclass `runner/adapters/base.py:RAGAdapter`, implement `run()`, place in `runner/adapters/`, and specify in `pipeline_config` when triggering a run:
```json
{
  "adapter_module": "runner.adapters.my_adapter",
  "adapter_class": "MyAdapter",
  "model": "gpt-4o",
  "top_k": 5
}
```

**New system type:** Add to `SystemType` in `frontend/src/types/index.ts`, add metric/color/icon config to `frontend/src/lib/system-metrics.ts`, add evaluator mapping.

**New dashboard page:** Create `frontend/src/app/<route>/page.tsx` as a `"use client"` component, add nav entry in `frontend/src/components/layout/Sidebar.tsx`. If the page uses `useSearchParams()`, wrap the component in `<Suspense>` to avoid Next.js prerender errors.

**New alert destination:** Extend `alert_service.py` — the `_post_webhook()` helper sends JSON POST to any URL. Add new methods following the `_send_breach_alert()` / `send_completion_alert()` pattern.

**New generation prompt:** Add system-type-specific prompt templates to `SYSTEM_TYPE_PROMPTS` dict in `generation_service.py`. Each prompt instructs GPT-4o to return a JSON array of test case objects.

---

## Frontend UI conventions

### System type configuration (`frontend/src/lib/system-metrics.ts`)

Central config mapping 9 system types to their metrics, colors, icons, and labels. Key exports:
- `SYSTEM_TYPE_LABELS`, `SYSTEM_TYPE_COLORS`, `SYSTEM_TYPE_ICONS` — display mappings
- `getMetricsForSystemType(type)` — returns `MetricConfig[]` with key, label, color, threshold
- `getResultColumns(type)` — column definitions for results table
- `getMetricValue(metrics, key)` — extracts metric value from summary

### Shared UI components (`frontend/src/components/`)

| Component | Location | Purpose |
|-----------|----------|---------|
| `Sidebar` | `layout/Sidebar.tsx` | Fixed left nav: Dashboard, AI Systems, Playground, Test Sets, Eval Runs, Metrics, Production. Dark mode toggle (moon/sun icon) in footer. All items have `dark:` variants. |
| `Badge` | `ui/Badge.tsx` | Color variants: `green`, `red`, `yellow`, `blue`, `orange`, `gray`. Each has dark mode variants (e.g., `dark:bg-green-900/30 dark:text-green-400`). |
| `Card`, `CardHeader`, `CardBody` | `ui/Card.tsx` | White rounded card with shadow (`dark:bg-slate-800 dark:border-slate-700`); header has bottom border |
| `LoadingSpinner`, `PageLoader` | `ui/LoadingSpinner.tsx` | Inline spinner and full-page centered loader |
| `SummaryCards` | `dashboard/SummaryCards.tsx` | 4 `StatCard` tiles: Total Runs (24h), Gate Pass Rate, Active Blocks, Test Sets |
| `RecentRunsTable` | `dashboard/RecentRunsTable.tsx` | Last 10 runs, SWR 10s refresh |

### Dark mode (`frontend/src/lib/theme.tsx`)

- **Strategy**: Tailwind `darkMode: "class"` — toggles `dark` class on `<html>` element
- **ThemeProvider**: React context wrapping `layout.tsx` children; provides `useTheme()` hook with `{ theme, toggleTheme }`
- **Persistence**: Reads/writes `localStorage("theme")`; falls back to system preference via `prefers-color-scheme: dark`
- **SSR safety**: `<html suppressHydrationWarning>` prevents hydration mismatch
- **Toggle**: Moon/sun icon button in Sidebar footer

### Design tokens (Tailwind)

- **Brand colors:** `brand-50` (#f0f9ff), `brand-500` (#0ea5e9), `brand-600` (#0284c7), `brand-700` (#0369a1)
- **System colors:** RAG=blue, Agent=purple, Chatbot=pink, Search=teal, CodeGen=amber, Classification=orange, Summarization=indigo, Translation=emerald
- **Dark mode base:** `html.dark body { @apply bg-slate-900 text-gray-100; }`
- **Input styling:** `border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-500`
- **Primary button:** `px-4 py-2 bg-brand-600 text-white text-sm font-medium rounded-md hover:bg-brand-700 disabled:opacity-50`

### Phase 2 features (7 additions)

| Feature | Backend | Frontend | Key Detail |
|---------|---------|----------|------------|
| **Slack/Webhook Alerts** | `alert_service.py` — `_send_breach_alert()` with Block Kit, `send_completion_alert()` | — | `ALERT_ON_SUCCESS` env var controls whether all runs alert or just failures |
| **CSV/JSON Export** | `evaluation_results.py` — `GET /results/export` with `StreamingResponse` | `runs/[id]/page.tsx` — Export buttons | Dynamically collects `extended_metrics` keys as CSV columns |
| **User Feedback Loop** | `ingestion.py` — `PATCH /logs/{id}/feedback`, `GET /feedback-stats`; `ingestion_service.py` — `update_feedback()`, `get_feedback_stats()` | `production/page.tsx` — stats card; `playground/page.tsx` — thumbs buttons | `FeedbackUpdate` schema validates `thumbs_up\|thumbs_down` pattern |
| **LLM Test Case Generation** | `generation_service.py` — system-type-specific prompts; `generation_tasks.py` — Celery task; `test_sets.py` — `POST /{id}/generate` | `test-sets/[id]/page.tsx` — GenerateModal | Parses JSON with markdown fence stripping; bumps test set version |
| **Side-by-Side Comparison** | — | `runs/page.tsx` — checkbox selection; `runs/compare/page.tsx` — comparison view | `Suspense` boundary for `useSearchParams()`; parallel SWR fetching |
| **Multi-Model Comparison** | `evaluation_runs.py` — `POST /runs/multi` with `MultiRunRequest` (2–6 configs) | `test-sets/[id]/page.tsx` — CompareModelsModal | Creates N runs, returns `compare_url` for redirect |
| **Dark Mode** | — | `theme.tsx` — ThemeProvider; `layout.tsx` — wraps children; `globals.css` — dark base; Sidebar, Card, Badge — `dark:` variants | `darkMode: "class"` in `tailwind.config.ts`; `localStorage` + system preference |

### Docker notes

- `docker-compose.yml` mounts `./runner:/app/runner` in the `api`, `worker`, and `beat` containers
- API container has `PYTHONPATH=/app` so `import runner.adapters...` works
- Frontend Docker container (port 3000) requires `docker compose up --build frontend` to pick up code changes
- Frontend dev server (port 3001) hot-reloads automatically
