"use client";
import { Suspense } from "react";
import { useSearchParams } from "next/navigation";
import Link from "next/link";
import useSWR from "swr";
import { api } from "@/lib/api";
import { formatDate, formatPercent, formatScore } from "@/lib/utils";
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
import type { EvaluationResult, EvaluationRun, SystemType, TestCase } from "@/types";

const COLORS = ["#3b82f6", "#8b5cf6", "#ec4899", "#14b8a6"];

export default function ComparePage() {
  return (
    <Suspense fallback={<PageLoader />}>
      <ComparePageInner />
    </Suspense>
  );
}

function ComparePageInner() {
  const searchParams = useSearchParams();
  const ids = (searchParams.get("ids") ?? "").split(",").filter(Boolean);

  // Fetch all runs in parallel
  const { data: runs, isLoading: runsLoading } = useSWR(
    ids.length > 0 ? `compare-runs-${ids.join(",")}` : null,
    () => Promise.all(ids.map((id) => api.runs.get(id)))
  );

  // Fetch all results in parallel
  const { data: allResults, isLoading: resultsLoading } = useSWR(
    runs ? `compare-results-${ids.join(",")}` : null,
    () => Promise.all(ids.map((id) => api.results.list(id, { limit: 200 })))
  );

  // Fetch test set for system type
  const firstRun = runs?.[0];
  const { data: testSet } = useSWR(
    firstRun ? `compare-ts-${firstRun.test_set_id}` : null,
    () => api.testSets.get(firstRun!.test_set_id)
  );

  // Fetch test cases for queries
  const { data: testCases } = useSWR(
    firstRun ? `compare-cases-${firstRun.test_set_id}` : null,
    () => api.testCases.list(firstRun!.test_set_id, 0, 200)
  );

  if (ids.length < 2) {
    return (
      <div className="p-6">
        <p className="text-gray-500">Select at least 2 runs to compare. <Link href="/runs" className="text-brand-600 hover:underline">Back to runs</Link></p>
      </div>
    );
  }

  if (runsLoading || resultsLoading) return <PageLoader />;
  if (!runs || !allResults) return <p className="p-6 text-gray-500">Failed to load runs.</p>;

  const systemType = (testSet?.system_type ?? "rag") as SystemType;
  const metricConfigs = getMetricsForSystemType(systemType);
  const resultColumns = getResultColumns(systemType);

  const caseById = new Map<string, TestCase>(
    (testCases ?? []).map((tc) => [tc.id, tc])
  );

  // Build per-run result maps
  const resultMaps = allResults.map((results) =>
    new Map<string, EvaluationResult>(results.map((r) => [r.test_case_id, r]))
  );

  // Collect all test case IDs across all runs
  const allCaseIds = new Set<string>();
  for (const results of allResults) {
    for (const r of results) allCaseIds.add(r.test_case_id);
  }

  return (
    <div className="p-6 space-y-6 max-w-7xl mx-auto">
      {/* Header */}
      <div>
        <div className="flex items-center gap-2 text-sm text-gray-400 mb-1">
          <Link href="/runs" className="hover:text-gray-600">Runs</Link>
          <span>/</span>
          <span className="text-gray-700">Compare ({runs.length} runs)</span>
        </div>
        <h1 className="text-xl font-bold text-gray-900">Side-by-Side Run Comparison</h1>
        <div className="flex items-center gap-2 mt-2">
          <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium border ${SYSTEM_TYPE_COLORS[systemType]}`}>
            <span>{SYSTEM_TYPE_ICONS[systemType]}</span>
            {SYSTEM_TYPE_LABELS[systemType]}
          </span>
          <span className="text-xs text-gray-400">{testSet?.name}</span>
        </div>
      </div>

      {/* Summary Comparison Cards */}
      <div className={`grid grid-cols-${Math.min(runs.length, 4)} gap-4`}>
        {runs.map((run, i) => {
          const sm = run.summary_metrics;
          const passRate = sm?.pass_rate ?? 0;
          return (
            <Card key={run.id} className="relative overflow-hidden">
              <div className="absolute top-0 left-0 right-0 h-1" style={{ backgroundColor: COLORS[i] }} />
              <CardBody>
                <div className="space-y-3">
                  <div className="flex items-center justify-between">
                    <Link href={`/runs/${run.id}`} className="font-mono text-xs text-gray-500 hover:text-brand-600">
                      {run.id.slice(0, 8)}...
                    </Link>
                    <Badge variant={run.overall_passed ? "green" : "orange"}>
                      {run.overall_passed ? "Passed" : "Blocked"}
                    </Badge>
                  </div>
                  <p className="text-xs text-gray-500">
                    {run.pipeline_version ?? "—"} · {formatDate(run.started_at)}
                  </p>
                  <div className="text-center py-2">
                    <p className="text-3xl font-bold" style={{ color: COLORS[i] }}>
                      {formatPercent(passRate)}
                    </p>
                    <p className="text-xs text-gray-500">Pass Rate ({sm?.passed_cases ?? 0}/{sm?.total_cases ?? 0})</p>
                  </div>
                  <div className="grid grid-cols-2 gap-2">
                    {metricConfigs.slice(1).map((mc) => {
                      const val = sm?.[`avg_${mc.key}`] ?? sm?.[mc.key] ?? null;
                      return (
                        <div key={mc.key} className="text-center">
                          <p className="text-xs text-gray-400">{mc.label}</p>
                          <p className="text-sm font-semibold text-gray-800">
                            {val !== null && val !== undefined ? `${Math.round(Number(val) * 100)}%` : "—"}
                          </p>
                        </div>
                      );
                    })}
                  </div>
                </div>
              </CardBody>
            </Card>
          );
        })}
      </div>

      {/* Metric Comparison Table */}
      <Card>
        <CardHeader>
          <h2 className="text-sm font-semibold text-gray-900">Metric Comparison</h2>
        </CardHeader>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-100">
                <th className="px-4 py-2.5 text-left text-xs font-medium text-gray-500 uppercase tracking-wide">Metric</th>
                {runs.map((run, i) => (
                  <th key={run.id} className="px-4 py-2.5 text-left text-xs font-medium uppercase tracking-wide" style={{ color: COLORS[i] }}>
                    {run.id.slice(0, 8)}
                  </th>
                ))}
                <th className="px-4 py-2.5 text-left text-xs font-medium text-gray-500 uppercase tracking-wide">Best</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-50">
              {metricConfigs.map((mc) => {
                const values = runs.map((run) => {
                  const sm = run.summary_metrics;
                  return sm?.[`avg_${mc.key}`] ?? sm?.[mc.key] ?? null;
                });
                const numericValues = values.filter((v): v is number => v !== null);
                const bestVal = numericValues.length > 0 ? Math.max(...numericValues) : null;

                return (
                  <tr key={mc.key} className="hover:bg-gray-50">
                    <td className="px-4 py-3 text-xs font-medium text-gray-700">
                      <span className="inline-block w-2 h-2 rounded-full mr-2" style={{ backgroundColor: mc.color }} />
                      {mc.label}
                    </td>
                    {values.map((val, i) => (
                      <td
                        key={i}
                        className={`px-4 py-3 text-xs font-mono ${val !== null && val === bestVal ? "font-bold text-green-700" : "text-gray-700"}`}
                      >
                        {val !== null ? `${(Number(val) * 100).toFixed(1)}%` : "—"}
                      </td>
                    ))}
                    <td className="px-4 py-3 text-xs font-mono text-green-600 font-bold">
                      {bestVal !== null ? `${(bestVal * 100).toFixed(1)}%` : "—"}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </Card>

      {/* Per-Case Comparison Table */}
      <Card>
        <CardHeader>
          <h2 className="text-sm font-semibold text-gray-900">Per-Case Results</h2>
        </CardHeader>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-100">
                <th className="px-3 py-2.5 text-left text-xs font-medium text-gray-500 uppercase tracking-wide">Query</th>
                {runs.map((run, i) => (
                  <th key={run.id} colSpan={resultColumns.length} className="px-3 py-2.5 text-center text-xs font-medium uppercase tracking-wide border-l border-gray-100" style={{ color: COLORS[i] }}>
                    Run {run.id.slice(0, 6)}
                  </th>
                ))}
              </tr>
              <tr className="border-b border-gray-100">
                <th className="px-3 py-1.5"></th>
                {runs.map((run, i) =>
                  resultColumns.map((col) => (
                    <th key={`${run.id}-${col.key}`} className="px-2 py-1.5 text-left text-xs font-normal text-gray-400 border-l border-gray-50 first:border-l-gray-100">
                      {col.label}
                    </th>
                  ))
                )}
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-50">
              {Array.from(allCaseIds).slice(0, 50).map((caseId) => {
                const tc = caseById.get(caseId);
                return (
                  <tr key={caseId} className="hover:bg-gray-50">
                    <td className="px-3 py-2.5 text-xs text-gray-700 max-w-xs">
                      <p className="truncate">{tc?.query ?? caseId.slice(0, 8)}</p>
                    </td>
                    {resultMaps.map((resultMap, i) => {
                      const result = resultMap.get(caseId);
                      return resultColumns.map((col) => {
                        const val = result ? getMetricValue(result as unknown as Record<string, unknown>, col.key) : null;
                        return (
                          <td key={`${i}-${col.key}`} className="px-2 py-2.5 font-mono text-xs border-l border-gray-50 first:border-l-gray-100">
                            {formatScore(val)}
                          </td>
                        );
                      });
                    })}
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}
