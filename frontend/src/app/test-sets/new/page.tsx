"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { api } from "@/lib/api";
import { Card, CardBody } from "@/components/ui/Card";
import type { SystemType } from "@/types";

const SYSTEM_TYPES: { value: SystemType; label: string; description: string }[] = [
  { value: "rag", label: "RAG Pipeline", description: "Retrieval-augmented generation" },
  { value: "agent", label: "Tool-Use Agent", description: "LLM agent with tool calling" },
  { value: "chatbot", label: "Chatbot", description: "Conversational AI / customer support" },
  { value: "code_gen", label: "Code Generation", description: "Code completion / generation" },
  { value: "search", label: "Search / Retrieval", description: "Document search and ranking" },
  { value: "classification", label: "Classification", description: "Content moderation / labeling" },
  { value: "summarization", label: "Summarization", description: "Text summarization" },
  { value: "translation", label: "Translation", description: "Language translation" },
  { value: "custom", label: "Custom", description: "Other AI system type" },
];

export default function NewTestSetPage() {
  const router = useRouter();
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [systemType, setSystemType] = useState<SystemType>("rag");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!name.trim()) return;
    setSubmitting(true);
    setError(null);
    try {
      const ts = await api.testSets.create({
        name: name.trim(),
        description: description.trim() || undefined,
        system_type: systemType,
      });
      router.push(`/test-sets/${ts.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create test set");
      setSubmitting(false);
    }
  }

  return (
    <div className="p-6 max-w-lg mx-auto space-y-6">
      <div>
        <div className="flex items-center gap-2 text-sm text-gray-400 mb-1">
          <Link href="/test-sets" className="hover:text-gray-600">Test Sets</Link>
          <span>/</span>
          <span className="text-gray-700">New</span>
        </div>
        <h1 className="text-xl font-bold text-gray-900">Create Test Set</h1>
      </div>

      <Card>
        <CardBody>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Name</label>
              <input
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="e.g. Medical QA Safety Suite"
                className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
                required
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">AI System Type</label>
              <select
                value={systemType}
                onChange={(e) => setSystemType(e.target.value as SystemType)}
                className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-500 bg-white"
              >
                {SYSTEM_TYPES.map((st) => (
                  <option key={st.value} value={st.value}>
                    {st.label} — {st.description}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Description <span className="text-gray-400">(optional)</span>
              </label>
              <textarea
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="What this test set evaluates..."
                rows={3}
                className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
              />
            </div>
            {error && (
              <p className="text-sm text-red-600">{error}</p>
            )}
            <div className="flex gap-3">
              <button
                type="submit"
                disabled={submitting || !name.trim()}
                className="px-4 py-2 bg-brand-600 text-white text-sm font-medium rounded-md hover:bg-brand-700 disabled:opacity-50 transition-colors"
              >
                {submitting ? "Creating..." : "Create Test Set"}
              </button>
              <Link
                href="/test-sets"
                className="px-4 py-2 text-sm font-medium text-gray-600 hover:text-gray-900"
              >
                Cancel
              </Link>
            </div>
          </form>
        </CardBody>
      </Card>
    </div>
  );
}
