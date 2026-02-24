"use client";
import { useEffect, useState } from "react";
import useSWR from "swr";
import { api } from "@/lib/api";
import { Card, CardHeader, CardBody } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { LoadingSpinner, PageLoader } from "@/components/ui/LoadingSpinner";
import type { ProductionLog, SamplingStats } from "@/types";

export default function ProductionPage() {
  const { data: stats, isLoading: statsLoading } = useSWR(
    "production-stats",
    () => api.production.stats(),
    { refreshInterval: 15000 }
  );

  const { data: logs, isLoading: logsLoading } = useSWR(
    "production-logs",
    () => api.production.logs({ limit: 50 }),
    { refreshInterval: 10000 }
  );

  const { data: feedbackStats } = useSWR(
    "feedback-stats",
    () => api.production.feedbackStats(),
    { refreshInterval: 15000 }
  );

  if (statsLoading && logsLoading) return <PageLoader />;

  return (
    <div className="p-6 space-y-6">
      <div>
        <h1 className="text-xl font-bold text-gray-900">Production Traffic</h1>
        <p className="text-sm text-gray-500 mt-1">
          Live view of ingested production Q&A pairs and sampling statistics
        </p>
      </div>

      {/* Feedback Stats Card */}
      {feedbackStats && feedbackStats.total > 0 && (
        <Card>
          <CardHeader>
            <h2 className="text-sm font-semibold text-gray-900">User Feedback Summary</h2>
          </CardHeader>
          <CardBody>
            <div className="flex items-center gap-8">
              <div className="flex items-center gap-3">
                <span className="text-2xl">+</span>
                <div>
                  <p className="text-2xl font-bold text-green-600">{feedbackStats.thumbs_up}</p>
                  <p className="text-xs text-gray-500">Thumbs Up</p>
                </div>
              </div>
              <div className="flex items-center gap-3">
                <span className="text-2xl">-</span>
                <div>
                  <p className="text-2xl font-bold text-red-600">{feedbackStats.thumbs_down}</p>
                  <p className="text-xs text-gray-500">Thumbs Down</p>
                </div>
              </div>
              <div className="flex items-center gap-3">
                <span className="text-2xl text-gray-300">?</span>
                <div>
                  <p className="text-2xl font-bold text-gray-400">{feedbackStats.no_feedback}</p>
                  <p className="text-xs text-gray-500">No Feedback</p>
                </div>
              </div>
              {feedbackStats.positive_rate !== null && (
                <div className="ml-auto text-center">
                  <p className="text-3xl font-bold text-brand-600">
                    {(feedbackStats.positive_rate * 100).toFixed(0)}%
                  </p>
                  <p className="text-xs text-gray-500">Positive Rate</p>
                </div>
              )}
            </div>
          </CardBody>
        </Card>
      )}

      {/* Sampling Stats Cards */}
      {stats && stats.length > 0 && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {stats.map((s) => (
            <Card key={s.source}>
              <CardHeader>
                <h3 className="text-sm font-semibold text-gray-900">{s.source}</h3>
              </CardHeader>
              <CardBody>
                <div className="grid grid-cols-2 gap-3 text-sm">
                  <div>
                    <span className="text-gray-500">Total Received</span>
                    <p className="text-lg font-bold text-gray-900">
                      {s.total_received + s.total_sampled + s.total_skipped + s.total_evaluated}
                    </p>
                  </div>
                  <div>
                    <span className="text-gray-500">Sampled</span>
                    <p className="text-lg font-bold text-brand-600">
                      {s.total_sampled + s.total_evaluated}
                    </p>
                  </div>
                  <div>
                    <span className="text-gray-500">Evaluated</span>
                    <p className="text-lg font-bold text-green-600">{s.total_evaluated}</p>
                  </div>
                  <div>
                    <span className="text-gray-500">Sample Rate</span>
                    <p className="text-lg font-bold text-gray-700">
                      {(s.sampling_rate * 100).toFixed(0)}%
                    </p>
                  </div>
                </div>
              </CardBody>
            </Card>
          ))}
        </div>
      )}

      {stats && stats.length === 0 && (
        <Card>
          <CardBody>
            <div className="text-center py-8 text-gray-500">
              <p className="text-lg font-medium">No production traffic yet</p>
              <p className="text-sm mt-2">
                Send Q&A pairs to <code className="bg-gray-100 px-1.5 py-0.5 rounded text-xs">POST /api/v1/ingest</code> to start monitoring
              </p>
            </div>
          </CardBody>
        </Card>
      )}

      {/* Recent Logs Table */}
      <Card>
        <CardHeader>
          <h2 className="text-sm font-semibold text-gray-900">Recent Ingested Logs</h2>
        </CardHeader>
        <CardBody>
          {logsLoading ? (
            <LoadingSpinner />
          ) : logs && logs.length > 0 ? (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-gray-200 text-left text-gray-500">
                    <th className="pb-2 pr-4 font-medium">Source</th>
                    <th className="pb-2 pr-4 font-medium">Query</th>
                    <th className="pb-2 pr-4 font-medium">Status</th>
                    <th className="pb-2 pr-4 font-medium">Confidence</th>
                    <th className="pb-2 pr-4 font-medium">Feedback</th>
                    <th className="pb-2 font-medium">Ingested</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {logs.map((log) => (
                    <tr key={log.id} className="hover:bg-gray-50">
                      <td className="py-2 pr-4 font-medium text-gray-900">{log.source}</td>
                      <td className="py-2 pr-4 text-gray-700 max-w-xs truncate">{log.query}</td>
                      <td className="py-2 pr-4">
                        <Badge
                          variant={
                            log.status === "evaluated"
                              ? "green"
                              : log.status === "sampled"
                              ? "blue"
                              : log.status === "skipped"
                              ? "gray"
                              : "yellow"
                          }
                        >
                          {log.status}
                        </Badge>
                      </td>
                      <td className="py-2 pr-4 text-gray-600">
                        {log.confidence_score !== null
                          ? `${(log.confidence_score * 100).toFixed(0)}%`
                          : "—"}
                      </td>
                      <td className="py-2 pr-4">
                        {log.user_feedback ? (
                          <Badge variant={log.user_feedback === "thumbs_up" ? "green" : "red"}>
                            {log.user_feedback === "thumbs_up" ? "+" : "-"}
                          </Badge>
                        ) : (
                          <span className="text-gray-400">—</span>
                        )}
                      </td>
                      <td className="py-2 text-gray-500 text-xs">
                        {new Date(log.ingested_at).toLocaleString()}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="text-sm text-gray-500 text-center py-4">No logs ingested yet</p>
          )}
        </CardBody>
      </Card>
    </div>
  );
}
