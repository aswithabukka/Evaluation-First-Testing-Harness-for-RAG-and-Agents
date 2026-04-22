# Interview Cheatsheet — RAG Eval Harness

> Read top-to-bottom once. Skim Parts C and D the morning of the interview.
> Companion to the longer `INTERVIEW_PREP_RAG_EVAL.md` — this one is the night-before version.

---

## Part A — What & Why

### 1. The 60-second pitch (memorize)

> LLM applications fail silently — a prompt change can quietly drop answer faithfulness by 20 percentage points and nobody notices until users complain. I built an evaluation-first CI/CD platform that scores every pipeline change on ~19 evaluators (Ragas metrics, LLM-as-judge, tool-call accuracy, calibration, safety) and **blocks deploys when the regression is statistically significant** versus the last passing run — not when an absolute number crosses a threshold. The stack is FastAPI + Celery + Postgres + Redis + Next.js, plus a CLI that integrates with GitHub Actions. The differentiators are the significance-aware gate, a reproducibility manifest, and a provider-agnostic LLM client that can flip from GPT-4o to OpenRouter (Qwen, Kimi) for ~10× lower cost without code changes.

### 2. The problem in 3 sentences

1. LLM apps don't fail like normal software — they return confident, plausible answers that are wrong, and no unit test catches that.
2. Existing eval libraries (Ragas, DeepEval, LangSmith) give you metrics, but they don't give you a CI gate — you still need to know what counts as a regression and how to block a deploy on it.
3. Naive threshold gates trip constantly on sample noise (a 50-case eval has ±3pp natural wiggle), so teams either ignore them or stop running them.

### 3. Main objectives

- **Treat LLM quality as a first-class CI/CD check** — every PR gets scored, every regression is visible.
- **Block deploys only on statistically significant regressions** — bootstrap CIs vs. threshold + Mann-Whitney U vs. last passing baseline.
- **Make every run reproducible and auditable** — manifest captures evaluator versions, prompt hashes, seeds, git SHA → 16-char fingerprint.
- **Stay provider-agnostic** — same code path runs against OpenAI, OpenRouter, or any OpenAI-compatible endpoint; switching is an env var.

### 4. Why I built it (vs. just using Ragas / LangSmith / DeepEval)

- **Ragas** = metrics library, not a platform. No CI, no gate, no UI, no history, no significance testing.
- **LangSmith / Langfuse** = observability + tracing, optimized for debugging single calls, not for batch eval-as-CI. Vendor-locked.
- **DeepEval / Promptfoo** = closer in spirit, but neither does statistical significance gating; both treat the metric value as ground truth.
- **The gap I fill:** an opinionated eval gate that's noise-aware, reproducible, and pluggable across providers.

---

## Part B — How it works

### 5. Main components (the 5 layers)

| Layer | What it does |
|------|------|
| **CLI** (`runner/cli.py`) | Entry point. Triggers runs, polls for completion, prints reports, evaluates the gate. Same binary used locally and in CI. |
| **FastAPI backend** (`backend/app/`) | REST API. Stores test sets, test cases, runs, results, metric history. Async (asyncpg). |
| **Celery worker** (`backend/app/workers/`) | Runs evaluations asynchronously so a 10-min run doesn't block the API or CI. Sync (psycopg2). |
| **Postgres + Redis** | Postgres = source of truth, JSONB for flexible metric storage. Redis = Celery broker (db1) + result backend (db2). |
| **Next.js dashboard** (`frontend/`) | Humans browse runs, compare models side-by-side, view metric trends, use the live playground. SWR-polled, dark-mode. |

### 6. End-to-end lifecycle of a run (the "how is it happening" answer)

A 7-step walkthrough — rehearse this; interviewers love it.

1. **Trigger.** CLI does `POST /api/v1/runs` with `test_set_id`, `pipeline_config`, git metadata.
2. **Run row created.** Backend snapshots the current thresholds onto the run row (immutable). Gate is always evaluated against the thresholds at run-creation time, never current config — so changing thresholds mid-run can't rewrite history.
3. **Celery dispatch.** Backend `apply_async()`s a task to the `evaluations` queue and returns 202 immediately.
4. **Adapter loaded dynamically.** The worker reads `pipeline_config.adapter_module` and `adapter_class`, uses `importlib` to load the user's pipeline (e.g., `DemoRAGAdapter`), and calls `setup()`.
5. **Per-case evaluation.** For each test case: `adapter.run(query, context)` → returns `PipelineOutput` (answer + retrieved_contexts + tool_calls + turn_history). Then every configured evaluator scores it. Results written to `evaluation_results` and `metrics_history`.
6. **Gate evaluation.** Once all cases are done, `release_gate_service` pulls per-case raw scores, calls `significance_gate()` to compute bootstrap CI + Mann-Whitney U vs. the last passing baseline, and decides per-metric pass/fail.
7. **Status flip.** Run status moves to `COMPLETED`, `GATE_BLOCKED`, or `FAILED`. Slack/webhook alert fires if configured.

### 7. How it triggers (the "how is it triggering" answer)

Three trigger paths — same evaluation engine in all three.

| Trigger | When | What it does |
|---|---|---|
| **GitHub Actions** (`.github/workflows/evaluate.yml`) | Every PR + push to `main`/`develop` | Spins up Postgres + Redis as services, starts FastAPI + Celery in background, runs `rageval run` then `rageval gate --fail-on-regression`, posts a PR comment with the metrics table and any regressions. **The primary path.** |
| **CLI** (`python -m runner.cli run`) | Local development | Hits a running backend (Docker Compose). Useful for testing a new adapter or a config change without pushing. |
| **Dashboard** (`/test-sets/[id]`) | Ad-hoc, by humans | "Run Evaluation" button → same `POST /runs`. "Compare Models" button creates N runs in parallel via `POST /runs/multi` for side-by-side model comparison. |

A second workflow (`.github/workflows/release-gate.yml`) queries `GET /runs?git_commit_sha=<sha>` and sets a GitHub commit status check — that's what blocks the merge button on the PR.

---

## Part C — The 5 things that make it interesting

These are the differentiators interviewers will probe hardest. Know them cold.

### A. Significance-aware gate

- **The naive approach:** `if metric_mean < threshold: fail`. Trips on noise (a 50-case eval has ±3pp natural variance), and a real 4pp regression hides inside that noise floor.
- **What I did:** `runner/gate/stats.py::significance_gate` computes a bootstrap 95% CI on the current run; gate fails only if the CI lower bound is below threshold. Plus a Mann-Whitney U test against the last passing baseline; baseline regressions only fail when p < 0.05.
- **Why it matters:** False-positive rate dropped from "trips daily" to "almost never," while real regressions still fail.
- **Mirrored implementation:** Pure-Python copies in `runner/gate/stats.py` and `backend/app/services/_gate_stats.py`; parity pinned by `backend/tests/test_gate_stats.py`. (Why two copies? Runner has to be able to compute the gate offline in CI without hitting the backend.)

### B. None-on-error semantics

- **The bug I avoided:** A flaky LLM judge that times out used to return `0.0`, which trips the gate as if quality regressed.
- **What I did:** LLM-based evaluators return `None` plus an `EvalError` on `MetricScores.error`. Gate ignores `None` for that metric instead of treating it as a zero.
- **Why it matters:** Infra errors don't masquerade as quality regressions. Codified as a rule in CLAUDE.md so future contributors don't break it.

### C. Reproducibility manifest

- `runner/manifest.py::Manifest` snapshots: every evaluator's `version`, every library's installed version, every prompt's SHA-256, every seed, the git commit, and the OS.
- The whole thing hashes into a 16-char `fingerprint`. Two runs with the same fingerprint should produce the same gate decision (up to LLM non-determinism).
- **Why it matters:** When somebody says "the gate is flaky," I can diff manifests and show them the actual change — usually a silent Ragas version bump that changed a prompt template.

### D. Provider-agnostic LLM client

- `runner/evaluators/_llm.py::LLMClient` is the single place every evaluator goes for LLM calls. Gives you for free: retries with exponential backoff, prompt-hash caching, per-model cost tracking via `MODEL_PRICES`, and a concurrency semaphore.
- Set `OPENROUTER_API_KEY` and every evaluator auto-routes through OpenRouter — no code change. A 200-case eval drops from ~$10 (GPT-4o) to ~$0.33 (Qwen 3.6).
- Even Ragas is wrapped via `LangchainLLMWrapper` + `ChatOpenAI(openai_api_base=...)` — see `_build_ragas_llm()` in `runner/evaluators/ragas_evaluator.py`.

### E. Adapter pattern

- Any pipeline plugs in by subclassing `runner/adapters/base.py::RAGAdapter` and implementing `setup()`, `run(query, context) -> PipelineOutput`, `teardown()`.
- `PipelineOutput` carries `answer`, `retrieved_contexts`, `tool_calls`, `turn_history`, `metadata` — covers all 9 system types.
- Loaded dynamically via `importlib` from `pipeline_config` on the run row, so a new adapter doesn't require redeploying the worker.
- 4 demo adapters ship in-tree (RAG, tool-agent, chatbot, search) so the system has something to evaluate out of the box.

---

## Part D — Interview prep

### 8. Why X, not Y (the design decisions interviewers probe hardest)

| Question | The 1-line answer |
|---|---|
| Why not just use Ragas? | Ragas is a metrics library, not a platform — no CI integration, no gate, no UI, no history, no significance testing. I use Ragas internally as one of ~19 evaluators. |
| Why not LangSmith / Langfuse? | They're observability/tracing tools, optimized for debugging single calls. Vendor-locked, no offline gate. |
| Why FastAPI + Celery instead of a single script? | A 10-minute eval can't block CI synchronously. Async dispatch + status polling lets CI fail fast on infra errors and lets humans cancel runs. |
| Why Postgres (JSONB) instead of Mongo or a vector DB? | I need ACID for the run/results write path (gate decisions are audit-grade), JSONB for flexible per-evaluator metric shapes, and SQL for trend queries. Mongo gives flexibility but loses joins; vector DB is the wrong tool — embeddings live in the adapter. |
| Why bootstrap CI instead of a t-test? | LLM scores aren't normal — they're often bimodal (judges pick 0 or 1) or skewed. Bootstrap is distribution-free. Same reason for Mann-Whitney U over a Welch's t-test for the baseline comparison. |
| Why LLM-as-judge at all (vs. embedding similarity)? | Embedding similarity rewards lexical overlap, not factual correctness. LLM judges catch hallucinations that have high cosine similarity to the reference. The trade-off is cost + judge bias, which I mitigate (next row). |
| Why self-consistency on the LLM judge? | A single judge call has ~10-15% flakiness. Self-consistency takes the median of `k` samples (default 3) and reports variance, so flaky cases are flagged for exclusion. |
| Why pairwise with position swapping? | LLM judges have a documented position bias (~5-10% preference for whichever answer comes first). Running each comparison twice with positions swapped cancels it; disagreement = ambiguous case. |
| Why a separate worker instead of running evals in the API process? | Crash isolation, horizontal scaling (more workers, same API), and so a long-running eval can't starve the API of its connection pool. |
| Why mirror the gate stats in two places? | Runner needs to compute the gate offline in CI without an HTTP round-trip to the backend. Parity is pinned by a test that runs both implementations on the same fixture. |

### 9. Top 15 expected questions (with bullet-form answers)

#### (a) Project & motivation

**Q1. Walk me through this project.**
- 60-second pitch (Section 1).
- Then offer to dive into either the gate, the architecture, or a specific evaluator.

**Q2. Why did you build this instead of using an existing tool?**
- Existing libraries give metrics, not a gate.
- None do statistical significance testing — they all treat the raw metric as ground truth.
- Wanted a platform that's vendor-neutral and reproducible end-to-end.

**Q3. Who would actually use this?**
- ML platform teams shipping LLM apps to production.
- Acts as the equivalent of a CI test runner (Jenkins/CircleCI for unit tests) but for LLM quality.

#### (b) Evaluators & metrics

**Q4. What does "faithfulness" mean and how do you measure it?**
- Whether the generated answer is grounded in the retrieved context (no hallucination).
- Ragas implementation: decompose answer into atomic claims, verify each against context with an LLM judge, faithfulness = supported / total.
- I also have a stricter `CitationEvaluator` that does the same thing but flags individual unsupported claims.

**Q5. Difference between context precision and context recall?**
- **Precision:** of the chunks I retrieved, how many are actually relevant? (Ranking quality.)
- **Recall:** of all relevant chunks in the corpus, how many did I retrieve? (Coverage.)
- Precision rewards a tight, relevant top-k; recall rewards finding everything.

**Q6. How do you evaluate a tool-using agent differently from a RAG pipeline?**
- `TrajectoryEvaluator`: tool-sequence similarity (1 - normalized Levenshtein on the tool call sequence), JSON-schema validation of args, semantic argument match.
- Plus rule-engine constraints like `must_call_tool` / `must_not_call_tool`.

**Q7. What is G-Eval and why use it over a plain LLM judge?**
- G-Eval (Liu et al., EMNLP 2023): auto-generates a rubric from the criterion, then forces chain-of-thought scoring on a 1-5 integer scale, normalized to 0-1.
- More reproducible than free-form judging because the rubric is explicit and the scale is bounded.

#### (c) Statistics & the gate

**Q8. Walk me through the gate logic.**
- Pull per-case raw scores for the run.
- For each metric: bootstrap 95% CI on the current run → fail if CI lower bound < threshold.
- Mann-Whitney U vs. last passing baseline → fail only if p < 0.05.
- Combine: gate blocks if any metric fails OR any rule fails.

**Q9. Why bootstrap and not a parametric CI?**
- LLM scores aren't normally distributed (often bimodal or skewed).
- Bootstrap is distribution-free, only assumes IID — fine for our case.
- 1000 resamples is enough for stable CIs at n=50+.

**Q10. How do you handle judge non-determinism?**
- Self-consistency: median of k samples, variance reported.
- Flakiness detector reruns top-N failing cases and excludes high-variance ones from gate decisions.
- Calibration harness measures Spearman vs. human-labeled gold to detect judge drift.

#### (d) Architecture

**Q11. Why async FastAPI + sync Celery?**
- API needs high concurrency for many small reads → asyncpg.
- Workers do CPU/IO-heavy batch work → sync psycopg2 is simpler and the GIL isn't the bottleneck (we're network-bound on LLM calls, mitigated by a concurrency semaphore in the LLMClient).

**Q12. How does the worker scale?**
- Horizontal: more Celery worker pods, same `evaluations` queue.
- Per-worker concurrency tuned to the LLM provider's rate limit (semaphore in `LLMClient`).
- Per-run cost + time budget (`runner/budget.py`) caps runaway evaluations.

**Q13. How would you scale to 10,000 test cases per run?**
- Shard cases across workers (Celery `group()` or Canvas `chord()`).
- Stream results into Postgres in batches instead of per-case writes.
- Increase bootstrap sample size proportionally; significance gets tighter, not weaker.
- Honest answer: I haven't load-tested past ~200 cases — that's a known gap.

#### (e) Trade-offs & scale

**Q14. What's the biggest weakness of this project?**
- LLM judges aren't ground truth — they're correlated with human preference but not equal to it. The calibration harness measures this but I haven't run it weekly in production.
- See Section 10.

**Q15. What would you do differently if you started over?**
- Add an offline-first mode where the runner can compute the gate without the backend (currently the gate logic is mirrored, but writes still go through the API).
- Build a judge-rotation harness that A/B-tests two judges on the same gold set continuously.
- Add a Postgres LISTEN/NOTIFY path so the dashboard updates without SWR polling.

### 10. Honest weaknesses to volunteer

Saying these unprompted earns more credit than waiting for the interviewer to find them.

- **No human-eval ground truth in the demo.** The calibration harness exists; the gold file is ~30 examples, not the 500+ you'd want in production.
- **Single-tenant.** No auth, no per-team isolation, no rate limiting on the API. Fine for a portfolio project, not fine for a real SaaS.
- **Haven't load-tested past ~200 cases.** I know what I'd do (sharding via Celery `group`) but haven't measured it.
- **Judge cost tracking is per-call, not per-run-budgeted-up-front.** The budget cuts off mid-run; better would be a pre-flight estimate that warns before starting.
- **The dashboard polls (SWR every 8-10s) instead of streaming.** Server-sent events or WebSocket would be cheaper at scale.

### 11. Vocabulary one-liners (so a term can't trip you up)

| Term | One-liner |
|---|---|
| **Faithfulness** | Is the answer grounded in retrieved context (no hallucination)? |
| **Answer relevancy** | Does the answer address the question (regardless of whether it's correct)? |
| **Context precision** | Of the chunks retrieved, what fraction are actually relevant? |
| **Context recall** | Of all relevant chunks, what fraction did we retrieve? |
| **ECE (Expected Calibration Error)** | Gap between predicted confidence and actual accuracy across bins. Low ECE = the model knows what it knows. |
| **NDCG** | Normalized Discounted Cumulative Gain. Rewards putting relevant results higher. Standard search metric. |
| **MRR** | Mean Reciprocal Rank. 1/rank of the first relevant result, averaged. |
| **MAP** | Mean Average Precision. Precision at every relevant rank, averaged. |
| **G-Eval** | LLM-as-judge with auto-generated rubric + forced chain-of-thought + bounded integer scale. |
| **Pairwise judging** | LLM picks A vs. B instead of scoring each absolutely. Run with position swap to cancel position bias. |
| **Self-consistency** | Sample the judge k times, take the median. Reduces flakiness, exposes variance. |
| **Bootstrap CI** | Resample with replacement N times, take the empirical CI. Distribution-free. |
| **Mann-Whitney U** | Non-parametric test for "do two samples come from the same distribution." Used to compare current run vs. baseline. |
| **Position bias** | LLM judges prefer whichever answer comes first by ~5-10%. Mitigate by swapping positions. |
| **Verbosity bias** | LLM judges prefer longer answers. Mitigate by including a hint in the judge prompt. |
| **Calibration (judge)** | Spearman correlation between judge scores and human-labeled gold. Run weekly to detect drift. |
| **Flakiness detection** | Rerun top-N failing cases k times, exclude high-variance ones from the gate decision. |

---

## Quick-reference: things to drop into answers to sound senior

- "We snapshot thresholds on the run row so the gate is evaluated against config-at-run-time, not current config — otherwise changing a threshold rewrites history."
- "The runner and backend have parity-pinned copies of the gate stats — the runner needs to compute the gate offline in CI without an HTTP round-trip."
- "LLM judges return `None`-on-error, not `0.0` — otherwise infra flakes look like quality regressions to the gate."
- "Provider switch is an env var, not a code change — `OPENROUTER_API_KEY` reroutes every judge call, even Ragas, via `LangchainLLMWrapper` + `openai_api_base`."
- "The manifest fingerprint lets me explain any gate decision in audit terms — pin every evaluator version, every prompt hash, every seed."
