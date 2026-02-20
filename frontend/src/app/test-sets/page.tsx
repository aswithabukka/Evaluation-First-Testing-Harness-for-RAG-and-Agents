"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import useSWR from "swr";
import { api } from "@/lib/api";
import { formatDate } from "@/lib/utils";
import { Badge } from "@/components/ui/Badge";
import { Card, CardBody } from "@/components/ui/Card";
import { PageLoader } from "@/components/ui/LoadingSpinner";
import type { RunStatus } from "@/types";

const statusBadge: Record<string, "green" | "red" | "yellow" | "blue" | "orange" | "gray"> = {
  completed: "green",
  gate_blocked: "orange",
  failed: "red",
  running: "blue",
  pending: "yellow",
};

export default function TestSetsPage() {
  const router = useRouter();
  const { data: testSets, isLoading } = useSWR("test-sets", () => api.testSets.list());

  if (isLoading) return <PageLoader />;

  return (
    <div className="p-6 space-y-6 max-w-5xl mx-auto">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-gray-900">Test Sets</h1>
          <p className="text-sm text-gray-500 mt-0.5">Manage your evaluation datasets</p>
        </div>
        <Link
          href="/test-sets/new"
          className="px-4 py-2 bg-brand-600 text-white text-sm font-medium rounded-md hover:bg-brand-700 transition-colors"
        >
          + New Test Set
        </Link>
      </div>

      {testSets && testSets.length === 0 && (
        <Card>
          <CardBody>
            <p className="text-center text-gray-400 py-8">
              No test sets yet.{" "}
              <Link href="/test-sets/new" className="text-brand-600 hover:underline">
                Create your first test set →
              </Link>
            </p>
          </CardBody>
        </Card>
      )}

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {(testSets ?? []).map((ts) => (
          <div key={ts.id} className="relative group">
            <Link href={`/test-sets/${ts.id}`}>
              <Card className="hover:border-brand-300 hover:shadow-md transition-all cursor-pointer h-full">
                <CardBody className="space-y-3">
                  <div className="flex items-start justify-between gap-2">
                    <h3 className="font-semibold text-gray-900 truncate">{ts.name}</h3>
                    <span className="text-xs text-gray-400 flex-shrink-0">v{ts.version}</span>
                  </div>
                  {ts.description && (
                    <p className="text-xs text-gray-500 line-clamp-2">{ts.description}</p>
                  )}
                  <div className="flex items-center justify-between text-xs text-gray-500">
                    <span>{ts.test_case_count} cases</span>
                    {ts.last_run_status && (
                      <Badge variant={statusBadge[ts.last_run_status] ?? "gray"}>
                        {ts.last_run_status.replace("_", " ")}
                      </Badge>
                    )}
                  </div>
                  <p className="text-xs text-gray-400">Created {formatDate(ts.created_at)}</p>
                </CardBody>
              </Card>
            </Link>
            {/* Quick-run button — visible on card hover */}
            <button
              onClick={(e) => {
                e.preventDefault();
                e.stopPropagation();
                router.push(`/test-sets/${ts.id}?run=1`);
              }}
              title="Trigger evaluation run"
              className="absolute top-3 right-3 opacity-0 group-hover:opacity-100 transition-opacity bg-brand-600 text-white text-xs font-medium px-2 py-1 rounded hover:bg-brand-700"
            >
              ▶ Run
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}
