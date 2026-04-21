"use client";

import Link from "next/link";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import type { GateDecision, MetricFailure } from "@/types";

/**
 * Significance-aware gate decision panel.
 *
 * Renders per-metric failures with:
 *   - point estimate + threshold
 *   - 95% bootstrap CI (when available)
 *   - Mann-Whitney p-value vs. last passing baseline
 *   - sample sizes
 *
 * Falls back to a compact summary row when a failure lacks CI / p-value
 * (e.g. the pass_rate case, where there's no per-case distribution to
 * bootstrap).
 */
export function GateDecisionPanel({ gate }: { gate: GateDecision }) {
  if (gate.passed === null) {
    return (
      <Card>
        <CardHeader>Release Gate</CardHeader>
        <CardBody>
          <div className="text-sm text-gray-500 dark:text-gray-400">
            Run is not yet complete.
          </div>
        </CardBody>
      </Card>
    );
  }

  const { passed, metric_failures, rule_failures, baseline_run_id } = gate;

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <span>Release Gate</span>
          <Badge variant={passed ? "green" : "red"}>
            {passed ? "APPROVED" : "BLOCKED"}
          </Badge>
        </div>
      </CardHeader>
      <CardBody>
        {baseline_run_id ? (
          <div className="mb-3 text-xs text-gray-600 dark:text-gray-400">
            Compared against baseline run{" "}
            <Link
              href={`/runs/${baseline_run_id}`}
              className="font-mono text-brand-600 hover:underline dark:text-brand-400"
            >
              {baseline_run_id.slice(0, 8)}
            </Link>
          </div>
        ) : (
          <div className="mb-3 text-xs text-gray-500 dark:text-gray-500">
            No baseline run available — absolute threshold only.
          </div>
        )}

        {passed && metric_failures.length === 0 && rule_failures.length === 0 ? (
          <div className="text-sm text-gray-700 dark:text-gray-300">
            All metrics within threshold. No statistically significant regression vs. baseline.
          </div>
        ) : null}

        {metric_failures.length > 0 && (
          <div className="space-y-3">
            {metric_failures.map((f) => (
              <MetricFailureRow key={f.metric} failure={f} />
            ))}
          </div>
        )}

        {rule_failures.length > 0 && (
          <div className="mt-4 border-t border-gray-200 pt-3 dark:border-slate-700">
            <div className="text-xs font-semibold text-gray-600 dark:text-gray-400">
              Rule violations ({rule_failures.length})
            </div>
            <ul className="mt-1 space-y-1 text-xs text-gray-700 dark:text-gray-300">
              {rule_failures.slice(0, 5).map((rf) => (
                <li key={rf.result_id} className="font-mono">
                  case {rf.test_case_id.slice(0, 8)}
                </li>
              ))}
              {rule_failures.length > 5 && (
                <li className="text-gray-500">
                  + {rule_failures.length - 5} more
                </li>
              )}
            </ul>
          </div>
        )}
      </CardBody>
    </Card>
  );
}

function MetricFailureRow({ failure }: { failure: MetricFailure }) {
  const { metric, actual, threshold, ci_lower, ci_upper, p_value, sample_size, reason } = failure;

  const hasCi = ci_lower !== null && ci_lower !== undefined && ci_upper !== null && ci_upper !== undefined;
  const hasP = p_value !== null && p_value !== undefined;

  return (
    <div className="rounded-md border border-red-200 bg-red-50 p-3 text-sm dark:border-red-900/50 dark:bg-red-900/10">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="font-semibold text-red-900 dark:text-red-300">
            {formatMetricName(metric)}
          </div>
          <div className="mt-0.5 font-mono text-xs text-red-800 dark:text-red-400">
            point={actual.toFixed(3)} threshold={threshold.toFixed(3)} Δ={(actual - threshold).toFixed(3)}
          </div>
        </div>
        {sample_size ? (
          <Badge variant="gray">n={sample_size}</Badge>
        ) : null}
      </div>

      {(hasCi || hasP) && (
        <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-red-900 dark:text-red-300">
          {hasCi && (
            <span className="font-mono">
              95% CI [{(ci_lower as number).toFixed(3)}, {(ci_upper as number).toFixed(3)}]
            </span>
          )}
          {hasP && (
            <span className="font-mono" title="Mann-Whitney U p-value vs. baseline run">
              p = {(p_value as number).toFixed(3)}
            </span>
          )}
        </div>
      )}

      {hasCi && (
        <CIBar
          threshold={threshold}
          ciLower={ci_lower as number}
          ciUpper={ci_upper as number}
          point={actual}
        />
      )}

      {reason && (
        <div className="mt-2 text-xs italic text-red-700 dark:text-red-400">
          {reason}
        </div>
      )}
    </div>
  );
}

/** Simple 0..1 bar showing threshold position, CI range, and point estimate. */
function CIBar({
  threshold,
  ciLower,
  ciUpper,
  point,
}: {
  threshold: number;
  ciLower: number;
  ciUpper: number;
  point: number;
}) {
  const clamp = (x: number) => Math.max(0, Math.min(1, x));
  const t = clamp(threshold) * 100;
  const lo = clamp(ciLower) * 100;
  const hi = clamp(ciUpper) * 100;
  const p = clamp(point) * 100;

  return (
    <div className="mt-3">
      <div className="relative h-5 w-full rounded bg-gray-200 dark:bg-slate-700">
        {/* CI range */}
        <div
          className="absolute top-0 h-5 rounded bg-red-300/70 dark:bg-red-800/60"
          style={{ left: `${lo}%`, width: `${Math.max(hi - lo, 0.5)}%` }}
          aria-label="95% CI"
        />
        {/* Threshold line */}
        <div
          className="absolute top-0 h-5 w-0.5 bg-gray-900 dark:bg-gray-100"
          style={{ left: `${t}%` }}
          aria-label="threshold"
        />
        {/* Point estimate */}
        <div
          className="absolute top-0 h-5 w-0.5 bg-red-700 dark:bg-red-400"
          style={{ left: `${p}%` }}
          aria-label="point estimate"
        />
      </div>
      <div className="mt-1 flex justify-between text-[10px] text-gray-500 dark:text-gray-400">
        <span>0.0</span>
        <span>threshold={threshold.toFixed(2)}</span>
        <span>1.0</span>
      </div>
    </div>
  );
}

function formatMetricName(metric: string): string {
  return metric
    .split("_")
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(" ");
}
