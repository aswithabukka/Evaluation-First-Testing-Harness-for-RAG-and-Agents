"use client";
import { useState } from "react";
import useSWR from "swr";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ReferenceLine,
  ResponsiveContainer,
} from "recharts";
import { api } from "@/lib/api";
import { formatDate } from "@/lib/utils";
import { Card, CardHeader, CardBody } from "@/components/ui/Card";
import { PageLoader } from "@/components/ui/LoadingSpinner";

const METRICS = [
  {
    key: "faithfulness",
    label: "Faithfulness",
    color: "#0ea5e9",
    threshold: 0.7,
    description: "Does the answer contain only facts from the retrieved context? High faithfulness means no hallucination — the model sticks to what was retrieved.",
  },
  {
    key: "answer_relevancy",
    label: "Answer Relevancy",
    color: "#8b5cf6",
    threshold: 0.7,
    description: "Is the answer on-topic and directly responsive to the question? Low scores mean the model answered something adjacent rather than what was asked.",
  },
  {
    key: "context_precision",
    label: "Context Precision",
    color: "#f59e0b",
    threshold: 0.6,
    description: "Are the retrieved chunks actually useful for answering the question? High precision means retrieval is targeted — few irrelevant chunks are pulled in.",
  },
  {
    key: "context_recall",
    label: "Context Recall",
    color: "#10b981",
    threshold: 0.6,
    description: "Did retrieval surface all the chunks needed to answer the question fully? Low recall means key facts were missed and the answer may be incomplete.",
  },
  {
    key: "pass_rate",
    label: "Pass Rate",
    color: "#ef4444",
    threshold: 0.8,
    description: "Percentage of test cases where all metric thresholds and failure rules were satisfied. This is your overall pipeline quality gate.",
  },
];

const DAYS_OPTIONS = [7, 30, 90];

function MetricChart({
  testSetId,
  metric,
  label,
  description,
  color,
  threshold,
  days,
}: {
  testSetId: string;
  metric: string;
  label: string;
  description: string;
  color: string;
  threshold: number;
  days: number;
}) {
  const { data, isLoading } = useSWR(
    `trends-${testSetId}-${metric}-${days}`,
    () => api.metrics.trends(testSetId, metric, days)
  );

  if (isLoading) return <div className="h-48 flex items-center justify-center text-gray-300 text-sm">Loading…</div>;

  const chartData = (data ?? []).map((p) => ({
    date: new Date(p.recorded_at).toLocaleDateString(),
    value: p.metric_value,
    sha: p.git_commit_sha?.slice(0, 7),
  }));

  const latest = chartData.length > 0 ? chartData[chartData.length - 1].value : null;
  const passing = latest !== null && latest >= threshold;

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <span
              className="inline-block w-2.5 h-2.5 rounded-full flex-shrink-0"
              style={{ backgroundColor: color }}
            />
            <h3 className="text-sm font-semibold text-gray-800">{label}</h3>
          </div>
          {latest !== null && (
            <div className="flex items-center gap-2">
              <span
                className={`text-xs font-medium px-2 py-0.5 rounded-full ${
                  passing
                    ? "bg-green-50 text-green-700 ring-1 ring-green-200"
                    : "bg-red-50 text-red-600 ring-1 ring-red-200"
                }`}
              >
                {passing ? "▲ Passing" : "▼ Failing"}
              </span>
              <p className={`text-lg font-bold leading-none ${passing ? "text-green-600" : "text-red-500"}`}>
                {(latest * 100).toFixed(1)}%
              </p>
            </div>
          )}
        </div>
      </CardHeader>
      <CardBody>
        {/* Description callout */}
        <div className="flex gap-2 mb-4 p-3 rounded-md bg-gray-50 border border-gray-100">
          <svg
            className="flex-shrink-0 w-4 h-4 mt-0.5 text-gray-400"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            strokeWidth={2}
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M13 16h-1v-4h-1m1-4h.01M12 2a10 10 0 110 20A10 10 0 0112 2z"
            />
          </svg>
          <p className="text-xs text-gray-600 leading-relaxed">{description}</p>
        </div>

        {chartData.length === 0 ? (
          <p className="text-center text-gray-400 text-sm py-8">No data for this period</p>
        ) : (
          <ResponsiveContainer width="100%" height={200}>
            <LineChart data={chartData} margin={{ top: 4, right: 8, bottom: 4, left: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
              <XAxis dataKey="date" tick={{ fontSize: 10 }} />
              <YAxis domain={[0, 1]} tick={{ fontSize: 10 }} />
              <Tooltip
                formatter={(value: number) => [`${(value * 100).toFixed(1)}%`, label]}
                labelFormatter={(label) => `Date: ${label}`}
              />
              <ReferenceLine
                y={threshold}
                stroke="#ef4444"
                strokeDasharray="4 4"
                label={{ value: `threshold ${threshold}`, fontSize: 9, fill: "#ef4444" }}
              />
              <Line
                type="monotone"
                dataKey="value"
                stroke={color}
                strokeWidth={2}
                dot={{ r: 3 }}
                activeDot={{ r: 5 }}
              />
            </LineChart>
          </ResponsiveContainer>
        )}
      </CardBody>
    </Card>
  );
}

export default function MetricsPage() {
  const [days, setDays] = useState(30);

  const { data: testSets, isLoading } = useSWR("test-sets-metrics", () => api.testSets.list());
  const [selectedTestSet, setSelectedTestSet] = useState<string | null>(null);

  if (isLoading) return <PageLoader />;

  const activeTestSetId = selectedTestSet ?? testSets?.[0]?.id ?? null;

  return (
    <div className="p-6 space-y-6 max-w-6xl mx-auto">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-xl font-bold text-gray-900">Metric Trends</h1>
          <p className="text-sm text-gray-500 mt-0.5">Quality over time across evaluation runs</p>
        </div>
        <div className="flex items-center gap-3">
          {testSets && testSets.length > 1 && (
            <select
              value={activeTestSetId ?? ""}
              onChange={(e) => setSelectedTestSet(e.target.value)}
              className="border border-gray-300 rounded-md px-3 py-1.5 text-sm text-gray-700 focus:outline-none focus:ring-2 focus:ring-brand-500"
            >
              {testSets.map((ts) => (
                <option key={ts.id} value={ts.id}>{ts.name}</option>
              ))}
            </select>
          )}
          <div className="flex rounded-md border border-gray-300 overflow-hidden text-sm">
            {DAYS_OPTIONS.map((d) => (
              <button
                key={d}
                onClick={() => setDays(d)}
                className={`px-3 py-1.5 font-medium transition-colors ${
                  days === d
                    ? "bg-brand-600 text-white"
                    : "bg-white text-gray-600 hover:bg-gray-50"
                }`}
              >
                {d}d
              </button>
            ))}
          </div>
        </div>
      </div>

      {!activeTestSetId ? (
        <Card>
          <CardBody>
            <p className="text-center text-gray-400 py-8">No test sets found. Create a test set first.</p>
          </CardBody>
        </Card>
      ) : (
        <div className="grid gap-4 md:grid-cols-2">
          {METRICS.map((m) => (
            <MetricChart
              key={m.key}
              testSetId={activeTestSetId}
              metric={m.key}
              label={m.label}
              description={m.description}
              color={m.color}
              threshold={m.threshold}
              days={days}
            />
          ))}
        </div>
      )}
    </div>
  );
}
