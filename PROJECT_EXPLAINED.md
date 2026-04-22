# Project Explained — RAG Eval Harness (Beginner-First)

> Read this top-to-bottom once. By the end you should be able to explain every part of the project to someone else, in your own words. No prior knowledge of "evaluation" is assumed — only that you know what RAG, agents, and chatbots are.

---

## Table of Contents

1. [The big idea in plain English](#1-the-big-idea-in-plain-english)
2. [What is "evaluation" and why does this project exist?](#2-what-is-evaluation-and-why-does-this-project-exist)
3. [The mental model: think of it as an exam system](#3-the-mental-model-think-of-it-as-an-exam-system)
4. [The whole picture in one diagram](#4-the-whole-picture-in-one-diagram)
5. [The 5 main components, explained simply](#5-the-5-main-components-explained-simply)
6. [What is a "test set" and what is a "test case"?](#6-what-is-a-test-set-and-what-is-a-test-case)
7. [What is an "evaluator"? Walk through with examples](#7-what-is-an-evaluator-walk-through-with-examples)
8. [The lifecycle — what happens when you press the button](#8-the-lifecycle--what-happens-when-you-press-the-button)
9. [The 3 ways to trigger an evaluation](#9-the-3-ways-to-trigger-an-evaluation)
10. [What is "the gate" and why it's the most important part](#10-what-is-the-gate-and-why-its-the-most-important-part)
11. [The dashboard — what humans see](#11-the-dashboard--what-humans-see)
12. [A complete walkthrough with a real example](#12-a-complete-walkthrough-with-a-real-example)
13. [Glossary — every term in one line](#13-glossary--every-term-in-one-line)

---

## 1. The big idea in plain English

Imagine you built a chatbot that answers customer questions. It works on Monday. On Tuesday, you tweak the prompt to make it "more polite." Now it sometimes makes up facts that aren't true. **You don't notice for a week.** Customers do.

This project solves that problem. It is a **system that automatically tests your AI every time you change something**, scores it, and stops bad changes from going live.

That's it. That's the whole project.

The fancy name is "an evaluation platform with a CI/CD release gate for LLM applications." But strip away the jargon and you get: **automated quality checking for AI, like unit tests for regular code.**

---

## 2. What is "evaluation" and why does this project exist?

### Why "regular" testing doesn't work for AI

For normal software, you write a unit test:
```python
assert add(2, 3) == 5
```
The test either passes or fails. There's a single right answer.

For AI, the question "what is the capital of France?" has many right answers:
- "Paris"
- "Paris, France"
- "The capital of France is Paris."
- "Paris is the capital."

All correct. None match each other character-for-character. So you can't write `assert chatbot.answer("...") == "Paris"`.

Worse: AI models can produce **plausible-sounding wrong answers**. Ask "who painted the Mona Lisa?" and the model might say "Leonardo da Vinci painted it in 1789." The author is right, the date is wrong by ~280 years. A unit test wouldn't catch that — the answer "looks" correct.

This is called a **hallucination**. AI models hallucinate confidently. You need a different kind of test.

### What "evaluation" actually means

**Evaluation** is the process of scoring an AI's output on different qualities:

- Is the answer **factually correct**? (groundedness)
- Does the answer actually **address the question**? (relevancy)
- For RAG: did we **retrieve the right documents**? (retrieval quality)
- For an agent: did it **call the right tools** in the right order? (trajectory)
- Is the answer **safe** (no PII leak, no toxic content)? (safety)

You score every test case on every quality, and the model gets a "report card" — a set of numbers between 0 and 1 for each metric.

### Why this project exists

Plenty of libraries exist to compute eval metrics (Ragas, DeepEval). But computing a number isn't useful by itself. You need:

1. **A place to store** test sets and historical scores.
2. **A way to trigger** evaluation on every code change.
3. **A way to decide** whether the new score is good enough to ship.
4. **A dashboard** so humans can see what changed.

This project is all four of those things wrapped together.

---

## 3. The mental model: think of it as an exam system

If you forget everything else in this doc, remember this analogy. The project is like a **standardized exam system for AI models**:

| Exam world | This project |
|---|---|
| The exam paper (a fixed set of questions) | A **test set** |
| One question on the exam | A **test case** |
| The student taking the exam | Your AI pipeline (the **adapter**) |
| The teacher who grades the answer | An **evaluator** (e.g., LLM-as-judge, Ragas) |
| The grading rubric | The metric definition (faithfulness, relevancy, etc.) |
| The pass mark (e.g., 60%) | The **threshold** |
| The decision to give the student a diploma | The **gate** (pass / fail / blocked) |
| The grade history of every student over years | The **metrics history** (trends over time) |

When a developer changes the AI pipeline (new prompt, new model, new retrieval index), the project automatically:
1. Hands the AI the same exam (test set).
2. Has multiple teachers grade each answer (evaluators).
3. Checks if the new grade is above the pass mark **and** not significantly worse than last time.
4. Either lets the change ship (gate passes) or blocks it (gate fails).

That's the whole project in one analogy.

---

## 4. The whole picture in one diagram

```
                          ┌──────────────────────────────────┐
                          │     YOUR AI PIPELINE             │
                          │  (RAG, agent, chatbot, search)   │
                          └──────────────┬───────────────────┘
                                         │
                                         │ (1) wrapped in an "adapter"
                                         ▼
   ┌──────────────┐    POST    ┌────────────────────┐    queues    ┌──────────────┐
   │              │ ─────────▶ │                    │ ───────────▶ │              │
   │  CLI         │            │  FastAPI Backend   │              │  Celery      │
   │  (rageval)   │            │  (the API server)  │              │  Worker      │
   │              │            │                    │ ◀─── reads   │  (runs evals)│
   └──────────────┘            └─────────┬──────────┘              └──────┬───────┘
         ▲                               │                                │
         │                               │ stores                         │ writes results
         │                               ▼                                ▼
   ┌──────────────┐              ┌────────────────────────────────────────────┐
   │  GitHub      │              │  PostgreSQL database                       │
   │  Actions     │              │  (test sets, runs, results, metrics)       │
   │  (CI)        │              └────────────────────┬───────────────────────┘
   └──────────────┘                                   │
                                                      │ reads
                                                      ▼
                                         ┌────────────────────────┐
                                         │  Next.js Dashboard     │
                                         │  (humans browse here)  │
                                         └────────────────────────┘

   Redis sits between the backend and the worker as a "message queue" — it's
   how the backend tells the worker "here's a new evaluation to run."
```

Five boxes. That's the whole system.

---

## 5. The 5 main components, explained simply

### Component 1 — The CLI (`runner/cli.py`)

**What it is:** A command-line tool you run in your terminal. Named `rageval`.

**What it does:** Three commands matter:
- `rageval run` — start a new evaluation
- `rageval gate` — check whether the most recent run passed the quality gate (used in CI to block deploys)
- `rageval report` — print a human-readable summary

**Why it exists:** So GitHub Actions can call it from a CI workflow without needing a browser. Same tool you use locally for development.

**Plain-English example:**
```bash
rageval run --config rageval.yaml --test-set <UUID>
# → "Started run abc-123. Polling for results..."
# → "Run completed. Faithfulness: 0.84, Relevancy: 0.79."
```

---

### Component 2 — The FastAPI Backend (`backend/app/`)

**What it is:** A web server (like a typical Flask/Django app) that exposes a REST API on port 8000.

**What it does:** It's the "brain" — it owns the database. Anything that needs to happen — create a test set, trigger a run, look up old results — goes through this API.

**Why it exists:** So the CLI, the dashboard, and any future integration (Slack bot, mobile app) all talk to the same source of truth.

**Key endpoints (URL paths):**
- `POST /api/v1/test-sets` — create a new test set
- `POST /api/v1/runs` — trigger an evaluation
- `GET /api/v1/runs/{id}` — look up the status/results of a run
- `GET /api/v1/metrics/gate/{run_id}` — ask whether the gate passed

---

### Component 3 — The Celery Worker (`backend/app/workers/`)

**What it is:** A background process that does long-running work. Celery is a popular Python library for "I have a task, I don't want to block — go do it in the background."

**What it does:** Runs the actual evaluation. When you trigger a run, the API immediately returns "OK, I queued it" — and the worker picks it up, runs every test case through your AI pipeline, scores each one, and writes the results back to the database.

**Why it exists:** Evaluations can take 5–10 minutes. If the API tried to do it synchronously, the request would time out and CI would think the system hung. Workers solve this.

**Analogy:** The API is like a restaurant waiter who takes your order. The worker is the kitchen that actually cooks. Redis is the spike where orders are stuck.

---

### Component 4 — PostgreSQL + Redis

**PostgreSQL** = the database. Stores everything that needs to last:
- Test sets and test cases
- Every run (its config, status, when it started)
- Every result (per test case, per metric, the actual scores)
- Historical metrics (so you can chart trends over time)

**Redis** = a fast in-memory store with two jobs here:
1. The **message queue** for Celery (the API drops a task in, the worker pulls it out).
2. A **cache** so we don't re-call the LLM if we've already seen the same prompt.

**Why both:** Postgres is durable but slow. Redis is fast but volatile. They complement each other.

---

### Component 5 — The Next.js Dashboard (`frontend/`)

**What it is:** A web app on port 3000. React-based, dark-mode, polls the API every few seconds for live updates.

**What it does:** Lets a human:
- Browse all test sets
- See the latest evaluation runs and their gate status
- Compare 2–4 runs side-by-side (e.g., "GPT-4o vs Claude on the same test set")
- See trends ("Has faithfulness been dropping over the last 30 days?")
- Use the **Playground** to chat live with the demo AI systems

**Why it exists:** The CLI and API are great for automation. But humans want a UI. The dashboard is what you'd show in a demo.

---

## 6. What is a "test set" and what is a "test case"?

This is the part you specifically asked about — what "sets" we use.

### Test case (one row)

A **test case** is a single question + the expected behavior. Stored in the `test_cases` table.

Concrete example:
```json
{
  "query": "What is the capital of France?",
  "expected_output": "Paris",
  "ground_truth": "Paris is the capital of France.",
  "context": ["France is a country in Western Europe. Its capital is Paris."],
  "failure_rules": [
    { "type": "must_not_contain", "value": "London" },
    { "type": "must_contain", "value": "Paris" }
  ],
  "tags": ["geography", "easy"]
}
```

Fields explained:
- **query** — the user's question (input to your AI).
- **expected_output** — the short ideal answer (used by some evaluators for similarity).
- **ground_truth** — the longer reference answer (used by Ragas).
- **context** — the documents your retriever should ideally find (used to score retrieval).
- **failure_rules** — hard rules that automatically fail the case (more on this below).
- **tags** — labels for filtering ("only run easy questions").

### Test set (a collection of test cases)

A **test set** is just a named collection of test cases — like a chapter in a textbook. Stored in the `test_sets` table.

Each test set has:
- A **name** (e.g., "Demo RAG Pipeline")
- A **system_type** (one of 9: `rag`, `agent`, `chatbot`, `search`, `code_gen`, `classification`, `summarization`, `translation`, `custom`)
- A **version number** that auto-increments every time you add or change a test case (so you can compare runs against the same exact test set)
- All the test cases that belong to it

### What test sets ship with the project (the "demo data")

The seed script creates **4 test sets**, one for each of the 4 demo AI systems. Each has 8 test cases:

| Test set | What it tests | Example test case |
|---|---|---|
| **Demo RAG Pipeline** | A RAG system with ~30 knowledge chunks | "What is photosynthesis?" expects an answer grounded in retrieved biology chunks |
| **Demo Tool Agent** | An OpenAI function-calling agent with 3 tools (calculator, weather, unit converter) | "What's 17 × 23?" expects the agent to call the `calculator` tool |
| **Demo Chatbot** | A TechStore customer support bot | "How do I return a laptop?" expects a polite, accurate return policy answer |
| **Demo Search Engine** | A semantic search over 15 dev docs | "How do I deploy a Docker container?" expects Docker-related docs ranked first |

You create your own test sets either by importing JSON, adding cases through the UI one-by-one, or using the **"Generate Cases"** button which calls GPT-4o to invent realistic test cases on a topic.

---

## 7. What is an "evaluator"? Walk through with examples

An **evaluator** is a piece of code that takes the AI's output for a test case and produces one or more scores between 0 and 1 (where 1 = perfect, 0 = terrible).

The project has ~19 evaluators in [runner/evaluators/](runner/evaluators/). You don't need to know all of them. Here are the 5 most important ones with concrete examples.

### Evaluator 1 — Ragas (the metrics library)

**What it does:** Computes 4 famous RAG metrics using an LLM under the hood.

| Metric | Question it answers |
|---|---|
| **Faithfulness** | Is every claim in the answer supported by the retrieved context? (catches hallucination) |
| **Answer relevancy** | Does the answer actually address the question that was asked? |
| **Context precision** | Of the chunks I retrieved, what fraction are actually relevant? |
| **Context recall** | Of all the relevant chunks in the corpus, what fraction did I retrieve? |

**Example:**
- Query: "Who painted the Mona Lisa?"
- Retrieved context: "The Mona Lisa was painted by Leonardo da Vinci between 1503 and 1519."
- AI answer: "Leonardo da Vinci painted the Mona Lisa in 1789."
- **Faithfulness score: ~0.5** — half the claims (the painter) are supported, half (the date) are not.

### Evaluator 2 — LLM-as-judge

**What it does:** Sends the question, the AI's answer, and a grading prompt to GPT-4o (or another LLM) and asks it to score the answer on a 1–5 scale.

**Example prompt to the judge:**
> You are a strict grader. Given a question and an answer, score the answer from 1–5 on factual correctness. Question: "..."  Answer: "..."  Score:

**Why use it:** Catches semantic problems that simple metrics miss. An answer can have high cosine similarity to the reference but still be wrong.

**Cleverness:** The project uses **self-consistency** — it asks the judge 3 times and takes the median. This reduces flakiness because LLMs are non-deterministic.

### Evaluator 3 — Rule evaluator (the "tripwire" evaluator)

**What it does:** Checks hard rules defined per test case. No LLM involved. Pure if/else.

Supported rules:
- `must_contain` / `must_not_contain` — the answer must (or must not) include some text
- `must_call_tool` / `must_not_call_tool` — the agent must (or must not) call a named tool
- `regex_must_match` — output matches a regex
- `must_refuse` — for safety questions, the AI must include a refusal phrase like "I can't help with that"
- `max_hallucination_risk` — faithfulness score must be ≥ a threshold

**Why it matters:** Some failures are non-negotiable. If a customer support bot leaks an internal password, you don't want a graceful degradation — you want a hard fail. Rules give you that.

### Evaluator 4 — Citation evaluator

**What it does:** Takes the AI's answer, splits it into individual atomic claims (one fact per sentence), and checks each claim against the retrieved context.

**Example:**
- Answer: "Paris is the capital of France. It has 2.1 million people. The Eiffel Tower was built in 1889."
- Decomposed claims:
  1. "Paris is the capital of France." — supported ✓
  2. "Paris has 2.1 million people." — supported ✓
  3. "The Eiffel Tower was built in 1889." — not in retrieved context ✗
- Citation score: **2/3 = 0.67**

This is stricter than Ragas faithfulness because it doesn't let multiple claims hide behind a single overall judgment.

### Evaluator 5 — Trajectory evaluator (for agents)

**What it does:** When an agent uses tools (e.g., calculator, weather), this evaluator checks **which tools it called and in what order**.

**Example:**
- Query: "What's the weather in Paris in Fahrenheit?"
- Expected tool sequence: `[get_weather(city="Paris"), unit_converter(value=..., to="F")]`
- Actual tool sequence: `[get_weather(city="Paris")]` — agent forgot to convert
- Trajectory score: ~0.5 (got 1 of 2 tools right, in the right order)

It uses Levenshtein distance (string edit distance) on the tool call sequence to score similarity.

### The other 14 evaluators

Briefly, so you know they exist:
- **G-Eval** — LLM-as-judge but with auto-generated rubric and forced reasoning steps
- **Pairwise** — A vs. B preference judging (used for "is the new prompt better than the old one?")
- **Robustness** — checks if the AI gives consistent answers when you paraphrase the question or add typos
- **Calibration** — measures whether the AI's confidence matches its actual accuracy
- **Safety** — checks for PII leaks, toxic content, jailbreaks (uses regex + Llama Guard if installed)
- **Multi-turn agent** — evaluates conversations across multiple turns
- **Code evaluator** — runs generated code, checks syntax, runs tests
- **Ranking evaluator** — for search systems: NDCG, MRR, MAP, precision@k
- **Similarity** — ROUGE-L, BLEU, cosine similarity (for summarization, translation)
- **Classification** — accuracy, F1, confusion matrix (for classification systems)
- **Conversation, agent, translation** evaluators — system-type-specific wrappers

---

## 8. The lifecycle — what happens when you press the button

This is the most important section to internalize. **Memorize these 7 steps.**

When somebody runs `rageval run` (or clicks "Run Evaluation" in the dashboard, or pushes a commit that triggers CI), here's exactly what happens:

### Step 1 — Trigger
The CLI sends `POST /api/v1/runs` to the FastAPI backend with:
- The test set ID
- The pipeline config (which adapter to use, what model, what settings)
- Git metadata (commit SHA, branch, PR number) — so we can link the run to the code change later

### Step 2 — Run row created
The backend immediately:
- Creates a new row in the `evaluation_runs` table with status `PENDING`
- **Snapshots the current thresholds** onto the run row (an immutable JSON column called `gate_threshold_snapshot`). This is critical — it means "the gate for this run is judged against the thresholds that existed at this exact moment, not whatever the thresholds are when somebody looks at the result later."

### Step 3 — Task queued
The backend calls `apply_async()` to push a task into the Redis queue, then returns `202 Accepted` to the CLI immediately with the run ID.

### Step 4 — Worker picks it up
A Celery worker (running in the background) sees the new task and starts processing:
- Looks up the `pipeline_config` from the database
- Calls `importlib.import_module(...)` to dynamically load the adapter class — e.g., `runner.adapters.demo_rag.DemoRAGAdapter`
- Calls `adapter.setup()` to do any one-time work (load embeddings, init OpenAI client)

### Step 5 — Per-case evaluation loop
For each test case in the test set:
1. The worker calls `adapter.run(query, context)` — this is where YOUR AI pipeline actually runs and produces an output (`PipelineOutput` object: answer + retrieved_contexts + tool_calls + turn_history).
2. The worker passes this output to every configured evaluator (Ragas, LLM-judge, rules, etc.).
3. Each evaluator returns a `MetricScores` object — a dict of metric name → float.
4. The worker writes one row to the `evaluation_results` table for this test case (with all the scores) and one row to `metrics_history` (so we can chart trends).

### Step 6 — Gate evaluation
After all test cases are scored, the worker calls the **release gate service**:
- Pulls all per-case raw scores
- For each metric: computes a 95% bootstrap confidence interval and compares it to the threshold (from the snapshot)
- For each metric: runs a Mann-Whitney U statistical test against the last passing run as a baseline
- Decides per-metric: pass / fail
- Combines: gate passes only if **every metric passes AND every rule passes**

### Step 7 — Status flip + notifications
- Run status changes to `COMPLETED` (gate passed), `GATE_BLOCKED` (gate failed but eval succeeded), or `FAILED` (eval crashed).
- If a Slack/webhook URL is configured, an alert fires.
- The dashboard, which is polling, picks up the new status on its next refresh.
- The CLI (or CI), which has been polling `GET /runs/{id}/status`, sees the result and exits with appropriate code.

That's the whole flow. **7 steps: trigger → row → queue → load adapter → score each case → evaluate gate → flip status.**

---

## 9. The 3 ways to trigger an evaluation

The same evaluation engine can be triggered three ways. Same code path internally — different entry points.

### Trigger 1 — GitHub Actions (the primary path)

File: `.github/workflows/evaluate.yml`

When someone pushes a commit or opens a PR:
1. GitHub spins up a Linux container, starts Postgres + Redis as services.
2. Installs Python deps, runs database migrations.
3. Starts the FastAPI backend and a Celery worker in the background.
4. Runs `python -m runner.cli run --config rageval.yaml --commit-sha <sha> --branch <name> --pr-number <n>`.
5. Runs `python -m runner.cli gate --fail-on-regression`. **If the gate failed, this command exits with code 1, which makes the whole CI job fail, which blocks the PR from being merged.**
6. Runs `python -m runner.cli report --format json --output eval-report.json` and uploads it as a CI artifact (90-day retention).
7. Posts a comment on the PR with a Markdown table showing all metric scores and any regressions.

A second workflow (`release-gate.yml`) queries `GET /runs?git_commit_sha=<sha>` and sets a GitHub commit status check — that's literally what controls whether the "Merge pull request" button on GitHub is enabled.

### Trigger 2 — The CLI (manual, for development)

When you're iterating locally on a new prompt or model:
```bash
python -m runner.cli run --config rageval.yaml --test-set <UUID> --timeout 300
```

This hits a backend running in your local Docker Compose, polls until done, prints a console report. Useful for "did my change improve things or break them?" before you push.

### Trigger 3 — The Dashboard (ad-hoc, for humans)

Two buttons in the dashboard:
- **"Run Evaluation"** on the test set page — fires `POST /runs` with default config.
- **"Compare Models"** — opens a modal where you choose 2–6 different configs (e.g., GPT-4o vs Claude vs Llama). Hits `POST /runs/multi`, which creates N parallel runs. After they finish, the UI takes you to a side-by-side comparison view.

Useful for non-engineers (PMs, researchers) who want to evaluate without touching the terminal.

---

## 10. What is "the gate" and why it's the most important part

The **gate** is the decision: "based on this run's scores, should we let this code change ship to production?"

Without a gate, you have a dashboard with pretty numbers and no consequences. The gate is what turns evaluation from "interesting data" into "actionable enforcement."

### How a naive gate would work (and why it's broken)

The obvious approach:
```python
if faithfulness_score < 0.7:
    fail()
```

This is broken in two ways:

**Problem 1 — Sample noise.** With only 50 test cases, scores naturally wiggle by ±3 percentage points run-to-run, even if nothing changed. So a gate at 0.70 will trip whenever a run randomly scores 0.69. You'd get false alarms daily, and developers would learn to ignore the gate.

**Problem 2 — Hidden regressions.** If the threshold is 0.70 and you regress from 0.85 to 0.75, the gate doesn't fire — even though that's a real 10-point drop. The threshold approach can't see "worse than usual but still above the line."

### How this project's gate works

Two statistical tests, both must pass.

**Test 1 — Bootstrap confidence interval vs threshold.**
- Take the per-case scores for the current run.
- Resample them with replacement 1000 times to compute a 95% confidence interval.
- The gate fails only if the **lower bound** of the CI is below the threshold.
- This means "we are 95% confident the true score is at or above the threshold." Random noise no longer trips the gate.

**Test 2 — Mann-Whitney U vs baseline.**
- Compare the current run's per-case scores to the last passing run's per-case scores.
- Run a Mann-Whitney U test (a non-parametric stats test for "do these two samples come from the same distribution?").
- The gate fails on the baseline comparison only if **p < 0.05** — meaning "this difference is unlikely to be random noise."
- Real regressions get caught even if they're still above the absolute threshold.

**Combined logic:** Gate passes iff (every metric's CI lower bound ≥ threshold) AND (no metric is significantly worse than baseline) AND (every failure rule passed).

### Why this matters for the project's credibility

This is the part interviewers will probe hardest. The naive threshold approach is what every other tool does. The statistical approach is what makes this project not a toy.

The implementation lives in two parallel files (`runner/gate/stats.py` and `backend/app/services/_gate_stats.py`) — kept in sync by a parity test. Why duplicate? Because the runner needs to compute the gate offline in CI without making an HTTP round-trip to the backend.

---

## 11. The dashboard — what humans see

The dashboard (Next.js, port 3000) has these pages. Skim once so you can describe them.

| Page | What's on it |
|---|---|
| `/dashboard` | 4 stat cards (Total Runs in 24h, Gate Pass Rate, Active Blocks, Test Sets) + a table of the 10 most recent runs. Polls every 10 seconds. |
| `/systems` | Health view of all 9 system types. Each shows a colored status badge (Healthy / Degraded / Failing) and key metrics. |
| `/playground` | **Live demo!** Tabbed interface to chat with all 4 demo AI systems (RAG, agent, chatbot, search). Lets you see them respond in real-time. Has thumbs-up/thumbs-down feedback buttons. |
| `/test-sets` | Grid of all test sets. Each card shows the system type, case count, and last run status. |
| `/test-sets/[id]` | List of test cases for one test set. Three big buttons: **Generate Cases** (LLM auto-creates new test cases), **Compare Models** (multi-run with different configs), **Run Evaluation** (single run). |
| `/runs` | All evaluation runs as a table. Checkbox selection (max 4) + a floating "Compare N Runs" button. |
| `/runs/[id]` | One run's detail view. Shows metric gauges, regression diff vs baseline, per-case results, **Export CSV/JSON** buttons. Auto-refreshes while running. |
| `/runs/compare` | Side-by-side comparison of 2–4 runs. Best metric values highlighted in green. |
| `/metrics` | Recharts line charts of every metric over time. Threshold shown as a horizontal reference line. 7/30/90 day selector. |
| `/production` | Production traffic logs (queries from real users), sampling stats, user feedback aggregates (thumbs up/down counts). |

Dark mode toggle is in the sidebar footer. All pages have `dark:` variants.

---

## 12. A complete walkthrough with a real example

Let's trace one specific scenario end-to-end. Use this as a story you can tell.

### The scenario

You're a developer on a customer support team. The chatbot is in production. You want to upgrade the underlying model from GPT-3.5 to GPT-4o-mini because it's cheaper at similar quality.

### What happens

1. **You open a PR** changing `model: gpt-3.5-turbo` to `model: gpt-4o-mini` in `rageval.yaml`.

2. **GitHub Actions fires.** The workflow `evaluate.yml` runs. It spins up Postgres + Redis + the FastAPI server + a Celery worker.

3. **CI calls the CLI.** `python -m runner.cli run --config rageval.yaml --commit-sha <your-commit> --branch <your-branch> --pr-number 42`.

4. **Backend creates a run.** Status = `PENDING`. Snapshots the current thresholds (e.g., faithfulness ≥ 0.70).

5. **Worker picks up the task.** Loads the `DemoChatbotAdapter` class via `importlib`. Calls `setup()` (initializes OpenAI client with the new model).

6. **For each of 8 test cases:**
   - Worker calls `adapter.run("How do I return a laptop?", ...)` → adapter sends the prompt to GPT-4o-mini → returns `PipelineOutput(answer="...", retrieved_contexts=[...])`.
   - Ragas scores it: `faithfulness=0.82, answer_relevancy=0.79, context_precision=0.75, context_recall=0.68`.
   - LLM-judge scores it: `judge_score=0.85`.
   - Rule evaluator: checks `must_not_contain: "credit card number"` → passes.
   - Worker writes a row to `evaluation_results` and `metrics_history`.

7. **All 8 cases done.** Worker calls release gate service:
   - Faithfulness: 95% bootstrap CI = [0.74, 0.88], lower bound 0.74 ≥ threshold 0.70 ✓
   - Mann-Whitney U vs last passing run: p = 0.42 (no significant change) ✓
   - All rules passed ✓
   - **Gate passes.** Run status = `COMPLETED`.

8. **Slack alert fires** (if configured): "Run abc-123 completed. Gate passed. View: https://..."

9. **CI calls `rageval gate --fail-on-regression`.** The command queries `GET /metrics/gate/<run-id>`, sees `overall_passed=true`, exits with code 0.

10. **GitHub Actions posts a PR comment:**
    ```
    ✅ Evaluation passed
    Run: abc-123
    Faithfulness: 0.82 (CI [0.74, 0.88])
    Relevancy:    0.79 (CI [0.71, 0.85])
    8/8 cases passed all rules.
    ```

11. **Release-gate workflow** sets a green commit status check on the PR.

12. **You merge the PR.** GPT-4o-mini ships to production.

### Now imagine the same scenario goes wrong

GPT-4o-mini has worse retrieval grounding for your domain. Faithfulness drops to 0.62.

- Step 7 changes: bootstrap CI = [0.55, 0.69], lower bound 0.55 < threshold 0.70 ✗
- Mann-Whitney U vs baseline: p = 0.003 (significant regression) ✗
- **Gate fails.** Run status = `GATE_BLOCKED`.
- Step 9: `rageval gate` sees `overall_passed=false`, exits with code 1.
- GitHub Actions job fails, PR comment shows red ❌, commit status check is red, **Merge button is disabled.**
- You roll back the model change without ever shipping the regression.

That's the entire value proposition of the project, in one example.

---

## 13. Glossary — every term in one line

Read once. Refer back as needed.

| Term | One-line definition |
|---|---|
| **Adapter** | A Python class that wraps your AI pipeline so the eval system can call it (`setup`, `run`, `teardown`). |
| **Answer relevancy** | Does the answer address the question that was asked? |
| **Bootstrap CI** | Resample the data 1000× with replacement to estimate a confidence interval. Distribution-free. |
| **Calibration** | Does the AI's confidence match its actual accuracy? Measured by ECE (Expected Calibration Error). |
| **Celery** | A Python library for async background tasks. Used here to run evaluations off the API request thread. |
| **Confidence interval (CI)** | A range that contains the true value with some probability (e.g., 95%). |
| **Context precision** | Of the chunks I retrieved, what fraction are actually relevant? |
| **Context recall** | Of all relevant chunks in the corpus, what fraction did I retrieve? |
| **ECE** | Expected Calibration Error. The gap between predicted confidence and actual accuracy. |
| **Evaluator** | Code that scores an AI's output on one or more metrics. |
| **Faithfulness** | Is every claim in the answer supported by the retrieved context? (Catches hallucination.) |
| **Failure rule** | A hard if/else check that auto-fails a test case (e.g., "must not contain `password`"). |
| **Gate** | The pass/fail decision: "should this run be allowed to ship?" |
| **G-Eval** | LLM-as-judge with auto-generated rubric + forced chain-of-thought + bounded score scale. |
| **Hallucination** | The AI confidently states something that isn't true or isn't in its context. |
| **LLM-as-judge** | Using a powerful LLM (e.g., GPT-4o) to grade the output of another LLM. |
| **MAP** | Mean Average Precision. A search-quality metric. |
| **Manifest** | A snapshot of every version, prompt hash, and seed used in a run. Hashes to a fingerprint. |
| **Mann-Whitney U** | A non-parametric statistical test for "do these two samples come from the same distribution?" |
| **MRR** | Mean Reciprocal Rank. 1/(rank of first relevant result), averaged. |
| **NDCG** | Normalized Discounted Cumulative Gain. Rewards putting relevant search results higher. |
| **Pairwise judging** | LLM picks A vs. B instead of scoring each separately. Run with position swap to cancel position bias. |
| **PipelineOutput** | The standard object an adapter returns: `answer`, `retrieved_contexts`, `tool_calls`, `turn_history`, `metadata`. |
| **Position bias** | LLM judges have a ~5–10% preference for whichever answer comes first in a pairwise comparison. |
| **Postgres / PostgreSQL** | The relational database. Source of truth for test sets, runs, results. |
| **Ragas** | A popular open-source library for RAG metrics. Used internally as one evaluator among many. |
| **Redis** | An in-memory store. Used here as Celery's message queue and as a prompt cache. |
| **Run** | One execution of a test set. Has a status (`PENDING` / `RUNNING` / `COMPLETED` / `GATE_BLOCKED` / `FAILED`). |
| **Self-consistency** | Run the LLM judge k times, take the median. Reduces flakiness. |
| **System type** | The category of AI being evaluated (rag / agent / chatbot / search / etc.). 9 types supported. |
| **Test case** | One question + expected behavior. |
| **Test set** | A collection of test cases. Has a name, a system type, and a version number. |
| **Threshold** | The minimum acceptable score for a metric (e.g., faithfulness ≥ 0.7). |
| **Threshold snapshot** | The thresholds copied onto the run row at run creation, so the gate is always evaluated against config-at-the-time. |
| **Trajectory** | The sequence of tool calls an agent made. Scored against the expected sequence using Levenshtein distance. |
| **Verbosity bias** | LLM judges tend to prefer longer answers. Mitigate by hinting against it in the judge prompt. |

---

## What you should be able to do after reading this

- Explain in 60 seconds what the project does and why it exists.
- Sketch the 5-component architecture diagram from memory.
- Describe what's in a test case and what's in a test set.
- Name 5 evaluators and what each one measures.
- Walk through the 7-step lifecycle of an evaluation run.
- Describe the 3 ways to trigger an evaluation.
- Explain why a naive threshold gate is broken and how the statistical gate fixes it.
- Tell the GPT-3.5 → GPT-4o-mini story end-to-end.

If any of those feel shaky, re-read that section. Once they all feel solid, you're ready for the interview.
