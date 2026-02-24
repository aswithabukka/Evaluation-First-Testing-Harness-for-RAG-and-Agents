"use client";
import useSWR from "swr";
import { api } from "@/lib/api";
import { formatPercent } from "@/lib/utils";
import { Card, CardBody } from "@/components/ui/Card";
import { PageLoader } from "@/components/ui/LoadingSpinner";
import { SYSTEM_TYPE_LABELS } from "@/lib/system-metrics";
import type { SystemType } from "@/types";

interface StatCardProps {
  label: string;
  value: string;
  sub?: string;
  accent?: "green" | "red" | "neutral";
}

function StatCard({ label, value, sub, accent = "neutral" }: StatCardProps) {
  const accents = {
    green: "border-l-green-500",
    red: "border-l-red-500",
    neutral: "border-l-brand-500",
  };
  return (
    <Card className={`border-l-4 ${accents[accent]}`}>
      <CardBody>
        <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">{label}</p>
        <p className="mt-1 text-2xl font-bold text-gray-900">{value}</p>
        {sub && <p className="mt-0.5 text-xs text-gray-500">{sub}</p>}
      </CardBody>
    </Card>
  );
}

export function SummaryCards() {
  const { data: runs, isLoading: runsLoading } = useSWR("runs-recent", () =>
    api.runs.list({ limit: 50 })
  );
  const { data: testSets, isLoading: tsLoading } = useSWR("test-sets-dashboard", () =>
    api.testSets.list()
  );

  if (runsLoading || tsLoading) return <PageLoader />;
  if (!runs) return null;

  const completed = runs.filter((r) => r.status === "completed" || r.status === "gate_blocked");
  const passing = completed.filter((r) => r.overall_passed === true);
  const blocked = runs.filter((r) => r.status === "gate_blocked").length;
  const last24h = runs.filter(
    (r) => new Date(r.started_at) > new Date(Date.now() - 86400000)
  ).length;

  const avgPassRate =
    completed.length > 0
      ? completed.reduce((s, r) => s + (r.summary_metrics?.pass_rate ?? 0), 0) / completed.length
      : null;

  // Count unique system types
  const systemTypeCounts = new Map<string, number>();
  (testSets ?? []).forEach((ts) => {
    const st = ts.system_type ?? "rag";
    systemTypeCounts.set(st, (systemTypeCounts.get(st) ?? 0) + 1);
  });
  const systemTypeSub = Array.from(systemTypeCounts.entries())
    .map(([st, count]) => `${count} ${SYSTEM_TYPE_LABELS[st as SystemType] ?? st}`)
    .join(", ");

  return (
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
      <StatCard
        label="Total Runs (24h)"
        value={String(last24h)}
        sub={`${runs.length} total`}
      />
      <StatCard
        label="Gate Pass Rate"
        value={formatPercent(avgPassRate)}
        sub={`${passing.length}/${completed.length} runs passed`}
        accent={avgPassRate !== null && avgPassRate >= 0.8 ? "green" : "red"}
      />
      <StatCard
        label="Active Blocks"
        value={String(blocked)}
        sub="Gate-blocked runs"
        accent={blocked > 0 ? "red" : "green"}
      />
      <StatCard
        label="Test Sets"
        value={String(testSets?.length ?? 0)}
        sub={systemTypeSub || "No test sets yet"}
      />
    </div>
  );
}
