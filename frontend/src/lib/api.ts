import type {
  EvaluationResult,
  EvaluationRun,
  GateDecision,
  IngestResponse,
  MetricTrendPoint,
  PlaygroundInteraction,
  PlaygroundSystem,
  ProductionLog,
  RegressionDiff,
  ResultSummary,
  SamplingStats,
  SystemType,
  TestCase,
  TestSet,
} from "@/types";

const BASE_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";

const API_KEY = process.env.NEXT_PUBLIC_API_KEY ?? "";

class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

async function apiFetch<T>(path: string, options?: RequestInit): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(API_KEY ? { "X-API-Key": API_KEY } : {}),
  };
  const res = await fetch(`${BASE_URL}${path}`, {
    headers,
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
    create: (data: { name: string; description?: string; system_type?: SystemType }) =>
      apiFetch<TestSet>("/test-sets", {
        method: "POST",
        body: JSON.stringify(data),
      }),
    update: (id: string, data: { name?: string; description?: string; system_type?: SystemType }) =>
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

  // Playground — interactive demo
  playground: {
    systems: () => apiFetch<PlaygroundSystem[]>("/playground/systems"),
    interact: (data: { system_type: string; query: string; session_id?: string | null }) =>
      apiFetch<PlaygroundInteraction>("/playground/interact", {
        method: "POST",
        body: JSON.stringify(data),
      }),
    resetSession: (sessionId: string) =>
      apiFetch<{ message: string; session_id: string }>(
        `/playground/reset-session${qs({ session_id: sessionId })}`,
        { method: "POST" },
      ),
    uploadDocuments: (texts: string[]) =>
      apiFetch<{ added: number; total: number }>("/playground/rag/documents", {
        method: "POST",
        body: JSON.stringify({ texts }),
      }),
    listDocuments: () =>
      apiFetch<{ documents: string[]; count: number }>("/playground/rag/documents"),
    clearDocuments: () =>
      apiFetch<{ removed: number; message: string }>("/playground/rag/documents", {
        method: "DELETE",
      }),
    uploadFiles: async (files: File[]): Promise<{ added: number; total: number }> => {
      const formData = new FormData();
      for (const file of files) {
        formData.append("files", file);
      }
      const headers: Record<string, string> = {
        ...(API_KEY ? { "X-API-Key": API_KEY } : {}),
      };
      const res = await fetch(`${BASE_URL}/playground/rag/upload-files`, {
        method: "POST",
        headers,
        body: formData,
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new ApiError(res.status, body.detail ?? res.statusText);
      }
      return res.json();
    },
  },

  // Production traffic ingestion
  production: {
    logs: (params?: { source?: string; status?: string; skip?: number; limit?: number }) =>
      apiFetch<ProductionLog[]>(`/ingest/logs${qs(params)}`),
    getLog: (id: string) => apiFetch<ProductionLog>(`/ingest/logs/${id}`),
    stats: (source?: string) =>
      apiFetch<SamplingStats[]>(`/ingest/stats${qs({ source })}`),
  },
};
