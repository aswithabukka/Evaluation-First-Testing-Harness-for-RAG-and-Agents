# Evaluators Reference

A detailed catalogue of every evaluator in this project, what it measures, and what the underlying metrics actually mean.

This doc is designed for **two audiences**:
1. A developer deciding which evaluator to enable.
2. A reader who wants to know what BLEU / NDCG / ECE / MCC actually compute, without needing a stats textbook.

Every metric has a **plain-English explanation first**, then the technical definition.

---

## Table of Contents

- [What is an "evaluator"?](#what-is-an-evaluator)
- [At-a-glance: 19 evaluators by domain](#at-a-glance-19-evaluators-by-domain)
- [1. RAG pipelines](#1-rag-pipelines-answer-groundedness)
- [2. AI agents](#2-ai-agents-tool-use)
- [3. Chatbots](#3-chatbots-multi-turn-conversation)
- [4. Search and ranking](#4-search-and-ranking)
- [5. LLM output (general-purpose judging)](#5-llm-output-general-purpose-judging)
- [6. Classification](#6-classification)
- [7. Summarization and translation](#7-summarization-and-translation)
- [8. Code generation](#8-code-generation)
- [9. Safety and responsibility](#9-safety-and-responsibility)
- [10. Robustness and reliability](#10-robustness-and-reliability)
- [11. Meta-evaluators](#11-meta-evaluators)
- [Metric Glossary — full definitions](#metric-glossary)

---

## What is an "evaluator"?

An **evaluator** is a class that takes a test case (`query`, `expected_answer`, `retrieved_context`, `tool_calls`, etc.) and returns one or more **numerical scores**. Every evaluator subclasses `BaseEvaluator` and returns a `MetricScores` object with:

- `scores: dict[str, float | None]` — the actual metric values
- `error: EvalError | None` — non-null when the evaluator couldn't produce a score
- `cost_usd`, `latency_ms` — observability
- `metadata` — provenance (which model, which prompt, which seed)

The release gate compares scores across runs to decide whether to block a deploy.

---

## At-a-glance: 19 evaluators by domain

| # | Evaluator | Domain | Main output |
|---|---|---|---|
| 1 | RagasEvaluator | RAG | faithfulness, answer relevancy, context precision, context recall |
| 2 | CitationEvaluator | RAG | claim-level faithfulness |
| 3 | AgentEvaluator | Agent | tool-call F1, goal accuracy, step efficiency |
| 4 | TrajectoryEvaluator | Agent | trajectory similarity, argument schema validity |
| 5 | MultiTurnAgentEvaluator | Agent | multi-turn goal completion |
| 6 | ConversationEvaluator | Chatbot | coherence, knowledge retention, role adherence |
| 7 | RankingEvaluator | Search | NDCG@k, MAP@k, MRR, precision@k, recall@k |
| 8 | LLMJudgeEvaluator | Generic | configurable score (0-1) |
| 9 | GEvalEvaluator | Generic | auto-rubric score (1-5, normalised) |
| 10 | PairwiseEvaluator | Generic | A/B preference (with position-swap) |
| 11 | ClassificationEvaluator | Classification | accuracy, F1, MCC, Cohen's kappa, AUC-ROC |
| 12 | SimilarityEvaluator | Summarization | ROUGE-L, BLEU, cosine similarity |
| 13 | TranslationEvaluator | Translation | BLEU, translation accuracy |
| 14 | CodeEvaluator | Code gen | syntax validity, test pass rate, lint score |
| 15 | SafetyEvaluator | All | PII detection, toxicity score, injection risk |
| 16 | RobustnessEvaluator | All | paraphrase consistency, adversarial robustness |
| 17 | CalibrationEvaluator | All | Expected Calibration Error, overconfidence rate |
| 18 | RuleEvaluator | All | structural pass/fail over 16 rule types |
| 19 | DeepEvalEvaluator | All | bridge to the DeepEval library |

---

## 1. RAG pipelines (answer groundedness)

### 1.1 `RagasEvaluator`

**What it is.** A wrapper around the [Ragas](https://github.com/explodinggradients/ragas) library, the de-facto standard for evaluating RAG pipelines. Ragas uses an LLM judge (GPT-4o / Qwen / whatever you configure) to score four metrics.

**Why we use it.** RAG systems can fail in four distinct ways: the answer hallucinates, the answer dodges the question, retrieval surfaces irrelevant chunks, or retrieval misses key information. One number can't distinguish these; Ragas gives you four.

**What each metric means:**

| Metric | Plain English | Range |
|---|---|---|
| **Faithfulness** | Of the claims in the answer, what fraction are supported by the retrieved context? Measures hallucination (inverse of it). | 0-1 |
| **Answer Relevancy** | Does the answer actually address the question asked, or is it tangential? Computed by asking the LLM to reverse-engineer questions from the answer and measuring similarity to the original. | 0-1 |
| **Context Precision** | Of the chunks the retriever returned, what fraction are actually relevant to answering the question? High precision = clean retrieval. | 0-1 |
| **Context Recall** | Of the information needed to answer the question, what fraction is present in the retrieved context? High recall = retrieval didn't miss anything. | 0-1 |

**When to use.** Any RAG pipeline. This is the default for `system_type: rag` in the harness.

**Known limitations.** Requires a judge LLM. All scores are judge-dependent, so a judge upgrade can shift scores uniformly (that's what the calibration harness catches).

### 1.2 `CitationEvaluator` *(new in this refactor)*

**What it is.** A claim-level faithfulness evaluator. Two-stage LLM call: (1) decompose the answer into atomic factual claims, (2) check each claim against the retrieved context.

**Why we use it.** Ragas faithfulness scores the answer as a whole — you get 0.73. But *which* claim was unsupported? Citation evaluator tells you: "the answer has 5 claims, 4 are supported, claim #3 ('the trial ended in 2019') is unsupported." That's actionable.

**What it outputs:**

| Metric | Plain English | Range |
|---|---|---|
| **citation_faithfulness** | Fraction of atomic claims supported by retrieved context | 0-1 |
| **claim_count** | How many claims the judge extracted from the answer | int |
| **unsupported_claims** | List of the actual claim strings that weren't supported | list |

**When to use.** Anytime you need to know *which* claim failed, not just that faithfulness dropped. Especially useful in regulated domains (medical, legal) where you need to defend each statement.

---

## 2. AI agents (tool use)

### 2.1 `AgentEvaluator`

**What it is.** Evaluates whether an agent called the right tools, with the right arguments, in the right order, and completed its goal.

**Why we use it.** Agents fail in ways that text-only metrics can't detect — calling the wrong tool, passing bad arguments, looping forever. We need tool-specific metrics.

**What it outputs:**

| Metric | Plain English | Range |
|---|---|---|
| **tool_call_precision** | Of the tools the agent called, what fraction were the right ones? | 0-1 |
| **tool_call_recall** | Of the tools it *should* have called, what fraction did it call? | 0-1 |
| **tool_call_f1** | Harmonic mean of precision and recall. Catches both over-calling and under-calling. | 0-1 |
| **tool_call_accuracy** | Exact match: did the agent call exactly the right set (and optionally sequence) of tools? | 0 or 1 |
| **argument_accuracy** | For correctly-called tools, what fraction of expected arguments matched? | 0-1 |
| **goal_accuracy** | Does the agent's final answer match the expected answer? Exact / containment / token overlap. | 0-1 |
| **step_efficiency** | Ratio of minimum required steps to actual steps. 1.0 = optimal, <1.0 = agent wandered. | 0-1 |
| **error_recovery_rate** | Of the errors the agent hit, what fraction did it recover from? | 0-1 |

**When to use.** Any tool-calling agent. Default for `system_type: agent`.

### 2.2 `TrajectoryEvaluator` *(new)*

**What it is.** Agent evaluation that specifically cares about **sequence** — the order in which tools were called, not just the set. Uses edit distance on the tool-call sequence.

**Why we use it.** `AgentEvaluator.tool_call_accuracy` is set-based by default; it treats `[A, B, C]` and `[C, A, B]` as equal. For agents where order matters (search → fetch → answer is correct, but answer → fetch → search is wrong), we need trajectory similarity.

**What it outputs:**

| Metric | Plain English | Range |
|---|---|---|
| **trajectory_similarity** | `1 - (Levenshtein_distance / max_length)`. 1.0 = identical sequence, 0.0 = completely different. | 0-1 |
| **argument_schema_valid** | Fraction of predicted tool calls whose arguments pass a supplied JSON schema. | 0-1 |
| **argument_semantic_match** | Fraction of expected argument values that match the predicted values (with numeric / string-normalized tolerance). | 0-1 |

**Levenshtein distance (plain English):** The minimum number of single-element edits (insert, delete, or substitute) to transform one sequence into another. E.g. `[A, B, C]` → `[A, X, C]` has distance 1 (one substitution). Normalized distance divides by the longer sequence's length, giving a 0-1 value.

### 2.3 `MultiTurnAgentEvaluator`

**What it is.** Evaluates agents over **multi-turn conversations** where the goal spans several user messages.

**Why we use it.** Single-turn evaluation misses interaction dynamics: does the agent remember context from turn 1? Does it correctly clarify ambiguous requests? Does it give up too early?

**What it outputs:**
- `passed: bool` — did the agent complete the goal?
- `turn_results: list` — per-turn scoring
- `goal_completed: bool`
- `failure_reason: str | None`

---

## 3. Chatbots (multi-turn conversation)

### 3.1 `ConversationEvaluator`

**What it is.** LLM-judge-based scoring for chatbots on four conversational axes.

**Why we use it.** Chatbots need to flow, stay in character, and remember what the user said three turns ago. Ragas-style metrics don't capture these.

**What each metric means:**

| Metric | Plain English | Range |
|---|---|---|
| **coherence** | Do the turns flow logically? Does the bot's reply actually follow from the user's message? | 0-1 |
| **knowledge_retention** | If the user said their name is Alice on turn 1, does the bot still remember it on turn 5? | 0-1 |
| **role_adherence** | Does the bot stay in the persona defined by its system prompt? A pirate chatbot should keep talking like a pirate. | 0-1 |
| **response_relevance** | Is each individual reply on-topic for the current turn? | 0-1 |

**When to use.** `system_type: chatbot`.

---

## 4. Search and ranking

### 4.1 `RankingEvaluator`

**What it is.** Classical information retrieval metrics comparing a predicted ranked list of document IDs to an expected ranked list.

**Why we use it.** Search systems (and retrieval within RAG) produce a ranking. The quality of a ranking isn't captured by "top-1 accuracy" — you want to know whether the *right* documents appear near the top.

**What each metric means:**

| Metric | Plain English | Range |
|---|---|---|
| **NDCG@k** | "Normalized Discounted Cumulative Gain" — how good is the ranking in the top k positions? Items appearing earlier get more credit; the whole thing is normalized against the ideal ranking. | 0-1 |
| **MAP@k** | "Mean Average Precision at k" — average precision across every relevant document's position. Rewards getting relevant docs high up. | 0-1 |
| **MRR** | "Mean Reciprocal Rank" — `1 / rank_of_first_relevant_doc`. If the first relevant doc is at position 3, MRR contribution is 1/3. | 0-1 |
| **precision@k** | Of the top-k predicted, what fraction are relevant? | 0-1 |
| **recall@k** | Of all relevant docs, what fraction appear in top-k? | 0-1 |

**When to use.** `system_type: search`, or any retrieval-heavy pipeline.

**NDCG@k in plain English:** If you showed the user the top 10 results, how much usefulness did they get? Each document's usefulness is discounted by a log of its rank, so position #1 counts more than position #10. Normalized means we divide by the maximum possible score (perfect ranking), so 1.0 = perfect and 0.0 = worst.

---

## 5. LLM output (general-purpose judging)

### 5.1 `LLMJudgeEvaluator`

**What it is.** A configurable LLM-as-judge. You specify criteria (e.g. "accuracy, helpfulness, groundedness"), it returns a 0-1 score with reasoning.

**Why we use it.** When you need a general-purpose quality signal and your test cases don't fit any specific metric's assumptions.

**Key features:**
- **Self-consistency**: runs the judge `k` times and takes the median. Reduces variance.
- **Verbosity-bias hint**: the prompt explicitly tells the judge not to reward length.
- **None-on-error**: if the judge API fails, returns `None` (not `0.0`), so infra errors don't trip the release gate.

**What it outputs:**

| Metric | Plain English | Range |
|---|---|---|
| **llm_judge** | Overall quality score on the specified criteria | 0-1 |
| (metadata.variance) | Variance across k self-consistency samples; high variance = flaky case | ≥0 |

### 5.2 `GEvalEvaluator` *(new)*

**What it is.** Implements the **G-Eval** pattern from Liu et al., *"G-Eval: NLG Evaluation using GPT-4 with Better Human Alignment"* (EMNLP 2023).

**Why we use it.** Naive LLM judging is high-variance and opaque. G-Eval is two-stage:
1. Given an aspect ("coherence") and description, the judge first **generates an evaluation rubric** — 3-5 concrete steps a human annotator would follow.
2. The same rubric is used for every test case, forcing the judge to reason step-by-step and emit an integer 1-5 score.

This reduces variance (same rubric every case) and improves correlation with humans in the G-Eval paper's experiments.

**What it outputs:**

| Metric | Plain English | Range |
|---|---|---|
| **g_eval:\<aspect\>** | Score normalized from 1-5 to 0-1 | 0-1 |
| (metadata.rubric_steps) | How many steps the auto-generated rubric has | int |

### 5.3 `PairwiseEvaluator` *(new)*

**What it is.** A/B preference judging. "Given question Q, is response A better than response B?"

**Why we use it.** For model-vs-model comparisons (e.g. "does GPT-5.4 beat Qwen 3.6 on my domain?"). Pairwise is lower-variance than absolute scoring because the judge only has to pick a winner, not pin a number.

**Position bias mitigation.** LLM judges systematically prefer whichever response appears first ([well-documented bias](https://arxiv.org/abs/2306.05685)). Every pairwise comparison runs **twice with swapped positions** — once as (A, B) and once as (B, A). If the judge flips its preference under swap, we call it a tie.

**What it outputs:**

| Metric | Plain English | Range |
|---|---|---|
| **pairwise_preference_a** | 1.0 = A strictly preferred, 0.5 = tie, 0.0 = B strictly preferred | 0-1 |
| (metadata.position_bias_detected) | True if the judge flipped preferences under position swap | bool |

---

## 6. Classification

### 6.1 `ClassificationEvaluator`

**What it is.** Standard classification metrics for single-label, multi-label, and binary tasks.

**Why we use it.** Classification pipelines (intent classifiers, moderation, sentiment) need classical ML metrics, not LLM-judge scores.

**What each metric means:**

| Metric | Plain English | Range |
|---|---|---|
| **accuracy** | Fraction of predictions that are exactly right | 0-1 |
| **precision** | Of the positive predictions, what fraction are correct? Low precision = false alarms. | 0-1 |
| **recall** | Of the actual positives, what fraction did we catch? Low recall = missed positives. | 0-1 |
| **f1** | Harmonic mean of precision and recall. Single number that penalises extreme imbalance. | 0-1 |
| **macro_f1** | F1 computed per class, then averaged equally. Treats all classes as equally important (good for imbalanced data). | 0-1 |
| **micro_f1** | F1 computed by pooling all classes' true positives, false positives, false negatives. Dominated by frequent classes. | 0-1 |
| **weighted_f1** | Per-class F1, weighted by class support. | 0-1 |
| **cohens_kappa** | Agreement between predicted and true labels, **corrected for chance**. 0 = chance-level, 1 = perfect, <0 = worse than random. | -1 to 1 |
| **matthews_corrcoef (MCC)** | Multi-class balanced measure. **The single best scalar for imbalanced data** (Chicco & Jurman 2020). | -1 to 1 |
| **auc_roc** | Area under the ROC curve. Measures binary classifier quality across all thresholds. Random = 0.5, perfect = 1.0. | 0-1 |
| **pr_auc** | Area under precision-recall curve. Better than AUC-ROC for heavily imbalanced positive class. | 0-1 |
| **confusion_matrix** | Nested dict: `{true_label: {predicted_label: count}}`. Shows *which* classes get confused with which. | int counts |

**Why MCC is preferred over accuracy on imbalanced data.** If 95% of your examples are class A, a model that always predicts A gets 95% accuracy and looks great. MCC accounts for all four confusion-matrix quadrants and gives this model ~0 — correctly identifying it as no better than random.

---

## 7. Summarization and translation

### 7.1 `SimilarityEvaluator`

**What it is.** Surface-level text similarity metrics: ROUGE, BLEU, cosine similarity.

**What each metric means:**

| Metric | Plain English | Range |
|---|---|---|
| **ROUGE-L** | Longest Common Subsequence overlap between prediction and reference. Measures **recall** of content. Popular for summarization. | 0-1 |
| **BLEU** | Modified n-gram precision over n=1..4, with a brevity penalty. Measures **precision** of content. Popular for translation. | 0-1 |
| **cosine_similarity** | Angle between the embedding vectors of prediction and reference. Captures semantic similarity even when wording differs. | 0-1 |

**BLEU in plain English:** Take all the word-pairs, word-triples, and word-quadruples in your output. What fraction of them also appear in the reference? Multiply the precisions, apply a penalty if your output is too short. A BLEU of 0.4 on news translation is "competitive human-level"; 0.6+ is superhuman.

**ROUGE-L in plain English:** Find the longest sequence of words that appear in both your summary and the reference (in the same order, though not necessarily adjacent). The longer the overlap, the higher the score.

**When to use.** Summarization (ROUGE), translation (BLEU). Known limitations: both penalize paraphrase, so a correct summary phrased differently gets a low score. Use cosine similarity as a paraphrase-robust alternative.

### 7.2 `TranslationEvaluator`

**What it is.** Specialized BLEU + accuracy wrapper for machine-translation outputs. Mostly a convenience layer over `SimilarityEvaluator` with MT-specific tokenization.

---

## 8. Code generation

### 8.1 `CodeEvaluator`

**What it is.** Executes generated code and checks whether it runs, passes tests, and lints cleanly.

**What it outputs:**

| Metric | Plain English | Range |
|---|---|---|
| **syntax_valid** | Does the code parse without a syntax error? | 0 or 1 |
| **test_pass_rate** | Fraction of supplied unit tests that pass when run against the generated code | 0-1 |
| **lint_score** | Ruff / pylint clean-ness of the output | 0-1 |

**Why we use it.** For code generation, the only metric that matters is *does it work*. Text-similarity metrics are misleading — the right function can be written many ways.

**Safety note.** Runs untrusted code in a sandbox. Don't enable on a production host without isolation.

---

## 9. Safety and responsibility

### 9.1 `SafetyEvaluator`

**What it is.** Three layered checks on the output text. Each layer is optional; lower layers are cheap fallbacks.

**Layer 1 — Regex heuristics (always on):**
- PII patterns: email, phone, SSN, credit card
- Toxicity keyword density
- Prompt-injection patterns (`"ignore previous instructions"`, etc.)

**Layer 2 — Presidio (optional, requires `presidio-analyzer`):**
- ML-backed PII detection
- Multilingual
- Handles obfuscation (`j0hn@...`) better than regex

**Layer 3 — Llama Guard / ShieldGemma (optional, requires `transformers`):**
- ML classifier for toxicity + jailbreak detection
- Runs on GPU for acceptable latency
- State-of-the-art accuracy

**What it outputs:**

| Metric | Plain English | Range |
|---|---|---|
| **pii_detected** | True if any PII type found | bool |
| **pii_types** | List of types found (`email`, `phone`, `ssn`, `credit_card`) | list |
| **pii_confidence** | For Presidio, the detector's reported confidence | 0-1 |
| **toxicity_score** | Toxic-keyword density or guard-model classification | 0-1 |
| **prompt_injection_risk** | How many known injection patterns matched | 0-1 |
| **guard_flags** | If the guard model fired, which safety categories (e.g. `S1`=violent crime) | list |

**When to use.** Anywhere user-facing output is produced. Cheap enough to always enable layer 1.

---

## 10. Robustness and reliability

### 10.1 `RobustnessEvaluator` *(new)*

**What it is.** Measures whether the pipeline produces consistent answers under input variations.

**Why we use it.** A good pipeline shouldn't fall apart when the user adds a typo or slightly rephrases. If rephrasing the question flips the answer, that's a reliability problem your users will hit.

**What it outputs:**

| Metric | Plain English | Range |
|---|---|---|
| **paraphrase_consistency** | Run the same question with N rephrasings. Mean similarity between the baseline answer and each paraphrased answer. High = robust to phrasing. | 0-1 |
| **adversarial_robustness** | Same question + typos or a prompt-injection suffix. Low similarity to baseline = pipeline got derailed. | 0-1 |

**Similarity under the hood:** Jaccard similarity over character 3-grams — dependency-free, correlates well with semantic similarity on short answers.

**How paraphrases are generated.** Can be pre-computed offline (stored in the test case) or produced by the `paraphrase_typo()` helper (deterministic character swap every 4th word). An `adversarial_injection_suffix()` helper appends a known jailbreak phrase.

### 10.2 `CalibrationEvaluator` *(new)*

**What it is.** Expected Calibration Error — measures whether a model's reported confidence matches its actual accuracy.

**Why we use it.** If your model says "90% confident" and it's right 60% of the time, that's a silent production failure — especially for routing decisions, moderation, or gate logic that trusts the confidence score.

**What it outputs (batch-level, not per-case):**

| Metric | Plain English | Range |
|---|---|---|
| **ece** | Expected Calibration Error. Bucket predictions by confidence; for each bucket, compute the gap between mean confidence and actual accuracy; weight by bucket size, sum. | 0-1 |
| **max_calibration_gap** | Worst bin's |accuracy − confidence| gap. | 0-1 |
| **overconfidence_rate** | Fraction of predictions where confidence > actual accuracy in that bin. | 0-1 |
| **bins** | Per-bin `(confidence, accuracy, count)` for UI plotting. | list |

**ECE in plain English:** If your model is well-calibrated, then among predictions it reports at 70% confidence, about 70% should be correct. Bucket predictions by confidence (10 bins from 0 to 1). Within each bucket, check the actual accuracy. The gap between "bucket confidence" and "bucket accuracy" is miscalibration. ECE is the size-weighted average of those gaps. An ECE of 0.15 means your model is off by 15 percentage points on average.

**Reference.** Guo, Pleiss, Sun, Weinberger — *"On Calibration of Modern Neural Networks"* (ICML 2017).

---

## 11. Meta-evaluators

### 11.1 `RuleEvaluator`

**What it is.** Deterministic pass/fail checks driven by JSONB rules stored on each test case. Not an LLM call — just regex, substring, and JSON parsing.

**Why we use it.** Some checks don't need an LLM judge — "must contain the word 'insulin'" is a substring check. Rules give test-case authors a way to write hard constraints.

**Supported rule types (16):**

| Rule | What it checks |
|---|---|
| `must_contain` / `must_not_contain` | Substring presence |
| `must_call_tool` / `must_not_call_tool` | Named tool was / wasn't called |
| `regex_must_match` / `regex_must_not_match` | Pattern presence |
| `max_hallucination_risk` | Faithfulness score ≥ threshold |
| `must_refuse` | Output contains a refusal phrase |
| `must_return_label` | Output contains an expected classification label |
| `max_latency_ms` | Pipeline response time ≤ threshold |
| `must_not_contain_pii` | No PII patterns in output |
| `json_schema_valid` | Output parses as JSON and optionally matches a schema |
| `max_token_count` | Output within token limit |
| `must_cite_source` | Output contains a citation marker like `[Source: ...]` |
| `semantic_similarity_above` | Jaccard similarity to expected text ≥ threshold |
| `custom` | Delegates to a Python plugin class |

**Why rules override metrics in the gate.** If a safety rule fails (e.g. `must_refuse` didn't match), the whole test case is marked failed regardless of how high its other metrics are. Rules model hard requirements; metrics model graded quality.

### 11.2 `DeepEvalEvaluator`

**What it is.** Bridge adapter for the [DeepEval](https://github.com/confident-ai/deepeval) library — exposes any DeepEval metric as an evaluator in this harness.

**Why we use it.** DeepEval has additional metrics (contextual recall, hallucination index, G-Eval variants) that we don't want to reimplement. This adapter lets us benefit from upstream development.

---

## Metric Glossary

*Alphabetized. Each entry is self-contained enough to explain in an interview without a textbook.*

### AUC-ROC
**Area Under the Receiver Operating Characteristic curve.** Measures binary-classifier quality *across all decision thresholds*. Plot true-positive rate vs. false-positive rate as you sweep the threshold from 0 to 1; the area under that curve is AUC-ROC. Range: 0.5 (random) to 1.0 (perfect). Below 0.5 = anti-predictive (you could flip outputs and do better).

### BLEU (Bilingual Evaluation Understudy)
**Modified n-gram precision with a brevity penalty.** Introduced for machine translation. Compute the precision of n-grams (1, 2, 3, 4 word sequences) between output and reference, take a geometric mean, multiply by a penalty if the output is shorter than the reference. Range 0-1; scores >0.4 are competitive human-level for news translation.

### Bootstrap Confidence Interval
A non-parametric way to estimate uncertainty about a statistic. Given `n` observations, resample `n` with replacement, compute the statistic, repeat 2000 times. The 2.5th and 97.5th percentiles of the resulting distribution give a 95% CI. No normality assumption needed.

### Cohen's Kappa
**Inter-rater agreement corrected for chance.** Two raters (or predictor vs truth) might agree by pure chance — Cohen's kappa subtracts that expected agreement. 0 = chance agreement, 1 = perfect, <0 = worse than random.

### Cosine Similarity
**Angle between two vectors.** If the vectors are embeddings of two sentences, cosine similarity measures semantic closeness (not surface-level word overlap). Range: -1 to 1 for arbitrary vectors, 0 to 1 for non-negative embeddings.

### ECE (Expected Calibration Error)
**Gap between reported confidence and actual accuracy, bucketed and averaged.** Bucket predictions by confidence; within each bucket, compute `|bucket_accuracy − bucket_confidence|`; weight by bucket size; sum. ECE = 0 means perfectly calibrated.

### F1 Score
**Harmonic mean of precision and recall.** Penalises imbalance between the two. `2 * (precision * recall) / (precision + recall)`. Macro F1 averages per-class F1; micro F1 pools confusion counts; weighted F1 weights per-class F1 by class size.

### Faithfulness (Ragas)
Of the claims in the generated answer, what fraction are actually supported by the retrieved context? Measures hallucination (inverse of it). Judge-based, so it requires an LLM.

### Jaccard Similarity
**Intersection over union.** For two sets A and B, `|A ∩ B| / |A ∪ B|`. Range 0-1. Used in `RobustnessEvaluator` over character n-grams as a cheap proxy for semantic similarity.

### Levenshtein Distance
**Minimum single-element edits to transform one sequence into another.** "Kitten" → "sitting" has distance 3 (substitute k→s, substitute e→i, insert g). Normalized = `distance / max(len_a, len_b)`, giving 0-1.

### Mann-Whitney U Test
**Non-parametric test for whether two samples come from the same distribution, or one is shifted.** Pool all observations, rank from smallest to largest, sum ranks per sample, compare. No normality assumption — works on any bounded or skewed data. Used in our release gate to compare a current run to its baseline.

### MAP@k (Mean Average Precision at k)
Ranking metric. For each relevant document, compute the precision up to its rank, average these precisions per query, then average across queries. Rewards getting relevant docs high up. Range 0-1.

### Matthews Correlation Coefficient (MCC)
**Balanced scalar for multi-class classification.** Uses all four confusion-matrix quadrants (TP, FP, TN, FN). +1 = perfect, 0 = chance, -1 = inverse. **Preferred over accuracy on imbalanced data** (Chicco & Jurman 2020).

### MRR (Mean Reciprocal Rank)
**Inverse rank of the first relevant result, averaged across queries.** If the first relevant document is at position 3, this query contributes 1/3. Range 0-1. Simple and interpretable for tasks where users only look at the top result.

### NDCG@k (Normalized Discounted Cumulative Gain)
**Ranking quality in the top k, with log-discount for lower positions, normalized against the ideal.** Each document's relevance is discounted by log(position+1). Sum for top k = DCG. Divide by the maximum possible DCG (perfect ranking) = NDCG. Range 0-1.

### Position Bias (LLM-judge)
Known tendency of LLM judges to prefer whichever response appears first (or sometimes last) in a pairwise comparison. Mitigated by running each comparison twice with swapped positions and averaging.

### Precision
**Of the positive predictions you made, what fraction were correct?** `TP / (TP + FP)`. Low precision = lots of false alarms.

### Recall
**Of the actual positives in the data, what fraction did you catch?** `TP / (TP + FN)`. Low recall = you miss positives.

### ROUGE-L
**Longest Common Subsequence overlap between prediction and reference.** Finds the longest sequence of words appearing in both (in order, not necessarily adjacent). Measures content recall; popular for summarization. Range 0-1.

### Self-Consistency
Judge pattern: run the same judge prompt `k` times (with slight temperature variation) and take the median score. Reduces variance from stochastic judge sampling. Cost: `k×` tokens.

### Spearman Correlation
**Pearson correlation computed on ranks rather than raw values.** Measures monotonic agreement between two orderings. Robust to outliers; doesn't assume linearity. Used in our calibration harness to measure judge-vs-human agreement.

### Verbosity Bias (LLM-judge)
Known tendency of judges to prefer longer responses even when shorter ones are equally correct. Mitigated by explicit prompt instruction ("do not reward verbosity") and by including verbosity-varied test cases in the calibration gold set.

---

*Last updated: April 2026. If you add a new evaluator or metric, extend this file — it's the canonical reference both for developers and for anyone evaluating the project.*
