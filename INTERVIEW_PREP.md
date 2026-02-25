# Interview Prep: Evaluation-First Testing Harness for RAG and AI Agents

> Use this document to walk through the project end-to-end before an interview. Every section maps to a common interviewer question.

---

## 1. Elevator Pitch (30 seconds)

"I built a production-grade evaluation platform that lets teams test and quality-gate four types of AI systems — RAG pipelines, tool-calling agents, multi-turn chatbots, and search engines — before they ship. It works like CI/CD for LLMs: every pipeline change is automatically evaluated with 13 specialized scoring engines, gated against configurable thresholds, and if metrics regress, the deploy is blocked and Slack gets notified. The whole stack is FastAPI, Celery, PostgreSQL, and a Next.js dashboard with 10 interactive pages."

---

## 2. Why Did You Build This? (The Problem)

LLM applications **fail silently**. Unlike traditional software where a bug produces an error, an LLM regression looks like this:

- A retrieval model update **quietly drops faithfulness** from 0.91 to 0.62 — the system still responds, just with more hallucinations.
- A prompt tweak **breaks tool calling** — the agent stops invoking the right APIs but still generates plausible-looking text.
- A chatbot **loses context** across turns — it forgets what the user said two messages ago but still replies fluently.
- A re-indexed search corpus **degrades ranking quality** — relevant documents drop from position 1 to position 8.

**Without automated evaluation wired into the deployment pipeline, teams only discover these regressions when end users complain.** There's no unified, open-source platform that provides evaluation-as-a-service across multiple AI system types with automated quality gating.

**Key insight**: Evaluation should be a first-class CI/CD concern — not a manual notebook someone runs occasionally.

---

## 3. Architecture Overview

```
                                 ┌─────────────────────┐
                                 │  Next.js Dashboard   │
                                 │     (port 3000)      │
                                 └──────────┬───────────┘
                                            │ SWR polling (8-10s)
                                            ▼
┌──────────┐    POST /runs     ┌─────────────────────────┐   apply_async()   ┌──────────────┐
│ rageval  │ ───────────────→  │    FastAPI Backend       │ ────────────────→ │ Celery Worker│
│   CLI    │                   │     (port 8000)          │                   │  (4 threads) │
└──────────┘                   │                          │                   │              │
                               │  25+ REST endpoints      │                   │  Evaluates:  │
┌──────────┐   POST /ingest    │  • test-sets, cases      │                   │  • Ragas     │
│ Prod     │ ───────────────→  │  • runs, results         │                   │  • Rules     │
│ Traffic  │                   │  • metrics, gate          │                   │  • LLM Judge │
└──────────┘                   │  • ingest, playground     │                   │  • Agent     │
                               │  • export, feedback       │                   │  • Chatbot   │
┌──────────┐  POST /playground │  • generate, multi-run    │                   │  • Search    │
│ Play-    │ ───────────────→  │                          │                   └──────┬───────┘
│ ground   │                   └─────────┬────────────────┘                          │
└──────────┘                             │                                           │
                                         ▼                                           ▼
                               ┌──────────────────┐                        ┌──────────────────┐
                               │   PostgreSQL 15   │ ◄──────────────────── │      Redis 7     │
                               │   (7 tables)      │                       │  (broker+results) │
                               └──────────────────┘                        └──────────────────┘
```

### Why these technology choices?

| Component | Choice | Why I Chose It |
|-----------|--------|----------------|
| API framework | **FastAPI** | Async-native with `asyncpg`, automatic OpenAPI docs, Pydantic validation |
| Task queue | **Celery + Redis** | Durable background jobs — evaluations can take 30s–10min per run |
| Database | **PostgreSQL 15** | JSONB columns for flexible failure rules, extended metrics, pipeline configs |
| ORM | **SQLAlchemy + Alembic** | Type-safe models, versioned migrations, async session support |
| RAG evaluation | **Ragas 0.2.6** | Industry-standard metrics for retrieval-augmented generation |
| LLM judge | **GPT-4o** | Configurable free-form quality scoring with reasoning |
| Dashboard | **Next.js 14 + Tailwind** | App Router, SWR for live polling, fast development |
| Charts | **Recharts** | Composable trend lines with threshold overlays |
| CI/CD | **GitHub Actions** | Zero-infrastructure, native secret management |

---

## 4. The Four AI System Types

This is what makes this project unique — it's not just for RAG. It evaluates **four fundamentally different** AI system types, each with specialized metrics.

### RAG Pipeline
- **What it does**: Retrieves documents, then generates an answer grounded in those documents
- **Demo adapter**: OpenAI `text-embedding-ada-002` over 30 knowledge chunks → GPT-4o-mini generation
- **Metrics**: Faithfulness (is the answer grounded in context?), Answer Relevancy (does it answer the question?), Context Precision (are retrieved docs relevant?), Context Recall (did we find all relevant docs?)
- **Evaluator**: `RagasEvaluator` — uses the Ragas library with OpenAI as the LLM judge

### Tool-Calling Agent
- **What it does**: Decides which tools to call, with what arguments, in what order, to accomplish a goal
- **Demo adapter**: OpenAI function-calling agent with 3 tools: `calculator`, `get_weather`, `unit_converter`
- **Metrics**: Tool Call F1 (precision + recall of tool selections), Tool Call Accuracy (correct arguments?), Goal Accuracy (did it achieve the objective?), Step Efficiency (minimal steps?)
- **Evaluator**: `AgentEvaluator` — compares predicted vs expected tool call sequences

### Multi-Turn Chatbot
- **What it does**: Maintains a coherent conversation across multiple turns with personality/role adherence
- **Demo adapter**: TechStore customer support bot with 10-item product knowledge base
- **Metrics**: Coherence (logical flow?), Knowledge Retention (remembers earlier turns?), Role Adherence (stays in character?), Response Relevance (on-topic?)
- **Evaluator**: `ConversationEvaluator` — analyzes full conversation history using keyword/semantic matching

### Search Engine
- **What it does**: Returns a ranked list of documents for a query
- **Demo adapter**: Semantic search over 15-document developer knowledge base using cosine similarity
- **Metrics**: NDCG@k (ranking quality), MAP@k (mean average precision), MRR (mean reciprocal rank), Precision@k, Recall@k
- **Evaluator**: `RankingEvaluator` — compares predicted ranking against expected document order

### How auto-selection works

When you trigger a run from the UI, you don't pick an evaluator. The system reads `test_set.system_type` and auto-selects the correct adapter and metrics:

```python
DEFAULT_ADAPTERS = {
    "rag":     {"adapter_module": "runner.adapters.demo_rag",        "adapter_class": "DemoRAGAdapter"},
    "agent":   {"adapter_module": "runner.adapters.demo_tool_agent", "adapter_class": "DemoToolAgentAdapter"},
    "chatbot": {"adapter_module": "runner.adapters.demo_chatbot",    "adapter_class": "DemoChatbotAdapter"},
    "search":  {"adapter_module": "runner.adapters.demo_search",     "adapter_class": "DemoSearchAdapter"},
}
```

Adapters are loaded dynamically via `importlib` — true plug-and-play.

---

## 5. Evaluation Pipeline (How a Run Works)

This is the core of the system. Here's exactly what happens when you click "Run Evaluation":

### Step 1: Run Creation (FastAPI)
1. API receives `POST /runs` with `test_set_id` and optional `pipeline_config`
2. Looks up the test set → gets `system_type`
3. Auto-selects adapter + metrics if not provided
4. **Snapshots gate thresholds** immutably on the run record (audit trail)
5. Creates `EvaluationRun` in `PENDING` state
6. Dispatches Celery task → returns `202 Accepted` with run ID

### Step 2: Evaluation (Celery Worker)
For each test case in the test set:
1. **Adapter execution**: Calls `adapter.run(query, context)` → returns `PipelineOutput` (answer, contexts, tool_calls, turn_history)
2. **Metric evaluation**: System-type-specific evaluator computes scores
   - RAG → `RagasEvaluator` (faithfulness, answer_relevancy, etc.)
   - Agent → `AgentEvaluator` (tool_call_f1, goal_accuracy, etc.)
   - Stored in `extended_metrics` JSONB for non-RAG systems
3. **Rule evaluation**: `RuleEvaluator` checks failure rules (must_contain, must_call_tool, regex, etc.)
4. **Composite pass/fail**: A test case passes if:
   - Average of all non-null metrics >= 0.5
   - All failure rules pass

### Step 3: Gate Decision
1. Compute summary metrics (averages across all test cases)
2. Compare against **threshold snapshot** (not current config — immutable)
3. Check pass rate against gate threshold (default 80%)
4. Mark run `COMPLETED` (pass) or `GATE_BLOCKED` (fail)
5. Append metrics to `metrics_history` for trend tracking
6. Send Slack/webhook alert if configured

### Step 4: Regression Detection
- `GET /runs/{id}/diff` computes metric deltas vs the last passing baseline
- Highlights which metrics regressed, by how much
- CI workflow posts this as a PR comment

---

## 6. Database Design (7 Tables)

### Why JSONB is used extensively

PostgreSQL JSONB is used for 5 different column types because the schema needs to be flexible across 4+ AI system types:

| Column | Table | Why JSONB |
|--------|-------|-----------|
| `failure_rules` | TestCase | Rule structure varies (must_contain vs regex vs tool assertions) |
| `extended_metrics` | EvaluationResult | Agent metrics differ from chatbot metrics — can't have fixed columns |
| `pipeline_config` | EvaluationRun | Adapter class, model name, top_k, embedding model — varies per pipeline |
| `gate_threshold_snapshot` | EvaluationRun | Immutable copy of thresholds at run time for audit trail |
| `summary_metrics` | EvaluationRun | Cached aggregates — structure varies by system type |

### Key design decisions

1. **Immutable threshold snapshots**: When a run is created, thresholds are copied into `gate_threshold_snapshot`. This means re-evaluating an old run always reflects the policy that was active when it ran. You can't move the goalposts retroactively.

2. **Append-only metrics history**: `metrics_history` is indexed on `(test_set_id, metric_name, recorded_at)` and decoupled from result rows. This enables fast trend queries without scanning the full results table.

3. **Production log lifecycle**: `ProductionLog.status` progresses through `RECEIVED → SAMPLED → EVALUATED`, with FK links to the test case and run it was sampled into.

4. **Versioned test sets**: `TestSet.version` is bumped automatically on any case mutation (add/edit/delete). This ensures you know exactly which version of a test set a run was evaluated against.

---

## 7. The 13 Evaluators

| # | Evaluator | System Type | What It Scores |
|---|-----------|-------------|----------------|
| 1 | `RagasEvaluator` | RAG | Faithfulness, answer relevancy, context precision, context recall |
| 2 | `AgentEvaluator` | Agent | Tool call F1, tool call accuracy, goal accuracy, step efficiency |
| 3 | `ConversationEvaluator` | Chatbot | Coherence, knowledge retention, role adherence, response relevance |
| 4 | `RankingEvaluator` | Search | NDCG@k, MAP@k, MRR, precision@k, recall@k |
| 5 | `RuleEvaluator` | All | 9 rule types: must_contain, must_not_contain, regex, tool assertions, hallucination risk, refusal detection, custom plugins |
| 6 | `LLMJudgeEvaluator` | All | GPT-4o free-form quality scoring (0–1) with reasoning |
| 7 | `SimilarityEvaluator` | General | ROUGE-L, BLEU for text similarity |
| 8 | `ClassificationEvaluator` | Classification | Accuracy, F1, precision, recall |
| 9 | `CodeEvaluator` | Code Gen | Syntax validation, test execution, linting |
| 10 | `TranslationEvaluator` | Translation | BLEU, translation accuracy, fluency |
| 11 | `SafetyEvaluator` | All | Toxicity detection, refusal rate, jailbreak detection |
| 12 | `DeepEvalEvaluator` | All | Third-party DeepEval integration |
| 13 | `MultiTurnAgentEvaluator` | Agent | Multi-turn tool consistency, goal completion across turns |

### Failure Rule Engine — 9 built-in rule types

| Rule | What It Enforces | Example |
|------|-----------------|---------|
| `must_contain` | Substring must appear in output | `{"type": "must_contain", "value": "30-day return policy"}` |
| `must_not_contain` | Substring must NOT appear | `{"type": "must_not_contain", "value": "I don't know"}` |
| `must_call_tool` | Named tool must be invoked | `{"type": "must_call_tool", "tool": "drug_lookup"}` |
| `must_not_call_tool` | Named tool must NOT be invoked | `{"type": "must_not_call_tool", "tool": "delete_user"}` |
| `regex_must_match` | Regex pattern must match output | `{"type": "regex_must_match", "pattern": "\\d+ mg"}` |
| `regex_must_not_match` | Regex must NOT match | `{"type": "regex_must_not_match", "pattern": "password|secret"}` |
| `max_hallucination_risk` | Faithfulness must exceed threshold | `{"type": "max_hallucination_risk", "threshold": 0.7}` |
| `must_refuse` | Response must be a safety refusal | `{"type": "must_refuse"}` |
| `custom` | Delegates to user plugin class | `{"type": "custom", "plugin": "my_app.DrugDosageCheck"}` |

---

## 8. The Adapter Pattern (Pluggability)

Any AI pipeline plugs in via a 3-method interface:

```python
class RAGAdapter:
    def setup(self):     # Called once before all test cases
    def run(self, query: str, context: dict) -> PipelineOutput:  # Called per test case
    def teardown(self):  # Cleanup after all test cases

@dataclass
class PipelineOutput:
    answer: str                                           # Always required
    retrieved_contexts: list[str] = []                    # RAG + Search
    tool_calls: list[ToolCallResult] = []                 # Agent
    turn_history: list[dict[str, str]] = []               # Chatbot
    metadata: dict = {}                                   # Any extra data
```

### Pre-built adapters

| Adapter | Use Case |
|---------|----------|
| `DemoRAGAdapter` | Embedding search + GPT-4o-mini (built-in demo) |
| `DemoToolAgentAdapter` | OpenAI function calling with 3 tools |
| `DemoChatbotAdapter` | TechStore customer support bot |
| `DemoSearchAdapter` | Cosine similarity search over developer KB |
| `LangChainAdapter` | Wraps any LangChain chain/agent |
| `LlamaIndexAdapter` | Wraps any LlamaIndex query engine |
| `HTTPAdapter` | Calls any REST endpoint |

### Dynamic loading

Adapters are loaded at runtime from `pipeline_config`:

```python
module = importlib.import_module(config["adapter_module"])
adapter_class = getattr(module, config["adapter_class"])
adapter = adapter_class(**kwargs)
```

This means you can plug in a new pipeline without modifying any harness code — just point `pipeline_config` at your adapter class.

---

## 9. Seven Power Features (Added in Phase 2)

### 9.1 Slack/Webhook Alerts
- Rich Slack Block Kit formatting with header, metric fields, warning indicators
- Gate failure alerts: fired when any metric breaches its threshold
- Run completion alerts: optional (controlled by `ALERT_ON_SUCCESS` env var)
- Works with any webhook endpoint (Slack, Discord, custom)
- Uses a unified `_post_webhook()` helper for reliability

### 9.2 CSV/JSON Export
- `GET /results/export?run_id=...&format=csv|json`
- Joins `EvaluationResult` with `TestCase` to include query text and expected output
- **Dynamically discovers** all `extended_metrics` keys and adds them as CSV columns
- Returns `StreamingResponse` (CSV) or `JSONResponse` with `Content-Disposition` header
- Frontend: "Export CSV" / "Export JSON" buttons on run detail page

### 9.3 User Feedback Loop
- `PATCH /logs/{log_id}/feedback` with `thumbs_up` or `thumbs_down`
- `GET /feedback-stats` returns aggregated counts and positive rate
- Playground: thumbs up/down buttons below each assistant message
- Production page: feedback summary card showing counts and positive rate percentage
- Pydantic validation: `pattern=r"^(thumbs_up|thumbs_down)$"`

### 9.4 LLM Test Case Generation
- GPT-4o generates test cases with **system-type-specific prompt templates**:
  - RAG: queries + expected contexts + ground truth answers
  - Agent: queries + expected tool calls + arguments
  - Chatbot: multi-turn conversation scenarios
  - Search: queries + expected ranking order
- Runs as async Celery task (generation can take 10–30s)
- Parses JSON response, strips markdown fences, inserts `TestCase` rows
- Auto-bumps test set version after generation

### 9.5 Side-by-Side Run Comparison
- Runs page: checkbox selection (max 4 runs), floating "Compare N Runs" bar
- `/runs/compare?ids=uuid1,uuid2,...`
- Fetches all runs + results in parallel via `Promise.all`
- Summary cards per run with colored headers
- Metric comparison table: best values highlighted in green
- Per-case results table: all runs' metrics in columns

### 9.6 Multi-Model Comparison
- `POST /runs/multi` with `test_set_id` + array of `configs` (2–6)
- Creates N independent runs with different `pipeline_config` values
- Returns `run_ids` + `compare_url` for redirect
- UI modal: dynamic model config list (model name + top_k), add/remove buttons

### 9.7 Dark Mode
- Tailwind `darkMode: "class"` strategy
- `ThemeProvider` React context with `useTheme()` hook
- `localStorage` persistence + system preference detection (`prefers-color-scheme`)
- `suppressHydrationWarning` on `<html>` to prevent SSR/CSR mismatch
- All components (Card, Badge, Sidebar, etc.) have `dark:` variants

---

## 10. CI/CD Integration

### evaluate.yml — Runs on every push/PR to main

```
Push to main/develop
    → Spin up Postgres 15 + Redis 7 as GitHub Actions services
    → Run Alembic migrations
    → Start FastAPI + Celery worker
    → rageval run (execute all test cases against pipeline)
    → rageval gate --fail-on-regression (exit code 1 = blocked)
    → rageval report --format json --diff (generate report)
    → Upload JSON report as 90-day artifact
    → Post/update formatted Markdown PR comment with metrics table
```

### release-gate.yml — Sets commit status

```
PR opened/updated
    → Query API: GET /runs?git_commit_sha={sha}&limit=1
    → Extract overall_passed from response
    → Set GitHub commit status: success or failure
```

### PR Comment Format

```
| Metric              | Score  | Threshold | Status  |
|---------------------|--------|-----------|---------|
| Faithfulness        | 0.91   | 0.70      | ✅ Pass |
| Answer Relevancy    | 0.84   | 0.70      | ✅ Pass |
| Context Precision   | 0.63   | 0.60      | ✅ Pass |
| Pass Rate           | 0.87   | 0.80      | ✅ Pass |
```

---

## 11. Production Traffic Monitoring

### Ingestion flow
1. Application sends `POST /ingest` with query, answer, latency, confidence score, tags
2. System stores the raw `ProductionLog`
3. **Sampling decision**: 20% of normal traffic, 100% of error responses
4. Sampled logs are auto-converted to `TestCase` records
5. Playground interactions are automatically ingested with source `playground-{system_type}`

### Why this matters
- Detects **quality drift** in production without manual testing
- High-latency or low-confidence responses are flagged automatically
- User feedback (thumbs up/down) provides ground truth for future evaluation

---

## 12. Frontend Dashboard (10 Pages)

| Page | What It Shows | Key Technical Detail |
|------|---------------|---------------------|
| `/dashboard` | 4 stat cards + recent runs table | SWR polling every 10s, auto-refreshes |
| `/systems` | AI system health cards per type | Groups by system_type, shows last run metrics |
| `/playground` | 4-tab chat interface | Stateless RAG/Agent/Search cached; Chatbot maintains per-session state |
| `/test-sets` | Grid of test sets with badges | System type badge, case count, version |
| `/test-sets/[id]` | Case table + Generate + Compare Models | Inline edit/delete, trigger-run modal |
| `/runs` | All runs with comparison checkboxes | Auto-refresh 8s, max 4 selection |
| `/runs/[id]` | Metric gauges + per-case results | Export CSV/JSON buttons, regression diff |
| `/runs/compare` | Side-by-side run comparison | Parallel data fetching, best-value highlighting |
| `/metrics` | Trend charts with thresholds | 7/30/90-day selector, Recharts line charts |
| `/production` | Traffic logs + feedback stats | Sampling stats, feedback summary card |

---

## 13. Async/Sync Architecture Decision

**Problem**: FastAPI is async (`asyncpg`), but Celery workers run synchronously.

**Solution**: Two separate database URLs:
- `DATABASE_URL = postgresql+asyncpg://...` — used by FastAPI
- `SYNC_DATABASE_URL = postgresql+psycopg2://...` — used by Celery workers and Alembic

**Why not make Celery async?** Celery's execution model is process/thread-based. Running an asyncio event loop inside a Celery worker introduces complexity (nested event loops, `run_in_executor` wrappers). Keeping workers synchronous with `psycopg2` is simpler, battle-tested, and avoids event-loop conflicts.

---

## 14. Key Design Decisions to Highlight

### 1. Immutable Gate Thresholds
**Decision**: Snapshot thresholds at run creation, not at gate evaluation time.
**Why**: Prevents "moving the goalposts." If someone lowers thresholds after a run starts, the original policy still applies. Provides a complete audit trail.

### 2. JSONB for Extended Metrics
**Decision**: Store non-RAG metrics in a single `extended_metrics` JSONB column rather than adding columns per system type.
**Why**: Adding 20+ nullable columns for agent/chatbot/search metrics creates a sparse table. JSONB keeps the schema clean and supports new system types without migrations.

### 3. Append-Only Metrics History
**Decision**: Separate `metrics_history` table instead of computing trends from `evaluation_results`.
**Why**: Trend queries need to scan by `(test_set_id, metric_name, time_range)`. Doing this on the results table requires aggregating across all runs. A dedicated table with a composite index makes trend queries O(log n) instead of O(n).

### 4. Dynamic Adapter Loading
**Decision**: Load adapters via `importlib` from `pipeline_config` JSON rather than a fixed registry.
**Why**: Users can add a new pipeline without modifying any harness code. Just implement `RAGAdapter.run()` and point `pipeline_config` at it.

### 5. Composite Pass/Fail
**Decision**: A test case passes if avg(metrics) >= 0.5 AND all failure rules pass.
**Why**: Metrics alone can't catch structural failures (e.g., "the agent must NOT call the delete API"). Rules provide hard constraints; metrics provide soft quality signals.

---

## 15. Common Interview Questions & Answers

### "What's the most challenging technical problem you solved?"

"The async/sync split between FastAPI and Celery. FastAPI uses `asyncpg` for non-blocking database access, but Celery workers are process-based and don't play well with asyncio. I solved this by maintaining two database URLs — `asyncpg` for the API and `psycopg2` for workers — with the same connection parameters. This avoids nested event loops while keeping the API fully async. The Celery workers use a separate `SYNC_DATABASE_URL` environment variable."

### "How do you ensure evaluation consistency?"

"Three mechanisms: (1) Immutable threshold snapshots — thresholds are frozen at run creation, so you can't retroactively change pass criteria. (2) Versioned test sets — every case mutation bumps the version, so you know exactly which test set a run was evaluated against. (3) Deterministic adapter loading — the same `pipeline_config` JSON always loads the same adapter class with the same parameters."

### "How does this scale?"

"The evaluation work is distributed via Celery with Redis as the broker. Each test case is evaluated independently, so you can scale workers horizontally. The Celery worker runs with `concurrency=4` by default but can be scaled to N workers. The append-only `metrics_history` table is indexed for fast trend queries. The frontend uses SWR with polling intervals (8–10s) to avoid WebSocket complexity while still providing near-real-time updates."

### "Why not just use LangSmith / Braintrust / another managed platform?"

"Those are great for RAG-specific evaluation, but this project evaluates four fundamentally different system types with specialized metrics for each. An agent's Tool Call F1 is computed differently from a chatbot's Coherence score or a search engine's NDCG@k. The harness also integrates directly into CI/CD as a deploy gate, generates test cases via LLM, and provides A/B comparison across models — all self-hosted with full control over the evaluation pipeline."

### "Walk me through the data model."

"Seven tables. `TestSet` → `TestCase` is one-to-many. Each test set has a `system_type` that determines which evaluator and metrics are used. `EvaluationRun` links to a test set and tracks status through `PENDING → RUNNING → COMPLETED | GATE_BLOCKED | FAILED`. Each run produces multiple `EvaluationResult` rows — one per test case — with per-metric scores. RAG metrics have dedicated columns; non-RAG metrics go in an `extended_metrics` JSONB column. `MetricsHistory` is append-only for trend tracking. `ProductionLog` captures real-world traffic with sampling status tracking."

### "What would you change if you did it again?"

"Three things: (1) I'd add WebSocket support for real-time run progress instead of polling — it adds complexity but eliminates the 8-second update lag. (2) I'd implement per-evaluator cost tracking more granularly — right now it's tracked at the run level but not broken down by which evaluator (Ragas vs LLM Judge) consumed the most tokens. (3) I'd consider using a columnar store like ClickHouse for the metrics history table — append-only time-series data is a perfect fit."

### "How do you handle failures?"

"At three levels: (1) Per-case: if an adapter throws an exception, the case is marked `failed` with the error message, but the run continues. (2) Per-run: if the overall pass rate drops below the gate threshold, the run is marked `GATE_BLOCKED` — it's a soft failure that blocks deploy but preserves the results for debugging. (3) Infrastructure: Celery tasks have `max_retries=2` with exponential backoff. Webhook alerts have try/except to prevent alert failures from affecting the run."

---

## 16. Numbers to Remember

| Metric | Value |
|--------|-------|
| REST API endpoints | 25+ |
| Database tables | 7 |
| Evaluator types | 13 |
| AI system types | 4 active (9 total supported) |
| Failure rule types | 9 |
| Frontend pages | 10 |
| Docker services | 6 (+ 1 migration service) |
| Pre-built adapters | 11 (4 demo + 3 framework + 4 task-specific) |
| CI/CD workflows | 2 (evaluate + release-gate) |

---

## 17. Tech Stack Quick Reference

**Backend**: Python 3.11, FastAPI, Celery, PostgreSQL 15, Redis 7, SQLAlchemy (async), Alembic, Pydantic v2

**Evaluation**: Ragas 0.2.6, DeepEval, OpenAI GPT-4o (LLM Judge), Custom evaluators

**Frontend**: Next.js 14 (App Router), TypeScript, Tailwind CSS, Recharts, SWR

**Infrastructure**: Docker Compose (6 services), GitHub Actions (2 workflows)

**APIs**: OpenAI API (embeddings + chat), Serper API (web search fallback)

---

## 18. Project Timeline & Scope

- **Phase 1**: Core platform — 4 AI system types, 13 evaluators, adapter pattern, quality gates, CI/CD workflows, 8 dashboard pages, playground, production ingestion
- **Phase 2**: 7 power features — Slack alerts, CSV/JSON export, user feedback, LLM test case generation, side-by-side comparison, multi-model A/B testing, dark mode
- **Total**: 26+ files modified/created in Phase 2 alone, 1,302 lines added
