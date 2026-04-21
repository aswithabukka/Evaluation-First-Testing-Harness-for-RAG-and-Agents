"use client";

import { useState } from "react";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import type { RunManifest, BudgetSummary } from "@/types";

/**
 * Run reproducibility panel.
 *
 * Surfaces the pieces of runner.manifest.Manifest that matter for audits:
 *   - fingerprint (two runs with the same hash should produce the same gate decision)
 *   - evaluator identities + versions
 *   - library versions for the judge stack
 *   - prompt count + seeds
 *   - budget outcome (cost, time, whether the ceiling tripped)
 *
 * Everything else (full prompt hash map, env snapshot) is hidden behind a
 * "View raw JSON" toggle — useful for debugging but noisy by default.
 */
export function ManifestPanel({
  manifest,
  fingerprint,
  budget,
}: {
  manifest: RunManifest | null | undefined;
  fingerprint: string | null | undefined;
  budget: BudgetSummary | null | undefined;
}) {
  const [showRaw, setShowRaw] = useState(false);

  if (!manifest && !budget) {
    return null;
  }

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <span>Reproducibility</span>
          {fingerprint ? (
            <span
              className="font-mono text-xs text-gray-600 dark:text-gray-400"
              title="Stable hash of the manifest — same hash = same gate decision up to LLM non-determinism."
            >
              fingerprint {fingerprint}
            </span>
          ) : null}
        </div>
      </CardHeader>
      <CardBody>
        {budget && (
          <BudgetRow budget={budget} />
        )}

        {manifest && (
          <div className="mt-3 space-y-3">
            <EvaluatorList evaluators={manifest.evaluators} />
            <LibraryVersions libraries={manifest.libraries} />
            <div className="grid grid-cols-2 gap-2 text-xs text-gray-600 dark:text-gray-400">
              <div>
                <span className="font-semibold">Prompts recorded:</span>{" "}
                {Object.keys(manifest.prompts || {}).length}
              </div>
              <div>
                <span className="font-semibold">Seeds:</span>{" "}
                {Object.entries(manifest.seeds || {})
                  .map(([k, v]) => `${k}=${v}`)
                  .join(", ") || "—"}
              </div>
            </div>
            {manifest.env && (
              <div className="text-xs text-gray-500 dark:text-gray-500">
                {manifest.env.python ? `Python ${manifest.env.python}` : null}
                {manifest.env.platform ? ` · ${manifest.env.platform}` : null}
              </div>
            )}

            <button
              type="button"
              onClick={() => setShowRaw((v) => !v)}
              className="text-xs text-brand-600 hover:underline dark:text-brand-400"
            >
              {showRaw ? "Hide" : "View"} raw manifest JSON
            </button>
            {showRaw && (
              <pre className="max-h-64 overflow-auto rounded bg-gray-100 p-2 text-[11px] text-gray-800 dark:bg-slate-900 dark:text-gray-200">
                {JSON.stringify(manifest, null, 2)}
              </pre>
            )}
          </div>
        )}
      </CardBody>
    </Card>
  );
}

function BudgetRow({ budget }: { budget: BudgetSummary }) {
  const pctUsd =
    budget.max_usd && budget.max_usd > 0
      ? Math.min(100, (budget.spent_usd / budget.max_usd) * 100)
      : null;
  const pctTime =
    budget.max_seconds && budget.max_seconds > 0
      ? Math.min(100, (budget.elapsed_seconds / budget.max_seconds) * 100)
      : null;

  return (
    <div className="space-y-2 rounded-md border border-gray-200 p-3 dark:border-slate-700">
      <div className="flex items-center justify-between text-xs">
        <span className="font-semibold text-gray-700 dark:text-gray-300">Budget</span>
        {budget.exceeded ? (
          <Badge variant="red">EXCEEDED</Badge>
        ) : (
          <Badge variant="green">within limits</Badge>
        )}
      </div>

      {budget.max_usd !== null && (
        <ProgressRow
          label={`Cost: $${budget.spent_usd.toFixed(4)} / $${budget.max_usd.toFixed(2)}`}
          pct={pctUsd}
          exceeded={budget.exceeded}
        />
      )}
      {budget.max_seconds !== null && (
        <ProgressRow
          label={`Time: ${budget.elapsed_seconds.toFixed(1)}s / ${budget.max_seconds}s`}
          pct={pctTime}
          exceeded={budget.exceeded}
        />
      )}
      {budget.exceeded_reason && (
        <div className="text-xs italic text-red-700 dark:text-red-400">
          {budget.exceeded_reason}
        </div>
      )}
    </div>
  );
}

function ProgressRow({
  label,
  pct,
  exceeded,
}: {
  label: string;
  pct: number | null;
  exceeded: boolean;
}) {
  return (
    <div>
      <div className="text-xs text-gray-600 dark:text-gray-400">{label}</div>
      {pct !== null && (
        <div className="mt-1 h-1.5 w-full rounded bg-gray-200 dark:bg-slate-700">
          <div
            className={`h-1.5 rounded ${exceeded ? "bg-red-600" : "bg-brand-500"}`}
            style={{ width: `${pct}%` }}
          />
        </div>
      )}
    </div>
  );
}

function EvaluatorList({
  evaluators,
}: {
  evaluators: RunManifest["evaluators"];
}) {
  if (!evaluators?.length) return null;
  return (
    <div>
      <div className="text-xs font-semibold text-gray-700 dark:text-gray-300">
        Evaluators
      </div>
      <ul className="mt-1 flex flex-wrap gap-1.5">
        {evaluators.map((e) => (
          <li
            key={`${e.name}-${e.version}`}
            className="rounded bg-gray-100 px-2 py-0.5 font-mono text-[11px] text-gray-700 dark:bg-slate-700 dark:text-gray-200"
            title={e.class || ""}
          >
            {e.name}@{e.version}
          </li>
        ))}
      </ul>
    </div>
  );
}

function LibraryVersions({
  libraries,
}: {
  libraries: RunManifest["libraries"];
}) {
  if (!libraries) return null;
  const entries = Object.entries(libraries).filter(
    ([, v]) => v && v !== "<not-installed>"
  );
  if (!entries.length) return null;
  return (
    <div>
      <div className="text-xs font-semibold text-gray-700 dark:text-gray-300">
        Libraries
      </div>
      <ul className="mt-1 flex flex-wrap gap-1.5">
        {entries.map(([k, v]) => (
          <li
            key={k}
            className="rounded bg-gray-100 px-2 py-0.5 font-mono text-[11px] text-gray-700 dark:bg-slate-700 dark:text-gray-200"
          >
            {k} {v}
          </li>
        ))}
      </ul>
    </div>
  );
}
