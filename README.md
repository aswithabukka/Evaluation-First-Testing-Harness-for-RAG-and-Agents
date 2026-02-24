# RAG Eval Harness

**Evaluation-first testing infrastructure for RAG pipelines, AI agents, chatbots, and search engines.**

Ship LLM-powered features with the same rigor as software: every pipeline change is automatically evaluated, scored, and gated before it reaches production.

---

## Why This Exists

LLM applications fail silently. A retrieval model change can quietly drop faithfulness scores. A prompt tweak can introduce hallucinations. A chatbot can leak internal data. A tool-calling agent can invoke the wrong API. Without systematic evaluation wired into CI/CD, you only find out when users complain.

This project treats evaluation as a first-class concern — not an afterthought. It gives teams:

- **Reproducible test suites** with versioned test cases and structured failure rules
- **Automatic scoring** via Ragas, DeepEval, and LLM-as-judge on every commit
- **A hard gate** that blocks deploys when metrics regress below thresholds
- **A dashboard** for tracking metric trends, spotting regressions, and reviewing per-case results
- **4 AI system types** with specialized evaluators: RAG, Agent, Chatbot, Search
- **An interactive playground** to chat with each AI system and feed interactions into production monitoring
- **Production traffic ingestion** with automatic sampling and drift detection

---

## Supported AI System Types

| System Type | What It Evaluates | Key Metrics | Demo Adapter |
|-------------|-------------------|-------------|--------------|
| **RAG** | Retrieval-augmented generation pipelines | Faithfulness, Answer Relevancy, Context Precision, Context Recall | `DemoRAGAdapter` — embedding search + GPT-4o-mini |
| **Agent** | Tool-calling AI agents | Tool Call F1, Tool Call Accuracy, Goal Accuracy, Step Efficiency | `DemoToolAgentAdapter` — OpenAI function calling |
| **Chatbot** | Multi-turn conversational systems | Coherence, Knowledge Retention, Role Adherence, Response Relevance | `DemoChatbotAdapter` — customer support bot |
| **Search** | Semantic/keyword search engines | NDCG@k, MAP@k, MRR, Precision@k, Recall@k | `DemoSearchAdapter` — cosine similarity + Google fallback |

Each system type auto-selects the correct adapter and metrics when you trigger an evaluation run from the UI or API.

---

## What Was Built

### Backend (FastAPI + Celery + PostgreSQL)

- **REST API** with 20+ endpoints covering test sets, test cases, evaluation runs, results, metrics, ingestion, and playground
- **Async architecture**: FastAPI uses `asyncpg` for non-blocking I/O; Celery workers use sync `psycopg2` to avoid event-loop conflicts
- **Run lifecycle state machine**: `PENDING → RUNNING → COMPLETED | GATE_BLOCKED | FAILED`
- **Immutable gate snapshots**: thresholds are frozen at run-creation time so re-evaluating an old run always reflects the policy that was active when it ran
- **Regression diff endpoint** (`GET /runs/{id}/diff`): computes metric deltas and highlights regressions vs the last passing baseline
- **Metrics history table**: append-only, indexed by `(test_set_id, metric_name, recorded_at)` — decoupled from result rows for fast trend queries
- **Production traffic ingestion**: ingest real-world queries/answers via API, with configurable sampling rates (20% normal, 100% errors) to automatically generate test cases
- **Playground API**: interactive chat with all 4 AI systems, with automatic background ingestion into production traffic
- **Auto-adapter selection**: the backend resolves the correct adapter and metrics based on the test set's `system_type` — no manual configuration needed
- **Database migrations** with Alembic (versioned migrations included)
- **Celery beat** for background async evaluation tasks

### Evaluation Engine (Python CLI — `rageval`)

#### Core Evaluators

| Evaluator | System Type | What It Scores |
|-----------|-------------|----------------|
| `RagasEvaluator` | RAG | Faithfulness, answer relevancy, context precision, context recall via Ragas + OpenAI |
| `AgentEvaluator` | Agent | Tool call F1/precision/recall, argument accuracy, goal accuracy, step efficiency |
| `ConversationEvaluator` | Chatbot | Coherence, knowledge retention, role adherence, response relevance, conversation completion |
| `RankingEvaluator` | Search | NDCG@k, MAP@k, MRR, precision@k, recall@k |
| `RuleEvaluator` | All | Structural constraints: substring checks, regex, tool-call assertions, hallucination risk caps, refusal detection |
| `LLMJudgeEvaluator` | All | GPT-4o free-form quality scoring with configurable criteria; returns score (0–1) + reasoning |
| `SimilarityEvaluator` | General | ROUGE-L, BLEU scores for text similarity |
| `ClassificationEvaluator` | Classification | Accuracy, F1, precision, recall |
| `CodeEvaluator` | Code Gen | Syntax validation, test execution, linting |
| `TranslationEvaluator` | Translation | BLEU, translation accuracy |
| `SafetyEvaluator` | All | Safety/toxicity checks |
| `DeepEvalEvaluator` | All | DeepEval integration for additional metrics |
| `MultiTurnAgentEvaluator` | Agent | Multi-turn tool consistency, goal completion, refusal behavior |

#### Failure Rule Engine — 9 Built-in Rule Types

| Rule | What It Enforces |
|------|-----------------|
| `must_contain` / `must_not_contain` | Substring presence/absence in output |
| `must_call_tool` / `must_not_call_tool` | Named tool appears/is-absent in tool_calls |
| `regex_must_match` / `regex_must_not_match` | Regex pattern on output |
| `max_hallucination_risk` | Faithfulness score meets minimum threshold |
| `must_refuse` | Response is a safety refusal |
| `custom` | Delegates to user-supplied plugin class |

#### Adapter Pattern

Any AI pipeline plugs in via a 3-method interface (`setup / run / teardown`). The `run()` method returns a `PipelineOutput` with:

```python
@dataclass
class PipelineOutput:
    answer: str
    retrieved_contexts: list[str] = field(default_factory=list)
    tool_calls: list[ToolCallResult] = field(default_factory=list)     # Agent
    turn_history: list[dict[str, str]] = field(default_factory=list)   # Chatbot
    metadata: dict = field(default_factory=dict)                       # Any extra data
```

Pre-built adapters included for: **LangChain**, **LlamaIndex**, **HTTP/REST**, and 4 demo systems.

#### Three Reporters

- `console` — formatted terminal output with colors
- `json` — machine-readable evaluation report
- `diff` — regression diff vs last baseline run

### CI/CD (GitHub Actions)

Two workflows:

1. **`evaluate.yml`** — triggers on push/PR to `main`/`develop`:
   - Spins up Postgres 15 + Redis 7 as services
   - Runs Alembic migrations, starts FastAPI + Celery worker
   - Runs `rageval run` → `rageval gate` (exits non-zero if blocked) → `rageval report --diff`
   - Uploads the JSON evaluation report as a 90-day artifact
   - Posts (or updates) a formatted Markdown summary as a PR comment

2. **`release-gate.yml`** — queries runs by commit SHA and sets a GitHub commit status (`success` / `failure`)

### Frontend Dashboard (Next.js 14 + Tailwind + Recharts)

| Page | What You See |
|------|-------------|
| `/dashboard` | 4 stat cards (Total Runs 24h, Gate Pass Rate, Active Blocks, Test Sets); recent runs table with 10s live refresh |
| `/systems` | AI Systems health dashboard — cards for each system type showing status, adapter, last run metrics |
| `/playground` | Interactive 4-tab chat interface for RAG, Agent, Chatbot, Search with real-time detail panels |
| `/test-sets` | Test set grid with case counts, system type badge, version, last run status, and one-click "Run Evaluation" |
| `/test-sets/[id]` | Cases table with inline add/edit/delete; failure rule badges; trigger-run modal with auto-selected adapter |
| `/runs` | All evaluation runs, filterable by status/system; auto-refreshes every 8s |
| `/runs/[id]` | Per-metric gauge cards; regression diff table; per-case results with system-specific metric columns |
| `/metrics` | Recharts trend lines per metric with threshold overlay; 7/30/90-day selector |
| `/production` | Production traffic logs, sampling stats, drift indicators |

---

## Architecture

```
                                 ┌─────────────────────┐
                                 │  Next.js Dashboard   │
                                 │     (port 3000)      │
                                 └──────────┬───────────┘
                                            │ SWR polling
                                            ▼
┌──────────┐    POST /runs     ┌─────────────────────────┐    apply_async()    ┌──────────────┐
│ rageval  │ ───────────────→  │    FastAPI Backend       │ ─────────────────→  │ Celery Worker│
│   CLI    │                   │     (port 8000)          │                     │  (4 threads) │
└──────────┘                   │                          │                     │              │
                               │  Endpoints:              │                     │  Evaluates:  │
┌──────────┐   POST /ingest    │  • /test-sets            │                     │  • Ragas     │
│ Prod     │ ───────────────→  │  • /runs                 │                     │  • Rules     │
│ Traffic  │                   │  • /results              │                     │  • LLM Judge │
└──────────┘                   │  • /metrics              │                     │  • Agent     │
                               │  • /ingest               │                     │  • Chatbot   │
┌──────────┐  POST /playground │  • /playground            │                    │  • Search    │
│ Play-    │ ───────────────→  │                          │                     └──────┬───────┘
│ ground   │   (background     └─────────┬────────────────┘                            │
└──────────┘    ingestion)               │                                             │
                                         ▼                                             ▼
                               ┌──────────────────┐                          ┌──────────────────┐
                               │   PostgreSQL      │ ◄───────────────────── │      Redis        │
                               │  (7 tables)       │                         │  (broker+results) │
                               └──────────────────┘                          └──────────────────┘

GitHub Actions ── evaluate.yml ── triggers rageval CLI on push/PR
               └─ release-gate.yml ── sets commit status (pass/fail)
```

### Tech Stack

| Concern | Choice | Why |
|---------|--------|-----|
| API framework | FastAPI | Async-native, automatic OpenAPI docs |
| Task queue | Celery + Redis | Durable background evaluation jobs |
| Database | PostgreSQL 15 | JSONB for flexible failure rules and extended metrics |
| ORM / migrations | SQLAlchemy + Alembic | Type-safe models, versioned schema |
| RAG evaluation | Ragas 0.2.6 | Industry-standard metrics for retrieval-augmented generation |
| LLM judge | GPT-4o via OpenAI | Configurable free-form quality scoring |
| Dashboard | Next.js 14 + Tailwind CSS | App Router, SWR for live polling |
| Charts | Recharts | Trend lines with threshold overlays |
| CI/CD | GitHub Actions | Zero-infrastructure CI with native secret management |
| Web search | Serper API (Google) | Fallback for search engine when local KB lacks results |

---

## Quick Start

### Prerequisites

- Docker & Docker Compose
- An OpenAI API key (for evaluation metrics)
- (Optional) A Serper API key for web search fallback

### 1. Start the stack

```bash
cp .env.example .env          # add your OPENAI_API_KEY (and optionally SERPER_API_KEY)
make up                       # starts api, worker, db, redis, frontend
make migrate                  # runs Alembic migrations (required on first run)
```

- **API docs**: http://localhost:8000/api/v1/docs
- **Dashboard**: http://localhost:3000

### 2. Seed demo data (optional)

```bash
make seed
```

This populates 4 demo test sets (one per system type) with 8 test cases each, including pre-configured failure rules.

### 3. Run evaluations from the UI

1. Open http://localhost:3000/test-sets
2. Click on any test set (e.g., "Demo Chatbot")
3. Click **"Run Evaluation"** — the system auto-selects the correct adapter and metrics
4. Watch the run progress at http://localhost:3000/runs
5. Click into a completed run to see per-case results, metric gauges, and regression diffs

### 4. Try the Playground

1. Open http://localhost:3000/playground
2. Switch between tabs: **RAG**, **Agent**, **Chatbot**, **Search**
3. Type a query or click a sample chip
4. See the response + system-specific detail panel (contexts, tool calls, conversation turns, ranked results)
5. Playground interactions are automatically ingested into production traffic for monitoring

---

## Integrating Your Own Pipeline

### Step 1: Implement the adapter

```python
# my_app/pipeline.py
from runner.adapters.base import RAGAdapter, PipelineOutput

class MyRAGPipeline(RAGAdapter):
    def setup(self):
        self.retriever = MyRetriever(...)
        self.llm = openai.OpenAI()

    def run(self, query: str, context: dict) -> PipelineOutput:
        docs = self.retriever.retrieve(query, k=5)
        answer = self.llm.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "Answer based on context only."},
                {"role": "user", "content": f"Context: {docs}\n\nQ: {query}"}
            ]
        ).choices[0].message.content
        return PipelineOutput(
            answer=answer,
            retrieved_contexts=[d.text for d in docs],
        )

    def teardown(self): pass
```

For **agents**, return `tool_calls` in your `PipelineOutput`. For **chatbots**, return `turn_history`. For **search**, return `retrieved_contexts` with relevance scores in `metadata`.

### Step 2: Configure

Copy `rageval.yaml.example` to `rageval.yaml` and point to your adapter:

```yaml
adapter:
  module: my_app.pipeline
  class: MyRAGPipeline

metrics:
  - faithfulness
  - answer_relevancy
  - context_precision
  - context_recall
  - rule_evaluation

thresholds:
  faithfulness: 0.7
  answer_relevancy: 0.7
  pass_rate: 0.8
```

### Step 3: Run evaluations

```bash
# CLI
rageval run --config rageval.yaml --test-set <TEST_SET_ID>
rageval gate --fail-on-regression
rageval report --format console

# Or via API
curl -X POST http://localhost:8000/api/v1/runs/ \
  -H "Content-Type: application/json" \
  -d '{
    "test_set_id": "<TEST_SET_ID>",
    "pipeline_version": "v1.2.0",
    "pipeline_config": {
      "adapter_module": "my_app.pipeline",
      "adapter_class": "MyRAGPipeline"
    }
  }'
```

---

## Production Traffic Monitoring

Ingest real-world queries and responses to detect quality drift:

```bash
curl -X POST http://localhost:8000/api/v1/ingest/ \
  -H "Content-Type: application/json" \
  -d '{
    "logs": [
      {
        "source": "production-api",
        "query": "What is the return policy?",
        "answer": "You can return items within 30 days...",
        "latency_ms": 1200,
        "tags": ["returns", "policy"]
      }
    ]
  }'
```

The ingestion pipeline:
1. Stores the raw production log
2. Samples at a configurable rate (20% normal traffic, 100% error responses)
3. Auto-creates test cases from sampled logs
4. Flags high-latency or low-confidence responses for review

Playground interactions are automatically ingested with the source `playground-{system_type}`.

---

## Multi-Turn Agent Evaluation

For conversational agents, use `MultiTurnAgentEvaluator` to evaluate across a full conversation history:

```python
from runner.multi_turn.agent_evaluator import MultiTurnAgentEvaluator

evaluator = MultiTurnAgentEvaluator(adapter=my_adapter)
result = evaluator.evaluate(
    turns=[
        {"query": "What is the drug dosage for ibuprofen?"},
        {"query": "And for children under 5?"},
    ],
    failure_rules=[
        {"type": "must_call_tool", "tool": "drug_lookup"},
        {"type": "must_not_contain", "value": "I don't know"},
    ],
)
print(result.passed, result.turn_results)
```

Each turn is independently scored against the failure rules. The overall result is `passed=False` if any single turn fails.

---

## Custom Metric Plugins

```python
# my_app/custom_metrics.py
class DrugDosageHallucinationMetric:
    def evaluate(self, output: str, tool_calls: list, rule: dict) -> tuple[bool, str]:
        if "mg" in output and "drug_lookup" not in [tc["tool"] for tc in tool_calls]:
            return False, "Dosage mentioned without calling drug_lookup tool"
        return True, "OK"
```

Register in `rageval.yaml`:
```yaml
plugins:
  - module: my_app.custom_metrics
    class: DrugDosageHallucinationMetric
```

---

## GitHub Actions Integration

Add to `.github/workflows/evaluate.yml` (see the pre-built workflow in `.github/workflows/`).

Required secrets:
- `OPENAI_API_KEY` — for Ragas/LLM judge scoring
- `RAGEVAL_API_URL` — URL of your deployed backend (optional for self-hosted CI)

The workflow posts a formatted PR comment after each run:

```
| Metric              | Score  | Threshold | Status  |
|---------------------|--------|-----------|---------|
| Faithfulness        | 0.91   | 0.70      | ✅ Pass |
| Answer Relevancy    | 0.84   | 0.70      | ✅ Pass |
| Context Precision   | 0.63   | 0.60      | ✅ Pass |
| Context Recall      | 0.72   | 0.60      | ✅ Pass |
| Pass Rate           | 0.87   | 0.80      | ✅ Pass |
```

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `OPENAI_API_KEY` | — | **Required.** For Ragas, LLM judge, and demo adapters |
| `DATABASE_URL` | `postgresql+asyncpg://rageval:rageval@db:5432/rageval` | Async PostgreSQL (FastAPI) |
| `SYNC_DATABASE_URL` | `postgresql://rageval:rageval@db:5432/rageval` | Sync PostgreSQL (Celery + Alembic) |
| `REDIS_URL` | `redis://redis:6379/0` | Redis connection |
| `CELERY_BROKER_URL` | `redis://redis:6379/1` | Celery broker |
| `CELERY_RESULT_BACKEND` | `redis://redis:6379/2` | Celery results |
| `OPENAI_MODEL` | `gpt-4o` | LLM judge model |
| `DEFAULT_FAITHFULNESS_THRESHOLD` | `0.7` | Gate threshold |
| `DEFAULT_ANSWER_RELEVANCY_THRESHOLD` | `0.7` | Gate threshold |
| `DEFAULT_CONTEXT_PRECISION_THRESHOLD` | `0.6` | Gate threshold |
| `DEFAULT_CONTEXT_RECALL_THRESHOLD` | `0.6` | Gate threshold |
| `DEFAULT_PASS_RATE_THRESHOLD` | `0.8` | Gate threshold |
| `SAMPLING_RATE` | `0.2` | Production traffic sampling rate (0.0 – 1.0) |
| `SAMPLING_ERROR_RATE` | `1.0` | Error traffic sampling rate |
| `SERPER_API_KEY` | — | Optional. Enables Google web search fallback for Search Engine |
| `NEXT_PUBLIC_API_URL` | `http://localhost:8000/api/v1` | Frontend API URL |
| `API_KEYS` | — | Optional. Comma-separated API keys for authenticated endpoints |
| `CORS_ORIGINS` | `*` | Allowed CORS origins |
| `ALERT_WEBHOOK_URL` | — | Optional. Webhook for gate failure alerts |

---

## Extending the System

**Add a new AI system type:**
1. Create an adapter in `runner/adapters/` implementing `RAGAdapter`
2. Create an evaluator in `runner/evaluators/` returning a metrics dict
3. Add the system type to `DEFAULT_ADAPTERS` and `DEFAULT_METRICS` in `backend/app/services/evaluation_service.py`
4. Add metric display config in `frontend/src/lib/system-metrics.ts`
5. Add evaluation logic in `backend/app/workers/tasks/evaluation_tasks.py`

**Add a new rule type:**
Extend `RuleType` enum and add a branch in `RuleEvaluator._evaluate_rule()` in `runner/evaluators/rule_evaluator.py`.

**Add a new metric:**
Add to `RagasEvaluator.SUPPORTED_METRICS` in `runner/evaluators/ragas_evaluator.py`, then add a column via a new Alembic migration.

**Add a new adapter:**
Subclass `RAGAdapter` in `runner/adapters/base.py`, implement `run()`, and reference it from `rageval.yaml` or register it in `DEFAULT_ADAPTERS`.

---

## Project Structure

```
rag-eval-harness/
├── backend/                          # FastAPI + Celery application
│   ├── app/
│   │   ├── main.py                   # FastAPI entry point
│   │   ├── api/v1/
│   │   │   ├── router.py             # Route registration
│   │   │   ├── endpoints/            # 9 endpoint modules
│   │   │   │   ├── health.py
│   │   │   │   ├── test_sets.py
│   │   │   │   ├── test_cases.py
│   │   │   │   ├── evaluation_runs.py
│   │   │   │   ├── evaluation_results.py
│   │   │   │   ├── metrics.py
│   │   │   │   ├── ingestion.py
│   │   │   │   └── playground.py
│   │   │   └── schemas/              # 7 Pydantic schema modules
│   │   ├── core/                     # Config, exceptions, security
│   │   ├── db/
│   │   │   └── models/               # 7 SQLAlchemy ORM models
│   │   ├── services/                 # 11 business logic services
│   │   └── workers/
│   │       ├── celery_app.py
│   │       └── tasks/                # Celery evaluation tasks
│   ├── alembic/                      # Database migrations
│   ├── requirements.txt
│   └── Dockerfile
│
├── runner/                           # Python CLI evaluation engine
│   ├── cli.py                        # rageval CLI entry point
│   ├── config_loader.py
│   ├── adapters/                     # Pipeline integrations
│   │   ├── base.py                   # RAGAdapter interface + PipelineOutput
│   │   ├── demo_rag.py              # Demo: RAG (embedding + LLM)
│   │   ├── demo_tool_agent.py       # Demo: Agent (function calling)
│   │   ├── demo_chatbot.py          # Demo: Chatbot (multi-turn)
│   │   ├── demo_search.py           # Demo: Search (ranking + web)
│   │   ├── langchain_adapter.py     # Framework: LangChain
│   │   ├── llamaindex_adapter.py    # Framework: LlamaIndex
│   │   └── ...                       # 9 more system adapters
│   ├── evaluators/                   # 13 scoring engines
│   │   ├── ragas_evaluator.py       # Ragas metrics
│   │   ├── agent_evaluator.py       # Tool call F1, goal accuracy
│   │   ├── conversation_evaluator.py # Coherence, role adherence
│   │   ├── ranking_evaluator.py     # NDCG, MAP, MRR
│   │   ├── rule_evaluator.py        # Failure rule engine
│   │   ├── llm_judge_evaluator.py   # GPT-4o scoring
│   │   └── ...                       # 7 more evaluators
│   ├── multi_turn/                   # Multi-turn agent evaluator
│   ├── plugins/                      # Custom metric plugin loader
│   └── reporters/                    # Console, JSON, diff reporters
│
├── frontend/                         # Next.js 14 dashboard
│   └── src/
│       ├── app/                      # 9 pages (App Router)
│       │   ├── dashboard/            # Stats + recent runs
│       │   ├── systems/              # AI system health cards
│       │   ├── playground/           # Interactive 4-system chat
│       │   ├── test-sets/            # Test set management
│       │   ├── runs/                 # Evaluation run list + detail
│       │   ├── metrics/              # Trend charts
│       │   └── production/           # Production traffic logs
│       ├── components/               # Reusable UI components
│       │   ├── dashboard/            # SummaryCards, RecentRunsTable
│       │   ├── layout/               # Sidebar navigation
│       │   ├── metrics/              # MetricGauge, ChartPanel
│       │   └── ui/                   # Badge, Card, LoadingSpinner
│       └── lib/
│           ├── api.ts                # API client
│           ├── system-metrics.ts     # Per-system metric config
│           └── utils.ts
│
├── .github/workflows/
│   ├── evaluate.yml                  # CI: run evals on push/PR
│   └── release-gate.yml             # CD: set commit status
├── docker-compose.yml                # 7 services
├── Makefile                          # Developer shortcuts
├── rageval.yaml.example              # Evaluation config template
└── .env.example                      # Environment template
```

---

## Database Schema

```
┌──────────────┐     ┌──────────────────┐     ┌────────────────────┐
│  test_sets   │────→│   test_cases     │     │  evaluation_runs   │
│              │     │                  │     │                    │
│ id           │     │ id               │     │ id                 │
│ name         │     │ test_set_id (FK) │     │ test_set_id (FK)   │
│ description  │     │ query            │     │ status (enum)      │
│ system_type  │     │ expected_output  │     │ pipeline_version   │
│ version      │     │ ground_truth     │     │ git_commit_sha     │
│              │     │ context (JSONB)  │     │ gate_threshold_    │
│              │     │ failure_rules    │     │   snapshot (JSONB) │
│              │     │   (JSONB)        │     │ summary_metrics    │
│              │     │ tags (JSONB)     │     │   (JSONB)          │
│              │     │ conversation_    │     │ pipeline_config    │
│              │     │   turns (JSONB)  │     │   (JSONB)          │
└──────────────┘     └──────────────────┘     └────────┬───────────┘
                                                       │
                                              ┌────────▼───────────┐
                                              │ evaluation_results │
                                              │                    │
                                              │ id                 │
                                              │ run_id (FK)        │
                                              │ test_case_id (FK)  │
                                              │ faithfulness       │
                                              │ answer_relevancy   │
                                              │ context_precision  │
                                              │ context_recall     │
                                              │ extended_metrics   │
                                              │   (JSONB)          │
                                              │ rules_passed       │
                                              │ rules_detail       │
                                              │   (JSONB)          │
                                              │ passed (bool)      │
                                              │ raw_output         │
                                              │ tool_calls (JSONB) │
                                              │ duration_ms        │
                                              └────────────────────┘

┌──────────────────┐     ┌──────────────────┐
│ metrics_history  │     │ production_logs  │
│                  │     │                  │
│ test_set_id (FK) │     │ source           │
│ metric_name      │     │ query            │
│ metric_value     │     │ answer           │
│ recorded_at      │     │ status           │
│                  │     │ latency_ms       │
│ (indexed for     │     │ confidence_score │
│  fast trends)    │     │ user_feedback    │
└──────────────────┘     └──────────────────┘
```

---

## Makefile Commands

```bash
make up                    # Start all services (docker compose up -d)
make down                  # Stop all services
make migrate               # Run Alembic database migrations
make seed                  # Populate demo data (4 test sets, 32 test cases)
make shell-api             # Bash into API container
make eval-local            # Run CLI evaluation (TEST_SET_ID=<uuid>)
make test-backend          # Run pytest with coverage
make type-check-frontend   # TypeScript type checking
make lint                  # Ruff linter
make format                # Auto-format with ruff
make ingest-test           # Test production ingestion endpoint
```

---

## How Evaluation Works (Detailed)

### Per-Case Scoring

For each test case in a run:

1. **Adapter execution**: The correct adapter (`DemoRAGAdapter`, `DemoToolAgentAdapter`, etc.) processes the query and returns a `PipelineOutput`
2. **Metric evaluation**: System-type-specific evaluators compute scores (stored in `extended_metrics` JSONB for non-RAG systems)
3. **Rule evaluation**: Failure rules (if any) are checked against the output
4. **Composite pass/fail**: A case passes if:
   - The average of all non-null metrics ≥ 0.5 (composite threshold)
   - All failure rules pass

### Run-Level Gating

After all cases are scored:

1. Summary metrics are computed (averages across all cases)
2. The pass rate is checked against the gate threshold (default 0.8)
3. The run is marked `COMPLETED` (pass) or `GATE_BLOCKED` (fail)
4. Metrics are appended to the history table for trend tracking

---

## License

This project is intended for internal evaluation and testing of AI systems.
