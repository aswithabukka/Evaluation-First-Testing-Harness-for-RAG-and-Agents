"use client";
import React from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import useSWR from "swr";
import { useState } from "react";
import { api } from "@/lib/api";
import { formatDate, formatDuration, formatScore, formatPercent, truncate, passColor } from "@/lib/utils";
import { Badge } from "@/components/ui/Badge";
import { Card, CardHeader, CardBody } from "@/components/ui/Card";
import { PageLoader } from "@/components/ui/LoadingSpinner";
import {
  getMetricsForSystemType,
  getResultColumns,
  getMetricValue,
  SYSTEM_TYPE_LABELS,
  SYSTEM_TYPE_ICONS,
  SYSTEM_TYPE_COLORS,
} from "@/lib/system-metrics";
import type { EvaluationResult, RegressionItem, RunStatus, TestCase, SystemType } from "@/types";

const statusVariant: Record<RunStatus, "green" | "red" | "yellow" | "blue" | "orange"> = {
  completed: "green",
  gate_blocked: "orange",
  failed: "red",
  running: "blue",
  pending: "yellow",
};

function MetricGauge({ label, value, threshold = 0.7, color }: { label: string; value: number | null | undefined; threshold?: number; color?: string }) {
  const pct = value !== null && value !== undefined ? Math.round(value * 100) : null;
  const passing = pct !== null && value! >= threshold;
  return (
    <div className="text-center">
      <p className="text-xs text-gray-500 mb-1">{label}</p>
      <p className={`text-lg font-bold ${passing ? "text-green-600" : pct === null ? "text-gray-300" : "text-red-600"}`}>
        {pct !== null ? `${pct}%` : "—"}
      </p>
      {pct !== null && (
        <div className="mt-1 h-1 bg-gray-100 rounded-full overflow-hidden w-16 mx-auto">
          <div
            className="h-full rounded-full"
            style={{
              width: `${pct}%`,
              backgroundColor: passing ? (color ?? "#22c55e") : "#ef4444",
            }}
          />
        </div>
      )}
    </div>
  );
}

/* ─── Side-by-side response diff panel ─────────────────────────────── */
function ScoreRow({ label, current, baseline }: { label: string; current: number | null; baseline: number | null }) {
  const delta = current !== null && baseline !== null ? current - baseline : null;
  return (
    <div className="flex items-center justify-between text-xs">
      <span className="text-gray-500">{label}</span>
      <span className="font-mono">
        {current !== null ? current.toFixed(3) : "—"}
        {delta !== null && (
          <span className={`ml-1.5 ${delta < 0 ? "text-red-500" : "text-green-500"}`}>
            ({delta > 0 ? "+" : ""}{delta.toFixed(3)})
          </span>
        )}
      </span>
    </div>
  );
}

function ResponseDiffPanel({
  reg,
  currentResult,
  baselineResult,
  currentRunId,
  baselineRunId,
  columns,
}: {
  reg: RegressionItem;
  currentResult: EvaluationResult | undefined;
  baselineResult: EvaluationResult | undefined;
  currentRunId: string;
  baselineRunId: string;
  columns: Array<{ label: string; key: string }>;
}) {
  return (
    <div className="grid grid-cols-2 gap-4 p-4 bg-gray-50 text-xs">
      {/* Current */}
      <div className="space-y-2">
        <div className="flex items-center gap-2 mb-2">
          <span className="font-semibold text-red-700">Current</span>
          <span className="font-mono text-gray-400">{currentRunId.slice(0, 8)}…</span>
        </div>
        <div className="space-y-1 mb-3">
          {columns.slice(0, 3).map((col) => (
            <ScoreRow
              key={col.key}
              label={col.label}
              current={currentResult ? getMetricValue(currentResult as unknown as Record<string, unknown>, col.key) : null}
              baseline={baselineResult ? getMetricValue(baselineResult as unknown as Record<string, unknown>, col.key) : null}
            />
          ))}
        </div>
        <div className="bg-red-50 border border-red-100 rounded p-3 whitespace-pre-wrap font-mono leading-relaxed min-h-16">
          {currentResult?.raw_output ?? <span className="text-gray-400 italic">No output recorded</span>}
        </div>
      </div>

      {/* Baseline */}
      <div className="space-y-2">
        <div className="flex items-center gap-2 mb-2">
          <span className="font-semibold text-green-700">Baseline</span>
          <span className="font-mono text-gray-400">{baselineRunId.slice(0, 8)}…</span>
        </div>
        <div className="space-y-1 mb-3">
          {columns.slice(0, 3).map((col) => (
            <ScoreRow
              key={col.key}
              label={col.label}
              current={baselineResult ? getMetricValue(baselineResult as unknown as Record<string, unknown>, col.key) : null}
              baseline={null}
            />
          ))}
        </div>
        <div className="bg-green-50 border border-green-100 rounded p-3 whitespace-pre-wrap font-mono leading-relaxed min-h-16">
          {baselineResult?.raw_output ?? <span className="text-gray-400 italic">No output recorded</span>}
        </div>
      </div>
    </div>
  );
}

/* ─── Expandable result detail panel ──────────────────────────────────── */
function ResultDetailPanel({ result, testCase }: { result: EvaluationResult; testCase: TestCase | undefined }) {
  return (
    <div className="bg-gray-50 border-t border-gray-100 px-4 py-5 space-y-4 text-xs">
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* Left column: question + ground truth */}
        <div className="space-y-3">
          <div>
            <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1">Question</p>
            <p className="text-gray-900 bg-white border border-gray-200 rounded p-3 leading-relaxed">
              {testCase?.query ?? <span className="italic text-gray-400">—</span>}
            </p>
          </div>
          <div>
            <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1">Ground Truth</p>
            <p className="text-gray-700 bg-white border border-gray-200 rounded p-3 leading-relaxed">
              {testCase?.ground_truth ?? <span className="italic text-gray-400">not set</span>}
            </p>
          </div>
        </div>

        {/* Right column: pipeline answer */}
        <div className="space-y-3">
          <div>
            <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1">Pipeline Answer</p>
            <p className={`bg-white border rounded p-3 leading-relaxed whitespace-pre-wrap ${result.passed ? "border-green-200" : "border-red-200"}`}>
              {result.raw_output ?? <span className="italic text-gray-400">No output recorded</span>}
            </p>
          </div>
          {result.failure_reason && (
            <div>
              <p className="text-xs font-semibold text-red-500 uppercase tracking-wide mb-1">Failure Reason</p>
              <p className="text-red-700 bg-red-50 border border-red-100 rounded p-3">{result.failure_reason}</p>
            </div>
          )}
        </div>
      </div>

      {/* Tool calls (for agent systems) */}
      {result.tool_calls && result.tool_calls.length > 0 && (
        <div>
          <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">
            Tool Calls ({result.tool_calls.length})
          </p>
          <div className="space-y-2">
            {result.tool_calls.map((tc, i) => (
              <div key={i} className="bg-purple-50 border border-purple-100 rounded p-3 leading-relaxed">
                <span className="text-purple-600 font-semibold mr-2">{tc.tool}</span>
                <span className="text-gray-500 font-mono text-xs">{JSON.stringify(tc.args)}</span>
                {tc.result !== undefined && (
                  <div className="mt-1 text-gray-700 font-mono">→ {String(tc.result)}</div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Extended metrics (for non-RAG systems) */}
      {result.extended_metrics && Object.keys(result.extended_metrics).length > 0 && (
        <div>
          <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">Extended Metrics</p>
          <div className="flex flex-wrap gap-2">
            {Object.entries(result.extended_metrics).map(([k, v]) => (
              <span key={k} className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full bg-gray-100 text-xs font-medium text-gray-700">
                <span className="text-gray-400">{k}:</span>
                <span className="font-mono">{v !== null && v !== undefined ? String(typeof v === "number" ? v.toFixed(3) : v) : "—"}</span>
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Retrieved contexts */}
      {result.raw_contexts && result.raw_contexts.length > 0 && (
        <div>
          <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">
            Retrieved Contexts ({result.raw_contexts.length})
          </p>
          <div className="space-y-2">
            {result.raw_contexts.map((ctx, i) => (
              <div key={i} className="bg-blue-50 border border-blue-100 rounded p-3 leading-relaxed">
                <span className="text-blue-400 font-semibold mr-2">[{i + 1}]</span>
                {ctx}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

export default function RunDetailPage() {
  const { id } = useParams<{ id: string }>();
  const [expandedReg, setExpandedReg] = useState<string | null>(null);
  const [expandedResult, setExpandedResult] = useState<string | null>(null);
  const [showImprovements, setShowImprovements] = useState(false);

  const { data: run, isLoading: runLoading } = useSWR(`run-${id}`, () => api.runs.get(id), {
    refreshInterval: (run) =>
      run?.status === "running" || run?.status === "pending" ? 5000 : 0,
  });
  const { data: results, isLoading: resultsLoading } = useSWR(
    run ? `results-${id}` : null,
    () => api.results.list(id, { limit: 200 })
  );
  const { data: testCases } = useSWR(
    run?.test_set_id ? `test-cases-${run.test_set_id}` : null,
    () => api.testCases.list(run!.test_set_id, 0, 200)
  );
  // Fetch test set to get system_type
  const { data: testSet } = useSWR(
    run?.test_set_id ? `test-set-${run.test_set_id}` : null,
    () => api.testSets.get(run!.test_set_id)
  );
  const { data: diff } = useSWR(
    run?.status === "completed" || run?.status === "gate_blocked" ? `diff-${id}` : null,
    () => api.runs.getDiff(id)
  );
  const { data: baselineResults } = useSWR(
    diff?.baseline_run_id ? `results-${diff.baseline_run_id}` : null,
    () => api.results.list(diff!.baseline_run_id!, { limit: 200 })
  );
  const { data: baselineRun } = useSWR(
    diff?.baseline_run_id ? `baseline-run-${diff.baseline_run_id}` : null,
    () => api.runs.get(diff!.baseline_run_id!)
  );

  if (runLoading) return <PageLoader />;
  if (!run) return <p className="p-6 text-gray-500">Run not found.</p>;

  const systemType = (testSet?.system_type ?? "rag") as SystemType;
  const metricConfigs = getMetricsForSystemType(systemType);
  const resultColumns = getResultColumns(systemType);

  const sm = run.summary_metrics;
  const thresholds = run.gate_threshold_snapshot ?? {};
  const pc = run.pipeline_config;
  const pipelineVersionDisplay = run.pipeline_version
    ?? (pc ? `${String(pc.adapter ?? "pipeline")}/${String(pc.model ?? "?")}` : null)
    ?? "—";
  const runDurationMs = run.completed_at
    ? new Date(run.completed_at).getTime() - new Date(run.started_at).getTime()
    : null;

  const currentByCase = new Map<string, EvaluationResult>(
    (results ?? []).map((r) => [r.test_case_id, r])
  );
  const baselineByCase = new Map<string, EvaluationResult>(
    (baselineResults ?? []).map((r) => [r.test_case_id, r])
  );
  const caseById = new Map<string, TestCase>(
    (testCases ?? []).map((tc) => [tc.id, tc])
  );

  /** Get a metric value from the summary_metrics, checking both named fields and index signature */
  function getSummaryMetric(key: string): number | null {
    if (!sm) return null;
    // Check known fields with avg_ prefix
    const avgKey = `avg_${key}`;
    if (avgKey in sm && sm[avgKey] !== undefined) return sm[avgKey] ?? null;
    if (key in sm && sm[key] !== undefined) return sm[key] ?? null;
    return null;
  }

  const totalCols = resultColumns.length + 4; // Result, Question, Rules, Duration, Details + metric cols

  return (
    <div className="p-6 space-y-6 max-w-6xl mx-auto">
      {/* Header */}
      <div>
        <div className="flex items-center gap-2 text-sm text-gray-400 mb-1">
          <Link href="/runs" className="hover:text-gray-600">Runs</Link>
          <span>/</span>
          <span className="text-gray-700 font-mono text-xs">{id.slice(0, 8)}…</span>
        </div>
        <div className="flex items-center gap-3">
          <h1 className="text-xl font-bold text-gray-900">Run Detail</h1>
          <Badge variant={statusVariant[run.status] ?? "gray"}>
            {run.status.replace("_", " ")}
          </Badge>
          <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium border ${SYSTEM_TYPE_COLORS[systemType]}`}>
            <span>{SYSTEM_TYPE_ICONS[systemType]}</span>
            {SYSTEM_TYPE_LABELS[systemType]}
          </span>
          {(run.status === "completed" || run.status === "gate_blocked") && (
            <div className="ml-auto flex items-center gap-2">
              <button
                onClick={() => api.results.export(id, "csv")}
                className="px-3 py-1.5 text-xs font-medium text-gray-700 bg-white border border-gray-300 rounded-md hover:bg-gray-50"
              >
                Export CSV
              </button>
              <button
                onClick={() => api.results.export(id, "json")}
                className="px-3 py-1.5 text-xs font-medium text-gray-700 bg-white border border-gray-300 rounded-md hover:bg-gray-50"
              >
                Export JSON
              </button>
            </div>
          )}
        </div>
        <p className="text-sm text-gray-500 mt-0.5">
          <span className="font-medium text-gray-700">{pipelineVersionDisplay}</span>
          {" · "}Branch: {run.git_branch ?? "—"} · Commit: {run.git_commit_sha?.slice(0, 7) ?? "—"} · Started {formatDate(run.started_at)}
        </p>
      </div>

      {/* Pipeline & Run Info */}
      <Card>
        <CardHeader>
          <h2 className="text-sm font-semibold text-gray-900">Pipeline &amp; Run Info</h2>
        </CardHeader>
        <CardBody>
          <div className="space-y-5">
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-x-8 gap-y-5">
              {[
                { label: "Pipeline Version", value: pipelineVersionDisplay },
                { label: "Triggered By", value: run.triggered_by ?? "—" },
                { label: "Git Branch", value: run.git_branch ?? "—" },
                { label: "Git Commit", value: run.git_commit_sha ? run.git_commit_sha.slice(0, 7) : "—", mono: true },
                { label: "Cases Evaluated", value: sm ? `${sm.passed_cases} / ${sm.total_cases} passed` : "—" },
                { label: "Run Duration", value: formatDuration(runDurationMs) },
                { label: "Started", value: formatDate(run.started_at) },
                { label: "Completed", value: run.completed_at ? formatDate(run.completed_at) : "—" },
              ].map(({ label, value, mono }) => (
                <div key={label}>
                  <p className="text-xs text-gray-400 uppercase tracking-wide mb-0.5">{label}</p>
                  <p className={`text-sm font-medium text-gray-900 break-all ${mono ? "font-mono" : ""}`}>{value}</p>
                </div>
              ))}
            </div>

            {run.pipeline_config && Object.keys(run.pipeline_config).length > 0 && (
              <div>
                <p className="text-xs text-gray-400 uppercase tracking-wide mb-2">Pipeline Config</p>
                <div className="flex flex-wrap gap-2">
                  {Object.entries(run.pipeline_config).map(([k, v]) => (
                    <span key={k} className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full bg-gray-100 text-xs font-medium text-gray-700">
                      <span className="text-gray-400">{k}:</span>
                      <span className="font-mono">{String(v)}</span>
                    </span>
                  ))}
                </div>
              </div>
            )}

            {run.notes && (
              <div>
                <p className="text-xs text-gray-400 uppercase tracking-wide mb-1">What changed</p>
                <p className="text-sm text-gray-700 bg-amber-50 border border-amber-100 rounded-md px-3 py-2.5 leading-relaxed whitespace-pre-wrap">
                  {run.notes}
                </p>
              </div>
            )}
          </div>
        </CardBody>
      </Card>

      {/* Changes vs Baseline — dynamic metric columns */}
      {baselineRun && sm && (
        <Card className="border-blue-200">
          <CardHeader>
            <div className="flex items-center justify-between flex-wrap gap-2">
              <h2 className="text-sm font-semibold text-blue-800">Changes vs Baseline Run</h2>
              <Link
                href={`/runs/${baselineRun.id}`}
                className="text-xs text-gray-400 hover:text-blue-600 font-mono"
              >
                {baselineRun.id.slice(0, 8)}… · {formatDate(baselineRun.started_at)}
              </Link>
            </div>
            {(baselineRun.pipeline_version ?? null) !== (run.pipeline_version ?? null) && (
              <p className="text-xs text-gray-500 mt-1.5">
                Pipeline version:{" "}
                <code className="font-mono bg-gray-100 px-1 rounded">{baselineRun.pipeline_version ?? "unversioned"}</code>
                {" → "}
                <code className="font-mono bg-gray-100 px-1 rounded">{run.pipeline_version ?? "unversioned"}</code>
              </p>
            )}
            {(baselineRun.notes || run.notes) && (
              <div className="mt-3 grid grid-cols-2 gap-3">
                <div>
                  <p className="text-xs text-gray-400 uppercase tracking-wide mb-1">Baseline notes</p>
                  <p className="text-xs text-gray-600 bg-gray-50 border border-gray-100 rounded px-2.5 py-2 leading-relaxed whitespace-pre-wrap min-h-8">
                    {baselineRun.notes ?? <span className="italic text-gray-300">no notes recorded</span>}
                  </p>
                </div>
                <div>
                  <p className="text-xs text-gray-400 uppercase tracking-wide mb-1">Current notes</p>
                  <p className="text-xs text-gray-700 bg-amber-50 border border-amber-100 rounded px-2.5 py-2 leading-relaxed whitespace-pre-wrap min-h-8">
                    {run.notes ?? <span className="italic text-gray-300">no notes recorded</span>}
                  </p>
                </div>
              </div>
            )}
          </CardHeader>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-100">
                  {["Metric", "Baseline", "Current", "Change"].map((h) => (
                    <th key={h} className="px-4 py-2.5 text-left text-xs font-medium text-gray-500 uppercase tracking-wide">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-50">
                {metricConfigs.map((mc) => {
                  const bsm = baselineRun.summary_metrics;
                  const curr = getSummaryMetric(mc.key);
                  const base = bsm ? (bsm[`avg_${mc.key}`] ?? bsm[mc.key] ?? null) : null;
                  const delta = base !== null && curr !== null ? curr - base : null;
                  return (
                    <tr key={mc.key} className="hover:bg-blue-50/40">
                      <td className="px-4 py-3 text-xs font-medium text-gray-700">
                        <span className="inline-block w-2 h-2 rounded-full mr-2" style={{ backgroundColor: mc.color }} />
                        {mc.label}
                      </td>
                      <td className="px-4 py-3 text-xs font-mono text-gray-500">{formatPercent(base)}</td>
                      <td className="px-4 py-3 text-xs font-mono font-semibold text-gray-900">{formatPercent(curr)}</td>
                      <td className="px-4 py-3 text-xs font-mono">
                        {delta === null ? (
                          <span className="text-gray-300">—</span>
                        ) : Math.abs(delta) < 0.0001 ? (
                          <span className="text-gray-400">→ no change</span>
                        ) : delta > 0 ? (
                          <span className="text-green-600">↑ +{(delta * 100).toFixed(1)}%</span>
                        ) : (
                          <span className="text-red-600">↓ {(delta * 100).toFixed(1)}%</span>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      {/* Metric Gauges — dynamic based on system type */}
      {sm && (
        <Card>
          <CardBody>
            <div className={`grid grid-cols-2 sm:grid-cols-${Math.min(metricConfigs.length, 6)} gap-6 divide-x divide-gray-100`}>
              {metricConfigs.map((mc) => (
                <MetricGauge
                  key={mc.key}
                  label={mc.label}
                  value={getSummaryMetric(mc.key)}
                  threshold={(thresholds as Record<string, number>)[mc.key] ?? mc.threshold}
                  color={mc.color}
                />
              ))}
            </div>
          </CardBody>
        </Card>
      )}

      {/* Regression Diff — dynamic columns */}
      {diff && diff.regressions.length > 0 && (
        <Card className="border-orange-200">
          <CardHeader>
            <div className="flex items-center justify-between">
              <h2 className="text-sm font-semibold text-orange-700">
                {diff.regressions.length} Regression(s) vs Baseline
              </h2>
              {diff.baseline_run_id && (
                <Link
                  href={`/runs/${diff.baseline_run_id}`}
                  className="text-xs text-gray-500 hover:text-brand-600 font-mono"
                >
                  Baseline: {diff.baseline_run_id.slice(0, 8)}…
                </Link>
              )}
            </div>
          </CardHeader>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-100">
                  <th className="px-4 py-2.5 text-left text-xs font-medium text-gray-500 uppercase tracking-wide">Query</th>
                  <th className="px-4 py-2.5 text-left text-xs font-medium text-gray-500 uppercase tracking-wide">Failure Reason</th>
                  {resultColumns.slice(0, 2).map((col) => (
                    <th key={col.key} className="px-4 py-2.5 text-left text-xs font-medium text-gray-500 uppercase tracking-wide">{col.label} Δ</th>
                  ))}
                  <th className="px-4 py-2.5 text-left text-xs font-medium text-gray-500 uppercase tracking-wide"></th>
                </tr>
              </thead>
              <tbody>
                {diff.regressions.map((reg) => {
                  const isExpanded = expandedReg === reg.test_case_id;
                  return (
                    <React.Fragment key={reg.test_case_id}>
                      <tr className={`border-b border-gray-50 hover:bg-orange-50 ${isExpanded ? "bg-orange-50" : ""}`}>
                        <td className="px-4 py-3 text-xs max-w-xs">{truncate(reg.query, 80)}</td>
                        <td className="px-4 py-3 text-xs text-red-600">{reg.failure_reason ?? "threshold breach"}</td>
                        {resultColumns.slice(0, 2).map((col) => {
                          const delta = (reg.current_scores[col.key] ?? 0) - (reg.baseline_scores[col.key] ?? 0);
                          return (
                            <td key={col.key} className={`px-4 py-3 text-xs font-mono ${delta < 0 ? "text-red-600" : "text-green-600"}`}>
                              {delta > 0 ? "+" : ""}{delta.toFixed(3)}
                            </td>
                          );
                        })}
                        <td className="px-4 py-3">
                          <button
                            onClick={() => setExpandedReg(isExpanded ? null : reg.test_case_id)}
                            className="text-xs px-2.5 py-1 border border-orange-200 rounded hover:bg-orange-100 text-orange-700 whitespace-nowrap"
                          >
                            {isExpanded ? "Hide" : "Compare"}
                          </button>
                        </td>
                      </tr>
                      {isExpanded && diff.baseline_run_id && (
                        <tr key={`${reg.test_case_id}-expand`} className="border-b border-orange-100">
                          <td colSpan={resultColumns.slice(0, 2).length + 3} className="p-0">
                            <ResponseDiffPanel
                              reg={reg}
                              currentResult={currentByCase.get(reg.test_case_id)}
                              baselineResult={baselineByCase.get(reg.test_case_id)}
                              currentRunId={id}
                              baselineRunId={diff.baseline_run_id}
                              columns={resultColumns}
                            />
                          </td>
                        </tr>
                      )}
                    </React.Fragment>
                  );
                })}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      {/* Improvements (collapsible) — dynamic columns */}
      {diff && diff.improvements.length > 0 && (
        <Card className="border-green-200">
          <CardHeader>
            <button
              onClick={() => setShowImprovements(!showImprovements)}
              className="flex items-center justify-between w-full text-left"
            >
              <h2 className="text-sm font-semibold text-green-700">
                {diff.improvements.length} Improvement(s) vs Baseline
              </h2>
              <span className="text-xs text-gray-400">{showImprovements ? "hide" : "show"}</span>
            </button>
          </CardHeader>
          {showImprovements && (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-gray-100">
                    <th className="px-4 py-2.5 text-left text-xs font-medium text-gray-500 uppercase tracking-wide">Query</th>
                    {resultColumns.slice(0, 2).map((col) => (
                      <th key={col.key} className="px-4 py-2.5 text-left text-xs font-medium text-gray-500 uppercase tracking-wide">{col.label} Δ</th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-50">
                  {diff.improvements.map((imp) => (
                    <tr key={imp.test_case_id} className="hover:bg-green-50">
                      <td className="px-4 py-3 text-xs max-w-xs">{truncate(imp.query, 80)}</td>
                      {resultColumns.slice(0, 2).map((col) => {
                        const delta = (imp.current_scores[col.key] ?? 0) - (imp.baseline_scores[col.key] ?? 0);
                        return (
                          <td key={col.key} className="px-4 py-3 text-xs font-mono text-green-600">
                            +{delta.toFixed(3)}
                          </td>
                        );
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      )}

      {/* Per-case results — dynamic columns based on system type */}
      <Card>
        <CardHeader>
          <h2 className="text-sm font-semibold text-gray-900">
            Test Case Results ({sm?.passed_cases ?? 0}/{sm?.total_cases ?? 0} passed)
          </h2>
        </CardHeader>
        {resultsLoading ? (
          <CardBody><PageLoader /></CardBody>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-100">
                  <th className="px-3 py-2.5 text-left text-xs font-medium text-gray-500 uppercase tracking-wide">Result</th>
                  <th className="px-3 py-2.5 text-left text-xs font-medium text-gray-500 uppercase tracking-wide">Question</th>
                  {resultColumns.map((col) => (
                    <th key={col.key} className="px-3 py-2.5 text-left text-xs font-medium text-gray-500 uppercase tracking-wide">{col.label}</th>
                  ))}
                  <th className="px-3 py-2.5 text-left text-xs font-medium text-gray-500 uppercase tracking-wide">Rules</th>
                  <th className="px-3 py-2.5 text-left text-xs font-medium text-gray-500 uppercase tracking-wide">Duration</th>
                  <th className="px-3 py-2.5 text-left text-xs font-medium text-gray-500 uppercase tracking-wide"></th>
                </tr>
              </thead>
              <tbody>
                {(results ?? []).map((r) => {
                  const tc = caseById.get(r.test_case_id);
                  const isExpanded = expandedResult === r.id;
                  return (
                    <React.Fragment key={r.id}>
                      <tr
                        className={`border-b border-gray-50 hover:bg-gray-50 ${!r.passed ? "bg-red-50/30" : ""} ${isExpanded ? "bg-blue-50/30" : ""}`}
                      >
                        <td className="px-3 py-3">
                          <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium border ${passColor(r.passed)}`}>
                            {r.passed ? "PASS" : "FAIL"}
                          </span>
                        </td>
                        <td className="px-3 py-3 max-w-xs">
                          <p className="text-xs text-gray-900 font-medium leading-snug">
                            {tc ? truncate(tc.query, 70) : <span className="text-gray-400 font-mono">{r.test_case_id.slice(0, 8)}…</span>}
                          </p>
                          {r.raw_output && (
                            <p className="text-xs text-gray-400 mt-0.5 leading-snug">
                              ↳ {truncate(r.raw_output, 60)}
                            </p>
                          )}
                        </td>
                        {resultColumns.map((col) => (
                          <td key={col.key} className="px-3 py-3 font-mono text-xs">
                            {formatScore(getMetricValue(r as unknown as Record<string, unknown>, col.key))}
                          </td>
                        ))}
                        <td className="px-3 py-3">
                          {r.rules_passed === null ? <span className="text-gray-300">—</span> :
                            r.rules_passed ? <Badge variant="green">OK</Badge> : <Badge variant="red">FAIL</Badge>}
                        </td>
                        <td className="px-3 py-3 text-xs text-gray-400 whitespace-nowrap">{formatDuration(r.duration_ms)}</td>
                        <td className="px-3 py-3">
                          <button
                            onClick={() => setExpandedResult(isExpanded ? null : r.id)}
                            className="text-xs px-2.5 py-1 border border-gray-200 rounded hover:bg-gray-100 text-gray-600 whitespace-nowrap"
                          >
                            {isExpanded ? "Hide" : "Details"}
                          </button>
                        </td>
                      </tr>
                      {isExpanded && (
                        <tr key={`${r.id}-detail`} className="border-b border-blue-100">
                          <td colSpan={totalCols} className="p-0">
                            <ResultDetailPanel result={r} testCase={tc} />
                          </td>
                        </tr>
                      )}
                    </React.Fragment>
                  );
                })}
                {(!results || results.length === 0) && (
                  <tr>
                    <td colSpan={totalCols} className="px-4 py-8 text-center text-gray-400 text-sm">
                      {run.status === "pending" || run.status === "running"
                        ? "Evaluation in progress…"
                        : "No results found."}
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}
