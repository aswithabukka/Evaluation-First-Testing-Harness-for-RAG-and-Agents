"use client";
import Link from "next/link";
import useSWR from "swr";
import { api } from "@/lib/api";
import { formatDate, formatPercent, statusColor } from "@/lib/utils";
import { Badge } from "@/components/ui/Badge";
import { Card, CardHeader, CardBody } from "@/components/ui/Card";
import { PageLoader } from "@/components/ui/LoadingSpinner";
import type { RunStatus } from "@/types";

const statusVariant: Record<RunStatus, "green" | "red" | "yellow" | "blue" | "orange"> = {
  completed: "green",
  gate_blocked: "orange",
  failed: "red",
  running: "blue",
  pending: "yellow",
};

export function RecentRunsTable() {
  const { data: runs, isLoading } = useSWR(
    "runs-table",
    () => api.runs.list({ limit: 10 }),
    { refreshInterval: 10000 }
  );

  if (isLoading) return <PageLoader />;

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-semibold text-gray-900">Recent Evaluation Runs</h2>
          <Link href="/runs" className="text-xs text-brand-600 hover:underline">
            View all →
          </Link>
        </div>
      </CardHeader>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-100">
              {["Status", "Test Set", "Branch", "Pass Rate", "Commit", "Started"].map((h) => (
                <th key={h} className="px-4 py-2.5 text-left text-xs font-medium text-gray-500 uppercase tracking-wide">
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-50">
            {(runs ?? []).map((run) => (
              <tr key={run.id} className="hover:bg-gray-50 transition-colors">
                <td className="px-4 py-3">
                  <Badge variant={statusVariant[run.status] ?? "gray"}>
                    {run.status.replace("_", " ")}
                  </Badge>
                </td>
                <td className="px-4 py-3 font-mono text-xs text-gray-500">
                  {run.test_set_id.slice(0, 8)}…
                </td>
                <td className="px-4 py-3 text-gray-700">
                  {run.git_branch ?? "—"}
                </td>
                <td className="px-4 py-3">
                  {run.summary_metrics
                    ? formatPercent(run.summary_metrics.pass_rate)
                    : "—"}
                </td>
                <td className="px-4 py-3 font-mono text-xs text-gray-500">
                  {run.git_commit_sha?.slice(0, 7) ?? "—"}
                </td>
                <td className="px-4 py-3 text-gray-500 text-xs">
                  {formatDate(run.started_at)}
                </td>
              </tr>
            ))}
            {(!runs || runs.length === 0) && (
              <tr>
                <td colSpan={6} className="px-4 py-8 text-center text-gray-400 text-sm">
                  No evaluation runs yet. Trigger one via the CLI or API.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </Card>
  );
}
