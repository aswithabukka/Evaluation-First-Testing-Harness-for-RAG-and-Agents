export type SystemType =
  | "rag"
  | "agent"
  | "chatbot"
  | "code_gen"
  | "search"
  | "classification"
  | "summarization"
  | "translation"
  | "custom";

export interface TestSet {
  id: string;
  name: string;
  description: string | null;
  system_type: SystemType;
  version: string;
  created_at: string;
  updated_at: string;
  test_case_count: number;
  last_run_status: string | null;
}

export interface FailureRule {
  type: string;
  value?: string;
  tool?: string;
  threshold?: number;
  pattern?: string;
  plugin_class?: string;
}

export interface TestCase {
  id: string;
  test_set_id: string;
  query: string;
  expected_output: string | null;
  ground_truth: string | null;
  context: string[] | null;
  failure_rules: FailureRule[] | null;
  tags: string[] | null;
  expected_labels: string[] | null;
  expected_ranking: string[] | null;
  conversation_turns: Array<Record<string, unknown>> | null;
  created_at: string;
}

export type RunStatus = "pending" | "running" | "completed" | "failed" | "gate_blocked";

export interface SummaryMetrics {
  total_cases: number;
  passed_cases: number;
  failed_cases: number;
  pass_rate: number;
  avg_faithfulness: number | null;
  avg_answer_relevancy: number | null;
  avg_context_precision: number | null;
  avg_context_recall: number | null;
  [key: string]: number | null | undefined;
}

export interface EvaluationRun {
  id: string;
  test_set_id: string;
  pipeline_version: string | null;
  git_commit_sha: string | null;
  git_branch: string | null;
  git_pr_number: string | null;
  status: RunStatus;
  triggered_by: string;
  started_at: string;
  completed_at: string | null;
  overall_passed: boolean | null;
  gate_threshold_snapshot: Record<string, number> | null;
  summary_metrics: SummaryMetrics | null;
  /** Free-text changelog describing what changed in this version */
  notes: string | null;
  /** Structured pipeline config captured at run time */
  pipeline_config: Record<string, unknown> | null;
  /** Reproducibility manifest: evaluator versions, prompt hashes, seeds, libs. */
  manifest?: RunManifest | null;
  manifest_fingerprint?: string | null;
  /** Cost + time budget outcome. Null when no budget was configured. */
  budget_summary?: BudgetSummary | null;
}

export interface RunManifest {
  version: number;
  sealed_at: number | null;
  commit_sha: string | null;
  evaluators: Array<{ name: string; version: string; class?: string }>;
  prompts: Record<string, { model: string; params: Record<string, unknown> }>;
  libraries: Record<string, string>;
  env: { python?: string; platform?: string; machine?: string };
  seeds: Record<string, number>;
}

export interface BudgetSummary {
  spent_usd: number;
  max_usd: number | null;
  elapsed_seconds: number;
  max_seconds: number | null;
  exceeded: boolean;
  exceeded_reason: string | null;
}

export interface EvaluationResult {
  id: string;
  run_id: string;
  test_case_id: string;
  faithfulness: number | null;
  answer_relevancy: number | null;
  context_precision: number | null;
  context_recall: number | null;
  rules_passed: boolean | null;
  rules_detail: Array<{ rule: FailureRule; passed: boolean; reason: string }> | null;
  llm_judge_score: number | null;
  llm_judge_reasoning: string | null;
  passed: boolean;
  failure_reason: string | null;
  raw_output: string | null;
  raw_contexts: string[] | null;
  tool_calls: Array<{ tool: string; args: Record<string, unknown>; result: unknown }> | null;
  duration_ms: number | null;
  eval_cost_usd: number | null;
  tokens_used: number | null;
  extended_metrics: Record<string, number | string | boolean | null> | null;
  evaluated_at: string;
}

export interface ResultSummary {
  run_id: string;
  total_cases: number;
  passed_cases: number;
  failed_cases: number;
  pass_rate: number;
  avg_faithfulness: number | null;
  avg_answer_relevancy: number | null;
  avg_context_precision: number | null;
  avg_context_recall: number | null;
}

export interface MetricTrendPoint {
  recorded_at: string;
  metric_value: number;
  metric_name: string;
  pipeline_version: string | null;
  git_commit_sha: string | null;
  run_id: string;
}

export interface RegressionItem {
  test_case_id: string;
  query: string;
  failure_reason: string | null;
  current_scores: Record<string, number | null>;
  baseline_scores: Record<string, number | null>;
}

export interface RegressionDiff {
  run_id: string;
  baseline_run_id: string | null;
  regressions: RegressionItem[];
  improvements: RegressionItem[];
  metric_deltas: Record<string, number | null>;
  gate_blocked: boolean;
}

export interface MetricFailure {
  metric: string;
  actual: number;
  threshold: number;
  delta: number;
  // Significance-aware gate fields (nullable for pass_rate, where there's
  // no per-case distribution to bootstrap).
  ci_lower?: number | null;
  ci_upper?: number | null;
  p_value?: number | null;
  sample_size?: number;
  baseline_size?: number;
  reason?: string;
}

export interface GateDecision {
  passed: boolean | null;
  run_id: string;
  metric_failures: MetricFailure[];
  rule_failures: Array<{
    result_id: string;
    test_case_id: string;
    rules_detail: unknown;
  }>;
  baseline_run_id?: string | null;
}

// Production traffic types
export type IngestionStatus = "received" | "sampled" | "skipped" | "evaluated";

export interface ProductionLog {
  id: string;
  source: string;
  query: string;
  answer: string;
  is_error: boolean;
  status: IngestionStatus;
  confidence_score: number | null;
  user_feedback: string | null;
  ingested_at: string;
  sampled_into_test_set_id: string | null;
  evaluation_run_id: string | null;
}

export interface IngestResponse {
  ingested: number;
  sampled: number;
  skipped: number;
}

export interface SamplingStats {
  source: string;
  total_received: number;
  total_sampled: number;
  total_skipped: number;
  total_evaluated: number;
  sampling_rate: number;
  error_sampling_rate: number;
}

// Playground types
export interface PlaygroundSystem {
  system_type: string;
  name: string;
  description: string;
  icon: string;
  color: string;
  sample_queries: string[];
}

export interface PlaygroundToolCall {
  tool: string;
  args: Record<string, unknown>;
  result: Record<string, unknown> | null;
}

export interface PlaygroundInteraction {
  answer: string;
  retrieved_contexts: string[];
  tool_calls: PlaygroundToolCall[];
  turn_history: Array<{ role: string; content: string }>;
  metadata: Record<string, unknown>;
  session_id: string | null;
}
