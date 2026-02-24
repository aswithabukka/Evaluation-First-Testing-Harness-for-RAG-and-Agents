"use client";
import Link from "next/link";
import useSWR from "swr";
import { api } from "@/lib/api";
import { formatDate, formatPercent } from "@/lib/utils";
import { Badge } from "@/components/ui/Badge";
import { Card, CardHeader, CardBody } from "@/components/ui/Card";
import { PageLoader } from "@/components/ui/LoadingSpinner";
import {
  SYSTEM_TYPE_LABELS,
  SYSTEM_TYPE_ICONS,
  SYSTEM_TYPE_COLORS,
  getMetricsForSystemType,
  type MetricConfig,
} from "@/lib/system-metrics";
import type { SystemType, TestSet, EvaluationRun, SamplingStats } from "@/types";

/* ─── Health badge logic ─────────────────────────────────────────── */
function healthStatus(run: EvaluationRun | undefined): {
  label: string;
  variant: "green" | "red" | "yellow" | "orange" | "gray";
  description: string;
} {
  if (!run) return { label: "No runs", variant: "gray", description: "No evaluation runs yet" };
  if (run.status === "running" || run.status === "pending")
    return { label: "Running", variant: "blue" as "yellow", description: "Evaluation in progress" };
  if (run.overall_passed === true)
    return { label: "Healthy", variant: "green", description: "All quality gates passing" };
  if (run.status === "gate_blocked")
    return { label: "Degraded", variant: "orange", description: "Quality gate blocked" };
  if (run.status === "failed")
    return { label: "Error", variant: "red", description: "Last evaluation failed" };
  if (run.overall_passed === false)
    return { label: "Failing", variant: "red", description: "Quality thresholds not met" };
  return { label: "Unknown", variant: "gray", description: "" };
}

/* ─── Sparkline bar ──────────────────────────────────────────────── */
function MiniBar({ value, threshold, color }: { value: number | null; threshold: number; color: string }) {
  if (value === null || value === undefined) return <span className="text-gray-300 text-xs">—</span>;
  const pct = Math.round(value * 100);
  const passing = value >= threshold;
  return (
    <div className="flex items-center gap-2">
      <div className="w-20 h-2 bg-gray-100 rounded-full overflow-hidden">
        <div
          className="h-full rounded-full transition-all"
          style={{ width: `${pct}%`, backgroundColor: passing ? color : "#ef4444" }}
        />
      </div>
      <span className={`text-xs font-mono font-medium ${passing ? "text-gray-700" : "text-red-600"}`}>
        {pct}%
      </span>
    </div>
  );
}

/* ─── System Card ────────────────────────────────────────────────── */
function SystemCard({
  testSets,
  latestRuns,
  stats,
}: {
  testSets: TestSet[];
  latestRuns: Map<string, EvaluationRun>;
  stats: Map<string, SamplingStats>;
}) {
  if (testSets.length === 0) return null;

  const systemType = (testSets[0].system_type ?? "rag") as SystemType;
  const metrics = getMetricsForSystemType(systemType);

  // Find the most recent run across all test sets of this type
  let latestRun: EvaluationRun | undefined;
  let latestTestSet: TestSet | undefined;
  for (const ts of testSets) {
    const run = latestRuns.get(ts.id);
    if (run && (!latestRun || new Date(run.started_at) > new Date(latestRun.started_at))) {
      latestRun = run;
      latestTestSet = ts;
    }
  }

  const health = healthStatus(latestRun);
  const sm = latestRun?.summary_metrics;

  // Aggregate production traffic
  let totalReceived = 0;
  let totalSampled = 0;
  // Production stats won't map 1:1 to system types, so we just show if any exist

  return (
    <Card className="hover:shadow-md transition-shadow">
      <CardBody className="space-y-4">
        {/* Header */}
        <div className="flex items-start justify-between">
          <div className="flex items-center gap-3">
            <span className="text-2xl">{SYSTEM_TYPE_ICONS[systemType]}</span>
            <div>
              <h3 className="font-semibold text-gray-900">{SYSTEM_TYPE_LABELS[systemType]}</h3>
              <p className="text-xs text-gray-500">
                {testSets.length} test set{testSets.length !== 1 ? "s" : ""} · {testSets.reduce((sum, ts) => sum + ts.test_case_count, 0)} total cases
              </p>
            </div>
          </div>
          <Badge variant={health.variant}>{health.label}</Badge>
        </div>

        {/* Key Metrics */}
        {sm && (
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-xs font-medium text-gray-500 uppercase tracking-wide">Key Metrics</span>
              <span className="text-xs text-gray-400">
                Pass Rate: <span className={`font-semibold ${sm.pass_rate >= 0.8 ? "text-green-600" : "text-red-600"}`}>{formatPercent(sm.pass_rate)}</span>
              </span>
            </div>
            <div className="grid grid-cols-2 gap-x-6 gap-y-1.5">
              {metrics.slice(1, 5).map((mc) => {
                const val = sm[`avg_${mc.key}`] ?? sm[mc.key] ?? null;
                return (
                  <div key={mc.key} className="flex items-center justify-between">
                    <span className="text-xs text-gray-600">{mc.label}</span>
                    <MiniBar value={val} threshold={mc.threshold} color={mc.color} />
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {!sm && (
          <div className="py-4 text-center">
            <p className="text-sm text-gray-400">No evaluation data yet</p>
            <p className="text-xs text-gray-300 mt-1">Run an evaluation to see metrics</p>
          </div>
        )}

        {/* Latest Run Info */}
        {latestRun && (
          <div className="pt-3 border-t border-gray-100">
            <div className="flex items-center justify-between text-xs">
              <span className="text-gray-500">Latest run</span>
              <Link
                href={`/runs/${latestRun.id}`}
                className="text-brand-600 hover:underline font-medium"
              >
                {formatDate(latestRun.started_at)}
              </Link>
            </div>
            {latestRun.pipeline_version && (
              <div className="flex items-center justify-between text-xs mt-1">
                <span className="text-gray-500">Version</span>
                <span className="font-mono text-gray-700">{latestRun.pipeline_version}</span>
              </div>
            )}
            {latestRun.git_branch && (
              <div className="flex items-center justify-between text-xs mt-1">
                <span className="text-gray-500">Branch</span>
                <span className="text-gray-700">{latestRun.git_branch}</span>
              </div>
            )}
          </div>
        )}

        {/* Test Sets List */}
        <div className="pt-3 border-t border-gray-100">
          <p className="text-xs font-medium text-gray-500 uppercase tracking-wide mb-2">Test Sets</p>
          <div className="space-y-1.5">
            {testSets.map((ts) => {
              const tsRun = latestRuns.get(ts.id);
              return (
                <Link
                  key={ts.id}
                  href={`/test-sets/${ts.id}`}
                  className="flex items-center justify-between py-1.5 px-2 rounded hover:bg-gray-50 transition-colors group"
                >
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-medium text-gray-800 group-hover:text-brand-700">{ts.name}</span>
                    <span className="text-xs text-gray-400">({ts.test_case_count})</span>
                  </div>
                  {ts.last_run_status && (
                    <span className={`text-xs px-1.5 py-0.5 rounded ${
                      ts.last_run_status === "completed" ? "bg-green-50 text-green-700" :
                      ts.last_run_status === "gate_blocked" ? "bg-orange-50 text-orange-700" :
                      ts.last_run_status === "failed" ? "bg-red-50 text-red-700" :
                      "bg-gray-50 text-gray-500"
                    }`}>
                      {ts.last_run_status === "completed" ? formatPercent(tsRun?.summary_metrics?.pass_rate ?? null) : ts.last_run_status.replace("_", " ")}
                    </span>
                  )}
                </Link>
              );
            })}
          </div>
        </div>
      </CardBody>
    </Card>
  );
}

/* ─── Main Page ──────────────────────────────────────────────────── */
export default function SystemsPage() {
  const { data: testSets, isLoading: tsLoading } = useSWR("test-sets-systems", () => api.testSets.list());
  const { data: runs, isLoading: runsLoading } = useSWR("runs-systems", () => api.runs.list({ limit: 200 }));
  const { data: prodStats } = useSWR("prod-stats-systems", () => api.production.stats());

  if (tsLoading || runsLoading) return <PageLoader />;

  // Group test sets by system type
  const bySystemType = new Map<string, TestSet[]>();
  for (const ts of testSets ?? []) {
    const st = ts.system_type ?? "rag";
    if (!bySystemType.has(st)) bySystemType.set(st, []);
    bySystemType.get(st)!.push(ts);
  }

  // Find latest completed/gate_blocked run per test set
  const latestRunByTestSet = new Map<string, EvaluationRun>();
  for (const run of runs ?? []) {
    const existing = latestRunByTestSet.get(run.test_set_id);
    if (!existing || new Date(run.started_at) > new Date(existing.started_at)) {
      latestRunByTestSet.set(run.test_set_id, run);
    }
  }

  // Production stats by source
  const statsBySource = new Map<string, SamplingStats>();
  for (const s of prodStats ?? []) {
    statsBySource.set(s.source, s);
  }

  // Count health statuses
  const systemTypes = Array.from(bySystemType.keys()) as SystemType[];
  let healthyCount = 0;
  let degradedCount = 0;
  let failingCount = 0;
  let noDataCount = 0;

  for (const [, sets] of bySystemType) {
    let latestRun: EvaluationRun | undefined;
    for (const ts of sets) {
      const run = latestRunByTestSet.get(ts.id);
      if (run && (!latestRun || new Date(run.started_at) > new Date(latestRun.started_at))) {
        latestRun = run;
      }
    }
    const h = healthStatus(latestRun);
    if (h.variant === "green") healthyCount++;
    else if (h.variant === "orange") degradedCount++;
    else if (h.variant === "red") failingCount++;
    else noDataCount++;
  }

  return (
    <div className="p-6 space-y-6 max-w-6xl mx-auto">
      {/* Header */}
      <div>
        <h1 className="text-xl font-bold text-gray-900">AI Systems</h1>
        <p className="text-sm text-gray-500 mt-0.5">Health status and evaluation metrics for all monitored AI systems</p>
      </div>

      {/* Overview Stats */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        <Card className="border-l-4 border-l-brand-500">
          <CardBody>
            <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">Systems</p>
            <p className="mt-1 text-2xl font-bold text-gray-900">{systemTypes.length}</p>
            <p className="mt-0.5 text-xs text-gray-500">{(testSets ?? []).length} test sets total</p>
          </CardBody>
        </Card>
        <Card className={`border-l-4 ${healthyCount > 0 ? "border-l-green-500" : "border-l-gray-300"}`}>
          <CardBody>
            <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">Healthy</p>
            <p className="mt-1 text-2xl font-bold text-green-600">{healthyCount}</p>
            <p className="mt-0.5 text-xs text-gray-500">All gates passing</p>
          </CardBody>
        </Card>
        <Card className={`border-l-4 ${degradedCount > 0 ? "border-l-orange-500" : "border-l-gray-300"}`}>
          <CardBody>
            <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">Degraded</p>
            <p className="mt-1 text-2xl font-bold text-orange-600">{degradedCount}</p>
            <p className="mt-0.5 text-xs text-gray-500">Gate blocked</p>
          </CardBody>
        </Card>
        <Card className={`border-l-4 ${failingCount > 0 ? "border-l-red-500" : "border-l-gray-300"}`}>
          <CardBody>
            <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">Failing</p>
            <p className="mt-1 text-2xl font-bold text-red-600">{failingCount}</p>
            <p className="mt-0.5 text-xs text-gray-500">Thresholds not met</p>
          </CardBody>
        </Card>
      </div>

      {/* System Cards */}
      {systemTypes.length === 0 ? (
        <Card>
          <CardBody>
            <div className="py-8 text-center">
              <p className="text-gray-400 text-sm">No AI systems configured yet.</p>
              <p className="text-gray-300 text-xs mt-1">Create a test set to start monitoring a system.</p>
              <Link
                href="/test-sets/new"
                className="mt-4 inline-block px-4 py-2 bg-brand-600 text-white text-sm font-medium rounded-md hover:bg-brand-700 transition-colors"
              >
                + Add AI System
              </Link>
            </div>
          </CardBody>
        </Card>
      ) : (
        <div className="grid gap-6 md:grid-cols-2">
          {systemTypes.map((st) => (
            <SystemCard
              key={st}
              testSets={bySystemType.get(st)!}
              latestRuns={latestRunByTestSet}
              stats={statsBySource}
            />
          ))}
        </div>
      )}
    </div>
  );
}
