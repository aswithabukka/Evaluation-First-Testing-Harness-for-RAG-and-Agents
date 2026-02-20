export interface TestSet {
  id: string;
  name: string;
  description: string | null;
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

export interface GateDecision {
  passed: boolean | null;
  run_id: string;
  metric_failures: Array<{
    metric: string;
    actual: number;
    threshold: number;
    delta: number;
  }>;
  rule_failures: Array<{
    result_id: string;
    test_case_id: string;
    rules_detail: unknown;
  }>;
}
