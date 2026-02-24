"use client";
import Link from "next/link";
import useSWR from "swr";
import { api } from "@/lib/api";
import { formatDate, formatPercent } from "@/lib/utils";
import { Badge } from "@/components/ui/Badge";
import { Card, CardHeader } from "@/components/ui/Card";
import { PageLoader } from "@/components/ui/LoadingSpinner";
import { SYSTEM_TYPE_LABELS, SYSTEM_TYPE_ICONS, SYSTEM_TYPE_COLORS } from "@/lib/system-metrics";
import type { RunStatus, SystemType, TestSet } from "@/types";

const statusVariant: Record<RunStatus, "green" | "red" | "yellow" | "blue" | "orange"> = {
  completed: "green",
  gate_blocked: "orange",
  failed: "red",
  running: "blue",
  pending: "yellow",
};

export default function RunsPage() {
  const { data: runs, isLoading } = useSWR(
    "runs-all",
    () => api.runs.list({ limit: 100 }),
    { refreshInterval: 8000 }
  );
  const { data: testSets } = useSWR("test-sets-for-runs", () => api.testSets.list());

  if (isLoading) return <PageLoader />;

  // Build a lookup map from test_set_id → TestSet
  const tsById = new Map<string, TestSet>(
    (testSets ?? []).map((ts) => [ts.id, ts])
  );

  return (
    <div className="p-6 space-y-6 max-w-6xl mx-auto">
      <div>
        <h1 className="text-xl font-bold text-gray-900">Evaluation Runs</h1>
        <p className="text-sm text-gray-500 mt-0.5">All evaluation runs across all test sets</p>
      </div>

      <Card>
        <CardHeader>
          <span className="text-sm font-semibold text-gray-900">
            {runs?.length ?? 0} runs
          </span>
        </CardHeader>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-100">
                {["Status", "System", "Pass Rate", "Cases", "Branch", "Commit", "Version", "Started"].map((h) => (
                  <th key={h} className="px-4 py-2.5 text-left text-xs font-medium text-gray-500 uppercase tracking-wide">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-50">
              {(runs ?? []).map((run) => {
                const ts = tsById.get(run.test_set_id);
                const st = (ts?.system_type ?? "rag") as SystemType;
                return (
                  <tr key={run.id} className="hover:bg-gray-50 transition-colors">
                    <td className="px-4 py-3">
                      <Link href={`/runs/${run.id}`}>
                        <Badge variant={statusVariant[run.status] ?? "gray"}>
                          {run.status.replace("_", " ")}
                        </Badge>
                      </Link>
                    </td>
                    <td className="px-4 py-3">
                      <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium border ${SYSTEM_TYPE_COLORS[st]}`}>
                        <span className="text-xs">{SYSTEM_TYPE_ICONS[st]}</span>
                        {SYSTEM_TYPE_LABELS[st]}
                      </span>
                    </td>
                    <td className="px-4 py-3 font-medium">
                      {run.summary_metrics ? formatPercent(run.summary_metrics.pass_rate) : "—"}
                    </td>
                    <td className="px-4 py-3 text-gray-500">
                      {run.summary_metrics
                        ? `${run.summary_metrics.passed_cases}/${run.summary_metrics.total_cases}`
                        : "—"}
                    </td>
                    <td className="px-4 py-3 text-gray-700">{run.git_branch ?? "—"}</td>
                    <td className="px-4 py-3 font-mono text-xs text-gray-500">
                      {run.git_commit_sha?.slice(0, 7) ?? "—"}
                    </td>
                    <td className="px-4 py-3 text-xs text-gray-500">
                      {run.pipeline_version ?? "—"}
                    </td>
                    <td className="px-4 py-3 text-xs text-gray-400">{formatDate(run.started_at)}</td>
                  </tr>
                );
              })}
              {(!runs || runs.length === 0) && (
                <tr>
                  <td colSpan={8} className="px-4 py-8 text-center text-gray-400 text-sm">
                    No runs yet. Trigger one via the CLI: <code className="bg-gray-100 px-1 rounded">rageval run</code>
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}
