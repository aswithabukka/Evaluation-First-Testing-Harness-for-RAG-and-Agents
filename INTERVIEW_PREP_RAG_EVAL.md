# Interview Prep — RAG Eval Harness

> A self-teaching guide to my RAG evaluation project, written to help me explain it clearly in an interview. Every section has a "what it is", a "why I built it", and a "how I'd explain it in 30 seconds."

---

## How to use this document

Read it end-to-end once to rebuild the mental model. Before an interview, skim:

- §1 (elevator pitches) — warm up your voice.
- §6 (why X, not Y) — the decision section interviewers probe hardest.
- §7 (expected questions) — rehearse the ones that scare you.
- §10 (glossary) — fill in any term you've forgotten.

Every concept has a plain-English explanation **before** the technical one, because in interviews you'll be asked "explain this to a non-specialist" at least once.

---

## Table of Contents

1. [Elevator Pitches (30s / 2min / 5min)](#1-elevator-pitches)
2. [Why I Built This](#2-why-i-built-this)
3. [Architecture Tour](#3-architecture-tour)
4. [Component Deep-Dives](#4-component-deep-dives)
5. [Life of an Evaluation Run](#5-life-of-an-evaluation-run)
6. [Why X, Not Y — Design Decisions](#6-why-x-not-y--design-decisions)
7. [Expected Interview Questions (with Framework Answers)](#7-expected-interview-questions)
8. [Honest Weaknesses](#8-honest-weaknesses)
9. [Demo Script (3 minutes)](#9-demo-script)
10. [Glossary of Concepts](#10-glossary-of-concepts)

---

## 1. Elevator Pitches

### The 30-second version

> LLM applications fail silently. A prompt change can quietly drop answer faithfulness by 20 percentage points and nobody finds out until users complain. I built an evaluation-first CI/CD platform that scores every pipeline change on 13 different metrics — including LLM-as-judge, tool-call accuracy, and calibration — and blocks deploys when the regression is **statistically significant** vs. the last passing run, not when the absolute number crosses a threshold. Full stack: FastAPI + Celery + PostgreSQL + Next.js. 65 unit tests. Runs open-source judges like Qwen 3.6 and Kimi K2.6 through OpenRouter for 1/10th the cost of GPT-4o.

### The 2-minute version

Here's what's broken about LLM app development today. When you change a prompt, a retrieval index, or a model, you don't know if quality got better or worse until your users tell you. Teams either don't evaluate at all, or they run notebooks manually and eyeball Streamlit dashboards. That doesn't scale and it doesn't gate deploys.

I built a platform that treats evaluation like any other CI check. You point it at your pipeline, you define a test set, and every PR automatically runs the full evaluation, scores each case on 13 metrics, and blocks the release if quality regresses.

The hard parts were statistical: a naive threshold gate trips constantly on sample noise (a 50-case eval has ±3pp wiggle) and misses real regressions hidden in the noise floor. I use bootstrap confidence intervals to compare the CI-lower-bound to the threshold, and a Mann-Whitney U test to compare the current run to the last passing baseline. The gate only fails when the drop is statistically significant at p<0.05.

Beyond that, everything is built for reproducibility and cost control. Every run produces a manifest pinning evaluator versions, prompt hashes, library versions, and seeds — two runs with the same fingerprint should give the same gate decision. A per-run cost and time budget trips cleanly with a `partial` status instead of crashing. And the LLM-judge layer is provider-agnostic: adding `OPENROUTER_API_KEY` auto-routes every evaluator to models like Qwen 3.6 Plus or Kimi K2.6, which are 10-20× cheaper than GPT-4o.

I wrote 65 unit tests covering the statistical helpers, the evaluators, and the parity contract between the backend and runner copies of the gate logic.

### The 5-minute version

*(For "tell me about a project" prompts. Pace yourself — 10-12 sentences spoken per minute.)*

I'll start with the problem. LLM applications are unique because they can fail in ways traditional software can't. A conventional service either returns the right response or it doesn't. An LLM service can return a plausible, confident answer that's factually wrong, and no unit test will catch that. Teams at Anthropic, OpenAI, and every large RAG shop have discovered this the hard way: a prompt change or a retrieval re-index can silently introduce hallucinations that only surface in production.

The industry response has been a wave of evaluation libraries — Ragas, DeepEval, LlamaIndex eval, Langfuse, LangSmith, Weights & Biases. These give you metrics but they don't give you CI/CD. You still have to know when to look, what counts as a regression, and how to gate a deploy on the answer. That's the gap I wanted to fill.

I built an evaluation-first testing harness that treats LLM quality like a first-class engineering concern. You write your pipeline as an adapter — a class with `setup()`, `run()`, and `teardown()` methods. You define a test set of questions with ground truth, expected tool calls, failure rules. You configure thresholds. From then on, every commit triggers a GitHub Action that calls the backend API, spawns a Celery worker, runs all test cases through your adapter, scores every case on the relevant metrics, computes a statistically significant gate decision, and either passes or blocks the PR.

The three parts I'm proudest of are the **significance-aware gate**, the **reproducibility manifest**, and the **provider-agnostic judge layer**.

The significance gate solves a real problem. Before, our gate compared the mean metric to a threshold. That's fragile because on a 50-case eval there's natural noise of ±3pp. The gate trips constantly on meaningless wiggle, and worse, a real 4pp regression gets lost in that noise. I switched to a bootstrap confidence interval on the current run — if the CI lower bound is below threshold, the gate fails — plus a Mann-Whitney U test against the last passing baseline. Real regressions always fail the gate. Noise never does. The false positive rate dropped from "trips daily" to "almost never."

The reproducibility manifest is audit infrastructure. It captures every piece of context needed to explain a gate decision: the version of every evaluator, the hash of every prompt, the version of every judge library, every seed I used, and the git commit. The whole thing gets hashed into a 16-character fingerprint. Two runs with the same fingerprint should produce the same gate decision, up to LLM non-determinism. When a developer says "I think the gate is flaky," I can pull both manifests and show them exactly what changed — usually it's a new Ragas version that silently changed the prompts.

The provider layer is the part that matters most for cost. All LLM-based evaluators go through a shared `LLMClient` with retries, backoff, prompt caching, and cost tracking. Setting `OPENROUTER_API_KEY` in the env auto-routes every judge call through OpenRouter to models like Qwen 3.6 Plus or Kimi K2.6, which cost $0.33/$1.95 per million tokens versus $2.50/$10 for GPT-4o. A full 200-case eval with Qwen 3.6 costs about 33 cents instead of $10. Same JSON interface, same unit tests pass, same gate decisions within noise.

The stack is FastAPI for the API layer with async SQLAlchemy over asyncpg, Celery with Redis for async evaluation workers, PostgreSQL 15 with JSONB for flexible metric storage, Next.js 14 with Tailwind and Recharts for the dashboard, and GitHub Actions for CI. 65 unit tests, TypeScript clean, Docker Compose for local dev. On the deployment side I've got a per-run cost + time budget that caps runaway judges and a flakiness detector that reruns the top-N failing cases and flags high-variance ones so they're excluded from gate decisions.

If I had three more months I'd add load testing under 10k cases, cross-run manifest diffing in the UI, and a judge-calibration scheduled job that runs weekly and alerts when any judge drifts more than 0.1 Spearman vs. human labels.

---

## 2. Why I Built This

### The problem in one sentence

LLM applications fail silently, and almost no team gates deploys on evaluation quality the way they gate on passing unit tests.

### What failure looks like in practice

Three concrete ways LLM apps fail silently that this project would catch:

**1. Prompt regression from a "harmless" tweak.** An engineer adds a new instruction to the system prompt to fix one edge case. Faithfulness drops 15 percentage points on unrelated cases because the new instruction is making the model hedge more. Nobody notices for two weeks because the engineer only tested the edge case.

**2. Retrieval silently breaking.** Someone reindexes the corpus with a new embedding model. Context precision drops from 0.8 to 0.5 but the answers still look plausible. Only a statistically significant comparison against the last run catches it.

**3. Judge drift after a model upgrade.** You were judging with GPT-4o. OpenAI ships a new version that interprets your criteria more strictly. Your scores drop uniformly by 8 points and you conclude your pipeline regressed. It didn't — the judge did. My calibration harness catches this by periodically comparing the judge's scores against a human-labeled gold file.

### Why "eval libraries" aren't enough

Ragas, DeepEval, G-Eval, and LLM-as-judge patterns give you *metrics*. They don't give you:

- A gate that blocks a merge
- A way to tell noise from real regression
- A manifest that makes a decision reproducible
- A cost budget so a runaway judge doesn't burn $200
- A UI with per-case drilldown
- A CI integration that posts back to the PR

All of that is infrastructure around the metrics. That's what I built.

### Who would use this

- An ML team shipping a RAG product who wants eval in CI like they have pytest in CI
- A platform team running multiple LLM features that need one evaluation layer, not five
- Anyone running production LLM traffic who wants sampled eval on real queries, not just synthetic ones

---

## 3. Architecture Tour

### The 5-layer stack

```
┌──────────────────────────────────────────────────────────────┐
│  Layer 1: CLI + GitHub Actions                               │
│  rageval run → HTTP POST to backend                          │
│  rageval gate → blocks merge if quality regressed            │
│  rageval calibrate → judge drift detection                   │
└──────────────────────────────────────────────────────────────┘
                        ↓  HTTP (httpx)
┌──────────────────────────────────────────────────────────────┐
│  Layer 2: FastAPI Backend (async)                            │
│  /api/v1/runs — create run, read status, gate decision       │
│  /api/v1/test-sets — CRUD + LLM-powered test generation      │
│  /api/v1/results — per-case scores, CSV/JSON export          │
└──────────────────────────────────────────────────────────────┘
                        ↓  apply_async() → Redis queue
┌──────────────────────────────────────────────────────────────┐
│  Layer 3: Celery Worker (sync, psycopg2)                     │
│  • Loads pipeline adapter dynamically via importlib          │
│  • Per-case loop: pipeline.run() → evaluators → DB insert    │
│  • Budget.check() before each case; exits partial on breach  │
│  • Seals reproducibility Manifest before writing final row   │
└──────────────────────────────────────────────────────────────┘
                    ↓ reads/writes          ↓ queue/cache
┌─────────────────────────────────┐   ┌───────────────────────┐
│  Layer 4a: PostgreSQL 15        │   │  Layer 4b: Redis 7    │
│  JSONB-heavy schema:            │   │  DB 1: Celery broker  │
│  • test_sets, test_cases        │   │  DB 2: Celery results │
│  • evaluation_runs              │   │                       │
│    - gate_threshold_snapshot    │   └───────────────────────┘
│    - manifest (NEW)             │
│    - budget_summary (NEW)       │
│  • evaluation_results           │
│  • metrics_history (append-only)│
│  • production_logs              │
└─────────────────────────────────┘
                        ↑
                        │  polls via SWR every 8-10s
┌──────────────────────────────────────────────────────────────┐
│  Layer 5: Next.js 14 Dashboard                               │
│  /dashboard — run counts, pass rates                         │
│  /runs/[id] — ** GateDecisionPanel + ManifestPanel **        │
│  /metrics — trend charts with threshold overlays             │
│  /production — real-traffic sampling + feedback              │
│  /playground — interactive chat with 4 demo systems          │
└──────────────────────────────────────────────────────────────┘
```

### Why these layers, not fewer or more

**Why separate CLI from API?** So CI scripts can live in any language; the CLI is just an HTTP client.

**Why Celery, not FastAPI's `BackgroundTasks`?** Evaluations take minutes. A background task tied to the HTTP request dies if the API restarts. Celery has durable queues, retries, and separate scaling.

**Why PostgreSQL and not a time-series DB like InfluxDB?** Our queries are relational ("all results for run X where metric > threshold"), not time-series-shaped. JSONB gives us schema flexibility for per-system metrics without migrations. The `metrics_history` table is append-only and indexed for trend queries — effectively a TSDB view over a relational DB.

**Why two Redis databases?** Celery separates broker (task queue, DB 1) from result backend (task status cache, DB 2) so they can be tuned separately. Flushing DB 2 doesn't lose queued work.

**Why split `runner/` and `backend/` as separate deployables?** The CLI can run without the API stack (e.g. local eval before pushing). The backend doesn't depend on evaluator code except through the worker's `runner/` bind mount.

---

## 4. Component Deep-Dives

### 4.1 The Evaluator Family (19 evaluators)

**The problem they solve:** Different AI system types (RAG, agents, chatbots, search, classification) need different metrics. A one-size-fits-all "accuracy" number is useless.

**My approach:** One `BaseEvaluator` contract returning `MetricScores`, with 13 concrete implementations grouped by what they evaluate.

#### The RAG family
- **`RagasEvaluator`** — the classic four: faithfulness, answer relevancy, context precision, context recall. Uses an LLM judge under the hood (routed through OpenRouter when configured).
- **`CitationEvaluator`** — claim-level. Decomposes the answer into atomic claims, checks each against retrieved contexts. Stricter than faithfulness because it attributes support at the claim level.

#### The LLM-judge family
- **`LLMJudgeEvaluator`** — general-purpose. Now with self-consistency (k-sample median) and None-on-error semantics.
- **`GEvalEvaluator`** — implements G-Eval (Liu et al., EMNLP 2023): auto-generates a rubric, then forces chain-of-thought scoring.
- **`PairwiseEvaluator`** — A/B comparison with position swap to cancel position bias. For multi-model comparisons.

#### The agent family
- **`AgentEvaluator`** — tool call F1, goal accuracy, step efficiency.
- **`TrajectoryEvaluator`** — order-aware. Normalised Levenshtein distance on tool sequences plus JSON-schema validation of arguments.

#### The classification family
- **`ClassificationEvaluator`** — accuracy, F1 (macro/micro/weighted), Cohen's kappa, AUC-ROC, PR-AUC, **confusion matrix**, and **Matthews correlation coefficient** (MCC is the best single scalar for imbalanced datasets).

#### The safety + robustness family
- **`SafetyEvaluator`** — three layers: regex PII, optional Presidio (ML-based PII), optional Llama Guard (toxicity + jailbreak). Falls back cleanly when a layer isn't installed.
- **`RobustnessEvaluator`** — paraphrase consistency + adversarial perturbation using char-n-gram Jaccard similarity.

#### The meta-evaluators
- **`CalibrationEvaluator`** — Expected Calibration Error (ECE). Batch-level, not per-case.
- **`RuleEvaluator`** — deterministic rules from the test case JSONB (must_contain, must_call_tool, must_refuse, etc.). 16 rule types.
- **`RankingEvaluator`** — NDCG, MAP, MRR, precision@k, recall@k for search.

#### The "how I'd explain in 30 seconds"

> "Thirteen evaluators grouped by what they measure. RAG uses Ragas and claim-level citation. Agents get tool-sequence edit distance. Classification reports MCC and a confusion matrix. Safety is layered regex → Presidio → Llama Guard so you can enable whatever you've installed. Every evaluator returns a typed `MetricScores` object with cost, latency, and error metadata so the run manifest has enough info to reproduce the decision."

---

### 4.2 The Significance-Aware Release Gate

**The problem it solves:** A naive gate is either too strict (trips on noise) or too loose (misses regressions).

#### What a naive gate does

```python
if run.mean_faithfulness < 0.70:
    block_deploy()
```

On a 50-case eval with standard deviation 5pp, this gate has a ~15% false positive rate on runs that are statistically indistinguishable from passing runs.

#### What my gate does

```python
# 1. Compute 95% bootstrap CI on the current run's per-case scores
point, ci_lower, ci_upper = bootstrap_ci(current_scores)

# 2. If there's a baseline, run Mann-Whitney U vs. it
if baseline_scores:
    _, p_value = mann_whitney_u(current_scores, baseline_scores)
    if current_mean < baseline_mean and p_value < 0.05:
        return "block: significant regression"

# 3. Otherwise compare the CI lower bound to the threshold
if ci_lower < threshold:
    return "block: CI lower bound below threshold"

return "pass"
```

#### What these concepts mean — plain English

**Bootstrap CI:** I have 50 scores from this run. I don't know what the "true" mean would be if I had infinite cases. But I can estimate it by resampling. I draw 50 scores with replacement from my 50 scores, take the mean, repeat 2000 times. That gives me 2000 plausible means. The 2.5th and 97.5th percentiles of that distribution are my 95% confidence interval on the true mean.

**Why CI lower bound, not the point estimate?** If my mean is 0.72 and my threshold is 0.70, am I actually above the threshold? Only if the CI is `[0.71, 0.74]`. If it's `[0.65, 0.79]`, my mean might be 0.72 by luck — the true mean could be 0.65. Using the lower bound forces the sample size to be large enough to be confident.

**Mann-Whitney U:** A non-parametric test of "are these two samples from the same distribution, or is one shifted?" Rank all observations across both samples, sum the ranks for each sample, and compare. Doesn't assume normality — important because metric scores are often bounded in [0,1] and bimodal.

**Why p<0.05?** Convention. Means "if the current run were truly no different from the baseline, we'd see a difference this extreme only 5% of the time by chance." We accept a 5% false-positive rate because the cost of a false positive (a blocked deploy) is small compared to the cost of a false negative (shipping a regression).

#### The 30-second explanation

> "A naive threshold gate trips on sample noise — my 50-case evals have a natural ±3pp wiggle, so a real 4pp regression gets lost and a 3pp lucky draw trips the gate. I use the lower bound of a 95% bootstrap CI vs. the threshold, plus a Mann-Whitney U test vs. the last passing run. The gate only fails when the regression is statistically significant at p<0.05. False positive rate is now near zero."

---

### 4.3 The Shared `LLMClient`

**The problem it solves:** Without this, every LLM-based evaluator would reimplement retries, cost tracking, and caching — and get it wrong slightly differently each time.

**What it provides:**
- `chat_json()` — a single deterministic JSON call.
- Automatic retries with exponential backoff + jitter on rate limit / timeout / 5xx.
- Cost tracking via a `MODEL_PRICES` table.
- Prompt-hash caching: identical (model, system, user, params) calls return cached results.
- Concurrency limit via a `threading.Semaphore`.
- **Provider routing**: auto-detects OpenRouter when the model ID has a `provider/model` slug format OR when `OPENROUTER_API_KEY` is set without `OPENAI_API_KEY`.
- Errors returned as `LLMError` instead of raising — callers map to `EvalError` on the MetricScores.

**Why caching matters:** When we run the same test case through three evaluators that use the same underlying Ragas prompts, we pay OpenRouter once. Across a 50-case run this often saves 30-40% of tokens.

**Why retries matter:** OpenRouter sporadically returns 429s during peak hours. Without retries, a single rate limit would null out an entire metric for the whole run.

#### The 30-second explanation

> "A provider-agnostic wrapper over the OpenAI SDK. Every LLM-based evaluator uses it, so they all get retries, prompt caching, cost tracking, and OpenRouter routing for free. Adding `OPENROUTER_API_KEY` to `.env` auto-switches every judge from GPT-4o to Qwen 3.6 or whatever I set — 10× cheaper, same interface."

---

### 4.4 The Reproducibility Manifest

**The problem it solves:** When someone asks "why did this run's gate decision differ from yesterday's?", the answer is usually one of: evaluator version change, judge model change, library upgrade, seed change, or a prompt tweak. Without a manifest, you can't tell.

**What it captures:**
```
{
  "evaluators": [
    {"name": "ragas", "version": "2", "class": "RagasEvaluator"},
    {"name": "RuleEvaluator", "version": "unknown", ...}
  ],
  "prompts": {
    "<sha16>": {"model": "qwen/qwen3.6-plus", "params": {...}, "system_sha": "...", "user_sha": "..."}
  },
  "libraries": {
    "ragas": "0.2.6",
    "openai": "1.58.0",
    "datasets": "3.1.0",
    ...
  },
  "seeds": {"gate_bootstrap": 42, "llm_judge_base": 0},
  "env": {"python": "3.11.14", "platform": "Linux-..."},
  "commit_sha": "abc1234..."
}
```

**The fingerprint:** a 16-character SHA256 of the manifest (excluding `sealed_at`). Two runs with the same fingerprint should produce the same gate decision up to LLM non-determinism.

#### The 30-second explanation

> "Every run writes a manifest pinning evaluator versions, prompt hashes, library versions, and seeds. Two runs with the same fingerprint produce the same gate decision. When someone says 'the gate is flaky,' I pull both manifests and show them exactly what changed — usually a Ragas upgrade that silently rewrote the prompts."

---

### 4.5 The Cost + Time Budget

**The problem it solves:** A misconfigured self-consistency parameter (say, `samples=10` instead of `3`) can 4× your judge cost silently. An infinite retry loop on a 429 can hit the OpenRouter rate limit for hours. Without a hard ceiling, one bad run can burn the monthly eval budget.

**What it does:**
- `Budget(max_usd=5.00, max_seconds=600)` created from `pipeline_config.budget` at run start.
- The worker calls `budget.check()` before each test case. If either ceiling is breached, the loop exits cleanly.
- The run is marked `partial_run: True` in `summary_metrics` with `cases_evaluated` and `cases_total`. You keep what you got.

**Why exit-and-save instead of raise?** A partial run's data is still useful — you want to see what you got before the budget blew. Raising would roll back the DB insert and lose that data.

#### The 30-second explanation

> "Per-run cost and time ceilings. Breach marks the run `partial` with whatever cases got evaluated, instead of failing outright. A misconfigured self-consistency won't burn the monthly budget."

---

### 4.6 Registry-Driven Evaluator Dispatch

**The problem it solves:** Before this, adding a new evaluator meant editing the Celery worker, adding an `elif system_type == ...` branch, and shipping a new image. That's a PR per evaluator.

**What it does:** `EVALUATOR_REGISTRY` in `runner/evaluators/__init__.py` maps names to classes. Adding a name to the `metrics:` list in `rageval.yaml` turns that evaluator on. Per-evaluator config lives under `pipeline_config.evaluators.<name>`. No code changes, no image rebuild.

```yaml
metrics:
  - faithfulness
  - g_eval          # ← new — just added this
  - citation
  - trajectory

pipeline_config:
  evaluators:
    g_eval:
      aspect: coherence
      description: "Is the response logically consistent?"
      samples: 3
```

**Why a registry, not a plugin system?** Plugin systems require entry points, setup.py, dynamic imports from user code. Overkill for a project where "new evaluator" happens once a month. A dict is 10 lines.

#### The 30-second explanation

> "New evaluators activate from config, not code. There's a registry — name-to-class dict — and the worker dispatches against it. Adding `g_eval` to the metrics list in YAML turns it on, no image rebuild."

---

### 4.7 Flakiness Detection

**The problem it solves:** LLM judges are stochastic even at `temperature=0`. A case that fails once might pass the next time. Treating flaky cases as gate-blocking regressions is wrong; they're real quality signal but not gate-able.

**What it does:** `detect_flaky(cases, score_fn, k=3, variance_threshold=0.05)` reruns the top-N failing cases k times. Cases with variance above threshold are flagged flaky and excluded from gate decisions (but still reported on the dashboard so developers can investigate).

#### The 30-second explanation

> "Reruns the top-N failing cases three times. If the variance across runs is above 0.05, I mark the case flaky and exclude it from gate decisions. Still reports it in the dashboard so you know, but doesn't let noise block a deploy."

---

### 4.8 Judge Calibration Harness

**The problem it solves:** Judges drift. A model update, a prompt rewrite, a Ragas upgrade — any of these can move judge scores relative to ground truth without anyone noticing.

**What it does:** A JSONL file of human-labeled examples: `{"query": "...", "answer": "...", "human_score": 0.8}`. `rageval calibrate --gold gold.jsonl --min-spearman 0.7` runs the judge against every example and computes Spearman + Kendall correlation against the human scores. CI fails if correlation drops below threshold.

#### Why Spearman AND Kendall?

- **Spearman** — ranks the scores, measures linear correlation on ranks. Good at "is the judge monotonically agreeing with humans?"
- **Kendall tau** — counts concordant vs discordant pairs. More robust on small samples (~20-50 gold examples) because it's less sensitive to outliers.

#### The 30-second explanation

> "A small JSONL file of human-labeled examples. I run my judge against them weekly and compute Spearman + Kendall vs. the humans. Drops below 0.7 means the judge drifted — could be a new Ragas version, could be OpenRouter changed model weights. CI fails so we investigate before trusting the judge on real evals."

---

### 4.9 Backend: FastAPI + Celery + PostgreSQL

**FastAPI** for the API because async + type hints + auto-generated OpenAPI + Pydantic validation all come in one package.

**Celery** for workers because:
- Evaluations take 1-10 minutes; you can't tie that to an HTTP request.
- Durable queue: if the API crashes mid-run, the worker still has the task.
- Separate scaling: API is small and fast; worker is CPU-heavy.

**PostgreSQL 15 with JSONB** for storage because:
- Test sets and results have heterogeneous shapes (different metrics per system type). JSONB gives schema flexibility without a migration per new metric.
- Queries are relational ("all results for run X where faithfulness < 0.5") — not time-series-shaped.
- `metrics_history` is append-only and GIN-indexed for trend queries. Effectively a TSDB view over a relational DB.

#### Key DB design decisions

**Immutable threshold snapshot.** When a run is created, the current thresholds are copied onto the run row. Later edits to global thresholds don't retroactively change a past run's gate decision. Important for audit trails — "why did run X pass?" must always have the same answer.

**Manifest as JSONB on the run row.** Not a separate `manifests` table because there's a 1:1 relationship and we never query across manifests independently.

**Per-case rows vs. aggregated-only.** We store every per-case score. That's what makes the bootstrap CI possible — you can't bootstrap from aggregated means.

---

### 4.10 Frontend: Next.js 14 + Tailwind + Recharts

The UI has two jobs: show the decision and show the reasoning. Every page polls via SWR so running evals update live without page reloads.

**Key new components (mine):**

- **`GateDecisionPanel`** — per-metric failure cards with visual CI bars (a 0..1 bar with a threshold marker, CI range shaded, point estimate as a vertical tick). Shows p-value, sample size, baseline run link.
- **`ManifestPanel`** — evaluator chips (`ragas@2`), library version chips, prompt count, seeds, budget progress bars with red/green coloring, fingerprint, "View raw JSON" toggle.

These are the two components that make the project look production-grade rather than a demo. Interviewers will probably screenshot them on the live call.

---

## 5. Life of an Evaluation Run

*This section traces what happens end-to-end when you click "Run Evaluation." It's the best teaching device I have — it shows how every component fits together.*

**Setup:** You've defined a test set with 8 cases, configured `metrics: [faithfulness, g_eval, rule_evaluation]`, and set `pipeline_config.budget = {max_usd: 1.0, max_seconds: 300}`.

### Step 1 — Trigger

You click "Run Evaluation" in the UI, which POSTs to `/api/v1/runs`:
```json
{
  "test_set_id": "...",
  "metrics": ["faithfulness", "g_eval", "rule_evaluation"],
  "triggered_by": "manual",
  "pipeline_config": {...}
}
```

### Step 2 — API creates the run row

FastAPI's `EvaluationService`:
1. Reads global thresholds.
2. **Snapshots them onto the run row** — immutable audit trail.
3. Inserts an `EvaluationRun` row with `status=PENDING`.
4. Dispatches `run_evaluation(run_id, metrics)` to Celery via `apply_async()`.
5. Returns 202 with the run ID.

The frontend starts polling `/api/v1/runs/{id}/status` every 8 seconds via SWR.

### Step 3 — Celery worker picks up the task

The worker dequeues from Redis, connects to Postgres via synchronous `psycopg2`, and reads the run row.

### Step 4 — Adapter boots

`_load_adapter(pipeline_config)` uses `importlib.import_module` to dynamically load the adapter class (e.g. `DemoRAGAdapter`). Calls `.setup()` once. This is where embeddings get loaded, indexes get opened, API clients get initialized.

### Step 5 — Budget + Manifest initialize

```python
budget = Budget(max_usd=1.0, max_seconds=300)
manifest = Manifest()
manifest.record_seed("gate_bootstrap", 42)
```

### Step 6 — Per-case loop begins

For each test case:

**6a. Budget check.** `budget.check()` — if over, break out of loop with `budget_exceeded=True`.

**6b. Call the pipeline.** `output = pipeline.run(tc.query, tc.context)`. Returns `PipelineOutput(answer, retrieved_contexts, tool_calls)`. If the pipeline raises, fall back to ground truth as the answer and record a `failure_reason`.

**6c. System-type evaluation.** For RAG, call `_run_ragas()` — which uses `_build_ragas_llm()` to route through OpenRouter if configured. Ragas computes faithfulness, answer_relevancy, context_precision, context_recall. Null results stay null (not 0.0).

**6d. Registry dispatch.** `run_registry_evaluators()` iterates through the `metrics` list. For each name in `EVALUATOR_REGISTRY`, instantiate the evaluator with config from `pipeline_config.evaluators.<name>`, run `evaluate_batch([case])`, merge the resulting scores. Each evaluator's `cost_usd` is recorded on the Budget.

**6e. Rule evaluation.** `RuleEvaluator.evaluate_single(query, output, tool_calls, failure_rules)`. For this case's `must_contain`, `must_call_tool`, `max_hallucination_risk` rules, return `(passed: bool, details: list)`.

**6f. Composite pass/fail.** Combine all metrics into a composite average. Compare to `COMPOSITE_THRESHOLD = 0.5`. Any rule failure forces `passed = False`.

**6g. Write the EvaluationResult row.**

### Step 7 — Post-loop: batch-level evaluators

If `calibration` is in the metrics list, `extract_calibration_batch(results)` collects `(confidence, correct)` pairs across all cases. `CalibrationEvaluator.evaluate_batch(batch)` computes ECE, max calibration gap, overconfidence rate. Broadcast those scalar scores into every case's metadata.

### Step 8 — Summary aggregation

Compute mean of each metric across cases. If budget was exceeded, set `partial_run: True`, `cases_evaluated: 5`, `cases_total: 8`, and the reason.

### Step 9 — Gate decision

The worker doesn't compute the gate here — it's computed on-read by `ReleaseGateService.evaluate_gate(run_id)` whenever the UI or CLI asks for it. This is so that changing the gate algorithm doesn't require rerunning old runs. The gate pulls per-case raw scores from `evaluation_results`, finds the last passing baseline run, runs `significance_gate()` for each metric, and returns a decision with CI bounds and p-values.

### Step 10 — Manifest sealed and persisted

```python
manifest.seal(commit_sha=run.git_commit_sha)
run.manifest = manifest.to_dict()
run.manifest_fingerprint = manifest.fingerprint()
run.budget_summary = budget.summary()
```

Status flips to `COMPLETED` or `GATE_BLOCKED`.

### Step 11 — MetricsHistory inserts

For every `avg_<metric>` key in the summary, append a row to `metrics_history` for trend queries.

### Step 12 — Alerts

`AlertService.check_and_alert()` fires if the gate was breached and a webhook is configured. Separately, `send_completion_alert()` fires for all runs (or failures only) depending on `ALERT_ON_SUCCESS` env var.

### Step 13 — Frontend picks up the status change

The UI's SWR poll sees `status=gate_blocked`, stops polling, fetches full run data + the gate decision. Renders `GateDecisionPanel` (CI bars, reasoning) and `ManifestPanel` (evaluator chips, budget bars).

### Step 14 — CI integration

In CI, `rageval gate --fail-on-regression` exits non-zero. The GitHub Action posts a PR comment with the metrics table and regression reasons.

### Step 15 — You look at it

You see a `BLOCKED` badge, a CI bar showing the faithfulness CI lower bound below threshold, a p-value of 0.02 vs. baseline, and a specific reason: "faithfulness dropped from 0.85 to 0.71, p=0.02 vs. run c196c36d." You know exactly what changed.

---

## 6. Why X, Not Y — Design Decisions

*The most interview-relevant section. For each, I have a 30-second answer ready.*

### 6.1 Mann-Whitney U, not t-test

**Chose:** Mann-Whitney U (non-parametric rank-sum test).
**Rejected:** Student's t-test.
**Why:** Metric scores are often bounded in [0, 1], frequently bimodal (a judge either agrees or doesn't), and the sample size is small (10-50 cases). T-test assumes normality; we don't have it. Mann-Whitney makes no distributional assumption — just ranks. For rank-distribution shifts the non-parametric test is strictly safer.

### 6.2 Bootstrap CI, not analytical CI

**Chose:** Percentile bootstrap (2000 resamples).
**Rejected:** Analytical CI from t-distribution.
**Why:** Analytical CI assumes normality of the mean's sampling distribution, which is asymptotically valid but fails badly with n=10-20. Bootstrap is distribution-free and just resamples from the observed data. Percentile method (vs BCa) because it's simpler to audit and the bias correction matters less at 2000 iterations.

### 6.3 CI lower bound vs. point estimate for gating

**Chose:** Compare CI lower bound to threshold (higher_is_better case).
**Rejected:** Compare point estimate to threshold.
**Why:** Point estimate treats "mean = 0.71 with CI [0.65, 0.77]" and "mean = 0.71 with CI [0.70, 0.72]" the same. They're not the same. If my threshold is 0.70, I need evidence I'm above it, not just a hopeful point. Using the CI lower bound forces the sample size to be large enough to be confident.

### 6.4 Median self-consistency, not single call

**Chose:** Run the judge k times (k=3 default) and take the median.
**Rejected:** Single call with `temperature=0`.
**Why:** Even at temp=0, LLMs are stochastic under the hood (non-deterministic kernel order, prompt caching, hardware variance). Self-consistency reduces variance at the cost of 3× tokens. Median over mean because outliers from a bad parse shouldn't skew the score. Variance across samples is reported on the MetricScores so flaky cases can be flagged.

### 6.5 Generic `scores` dict, not typed columns

**Chose:** `MetricScores(scores: dict[str, float | None], ...)`.
**Rejected:** A typed column per metric name (faithfulness, answer_relevancy, etc.).
**Why:** New metrics are added all the time (registry dispatch makes this trivial). A typed column per metric requires a migration for every new metric. The dict is schema-flexible and stores efficiently in JSONB. We keep the legacy Ragas fields as typed columns for backward compatibility with existing dashboards.

### 6.6 `None`-on-error, not `0.0`-on-error

**Chose:** Judge failure → `None` score + `EvalError`.
**Rejected:** Judge failure → `0.0`.
**Why:** Returning 0.0 for a judge timeout makes the gate trip on infrastructure problems rather than quality problems. A `None` with an explicit error lets the gate skip the row (and report the error) instead of treating it as a regression. This is the single most impactful design decision I made.

### 6.7 Immutable threshold snapshot per run

**Chose:** Copy thresholds onto the run row at creation time.
**Rejected:** Read thresholds live at gate-decision time.
**Why:** Audit trail. "Why did run X pass yesterday but would fail today with the same data?" should not be a valid question. Someone changing a threshold should not retroactively change past gate decisions. The snapshot is in JSONB, so old decisions are always reproducible.

### 6.8 Celery, not FastAPI `BackgroundTasks`

**Chose:** Celery + Redis broker.
**Rejected:** Native async background tasks.
**Why:** Evaluations take 1-10 minutes. If I use FastAPI's in-process background tasks, a restart loses in-flight work. Celery has durable queues, retries, and scales separately. The cost is a slightly heavier stack — I think that's worth it for production reliability.

### 6.9 PostgreSQL + JSONB, not a TSDB

**Chose:** Postgres 15 with JSONB columns.
**Rejected:** InfluxDB / TimescaleDB.
**Why:** My dominant queries are relational (joins between runs, test sets, results), not time-series. JSONB gives schema flexibility for per-metric fields. The `metrics_history` table is append-only with a GIN index on `(test_set_id, metric_name, recorded_at)` — effectively a time-series view over a relational DB, which is good enough at my scale.

### 6.10 OpenRouter auto-detection, not explicit config

**Chose:** `LLMClient` detects OpenRouter from the model ID (slug format) OR env var presence.
**Rejected:** Require `provider=openrouter` in every config.
**Why:** Reduces friction for the common case — I want a user to be able to set `OPENROUTER_API_KEY` and have it Just Work. Explicit config is still supported as an override. Auto-detection is safe because the slug format (`provider/model`) is a clear signal.

### 6.11 Backend + runner parity copies of gate stats

**Chose:** Two copies of `bootstrap_ci`, `mann_whitney_u`, `significance_gate` — one in `runner/gate/stats.py`, one in `backend/app/services/_gate_stats.py`. Parity pinned by a test.
**Rejected:** A shared library imported by both.
**Why:** The runner and backend are separate deployables. A shared library means either (a) the runner depends on the backend image, which breaks the CLI use case, or (b) we publish a third Python package, which is overkill. Two copies with a parity test is strictly simpler for a small amount of math.

### 6.12 Registry dispatch, not if/else chain

**Chose:** `EVALUATOR_REGISTRY: dict[str, type]` with dispatch at runtime.
**Rejected:** A hardcoded `if metric == "g_eval": ...` chain.
**Why:** The if/else chain required a code edit + image rebuild for every new evaluator. Registry is 10 lines and makes new evaluators activatable from config alone. Plugin systems with entry points would be overkill at this scale.

### 6.13 Pairwise with position swap, not single-pass

**Chose:** Every pairwise comparison runs twice with swapped positions.
**Rejected:** A single A/B call.
**Why:** LLM judges have well-documented position bias — they systematically prefer whichever response appears first. Running with both positions averages out the bias. Cost is 2× but the signal quality improvement is substantial.

### 6.14 ECE, not Brier score

**Chose:** Expected Calibration Error.
**Rejected:** Brier score, log-loss.
**Why:** ECE is easy to explain to a non-statistician ("when you say 90% confident, are you right 90% of the time?"), and the per-bin breakdown is a UI-friendly visualization. Brier and log-loss are strictly proper scoring rules but harder to act on. Can add them later if needed.

### 6.15 Qwen 3.6 Plus as default judge, not GPT-4o

**Chose:** `qwen/qwen3.6-plus` via OpenRouter — 1M context, $0.33/$1.95 per 1M tokens.
**Rejected:** `gpt-4o` — $2.50/$10 per 1M tokens.
**Why:** For the judge workload — structured JSON output, consistent scoring criteria — the open-source flagships are within 3-5% of GPT-4o on human-agreement benchmarks, at 1/8th the cost. On a 200-case eval that's $0.33 vs. $10. I keep GPT-5.4 / Claude Sonnet 4.6 available as calibration baselines for periodic drift checks.

---

## 7. Expected Interview Questions

*For each question: a **3-5 sentence framework answer**, a **likely follow-up**, and a **red flag to avoid**.*

### 7.1 Architecture questions

#### "Walk me through the architecture."

> Five layers: CLI is a thin HTTP client driving CI. FastAPI API accepts run requests and snapshots immutable thresholds. Celery workers run the per-case loop with pluggable adapters, evaluators via a registry, a cost budget, and a reproducibility manifest. PostgreSQL stores runs with JSONB manifests and a per-case results table that's the source of truth for statistical gating. Next.js dashboard polls via SWR and renders CI bars + manifest chips on the run detail page.

**Follow-up:** "Where's the state of the system?"
> Postgres. Redis is ephemeral — just Celery's broker and result cache. If I lose Redis I lose in-flight tasks but not completed runs. If I lose Postgres I lose the system.

**Red flag:** Don't say "there's nothing stateful." Interviewers probe.

#### "What's the failure domain of each layer?"

> API can crash — new requests fail, completed runs are fine. Worker can crash — in-flight task retries via Celery's at-least-once semantics. DB is the single critical point. Redis broker loss retries the task from the queue. Redis result-backend loss means the API can't see task progress until the next DB poll.

#### "How would you scale this to 100k cases/day?"

> Bottleneck is the Celery workers plus the OpenRouter rate limit. I'd shard test sets across a worker pool sized by target throughput. Prompt-hash caching already deduplicates identical judge calls. For the DB, `metrics_history` is append-only and partitionable by month. For the frontend, SWR polling would need to downgrade to WebSocket pushes at that scale.

### 7.2 Statistics questions

#### "Explain Mann-Whitney U to a non-statistician."

> It's a test for whether two samples come from the same distribution or one is shifted higher. You pool all observations, rank them from smallest to largest, and sum the ranks for each sample. If the sums are similar, the distributions overlap. If one sum is much larger, that sample tends to have higher values. The p-value is the probability of seeing that big a difference by chance if the distributions were truly identical.

**Follow-up:** "Why not use t-test?"
> T-test assumes normality, which breaks when scores are bounded in [0,1] or bimodal. Mann-Whitney makes no distributional assumption — it only uses ranks. Safer default for metric scores.

#### "What does bootstrap sampling actually do?"

> I have 20 scores. I don't know what the true mean would be with infinite data. So I pretend my 20 scores are the whole population — I draw 20 with replacement, take the mean, repeat 2000 times. That gives me 2000 plausible "true means." The 2.5th and 97.5th percentiles of those means bound my 95% CI. Distribution-free; no normality assumption.

**Follow-up:** "Why percentile bootstrap and not BCa (bias-corrected accelerated)?"
> Simpler to audit in a code review. BCa's bias correction matters more at low iteration counts, and I do 2000 iterations. For gate decisions that need to be reproducible, simpler is better.

#### "Explain ECE."

> Expected Calibration Error. Take all predictions and bucket them by confidence — 0-0.1, 0.1-0.2, etc. For each bucket, compute the mean confidence and the actual accuracy. The gap between them is the miscalibration. ECE is the size-weighted average of these gaps. If ECE = 0.15, your model is on average 15 percentage points off — e.g. claiming 90% confidence but being right 75% of the time.

#### "Why p < 0.05 specifically?"

> Convention — not a law of nature. It means "if the runs were truly identical, we'd see this big a difference by chance only 5% of the time." We accept a 5% false positive rate because blocked deploys are cheap to unblock, and shipping a regression is expensive. For a much higher-stakes gate I'd tighten to 0.01.

### 7.3 LLM-as-judge questions

#### "Why would I trust an LLM judge at all?"

> I wouldn't — blindly. That's why I built a calibration harness. It runs the judge against a human-labeled gold file and computes Spearman + Kendall correlation. If correlation drops below 0.7, CI fails and we investigate before relying on the judge. Also, self-consistency — taking the median of 3 judge calls reduces variance. And position-swap for pairwise judging cancels the known position bias.

**Follow-up:** "How do you handle position bias?"
> For pairwise judging, every comparison runs twice with A and B positions swapped. If the judge flips its preference under swap, it's a tie. The score is the average across both positions.

#### "What happens if the judge model updates overnight?"

> Calibration harness catches it. Scores drift uniformly — faithfulness on the gold set drops from 0.85 to 0.78. Spearman vs. humans stays the same (since it's rank-based) but mean absolute error jumps. That's a signal the judge changed its scale without changing its rank ordering. The fix is to re-anchor thresholds or pin the model version in `LLM_DEFAULT_MODEL`.

#### "How do you detect verbosity bias?"

> My judge prompt explicitly says "do not reward verbosity." It's a mitigating heuristic, not a solution. A better approach is to run two variants of the judge — one prompt that asks to reward length, one that asks to penalize — and compare. If both give the same answer, length wasn't driving the score. I haven't implemented that yet; it's on the roadmap.

### 7.4 Trade-off questions

#### "Why not just use Langfuse or Weights & Biases?"

> Both are great for logging and observability. Neither gives me a CI gate with a statistical-significance test. Langfuse's scoring is flat — threshold vs. point estimate. W&B's evaluation suite doesn't integrate with GitHub Actions out of the box for PR comments. I built this because I wanted one system that spans PR gating + dashboard + production traffic monitoring, which is currently stitched together from 3-4 vendors.

#### "Why build this instead of contributing to Ragas or DeepEval?"

> Ragas is an evaluation library — computes metrics. My project is evaluation *infrastructure* — pipelines, storage, gating, dashboards. Different layer. I use Ragas as a dependency inside `RagasEvaluator`. If the Ragas maintainers wanted CI integration they'd accept a PR; if I wanted to open-source my gate logic I'd propose it upstream. Right now it's in my project because the piece I'm unique about is the gate, not the metrics.

#### "Why not a single monolith?"

> The runner is intentionally separable because people run `rageval` locally before pushing. If it depended on the backend image, you'd need Docker just to smoke-test an eval. The separation costs me one duplicated stats helper (backend/_gate_stats.py mirrors runner/gate/stats.py) — pinned by a parity test — and that's worth it.

### 7.5 Production-concerns questions

#### "What's your observability story?"

> Thin today. Structured logs in the worker, run-level cost and latency captured in `budget_summary`, and error types captured in `EvalError`. If I were shipping this at a real company, I'd add OpenTelemetry traces around every judge call and emit them to Langfuse or Phoenix for per-case drilldown. I'd also add Prometheus metrics on queue depth and gate pass rate.

#### "How do you prevent a runaway cost?"

> Three layers. Per-run `Budget` with hard `max_usd` and `max_seconds` ceilings — run exits cleanly on breach. Prompt-hash caching deduplicates identical judge calls within a run. OpenRouter's per-key spending limit is the backstop — a runaway loop can't spend more than the key's cap. I'd add alerting on the gate pass-rate metric itself so if 10 runs in a row budget-out, an oncall gets paged.

#### "How do you handle secrets?"

> Environment variables sourced from `.env` in local dev, from Kubernetes secrets in a real deployment. Compose substitutes `${OPENROUTER_API_KEY}` at container creation. Never commit `.env` — it's in `.gitignore`. API keys never appear in logs because I classify errors to extract status codes and scrub raw responses.

### 7.6 Failure-mode questions

#### "What breaks first under load?"

> OpenRouter rate limits. A 50-case eval with self-consistency=3 makes ~600 LLM calls across 4 metrics. At concurrency=8 that's saturating OpenRouter for a small tier. The `LLMClient` has exponential backoff + jitter + `max_retries=4`, but if rate limits persist, budget-time triggers and the run goes partial. I'd shard across multiple OpenRouter keys if I scaled up.

#### "What happens if the judge API returns garbage JSON?"

> `json.JSONDecodeError` inside `LLMClient._call_openai` becomes `LLMError(type='parse_error', retryable=False)`. The evaluator maps that to `MetricScores(error=EvalError(...))`, score stays `None`. The gate correctly skips the row instead of treating it as 0.0. That's one of my most-used test cases — the "don't let infrastructure errors trip the gate" behavior.

#### "What happens on a prompt-injection inside a test case?"

> The test case's `query` field goes through the pipeline as normal input. If the pipeline gets jailbroken and the answer contains an injected instruction, the judge's system prompt is independent of the pipeline's context — the judge can't be coerced by a string in the pipeline output (in most cases). If I were paranoid I'd add a `PromptInjectionDetector` evaluator that flags cases with known injection patterns and surfaces them on the dashboard.

### 7.7 Behavioral questions

#### "What was the hardest bug you hit?"

> Ragas was silently hitting `api.openai.com` even after I configured OpenRouter. My hardened `RagasEvaluator` class routed correctly, but the Celery worker had its own `_run_ragas()` helper that bypassed the class entirely — directly called `ragas.evaluate()` with no `llm=` kwarg. Symptom: 401 errors in the logs but the run "completed" with all scores null. Fix: patched `_run_ragas()` to call `_build_ragas_llm()` and pass `llm=` when an OpenRouter LLM is returned. Lesson: when you write an abstraction, grep for every caller — don't assume your abstraction is the only path in.

#### "What's the biggest trade-off you made?"

> Duplicating the gate-stats helpers. I wanted the backend and runner to be independently deployable. Splitting them means two copies of ~80 lines of statistical code. I chose the duplication and pinned parity with a test. The alternative was packaging a third library, which was overkill for three functions.

#### "What would you change with three more months?"

> Three things. One: a live deployment on Fly.io so recruiters can click around. Two: cross-run manifest diffing in the UI — "why did this run's gate decision differ from that run's?" — because the manifest data is there but not surfaced. Three: a load-test benchmark with 10k cases so I can claim throughput numbers in the README instead of hand-waving about scale.

#### "How did you prioritize what to build first?"

> I started with the evaluators because they're the concrete thing. Then the gate logic because a gate without significance is worse than no gate (false-positive trips). Then the manifest because otherwise my own teammates couldn't reproduce decisions. Then the frontend because an unseen metric is a dead metric. OpenRouter routing and registry dispatch came last because they're optimizations — they don't change correctness, only cost and ergonomics.

---

## 8. Honest Weaknesses

*Pre-empt these so the interviewer can't use them against me.*

**1. Not deployed publicly.** All my demos are localhost. That's a real gap — a live URL would add credibility. I'd deploy to Fly.io + Neon + Upstash for ~$10/month if asked.

**2. Limited real-world usage data.** The tests pass, the architecture is sound, but I haven't run this against 10k real production queries. My confidence in the gate is based on statistical theory, not empirical false-positive rates at scale.

**3. Some LLM evaluators are integration-verified but not benchmarked.** GEval, Pairwise, Citation all have unit tests that verify the wiring. I haven't run a head-to-head benchmark showing GEval agreement with humans is within 5% of GPT-4o judging.

**4. No load-test results to cite.** I don't have "we ran 1000 cases in 12 minutes" numbers.

**5. Pairwise evaluator is scaffolded, not proven.** Position-swap is implemented but I haven't used it to drive a real multi-model A/B comparison yet. It's wired for the workflow, not battle-tested.

**6. Frontend is functional but not a design showcase.** Tailwind defaults, Recharts, dark mode. It works but isn't portfolio-level pretty.

**7. "Built by one person in a month" — double-edged.** At this scope, an interviewer may reasonably suspect heavy AI pairing. Own it. Point to specific decisions I can defend without notes.

---

## 9. Demo Script (3 minutes)

*If they say "show me the project live," do this.*

**[0:00]** "Let me open the dashboard." → http://localhost:3000/dashboard.
**[0:15]** "These are recent runs, each with a status and pass rate. Let me click into one that's blocked."
**[0:30]** → http://localhost:3000/runs/e6e5d0dc-... "This is the run detail page. Two things I want you to see: the gate decision panel on the left, and the reproducibility manifest on the right."
**[0:45]** "The gate panel shows a specific metric failure — faithfulness point estimate 0.000, threshold 0.700. The 95% bootstrap CI is [0.000, 0.000] which means I'm very confident this is below threshold, not just lucky low. Sample size 5, which is why I have a CI bound at all."
**[1:15]** "The manifest on the right: fingerprint, evaluator chips showing I ran Ragas v2 and RuleEvaluator, the library versions frozen at run time, and the budget — see how the time exceeded the 300-second ceiling in red."
**[1:45]** "When someone says the gate is flaky, this manifest is the first thing I pull. Two runs with the same fingerprint should produce the same decision."
**[2:00]** → http://localhost:3000/metrics "Trends page shows each metric over time with the threshold overlay. You can see the regression vs. the baseline."
**[2:30]** "In CI, there's a rageval gate command that exits non-zero on a blocked gate and posts the same reasoning as a PR comment. That's how I block deploys on regressions automatically."
**[2:50]** "Happy to dig into any piece — the statistical code, the worker dispatch, the evaluator you're curious about."

---

## 10. Glossary of Concepts

*Alphabetized. Each entry is 2-4 sentences. Use as quick reference.*

**Adapter pattern** — A class with `setup/run/teardown` methods that wraps an arbitrary pipeline so the evaluation harness can call it uniformly. You implement the adapter; the harness calls it.

**AUC-ROC** — Area Under the Receiver Operating Characteristic curve. Measures binary classifier quality across all thresholds. 0.5 = random; 1.0 = perfect; <0.5 = anti-predictive.

**Bootstrap sampling** — A resampling technique. Given n observations, draw n with replacement from those n, compute a statistic, repeat many times. The distribution of statistics estimates the sampling distribution — no normality assumption needed.

**Cohen's kappa** — Inter-rater agreement corrected for chance. 0 = chance agreement; 1 = perfect; <0 = worse than random.

**Confidence interval (CI)** — A range of plausible values for a parameter. A 95% CI means "if we repeated the experiment many times and computed a CI each time, 95% of those intervals would contain the true value."

**Context precision** (Ragas) — Of the retrieved contexts, what fraction are actually relevant to answering the question?

**Context recall** (Ragas) — Of the information needed to answer the question, what fraction is present in retrieved contexts?

**ECE (Expected Calibration Error)** — Bucket predictions by confidence; within each bucket, compute the gap between mean confidence and actual accuracy; weight by bucket size. Measures how honest the model's confidence is.

**Faithfulness** (Ragas) — Of the claims in the answer, what fraction are supported by the retrieved contexts? Measures hallucination (inverse of it).

**G-Eval** — An LLM-as-judge pattern from Liu et al. (EMNLP 2023). Auto-generate a rubric from an aspect description, then force chain-of-thought scoring against that rubric.

**JSONB** — PostgreSQL's binary JSON column type. Supports GIN indexes for fast lookup, schema flexibility without migrations.

**Levenshtein distance** — Minimum number of single-element edits (insert/delete/substitute) to transform one sequence into another.

**Mann-Whitney U test** — Non-parametric test for whether two samples come from the same distribution. Uses ranks, not values. No normality assumption.

**MCC (Matthews correlation coefficient)** — Balanced measure of multi-class classifier quality. +1 perfect; 0 chance; -1 inverse. Preferred over accuracy on imbalanced data.

**NDCG (Normalized Discounted Cumulative Gain)** — Ranking metric that discounts the gain of each item by log of its rank. Normalizes against the ideal ranking so scores are comparable across queries.

**Percentile bootstrap** — The simplest bootstrap CI: take the 2.5th and 97.5th percentiles of resampled statistics. Good at n ≥ 10.

**Position bias** (LLM-judge) — Known tendency of LLM judges to prefer whichever response appears first (or last, depending on prompt). Mitigated by running the judge with swapped positions and averaging.

**Prompt caching** — Caching LLM responses keyed on `hash(model, system_prompt, user_prompt, params)`. Reused identically in the same run or across reruns.

**Self-consistency** — Running a stochastic judge k times and taking the median score. Reduces variance at the cost of k× tokens.

**Spearman correlation** — Pearson correlation applied to ranks rather than raw values. Measures monotonic agreement between two orderings. Robust to outliers.

**Verbosity bias** (LLM-judge) — Known tendency of judges to prefer longer responses even when shorter ones are equally correct. Mitigated by explicit prompt instruction and by including verbosity-varied test cases in the calibration gold set.

---

*End of document. Total read time ~30 minutes. Rehearse §1, §6, and §7 before any interview.*
