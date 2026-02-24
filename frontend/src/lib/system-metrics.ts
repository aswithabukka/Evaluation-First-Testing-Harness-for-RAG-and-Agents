import type { SystemType } from "@/types";

export interface MetricConfig {
  key: string;
  label: string;
  color: string;
  threshold: number;
  description: string;
}

export const SYSTEM_TYPE_LABELS: Record<SystemType, string> = {
  rag: "RAG Pipeline",
  agent: "AI Agent",
  chatbot: "Chatbot",
  code_gen: "Code Generation",
  search: "Search / IR",
  classification: "Classification",
  summarization: "Summarization",
  translation: "Translation",
  custom: "Custom",
};

export const SYSTEM_TYPE_COLORS: Record<SystemType, string> = {
  rag: "bg-blue-100 text-blue-700 border-blue-200",
  agent: "bg-purple-100 text-purple-700 border-purple-200",
  chatbot: "bg-pink-100 text-pink-700 border-pink-200",
  code_gen: "bg-amber-100 text-amber-700 border-amber-200",
  search: "bg-teal-100 text-teal-700 border-teal-200",
  classification: "bg-orange-100 text-orange-700 border-orange-200",
  summarization: "bg-indigo-100 text-indigo-700 border-indigo-200",
  translation: "bg-emerald-100 text-emerald-700 border-emerald-200",
  custom: "bg-gray-100 text-gray-700 border-gray-200",
};

export const SYSTEM_TYPE_ICONS: Record<SystemType, string> = {
  rag: "🔍",
  agent: "🤖",
  chatbot: "💬",
  code_gen: "💻",
  search: "🔎",
  classification: "🏷️",
  summarization: "📝",
  translation: "🌐",
  custom: "⚙️",
};

// ── RAG metrics (RAGAS framework) ──────────────────────────────────
const RAG_METRICS: MetricConfig[] = [
  {
    key: "pass_rate",
    label: "Pass Rate",
    color: "#ef4444",
    threshold: 0.8,
    description: "% of test cases where all thresholds and rules pass.",
  },
  {
    key: "faithfulness",
    label: "Faithfulness",
    color: "#0ea5e9",
    threshold: 0.7,
    description:
      "Does the answer contain only facts from the retrieved context? (RAGAS)",
  },
  {
    key: "answer_relevancy",
    label: "Answer Relevancy",
    color: "#8b5cf6",
    threshold: 0.7,
    description:
      "Is the answer on-topic and directly responsive to the question? (RAGAS)",
  },
  {
    key: "context_precision",
    label: "Context Precision",
    color: "#f59e0b",
    threshold: 0.6,
    description: "Are the retrieved chunks actually useful? (RAGAS)",
  },
  {
    key: "context_recall",
    label: "Context Recall",
    color: "#10b981",
    threshold: 0.6,
    description:
      "Did retrieval surface all the chunks needed? (RAGAS)",
  },
];

// ── Agent metrics ──────────────────────────────────────────────────
const AGENT_METRICS: MetricConfig[] = [
  { key: "pass_rate", label: "Pass Rate", color: "#ef4444", threshold: 0.8, description: "% of test cases passing all rules." },
  { key: "tool_call_f1", label: "Tool Call F1", color: "#8b5cf6", threshold: 0.7, description: "F1 of predicted vs expected tool calls." },
  { key: "tool_call_accuracy", label: "Tool Accuracy", color: "#0ea5e9", threshold: 0.7, description: "Exact match of the tool call set." },
  { key: "goal_accuracy", label: "Goal Accuracy", color: "#10b981", threshold: 0.7, description: "Did the agent achieve the stated goal?" },
  { key: "step_efficiency", label: "Step Efficiency", color: "#f59e0b", threshold: 0.5, description: "Ratio of minimum required steps to actual steps taken." },
];

// ── Chatbot metrics ────────────────────────────────────────────────
const CHATBOT_METRICS: MetricConfig[] = [
  { key: "pass_rate", label: "Pass Rate", color: "#ef4444", threshold: 0.8, description: "% of conversations passing all rules." },
  { key: "coherence", label: "Coherence", color: "#0ea5e9", threshold: 0.6, description: "Contextual n-gram overlap between consecutive turns." },
  { key: "knowledge_retention", label: "Knowledge Retention", color: "#8b5cf6", threshold: 0.6, description: "Fraction of required facts the bot recalled." },
  { key: "role_adherence", label: "Role Adherence", color: "#10b981", threshold: 0.7, description: "Does the bot stay in character (required/disallowed keywords)?" },
  { key: "response_relevance", label: "Response Relevance", color: "#f59e0b", threshold: 0.5, description: "Overlap between user query and bot response." },
];

// ── Code generation metrics ────────────────────────────────────────
const CODE_GEN_METRICS: MetricConfig[] = [
  { key: "pass_rate", label: "Pass Rate", color: "#ef4444", threshold: 0.8, description: "% of test cases passing all rules." },
  { key: "pass_at_k", label: "pass@k", color: "#0ea5e9", threshold: 0.5, description: "Unbiased estimator of pass@k (Chen et al., 2021 — HumanEval)." },
  { key: "syntax_valid", label: "Syntax Valid", color: "#10b981", threshold: 0.9, description: "Fraction of outputs that compile as valid Python." },
  { key: "security_score", label: "Security Score", color: "#8b5cf6", threshold: 0.7, description: "1.0 = clean code, 0.0 = many dangerous patterns." },
  { key: "has_code_block", label: "Code Block", color: "#f59e0b", threshold: 0.8, description: "Fraction of outputs containing fenced code blocks." },
];

// ── Search / IR metrics ────────────────────────────────────────────
const SEARCH_METRICS: MetricConfig[] = [
  { key: "pass_rate", label: "Pass Rate", color: "#ef4444", threshold: 0.8, description: "% of queries passing all rules." },
  { key: "ndcg_at_k", label: "NDCG@k", color: "#0ea5e9", threshold: 0.5, description: "Normalised Discounted Cumulative Gain (BEIR standard)." },
  { key: "map_at_k", label: "MAP@k", color: "#8b5cf6", threshold: 0.5, description: "Mean Average Precision at k (TREC standard)." },
  { key: "mrr", label: "MRR", color: "#10b981", threshold: 0.5, description: "Mean Reciprocal Rank of first relevant result." },
  { key: "recall_at_k", label: "Recall@k", color: "#f59e0b", threshold: 0.5, description: "Fraction of relevant docs in top-k." },
];

// ── Classification metrics ─────────────────────────────────────────
const CLASSIFICATION_METRICS: MetricConfig[] = [
  { key: "pass_rate", label: "Pass Rate", color: "#ef4444", threshold: 0.8, description: "% of samples passing all rules." },
  { key: "macro_f1", label: "Macro F1", color: "#0ea5e9", threshold: 0.7, description: "Per-class F1 averaged equally." },
  { key: "micro_f1", label: "Micro F1", color: "#8b5cf6", threshold: 0.7, description: "Global TP/FP/FN aggregated F1." },
  { key: "accuracy", label: "Accuracy", color: "#10b981", threshold: 0.7, description: "Exact-match accuracy." },
  { key: "auc_roc", label: "AUC-ROC", color: "#f59e0b", threshold: 0.7, description: "Area under the ROC curve (binary)." },
];

// ── Summarization metrics ──────────────────────────────────────────
const SUMMARIZATION_METRICS: MetricConfig[] = [
  { key: "pass_rate", label: "Pass Rate", color: "#ef4444", threshold: 0.8, description: "% of summaries passing all rules." },
  { key: "rouge_1", label: "ROUGE-1", color: "#0ea5e9", threshold: 0.3, description: "Unigram overlap F1 (Lin, 2004)." },
  { key: "rouge_2", label: "ROUGE-2", color: "#8b5cf6", threshold: 0.2, description: "Bigram overlap F1 (Lin, 2004)." },
  { key: "rouge_l", label: "ROUGE-L", color: "#10b981", threshold: 0.3, description: "LCS-based F1 score." },
  { key: "bert_score", label: "BERTScore", color: "#f59e0b", threshold: 0.6, description: "Contextual embedding similarity (Zhang et al., 2020)." },
];

// ── Translation metrics ────────────────────────────────────────────
const TRANSLATION_METRICS: MetricConfig[] = [
  { key: "pass_rate", label: "Pass Rate", color: "#ef4444", threshold: 0.8, description: "% of translations passing all rules." },
  { key: "sacrebleu", label: "SacreBLEU", color: "#0ea5e9", threshold: 0.3, description: "Detokenized BLEU (Post, 2018)." },
  { key: "chrf_plus_plus", label: "chrF++", color: "#8b5cf6", threshold: 0.4, description: "Character + word n-gram F-score (Popović, 2017)." },
  { key: "comet", label: "COMET", color: "#10b981", threshold: 0.7, description: "Neural MT evaluation (Rei et al., 2020)." },
  { key: "ter", label: "TER ↓", color: "#f59e0b", threshold: 0.5, description: "Translation Edit Rate (lower is better)." },
];

// ── Custom / fallback (same as RAG) ────────────────────────────────
const CUSTOM_METRICS = RAG_METRICS;

// ── Master lookup ──────────────────────────────────────────────────
export const METRICS_BY_SYSTEM_TYPE: Record<SystemType, MetricConfig[]> = {
  rag: RAG_METRICS,
  agent: AGENT_METRICS,
  chatbot: CHATBOT_METRICS,
  code_gen: CODE_GEN_METRICS,
  search: SEARCH_METRICS,
  classification: CLASSIFICATION_METRICS,
  summarization: SUMMARIZATION_METRICS,
  translation: TRANSLATION_METRICS,
  custom: CUSTOM_METRICS,
};

/**
 * Get metric configs for a system type, falling back to RAG metrics.
 */
export function getMetricsForSystemType(
  systemType: SystemType | undefined | null
): MetricConfig[] {
  return METRICS_BY_SYSTEM_TYPE[systemType ?? "rag"] ?? RAG_METRICS;
}

/**
 * Extract a metric value from an EvaluationResult, checking both the
 * top-level RAG fields and the extended_metrics JSONB.
 */
export function getMetricValue(
  result: Record<string, unknown>,
  key: string
): number | null {
  // Check top-level RAG fields first
  if (key in result && result[key] !== undefined) {
    const val = result[key];
    return typeof val === "number" ? val : null;
  }
  // Check extended_metrics
  const ext = result.extended_metrics as Record<string, unknown> | undefined;
  if (ext && key in ext) {
    const val = ext[key];
    return typeof val === "number" ? val : null;
  }
  return null;
}

/**
 * Get the per-case result table columns for a system type.
 * Returns [label, metricKey] pairs.
 */
export function getResultColumns(
  systemType: SystemType | undefined | null
): Array<{ label: string; key: string }> {
  const st = systemType ?? "rag";
  switch (st) {
    case "rag":
      return [
        { label: "Faithfulness", key: "faithfulness" },
        { label: "Relevancy", key: "answer_relevancy" },
        { label: "Precision", key: "context_precision" },
        { label: "Recall", key: "context_recall" },
      ];
    case "agent":
      return [
        { label: "Tool F1", key: "tool_call_f1" },
        { label: "Tool Acc", key: "tool_call_accuracy" },
        { label: "Goal Acc", key: "goal_accuracy" },
        { label: "Efficiency", key: "step_efficiency" },
      ];
    case "chatbot":
      return [
        { label: "Coherence", key: "coherence" },
        { label: "Knowledge", key: "knowledge_retention" },
        { label: "Role", key: "role_adherence" },
        { label: "Relevance", key: "response_relevance" },
      ];
    case "code_gen":
      return [
        { label: "pass@k", key: "pass_at_k" },
        { label: "Syntax", key: "syntax_valid" },
        { label: "Security", key: "security_score" },
        { label: "Code Block", key: "has_code_block" },
      ];
    case "search":
      return [
        { label: "NDCG@k", key: "ndcg_at_k" },
        { label: "MAP@k", key: "map_at_k" },
        { label: "MRR", key: "mrr" },
        { label: "Recall@k", key: "recall_at_k" },
      ];
    case "classification":
      return [
        { label: "Precision", key: "precision" },
        { label: "Recall", key: "recall" },
        { label: "F1", key: "f1" },
        { label: "Accuracy", key: "accuracy" },
      ];
    case "summarization":
      return [
        { label: "ROUGE-1", key: "rouge_1" },
        { label: "ROUGE-2", key: "rouge_2" },
        { label: "ROUGE-L", key: "rouge_l" },
        { label: "BERTScore", key: "bert_score" },
      ];
    case "translation":
      return [
        { label: "SacreBLEU", key: "sacrebleu" },
        { label: "chrF++", key: "chrf_plus_plus" },
        { label: "COMET", key: "comet" },
        { label: "TER", key: "ter" },
      ];
    default:
      return [
        { label: "Faithfulness", key: "faithfulness" },
        { label: "Relevancy", key: "answer_relevancy" },
        { label: "Precision", key: "context_precision" },
        { label: "Recall", key: "context_recall" },
      ];
  }
}
