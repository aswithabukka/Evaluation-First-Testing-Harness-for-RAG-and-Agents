# Weekly Progress Report

**Project:** Evaluation-First Testing Harness for RAG and AI Agents
**Student:** Aswitha Bukka
**Date:** February 25, 2026

---

## 1. Project Overview

This project addresses a critical gap in the AI/ML engineering lifecycle: the absence of systematic, automated evaluation infrastructure for Large Language Model (LLM) applications. Unlike traditional software where bugs produce clear errors, LLM-powered systems — such as Retrieval-Augmented Generation (RAG) pipelines, tool-calling agents, multi-turn chatbots, and semantic search engines — fail silently. A retrieval model update can quietly degrade faithfulness scores, a prompt tweak can introduce hallucinations, and an agent can begin invoking incorrect APIs without producing any visible errors.

This project treats LLM evaluation as a first-class CI/CD concern by building a production-grade, full-stack evaluation harness that automatically scores, gates, and monitors four distinct AI system types before they reach production.

---

## 2. System Architecture

The platform follows a distributed microservices architecture with six containerized services orchestrated via Docker Compose:

- **FastAPI Backend** (Python 3.11): Async REST API with 25+ endpoints serving as the central coordination layer. Uses `asyncpg` for non-blocking database I/O and Pydantic v2 for request/response validation.

- **Celery Workers** (Python): Distributed task queue processing evaluation jobs asynchronously. Each evaluation run is dispatched as a background task, enabling concurrent evaluation of multiple pipelines without blocking the API.

- **Celery Beat**: Periodic task scheduler that triggers hourly evaluation of sampled production traffic, enabling continuous quality monitoring.

- **PostgreSQL 15**: Primary data store with 7 tables utilizing JSONB columns extensively for flexible metric storage, failure rule definitions, and pipeline configuration. The schema supports 9 AI system types without requiring migrations for each new metric.

- **Redis 7**: Serves dual purpose as Celery's message broker (database 1) and result backend (database 2), enabling reliable task distribution and result retrieval.

- **Next.js 14 Dashboard**: Interactive frontend with 10 pages built using the App Router, Tailwind CSS for styling, Recharts for metric visualization, and SWR for live data polling.

---

## 3. AI System Types and Evaluation

The harness evaluates four fundamentally different AI system architectures, each with specialized evaluators and metrics:

### 3.1 RAG (Retrieval-Augmented Generation)
Evaluates pipelines that retrieve relevant documents and generate grounded answers. Metrics include Faithfulness (is the answer grounded in retrieved context?), Answer Relevancy (does it address the question?), Context Precision (are retrieved documents relevant?), and Context Recall (were all relevant documents found?). Evaluation is powered by the Ragas framework with OpenAI as the LLM judge.

### 3.2 Tool-Calling Agents
Evaluates AI agents that decide which tools to invoke, with what arguments, in what sequence. Metrics include Tool Call F1 (precision and recall of tool selections), Tool Call Accuracy (correctness of arguments), Goal Accuracy (did it achieve the objective?), and Step Efficiency (did it use minimal steps?).

### 3.3 Multi-Turn Chatbots
Evaluates conversational AI systems that maintain coherent dialogue across multiple turns. Metrics include Coherence (logical flow across turns), Knowledge Retention (remembers earlier context), Role Adherence (stays in character), and Response Relevance (on-topic replies).

### 3.4 Search Engines
Evaluates information retrieval systems that return ranked document lists. Metrics include NDCG@k (ranking quality), MAP@k (mean average precision), MRR (mean reciprocal rank), Precision@k, and Recall@k.

The system includes 13 evaluators in total, covering RAG metrics (via Ragas), rule-based evaluation (9 rule types including substring checks, regex matching, tool call assertions, hallucination risk thresholds, and refusal detection), LLM-as-Judge scoring (GPT-4o free-form quality assessment), and specialized evaluators for code generation, classification, translation, and safety.

---

## 4. Working with Claude (Anthropic)

A significant portion of this week's development was conducted in collaboration with **Claude**, Anthropic's AI assistant, through the **Claude Code** CLI tool. Claude Code is an agentic coding tool that operates directly in the terminal, providing the ability to understand codebases, edit files, run commands, and iteratively develop features.

### How Claude was integrated into the development workflow:

- **Architecture Planning**: Claude was used to design the implementation strategy for all seven new features, analyzing the existing codebase structure, identifying the correct files to modify, and proposing the API contract, database schema changes, and frontend component architecture before any code was written.

- **Full-Stack Feature Implementation**: Each of the seven features (detailed in Section 5) was implemented through iterative collaboration with Claude. Claude read existing source files, understood patterns and conventions already established in the codebase, and generated code that maintained consistency with the existing architecture — including the async/sync database split, Pydantic schema conventions, SWR data fetching patterns, and Tailwind styling approach.

- **Multi-System Integration**: Claude helped integrate multiple external systems into the harness:
  - **OpenAI API** integration for LLM-powered test case generation with system-type-specific prompt engineering
  - **Slack Block Kit API** integration for rich webhook alert formatting
  - **Celery task queue** integration for async generation workflows
  - **Next.js Suspense boundaries** for proper server-side rendering with client-side hooks

- **Build Verification and Debugging**: Claude identified and resolved TypeScript compilation errors (missing `useRouter()` declarations, `useSearchParams()` Suspense boundary requirements, incorrect component prop types), verified the frontend build compiled successfully across all 13 pages, and managed Docker container rebuilds.

- **Documentation Generation**: Claude assisted in creating comprehensive documentation including README updates, CLAUDE.md (developer guide) updates, and this report — ensuring all technical details accurately reflected the implemented code.

This workflow demonstrated how AI-assisted development can significantly accelerate the implementation of complex, multi-layered features while maintaining code quality and architectural consistency across a full-stack application.

---

## 5. Features Implemented This Week

Seven major features were added to the platform during this development cycle:

### 5.1 Slack/Webhook Alerts
Implemented a notification system that sends rich Slack Block Kit messages when evaluation runs complete or quality gate thresholds are breached. Gate failure alerts include the specific metrics that regressed, their threshold values, and actual scores. Run completion alerts provide a summary of all metrics with pass/fail status. The system supports any webhook endpoint (Slack, Discord, or custom) and is controlled via environment variables (`ALERT_WEBHOOK_URL`, `ALERT_ON_SUCCESS`).

**Technical details:** The `AlertService` class uses a unified `_post_webhook()` helper for HTTP POST delivery. Block Kit payloads are constructed with header blocks, section fields, and context blocks for a professional Slack message appearance.

### 5.2 CSV/JSON Export
Added the ability to download complete evaluation results for offline analysis. The `GET /results/export` endpoint joins `EvaluationResult` rows with their corresponding `TestCase` records to include query text, expected outputs, all metric scores, rule pass/fail details, and raw model output. The CSV format dynamically discovers all `extended_metrics` keys across results and adds them as additional columns, ensuring system-specific metrics (e.g., `tool_call_f1`, `coherence`, `ndcg_at_5`) are fully exported.

**Technical details:** Uses FastAPI `StreamingResponse` with Python's `csv` module writing to `io.StringIO` for memory-efficient CSV generation. JSON export returns a `JSONResponse` with `Content-Disposition` headers for browser download.

### 5.3 User Feedback Loop
Implemented a feedback collection mechanism enabling users to provide thumbs up/down ratings on AI system outputs. In the Playground, each assistant message displays feedback buttons that persist to the database. On the Production page, a feedback statistics card shows aggregated counts (total thumbs up, thumbs down, no feedback) and calculates the positive feedback rate percentage.

**Technical details:** Added `FeedbackUpdate` Pydantic schema with regex pattern validation (`^(thumbs_up|thumbs_down)$`), `PATCH /logs/{id}/feedback` endpoint, and `GET /feedback-stats` endpoint using SQLAlchemy `func.count` with conditional filtering for aggregation.

### 5.4 LLM-Powered Test Case Generation
Built an AI-powered test case generator that uses GPT-4o to create structured evaluation test cases based on a user-specified topic. Each of the four system types has a specialized prompt template:
- **RAG**: Generates queries with expected ground truth answers and relevant context hints
- **Agent**: Generates queries with expected tool call sequences and arguments
- **Chatbot**: Generates multi-turn conversation scenarios with expected responses
- **Search**: Generates queries with expected document ranking orders

**Technical details:** Implemented as an async Celery task (`generation_tasks.py`) that calls the `GenerationService`, which sends system-type-specific prompts to the OpenAI Chat Completions API, parses the JSON response (stripping markdown fences if present), inserts `TestCase` rows, and bumps the test set version.

### 5.5 Side-by-Side Run Comparison
Added the ability to visually compare 2-4 evaluation runs simultaneously. The Runs page now includes checkbox selection with a floating "Compare N Runs" action bar. The comparison page (`/runs/compare`) displays:
- Summary cards per run with pass rate and key metric values
- A metric comparison table highlighting the best value for each metric in green
- A per-case results grid showing all runs' metric scores side by side

**Technical details:** Uses `useSearchParams()` wrapped in a `<Suspense>` boundary (required by Next.js 15 for static generation). Data is fetched in parallel via `Promise.all` with SWR for caching.

### 5.6 Multi-Model A/B Comparison
Implemented batch-triggered evaluation runs for comparing different model configurations. Users can specify 2-6 model configurations (model name + retrieval parameter `top_k`), and the system creates N independent evaluation runs with different `pipeline_config` values. Upon completion, users are redirected to the comparison page.

**Technical details:** Added `POST /runs/multi` endpoint with `MultiRunRequest` schema (validates 2-6 configs). Returns `run_ids` array and a `compare_url` for frontend redirect.

### 5.7 Dark Mode
Implemented a complete dark mode theme using Tailwind CSS's class-based strategy. A `ThemeProvider` React context manages theme state, persists the preference to `localStorage`, and detects the user's system preference (`prefers-color-scheme: dark`) on first visit. All UI components (Sidebar, Card, Badge, tables, form inputs) have corresponding `dark:` variant styles.

**Technical details:** Uses `suppressHydrationWarning` on the `<html>` element to prevent SSR/CSR mismatch when the theme is read from `localStorage` on mount.

---

## 6. Technical Metrics

| Metric | Value |
|--------|-------|
| Files modified/created | 26 |
| Lines of code added | 1,302 |
| Total REST API endpoints | 25+ |
| Database tables | 7 |
| Evaluator types | 13 |
| AI system types (active) | 4 |
| Frontend pages | 10 |
| Docker services | 6 |
| Pre-built adapters | 11 |
| CI/CD workflows | 2 |

---

## 7. Technology Stack

| Layer | Technologies |
|-------|-------------|
| Backend API | Python 3.11, FastAPI, Pydantic v2, SQLAlchemy (async), Alembic |
| Task Processing | Celery, Redis 7 |
| Database | PostgreSQL 15 (JSONB columns) |
| Evaluation | Ragas 0.2.6, DeepEval, OpenAI GPT-4o (LLM Judge), Custom evaluators |
| Frontend | Next.js 14 (App Router), TypeScript, Tailwind CSS, Recharts, SWR |
| Infrastructure | Docker Compose, GitHub Actions |
| External APIs | OpenAI API (embeddings + chat completions), Serper API (web search) |
| AI Development Tools | Claude Code (Anthropic) for AI-assisted development |

---

## 8. Key Design Decisions

1. **Immutable Threshold Snapshots**: Gate thresholds are captured at run creation time in a JSONB column, preventing retroactive policy changes and providing a complete audit trail.

2. **JSONB for Extended Metrics**: Non-RAG system metrics are stored in a single `extended_metrics` JSONB column rather than adding fixed columns per system type, keeping the schema clean and extensible without migrations.

3. **Async/Sync Database Split**: FastAPI uses `asyncpg` for non-blocking I/O while Celery workers use synchronous `psycopg2`, avoiding nested event loop conflicts in the task queue.

4. **Dynamic Adapter Loading**: Pipeline adapters are loaded at runtime via `importlib` from `pipeline_config` JSON, enabling plug-and-play pipeline integration without code changes to the harness.

5. **Composite Pass/Fail Logic**: A test case passes only if the average of all metrics exceeds 0.5 AND all structural failure rules pass, combining soft quality signals with hard constraints.

---

## 9. Challenges and Resolutions

| Challenge | Resolution |
|-----------|-----------|
| TypeScript error: `Cannot find name 'router'` in test set detail page | Added `const router = useRouter()` to the main component scope (was only declared inside a child modal component) |
| Next.js prerender error: `useSearchParams()` requires Suspense boundary | Wrapped the comparison page component in `<Suspense fallback={<PageLoader />}>` with an inner component pattern |
| Docker Desktop disk space issues (94% full) | Used `docker system prune` and `docker builder prune` to reclaim space; verified builds via `next build` as fallback |
| SSR/CSR hydration mismatch with dark mode | Added `suppressHydrationWarning` to `<html>` element since theme is read from `localStorage` on client mount |

---

## 10. GitHub Repository

All code has been committed and pushed to the GitHub repository. The commit history reflects the development progression:

- `4769e9c` — Add 7 power features: alerts, export, feedback, LLM generation, comparison, multi-model, dark mode (26 files, +1,302 lines)
- `2ff02de` — Update README with 7 new features (+183 lines)
- `9909c60` — Update CLAUDE.md with Phase 2 features (+47 lines)

---

## 11. Next Steps

- End-to-end testing of all 7 new features in the Docker environment
- Adding unit tests for the new service layer (AlertService, GenerationService, feedback endpoints)
- Exploring integration with additional LLM providers (Anthropic Claude, Google Gemini) for evaluation scoring
- Performance benchmarking under concurrent evaluation load
- Adding WebSocket support for real-time run progress updates (replacing current polling approach)
