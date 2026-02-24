"use client";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import useSWR, { useSWRConfig } from "swr";
import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import { formatDate, truncate } from "@/lib/utils";
import { Badge } from "@/components/ui/Badge";
import { Card, CardHeader } from "@/components/ui/Card";
import { PageLoader } from "@/components/ui/LoadingSpinner";
import type { EvaluationRun, TestCase } from "@/types";

/* ─── System-type display config ──────────────────────────────────── */
const SYSTEM_LABELS: Record<string, { label: string; color: string; defaultVersion: string }> = {
  rag:      { label: "RAG Pipeline",    color: "bg-blue-100 text-blue-800",   defaultVersion: "demo-rag-v1" },
  agent:    { label: "Tool Agent",      color: "bg-purple-100 text-purple-800", defaultVersion: "demo-agent-v1" },
  chatbot:  { label: "Chatbot",         color: "bg-pink-100 text-pink-800",   defaultVersion: "demo-chatbot-v1" },
  search:   { label: "Search Engine",   color: "bg-teal-100 text-teal-800",   defaultVersion: "demo-search-v1" },
};

/* ─── Trigger-run modal ─────────────────────────────────────────────── */
function TriggerRunModal({ testSetId, systemType, onClose }: { testSetId: string; systemType: string; onClose: () => void }) {
  const router = useRouter();
  const cfg = SYSTEM_LABELS[systemType] ?? SYSTEM_LABELS.rag;
  const [pipelineVersion, setPipelineVersion] = useState(cfg.defaultVersion);
  const [triggeredBy, setTriggeredBy] = useState("browser");
  const [notes, setNotes] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const overlayRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  async function handleStart() {
    setLoading(true);
    setError(null);
    try {
      const run: EvaluationRun = await api.runs.trigger({
        test_set_id: testSetId,
        pipeline_version: pipelineVersion || undefined,
        triggered_by: triggeredBy || "browser",
        notes: notes.trim() || undefined,
      });
      router.push(`/runs/${run.id}`);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to trigger run");
      setLoading(false);
    }
  }

  return (
    <div
      ref={overlayRef}
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/30"
      onClick={(e) => { if (e.target === overlayRef.current) onClose(); }}
    >
      <div className="bg-white rounded-xl border border-gray-200 shadow-xl w-full max-w-md mx-4 p-6 space-y-5">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <h2 className="text-base font-semibold text-gray-900">Trigger Evaluation Run</h2>
            <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${cfg.color}`}>{cfg.label}</span>
          </div>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600 text-lg leading-none">✕</button>
        </div>
        {error && (
          <p className="text-xs text-red-600 bg-red-50 border border-red-200 rounded px-3 py-2">{error}</p>
        )}
        <div className="space-y-4">
          <div>
            <label className="block text-xs font-medium text-gray-700 mb-1">
              Pipeline version <span className="font-normal text-gray-400">(optional)</span>
            </label>
            <input
              value={pipelineVersion}
              onChange={(e) => setPipelineVersion(e.target.value)}
              placeholder="e.g. v1.2.3 or main"
              className="w-full text-sm border border-gray-200 rounded-md px-3 py-2 focus:outline-none focus:ring-2 focus:ring-brand-500"
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-700 mb-1">
              What changed in this version? <span className="font-normal text-gray-400">(optional)</span>
            </label>
            <textarea
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              placeholder={"e.g. Switched LLM to gpt-4o, increased top-k from 3→5, rewrote system prompt to be more concise"}
              rows={3}
              className="w-full text-sm border border-gray-200 rounded-md px-3 py-2 focus:outline-none focus:ring-2 focus:ring-brand-500 resize-none"
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-700 mb-1">Triggered by</label>
            <input
              value={triggeredBy}
              onChange={(e) => setTriggeredBy(e.target.value)}
              placeholder="browser"
              className="w-full text-sm border border-gray-200 rounded-md px-3 py-2 focus:outline-none focus:ring-2 focus:ring-brand-500"
            />
          </div>
        </div>
        <div className="flex gap-3 pt-1">
          <button
            onClick={handleStart}
            disabled={loading}
            className="flex-1 bg-brand-600 text-white text-sm font-medium py-2 rounded-md hover:bg-brand-700 disabled:opacity-50 transition-colors"
          >
            {loading ? "Starting…" : "▶ Start Run"}
          </button>
          <button
            onClick={onClose}
            className="flex-1 text-sm font-medium py-2 rounded-md border border-gray-200 hover:bg-gray-50 transition-colors"
          >
            Cancel
          </button>
        </div>
      </div>
    </div>
  );
}

/* ─── Main page ─────────────────────────────────────────────────────── */
export default function TestSetDetailPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const searchParams = useSearchParams();
  const { mutate } = useSWRConfig();

  const { data: testSet } = useSWR(`test-set-${id}`, () => api.testSets.get(id));
  const { data: cases, isLoading } = useSWR(`test-cases-${id}`, () =>
    api.testCases.list(id, 0, 200)
  );

  // Inline editing state
  const [editingId, setEditingId] = useState<string | null>(null);
  const [draft, setDraft] = useState({ query: "", ground_truth: "", tags: "" });
  const [saving, setSaving] = useState(false);
  const [tableError, setTableError] = useState<string | null>(null);

  // Add new test case state
  const [showAddForm, setShowAddForm] = useState(false);
  const [newCase, setNewCase] = useState({ query: "", ground_truth: "", tags: "" });
  const [adding, setAdding] = useState(false);

  // Run modal state
  const [showRunModal, setShowRunModal] = useState(false);
  useEffect(() => {
    if (searchParams.get("run") === "1") setShowRunModal(true);
  }, [searchParams]);

  // Generate modal state
  const [showGenerateModal, setShowGenerateModal] = useState(false);
  const [genTopic, setGenTopic] = useState("");
  const [genCount, setGenCount] = useState(10);
  const [generating, setGenerating] = useState(false);
  const [genStatus, setGenStatus] = useState<string | null>(null);

  // Compare models modal state
  const [showCompareModal, setShowCompareModal] = useState(false);
  const [modelConfigs, setModelConfigs] = useState<{ model: string; top_k: string }[]>([
    { model: "gpt-4o", top_k: "5" },
    { model: "gpt-4o-mini", top_k: "5" },
  ]);
  const [comparing, setComparing] = useState(false);

  if (!testSet || isLoading) return <PageLoader />;

  function startEdit(tc: TestCase) {
    setEditingId(tc.id);
    setDraft({
      query: tc.query,
      ground_truth: tc.ground_truth ?? "",
      tags: (tc.tags ?? []).join(", "),
    });
    setTableError(null);
  }

  function cancelEdit() {
    setEditingId(null);
    setTableError(null);
  }

  async function saveEdit(tc: TestCase) {
    setSaving(true);
    setTableError(null);
    try {
      await api.testCases.update(id, tc.id, {
        query: draft.query.trim(),
        ground_truth: draft.ground_truth.trim() || null,
        tags: draft.tags.split(",").map((t) => t.trim()).filter(Boolean),
      } as Partial<TestCase>);
      await mutate(`test-cases-${id}`);
      await mutate(`test-set-${id}`);
      setEditingId(null);
    } catch (e: unknown) {
      setTableError(e instanceof Error ? e.message : "Save failed");
    } finally {
      setSaving(false);
    }
  }

  async function deleteCase(tc: TestCase) {
    if (!window.confirm(`Delete this test case?\n\n"${truncate(tc.query, 80)}"`)) return;
    setTableError(null);
    try {
      await api.testCases.delete(id, tc.id);
      await mutate(`test-cases-${id}`);
      await mutate(`test-set-${id}`);
    } catch (e: unknown) {
      setTableError(e instanceof Error ? e.message : "Delete failed");
    }
  }

  async function createCase() {
    if (!newCase.query.trim()) return;
    setAdding(true);
    setTableError(null);
    try {
      await api.testCases.create(id, {
        query: newCase.query.trim(),
        ground_truth: newCase.ground_truth.trim() || null,
        tags: newCase.tags.split(",").map((t) => t.trim()).filter(Boolean),
      } as Partial<TestCase>);
      await mutate(`test-cases-${id}`);
      await mutate(`test-set-${id}`);
      setNewCase({ query: "", ground_truth: "", tags: "" });
      setShowAddForm(false);
    } catch (e: unknown) {
      setTableError(e instanceof Error ? e.message : "Failed to create test case");
    } finally {
      setAdding(false);
    }
  }

  async function handleCompareModels() {
    const configs = modelConfigs
      .filter((c) => c.model.trim())
      .map((c) => ({
        model: c.model.trim(),
        top_k: parseInt(c.top_k) || 5,
      }));
    if (configs.length < 2) return;
    setComparing(true);
    try {
      const result = await api.runs.triggerMulti({
        test_set_id: id,
        configs,
      });
      router.push(result.compare_url);
    } catch (e: unknown) {
      setTableError(e instanceof Error ? e.message : "Failed to trigger multi-run");
      setComparing(false);
    }
  }

  async function handleGenerate() {
    if (!genTopic.trim()) return;
    setGenerating(true);
    setGenStatus(null);
    try {
      await api.testSets.generate(id, { topic: genTopic.trim(), count: genCount });
      setGenStatus(`Generating ${genCount} cases... This may take a moment.`);
      // Poll for new cases after a delay
      setTimeout(async () => {
        await mutate(`test-cases-${id}`);
        await mutate(`test-set-${id}`);
        setGenerating(false);
        setGenStatus(`Done! Generated ${genCount} test cases.`);
        setTimeout(() => {
          setShowGenerateModal(false);
          setGenStatus(null);
          setGenTopic("");
        }, 2000);
      }, 8000);
    } catch (e: unknown) {
      setGenStatus(e instanceof Error ? e.message : "Generation failed");
      setGenerating(false);
    }
  }

  return (
    <>
      {showRunModal && (
        <TriggerRunModal testSetId={id} systemType={testSet.system_type} onClose={() => setShowRunModal(false)} />
      )}

      {/* Generate Modal */}
      {showGenerateModal && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/30"
          onClick={(e) => { if (e.target === e.currentTarget) setShowGenerateModal(false); }}
        >
          <div className="bg-white rounded-xl border border-gray-200 shadow-xl w-full max-w-md mx-4 p-6 space-y-5">
            <div className="flex items-center justify-between">
              <h2 className="text-base font-semibold text-gray-900">Generate Test Cases with AI</h2>
              <button onClick={() => setShowGenerateModal(false)} className="text-gray-400 hover:text-gray-600 text-lg leading-none">x</button>
            </div>
            <div className="space-y-4">
              <div>
                <label className="block text-xs font-medium text-gray-700 mb-1">Topic / Description</label>
                <textarea
                  value={genTopic}
                  onChange={(e) => setGenTopic(e.target.value)}
                  placeholder="e.g. Customer support for an e-commerce platform, handling returns and refund policies"
                  rows={3}
                  className="w-full text-sm border border-gray-200 rounded-md px-3 py-2 focus:outline-none focus:ring-2 focus:ring-brand-500 resize-none"
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-700 mb-1">
                  Number of cases: <span className="font-mono text-brand-600">{genCount}</span>
                </label>
                <input
                  type="range"
                  min={1}
                  max={50}
                  value={genCount}
                  onChange={(e) => setGenCount(Number(e.target.value))}
                  className="w-full accent-brand-600"
                />
                <div className="flex justify-between text-xs text-gray-400 mt-0.5">
                  <span>1</span><span>50</span>
                </div>
              </div>
            </div>
            {genStatus && (
              <p className={`text-xs px-3 py-2 rounded ${genStatus.startsWith("Done") ? "bg-green-50 text-green-700 border border-green-200" : genStatus.includes("failed") ? "bg-red-50 text-red-700 border border-red-200" : "bg-blue-50 text-blue-700 border border-blue-200"}`}>
                {genStatus}
              </p>
            )}
            <div className="flex gap-3 pt-1">
              <button
                onClick={handleGenerate}
                disabled={generating || !genTopic.trim()}
                className="flex-1 bg-brand-600 text-white text-sm font-medium py-2 rounded-md hover:bg-brand-700 disabled:opacity-50 transition-colors"
              >
                {generating ? "Generating..." : "Generate"}
              </button>
              <button
                onClick={() => setShowGenerateModal(false)}
                className="flex-1 text-sm font-medium py-2 rounded-md border border-gray-200 hover:bg-gray-50 transition-colors"
              >
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Compare Models Modal */}
      {showCompareModal && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/30"
          onClick={(e) => { if (e.target === e.currentTarget) setShowCompareModal(false); }}
        >
          <div className="bg-white rounded-xl border border-gray-200 shadow-xl w-full max-w-md mx-4 p-6 space-y-5">
            <div className="flex items-center justify-between">
              <h2 className="text-base font-semibold text-gray-900">Compare Models</h2>
              <button onClick={() => setShowCompareModal(false)} className="text-gray-400 hover:text-gray-600 text-lg leading-none">x</button>
            </div>
            <p className="text-xs text-gray-500">Add 2-6 model configurations to compare side-by-side on this test set.</p>
            <div className="space-y-3">
              {modelConfigs.map((config, i) => (
                <div key={i} className="flex items-center gap-2">
                  <input
                    value={config.model}
                    onChange={(e) => {
                      const next = [...modelConfigs];
                      next[i] = { ...next[i], model: e.target.value };
                      setModelConfigs(next);
                    }}
                    placeholder="Model name (e.g. gpt-4o)"
                    className="flex-1 text-sm border border-gray-200 rounded-md px-3 py-2 focus:outline-none focus:ring-2 focus:ring-brand-500"
                  />
                  <input
                    value={config.top_k}
                    onChange={(e) => {
                      const next = [...modelConfigs];
                      next[i] = { ...next[i], top_k: e.target.value };
                      setModelConfigs(next);
                    }}
                    placeholder="top_k"
                    className="w-20 text-sm border border-gray-200 rounded-md px-3 py-2 focus:outline-none focus:ring-2 focus:ring-brand-500"
                  />
                  {modelConfigs.length > 2 && (
                    <button
                      onClick={() => setModelConfigs(modelConfigs.filter((_, j) => j !== i))}
                      className="text-gray-400 hover:text-red-500 text-sm"
                    >
                      x
                    </button>
                  )}
                </div>
              ))}
              {modelConfigs.length < 6 && (
                <button
                  onClick={() => setModelConfigs([...modelConfigs, { model: "", top_k: "5" }])}
                  className="text-xs text-brand-600 hover:text-brand-700 font-medium"
                >
                  + Add model
                </button>
              )}
            </div>
            <div className="flex gap-3 pt-1">
              <button
                onClick={handleCompareModels}
                disabled={comparing || modelConfigs.filter((c) => c.model.trim()).length < 2}
                className="flex-1 bg-purple-600 text-white text-sm font-medium py-2 rounded-md hover:bg-purple-700 disabled:opacity-50 transition-colors"
              >
                {comparing ? "Starting..." : "Start Comparison"}
              </button>
              <button
                onClick={() => setShowCompareModal(false)}
                className="flex-1 text-sm font-medium py-2 rounded-md border border-gray-200 hover:bg-gray-50 transition-colors"
              >
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}

      <div className="p-6 space-y-6 max-w-5xl mx-auto">
        {/* Header */}
        <div className="flex items-start justify-between gap-4">
          <div>
            <div className="flex items-center gap-2 text-sm text-gray-400 mb-1">
              <Link href="/test-sets" className="hover:text-gray-600">Test Sets</Link>
              <span>/</span>
              <span className="text-gray-700">{testSet.name}</span>
            </div>
            <h1 className="text-xl font-bold text-gray-900">{testSet.name}</h1>
            <p className="text-sm text-gray-500">
              {testSet.test_case_count} cases · v{testSet.version} · Updated {formatDate(testSet.updated_at)}
            </p>
          </div>
          <div className="flex items-center gap-2 flex-shrink-0">
            <button
              onClick={() => setShowGenerateModal(true)}
              className="px-4 py-2 text-sm font-medium text-brand-700 bg-brand-50 border border-brand-200 rounded-md hover:bg-brand-100 transition-colors"
            >
              Generate Cases
            </button>
            <button
              onClick={() => setShowCompareModal(true)}
              className="px-4 py-2 text-sm font-medium text-purple-700 bg-purple-50 border border-purple-200 rounded-md hover:bg-purple-100 transition-colors"
            >
              Compare Models
            </button>
            <button
              onClick={() => setShowRunModal(true)}
              className="px-4 py-2 bg-brand-600 text-white text-sm font-medium rounded-md hover:bg-brand-700 transition-colors"
            >
              Run Evaluation
            </button>
          </div>
        </div>

        {testSet.description && (
          <p className="text-sm text-gray-600">{testSet.description}</p>
        )}

        {tableError && (
          <p className="text-xs text-red-600 bg-red-50 border border-red-200 rounded px-3 py-2">{tableError}</p>
        )}

        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <h2 className="text-sm font-semibold text-gray-900">Test Cases</h2>
              <button
                onClick={() => { setShowAddForm(true); setEditingId(null); setTableError(null); }}
                disabled={showAddForm}
                className="text-xs px-3 py-1.5 bg-brand-600 text-white rounded-md hover:bg-brand-700 disabled:opacity-40 transition-colors"
              >
                + Add Case
              </button>
            </div>
          </CardHeader>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-100">
                  {["Query", "Ground Truth", "Tags", "Rules", "Created", "Actions"].map((h) => (
                    <th key={h} className="px-4 py-2.5 text-left text-xs font-medium text-gray-500 uppercase tracking-wide">
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-50">
                {/* ── Inline add form ── */}
                {showAddForm && (
                  <tr className="bg-green-50/40">
                    <td className="px-4 py-3 align-top">
                      <textarea
                        autoFocus
                        value={newCase.query}
                        onChange={(e) => setNewCase({ ...newCase, query: e.target.value })}
                        placeholder="Enter the question or prompt…"
                        rows={3}
                        className="w-full text-xs border border-gray-300 rounded px-2 py-1.5 focus:outline-none focus:ring-2 focus:ring-brand-400 resize-none"
                      />
                    </td>
                    <td className="px-4 py-3 align-top">
                      <textarea
                        value={newCase.ground_truth}
                        onChange={(e) => setNewCase({ ...newCase, ground_truth: e.target.value })}
                        placeholder="Expected answer (optional)"
                        rows={3}
                        className="w-full text-xs border border-gray-300 rounded px-2 py-1.5 focus:outline-none focus:ring-2 focus:ring-brand-400 resize-none"
                      />
                    </td>
                    <td className="px-4 py-3 align-top">
                      <input
                        value={newCase.tags}
                        onChange={(e) => setNewCase({ ...newCase, tags: e.target.value })}
                        placeholder="tag1, tag2"
                        className="w-28 text-xs border border-gray-300 rounded px-2 py-1.5 focus:outline-none focus:ring-2 focus:ring-brand-400"
                      />
                    </td>
                    <td className="px-4 py-3 text-xs text-gray-300 align-top">—</td>
                    <td className="px-4 py-3 text-xs text-gray-300 align-top">now</td>
                    <td className="px-4 py-3 align-top whitespace-nowrap">
                      <div className="flex gap-2">
                        <button
                          onClick={createCase}
                          disabled={adding || !newCase.query.trim()}
                          className="text-xs px-2.5 py-1 bg-brand-600 text-white rounded hover:bg-brand-700 disabled:opacity-50 disabled:cursor-not-allowed"
                        >
                          {adding ? "Saving…" : "Save"}
                        </button>
                        <button
                          onClick={() => { setShowAddForm(false); setNewCase({ query: "", ground_truth: "", tags: "" }); }}
                          disabled={adding}
                          className="text-xs px-2.5 py-1 border border-gray-200 rounded hover:bg-gray-100"
                        >
                          Cancel
                        </button>
                      </div>
                    </td>
                  </tr>
                )}
                {(cases ?? []).map((tc) => {
                  const isEditing = editingId === tc.id;
                  return (
                    <tr key={tc.id} className={isEditing ? "bg-blue-50/40" : "hover:bg-gray-50"}>
                      {/* Query */}
                      <td className="px-4 py-3 max-w-xs align-top">
                        {isEditing ? (
                          <textarea
                            value={draft.query}
                            onChange={(e) => setDraft({ ...draft, query: e.target.value })}
                            rows={3}
                            className="w-full text-xs border border-gray-300 rounded px-2 py-1.5 focus:outline-none focus:ring-2 focus:ring-brand-400 resize-none"
                          />
                        ) : (
                          <p className="text-gray-900 text-xs">{truncate(tc.query, 100)}</p>
                        )}
                      </td>

                      {/* Ground Truth */}
                      <td className="px-4 py-3 max-w-xs align-top">
                        {isEditing ? (
                          <textarea
                            value={draft.ground_truth}
                            onChange={(e) => setDraft({ ...draft, ground_truth: e.target.value })}
                            rows={3}
                            placeholder="optional"
                            className="w-full text-xs border border-gray-300 rounded px-2 py-1.5 focus:outline-none focus:ring-2 focus:ring-brand-400 resize-none"
                          />
                        ) : (
                          <span className="text-xs text-gray-500">
                            {tc.ground_truth ? truncate(tc.ground_truth, 60) : "—"}
                          </span>
                        )}
                      </td>

                      {/* Tags */}
                      <td className="px-4 py-3 align-top">
                        {isEditing ? (
                          <input
                            value={draft.tags}
                            onChange={(e) => setDraft({ ...draft, tags: e.target.value })}
                            placeholder="tag1, tag2"
                            className="w-28 text-xs border border-gray-300 rounded px-2 py-1.5 focus:outline-none focus:ring-2 focus:ring-brand-400"
                          />
                        ) : (
                          <div className="flex flex-wrap gap-1">
                            {(tc.tags ?? []).map((tag) => (
                              <Badge key={tag} variant="blue">{tag}</Badge>
                            ))}
                          </div>
                        )}
                      </td>

                      {/* Rules — read-only */}
                      <td className="px-4 py-3 text-xs text-gray-500 align-top">
                        {(tc.failure_rules ?? []).length > 0 ? (
                          <Badge variant="orange">{tc.failure_rules!.length} rules</Badge>
                        ) : (
                          <span className="text-gray-300">none</span>
                        )}
                      </td>

                      {/* Created */}
                      <td className="px-4 py-3 text-xs text-gray-400 align-top whitespace-nowrap">
                        {formatDate(tc.created_at)}
                      </td>

                      {/* Actions */}
                      <td className="px-4 py-3 align-top whitespace-nowrap">
                        {isEditing ? (
                          <div className="flex gap-2">
                            <button
                              onClick={() => saveEdit(tc)}
                              disabled={saving || !draft.query.trim()}
                              className="text-xs px-2.5 py-1 bg-brand-600 text-white rounded hover:bg-brand-700 disabled:opacity-50 disabled:cursor-not-allowed"
                            >
                              {saving ? "Saving…" : "Save"}
                            </button>
                            <button
                              onClick={cancelEdit}
                              disabled={saving}
                              className="text-xs px-2.5 py-1 border border-gray-200 rounded hover:bg-gray-100"
                            >
                              Cancel
                            </button>
                          </div>
                        ) : (
                          <div className="flex gap-2">
                            <button
                              onClick={() => startEdit(tc)}
                              className="text-xs px-2.5 py-1 border border-gray-200 rounded hover:bg-gray-100 text-gray-600"
                            >
                              ✎ Edit
                            </button>
                            <button
                              onClick={() => deleteCase(tc)}
                              className="text-xs px-2.5 py-1 border border-red-200 rounded hover:bg-red-50 text-red-600"
                            >
                              Delete
                            </button>
                          </div>
                        )}
                      </td>
                    </tr>
                  );
                })}
                {cases?.length === 0 && !showAddForm && (
                  <tr>
                    <td colSpan={6} className="px-4 py-8 text-center text-gray-400 text-sm">
                      No test cases yet.{" "}
                      <button
                        onClick={() => setShowAddForm(true)}
                        className="text-brand-600 hover:underline"
                      >
                        Add your first test case →
                      </button>
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </Card>
      </div>
    </>
  );
}
