import type {
  EvaluationResult,
  EvaluationRun,
  GateDecision,
  MetricTrendPoint,
  RegressionDiff,
  ResultSummary,
  TestCase,
  TestSet,
} from "@/types";

const BASE_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";

class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

async function apiFetch<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new ApiError(res.status, body.detail ?? res.statusText);
  }
  return res.json() as Promise<T>;
}

function qs(params?: Record<string, string | number | boolean | undefined | null>): string {
  if (!params) return "";
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null) p.set(k, String(v));
  }
  const s = p.toString();
  return s ? `?${s}` : "";
}

export const api = {
  testSets: {
    list: (skip = 0, limit = 50) =>
      apiFetch<TestSet[]>(`/test-sets${qs({ skip, limit })}`),
    get: (id: string) => apiFetch<TestSet>(`/test-sets/${id}`),
    create: (data: { name: string; description?: string }) =>
      apiFetch<TestSet>("/test-sets", {
        method: "POST",
        body: JSON.stringify(data),
      }),
    update: (id: string, data: { name?: string; description?: string }) =>
      apiFetch<TestSet>(`/test-sets/${id}`, {
        method: "PUT",
        body: JSON.stringify(data),
      }),
    delete: (id: string) =>
      apiFetch<void>(`/test-sets/${id}`, { method: "DELETE" }),
    export: (id: string) => apiFetch<unknown>(`/test-sets/${id}/export`),
  },

  testCases: {
    list: (testSetId: string, skip = 0, limit = 100, tag?: string) =>
      apiFetch<TestCase[]>(
        `/test-sets/${testSetId}/cases${qs({ skip, limit, tag })}`,
      ),
    get: (testSetId: string, caseId: string) =>
      apiFetch<TestCase>(`/test-sets/${testSetId}/cases/${caseId}`),
    create: (testSetId: string, data: Partial<TestCase>) =>
      apiFetch<TestCase>(`/test-sets/${testSetId}/cases`, {
        method: "POST",
        body: JSON.stringify(data),
      }),
    bulkCreate: (testSetId: string, cases: Partial<TestCase>[]) =>
      apiFetch<TestCase[]>(`/test-sets/${testSetId}/cases/bulk`, {
        method: "POST",
        body: JSON.stringify({ cases }),
      }),
    update: (testSetId: string, caseId: string, data: Partial<TestCase>) =>
      apiFetch<TestCase>(`/test-sets/${testSetId}/cases/${caseId}`, {
        method: "PUT",
        body: JSON.stringify(data),
      }),
    delete: (testSetId: string, caseId: string) =>
      apiFetch<void>(`/test-sets/${testSetId}/cases/${caseId}`, {
        method: "DELETE",
      }),
  },

  runs: {
    list: (params?: {
      test_set_id?: string;
      status?: string;
      git_branch?: string;
      skip?: number;
      limit?: number;
    }) => apiFetch<EvaluationRun[]>(`/runs${qs(params)}`),
    get: (id: string) => apiFetch<EvaluationRun>(`/runs/${id}`),
    getStatus: (id: string) =>
      apiFetch<{ run_id: string; status: string; overall_passed: boolean | null }>(`/runs/${id}/status`),
    getDiff: (id: string) => apiFetch<RegressionDiff>(`/runs/${id}/diff`),
    trigger: (data: {
      test_set_id: string;
      pipeline_version?: string;
      git_commit_sha?: string;
      triggered_by?: string;
      metrics?: string[];
      notes?: string;
    }) =>
      apiFetch<EvaluationRun>("/runs", {
        method: "POST",
        body: JSON.stringify(data),
      }),
    cancel: (id: string) =>
      apiFetch<void>(`/runs/${id}/cancel`, { method: "POST" }),
  },

  results: {
    list: (
      runId: string,
      params?: { passed?: boolean; skip?: number; limit?: number },
    ) =>
      apiFetch<EvaluationResult[]>(`/results${qs({ run_id: runId, ...params })}`),
    get: (id: string) => apiFetch<EvaluationResult>(`/results/${id}`),
    summary: (runId: string) =>
      apiFetch<ResultSummary>(`/results/summary${qs({ run_id: runId })}`),
  },

  metrics: {
    trends: (testSetId: string, metric: string, days = 30) =>
      apiFetch<MetricTrendPoint[]>(
        `/metrics/trends${qs({ test_set_id: testSetId, metric, days })}`,
      ),
    thresholds: (testSetId: string) =>
      apiFetch<Record<string, number>>(`/metrics/thresholds/${testSetId}`),
    gate: (runId: string) =>
      apiFetch<GateDecision>(`/metrics/gate/${runId}`),
  },
};
