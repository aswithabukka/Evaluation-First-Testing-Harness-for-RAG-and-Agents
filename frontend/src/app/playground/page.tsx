"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import useSWR, { mutate as globalMutate } from "swr";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import { PageLoader } from "@/components/ui/LoadingSpinner";
import type { PlaygroundInteraction, PlaygroundSystem, PlaygroundToolCall } from "@/types";

/* ─── Types ─────────────────────────────────────────────────────────── */

interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  timestamp: number;
}

const SYSTEM_ACCENTS: Record<string, { bg: string; text: string; border: string; ring: string; light: string; dot: string }> = {
  rag:     { bg: "bg-blue-600",   text: "text-blue-700",   border: "border-blue-200", ring: "ring-blue-400",   light: "bg-blue-50",   dot: "bg-blue-400" },
  agent:   { bg: "bg-purple-600", text: "text-purple-700", border: "border-purple-200", ring: "ring-purple-400", light: "bg-purple-50", dot: "bg-purple-400" },
  chatbot: { bg: "bg-pink-600",   text: "text-pink-700",   border: "border-pink-200", ring: "ring-pink-400",   light: "bg-pink-50",   dot: "bg-pink-400" },
  search:  { bg: "bg-teal-600",   text: "text-teal-700",   border: "border-teal-200", ring: "ring-teal-400",   light: "bg-teal-50",   dot: "bg-teal-400" },
};

/* ─── Chat Message ──────────────────────────────────────────────────── */

function ChatMessage({ msg, accentDot }: { msg: Message; accentDot: string }) {
  const isUser = msg.role === "user";
  return (
    <div className={cn("flex gap-2.5 max-w-[85%]", isUser ? "ml-auto flex-row-reverse" : "mr-auto")}>
      <div
        className={cn(
          "w-7 h-7 rounded-full flex-shrink-0 flex items-center justify-center text-xs font-bold mt-0.5",
          isUser ? "bg-brand-600 text-white" : `bg-gray-200 text-gray-600`
        )}
      >
        {isUser ? "U" : "AI"}
      </div>
      <div
        className={cn(
          "rounded-2xl px-4 py-2.5 text-sm leading-relaxed",
          isUser
            ? "bg-brand-600 text-white rounded-tr-md"
            : "bg-white border border-gray-200 text-gray-800 rounded-tl-md shadow-sm"
        )}
      >
        <p className="whitespace-pre-wrap">{msg.content}</p>
      </div>
    </div>
  );
}

/* ─── Typing Indicator ──────────────────────────────────────────────── */

function TypingIndicator({ dotColor }: { dotColor: string }) {
  return (
    <div className="flex gap-2.5 mr-auto max-w-[85%]">
      <div className="w-7 h-7 rounded-full flex-shrink-0 flex items-center justify-center text-xs font-bold bg-gray-200 text-gray-600 mt-0.5">
        AI
      </div>
      <div className="bg-white border border-gray-200 rounded-2xl rounded-tl-md px-4 py-3 shadow-sm flex items-center gap-1.5">
        {[0, 1, 2].map((i) => (
          <span
            key={i}
            className={cn("w-2 h-2 rounded-full animate-bounce", dotColor)}
            style={{ animationDelay: `${i * 150}ms`, animationDuration: "0.8s" }}
          />
        ))}
      </div>
    </div>
  );
}

/* ─── Document Upload Panel (RAG) ──────────────────────────────────── */

function DocumentUploadPanel() {
  const { data: docData, mutate: mutateDocs } = useSWR("rag-documents", () => api.playground.listDocuments());
  const [textInput, setTextInput] = useState("");
  const [uploading, setUploading] = useState(false);
  const [clearing, setClearing] = useState(false);
  const [dragOver, setDragOver] = useState(false);
  const [status, setStatus] = useState<{ type: "success" | "error"; msg: string } | null>(null);
  const fileInputId = "rag-file-upload";

  const docs = docData?.documents ?? [];
  const docCount = docData?.count ?? 0;

  // Clear status after 3s
  useEffect(() => {
    if (!status) return;
    const t = setTimeout(() => setStatus(null), 3000);
    return () => clearTimeout(t);
  }, [status]);

  const handleUploadText = useCallback(async () => {
    const text = textInput.trim();
    if (!text || uploading) return;
    setUploading(true);
    setStatus(null);
    try {
      const res = await api.playground.uploadDocuments([text]);
      setTextInput("");
      setStatus({ type: "success", msg: `Added 1 document (${res.total} total)` });
      mutateDocs();
    } catch (err) {
      setStatus({ type: "error", msg: err instanceof Error ? err.message : "Upload failed" });
    }
    setUploading(false);
  }, [textInput, uploading, mutateDocs]);

  const uploadFilesToServer = useCallback(async (fileList: File[]) => {
    if (fileList.length === 0) return;
    setUploading(true);
    setStatus(null);
    try {
      const res = await api.playground.uploadFiles(fileList);
      setStatus({ type: "success", msg: `Added ${res.added} file(s) (${res.total} total)` });
      mutateDocs();
    } catch (err) {
      setStatus({ type: "error", msg: err instanceof Error ? err.message : "Upload failed" });
    }
    setUploading(false);
  }, [mutateDocs]);

  const handleFileChange = useCallback(async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (!files || files.length === 0) return;
    await uploadFilesToServer(Array.from(files));
    e.target.value = "";
  }, [uploadFilesToServer]);

  const handleDrop = useCallback(async (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    const files = e.dataTransfer.files;
    if (!files || files.length === 0) return;
    await uploadFilesToServer(Array.from(files));
  }, [uploadFilesToServer]);

  const handleClear = useCallback(async () => {
    setClearing(true);
    setStatus(null);
    try {
      const res = await api.playground.clearDocuments();
      setStatus({ type: "success", msg: res.message });
      mutateDocs();
    } catch (err) {
      setStatus({ type: "error", msg: err instanceof Error ? err.message : "Clear failed" });
    }
    setClearing(false);
  }, [mutateDocs]);

  return (
    <div className="space-y-3 pb-4 border-b border-gray-100">
      <div className="flex items-center justify-between">
        <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wide">Your Documents</h3>
        {docCount > 0 && (
          <button
            onClick={handleClear}
            disabled={clearing}
            className="text-xs text-red-500 hover:text-red-600 font-medium hover:underline disabled:opacity-50"
          >
            {clearing ? "Clearing..." : `Clear all (${docCount})`}
          </button>
        )}
      </div>

      {/* Status message */}
      {status && (
        <div className={cn(
          "text-xs px-2.5 py-1.5 rounded-md",
          status.type === "success" ? "bg-green-50 text-green-700 border border-green-200" : "bg-red-50 text-red-700 border border-red-200"
        )}>
          {status.msg}
        </div>
      )}

      {/* File upload — using <label> wrapping a real <input> for reliable click */}
      <div
        onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
        onDragLeave={() => setDragOver(false)}
        onDrop={handleDrop}
        className={cn(
          "border-2 border-dashed rounded-lg p-3 transition-colors",
          dragOver ? "border-blue-400 bg-blue-50" : "border-gray-200"
        )}
      >
        <div className="flex flex-col items-center gap-2">
          <label
            htmlFor={fileInputId}
            className="px-3 py-1.5 bg-blue-600 text-white text-xs font-medium rounded-md hover:bg-blue-700 cursor-pointer transition-colors inline-block"
          >
            {uploading ? "Uploading..." : "Choose Files"}
          </label>
          <input
            id={fileInputId}
            type="file"
            multiple
            accept=".pdf,.txt,.md,.csv,.json,.html,.xml,.log,.py,.js,.ts,.jsx,.tsx,.yaml,.yml,.toml,.cfg,.ini,.rst,.tex"
            className="sr-only"
            onChange={handleFileChange}
            disabled={uploading}
          />
          <p className="text-xs text-gray-400">or drag & drop files here (.pdf, .txt, .md, etc.)</p>
        </div>
      </div>

      {/* Text paste area */}
      <div className="space-y-1.5">
        <textarea
          value={textInput}
          onChange={(e) => setTextInput(e.target.value)}
          placeholder="Or paste text content here..."
          rows={3}
          className="w-full border border-gray-200 rounded-md px-3 py-2 text-xs text-gray-700 placeholder:text-gray-400 focus:outline-none focus:ring-2 focus:ring-blue-400 focus:border-transparent resize-none"
        />
        <button
          onClick={handleUploadText}
          disabled={!textInput.trim() || uploading}
          className="w-full px-3 py-1.5 bg-blue-600 text-white text-xs font-medium rounded-md hover:bg-blue-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
        >
          {uploading ? "Adding..." : "Add Document"}
        </button>
      </div>

      {/* Uploaded docs list */}
      {docs.length > 0 && (
        <div className="space-y-1.5 max-h-40 overflow-y-auto">
          {docs.map((doc, i) => (
            <div key={i} className="bg-blue-50/60 border border-blue-100 rounded-md px-2.5 py-1.5">
              <p className="text-xs text-gray-700 line-clamp-2">{doc}</p>
            </div>
          ))}
        </div>
      )}

      {docCount === 0 && (
        <p className="text-xs text-gray-400 italic text-center py-1">
          No documents uploaded — the RAG system uses its built-in knowledge base
        </p>
      )}
    </div>
  );
}

/* ─── Detail: RAG Contexts ──────────────────────────────────────────── */

function RagPanel({ response }: { response: PlaygroundInteraction }) {
  const scores = (response.metadata?.scores as number[]) ?? [];
  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wide">Retrieved Contexts</h3>
        <span className="text-xs text-gray-400">{response.retrieved_contexts.length} chunks</span>
      </div>
      {response.retrieved_contexts.length === 0 && (
        <p className="text-xs text-gray-400 italic">No contexts retrieved</p>
      )}
      {response.retrieved_contexts.map((ctx, i) => (
        <div key={i} className="bg-blue-50/60 border border-blue-100 rounded-lg p-3 space-y-1">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-blue-700">Chunk #{i + 1}</span>
            {scores[i] != null && (
              <span className="text-xs font-mono text-blue-600">{(scores[i] as number).toFixed(3)}</span>
            )}
          </div>
          <p className="text-xs text-gray-700 leading-relaxed">{ctx}</p>
        </div>
      ))}
      {response.metadata && Object.keys(response.metadata).length > 0 && (
        <div className="pt-2 border-t border-gray-100">
          <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1.5">Metadata</p>
          <pre className="text-xs text-gray-600 bg-gray-50 rounded-md p-2 overflow-x-auto font-mono leading-relaxed">
            {JSON.stringify(response.metadata, null, 2)}
          </pre>
        </div>
      )}
    </div>
  );
}

/* ─── Detail: Agent Tool Calls ──────────────────────────────────────── */

function AgentPanel({ response }: { response: PlaygroundInteraction }) {
  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wide">Tool Calls</h3>
        <span className="text-xs text-gray-400">{response.tool_calls.length} call{response.tool_calls.length !== 1 ? "s" : ""}</span>
      </div>
      {response.tool_calls.length === 0 && (
        <p className="text-xs text-gray-400 italic">No tools called</p>
      )}
      {response.tool_calls.map((tc: PlaygroundToolCall, i: number) => (
        <div key={i} className="bg-purple-50/60 border border-purple-100 rounded-lg p-3 space-y-2">
          <div className="flex items-center gap-2">
            <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-semibold bg-purple-100 text-purple-700 border border-purple-200">
              {tc.tool}
            </span>
            <span className="text-xs text-gray-400">#{i + 1}</span>
          </div>
          <div>
            <p className="text-xs font-medium text-gray-500 mb-0.5">Arguments</p>
            <pre className="text-xs font-mono text-gray-700 bg-white/60 rounded p-1.5 overflow-x-auto">
              {JSON.stringify(tc.args, null, 2)}
            </pre>
          </div>
          {tc.result && (
            <div>
              <p className="text-xs font-medium text-gray-500 mb-0.5">Result</p>
              <pre className="text-xs font-mono text-gray-700 bg-white/60 rounded p-1.5 overflow-x-auto">
                {JSON.stringify(tc.result, null, 2)}
              </pre>
            </div>
          )}
        </div>
      ))}
      {response.retrieved_contexts.length > 0 && (
        <div className="pt-2 border-t border-gray-100">
          <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1.5">Grounding Contexts</p>
          {response.retrieved_contexts.map((ctx, i) => (
            <p key={i} className="text-xs text-gray-600 bg-gray-50 rounded p-2 mb-1.5 font-mono">{ctx}</p>
          ))}
        </div>
      )}
    </div>
  );
}

/* ─── Detail: Chatbot Conversation ──────────────────────────────────── */

function ChatbotPanel({
  response,
  onReset,
}: {
  response: PlaygroundInteraction;
  onReset: () => void;
}) {
  const turnCount = response.turn_history.filter((t) => t.role === "user").length;
  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wide">Conversation</h3>
        <div className="flex items-center gap-2">
          <span className="text-xs text-gray-400">{turnCount} turn{turnCount !== 1 ? "s" : ""}</span>
          <button
            onClick={onReset}
            className="text-xs text-pink-600 hover:text-pink-700 font-medium hover:underline"
          >
            New Chat
          </button>
        </div>
      </div>
      {response.turn_history.length === 0 && (
        <p className="text-xs text-gray-400 italic">No conversation yet</p>
      )}
      <div className="space-y-2">
        {response.turn_history.map((turn, i) => (
          <div
            key={i}
            className={cn(
              "rounded-lg px-3 py-2 text-xs leading-relaxed",
              turn.role === "user"
                ? "bg-pink-50/60 border border-pink-100 text-gray-800"
                : "bg-white border border-gray-150 text-gray-700"
            )}
          >
            <span className={cn("font-semibold text-xs mr-1.5", turn.role === "user" ? "text-pink-700" : "text-gray-500")}>
              {turn.role === "user" ? "User" : "Alex"}:
            </span>
            {turn.content}
          </div>
        ))}
      </div>
      {response.retrieved_contexts.length > 0 && (
        <div className="pt-2 border-t border-gray-100">
          <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1.5">Knowledge Used</p>
          {response.retrieved_contexts.map((ctx, i) => (
            <p key={i} className="text-xs text-gray-600 bg-gray-50 rounded p-2 mb-1.5">{ctx}</p>
          ))}
        </div>
      )}
    </div>
  );
}

/* ─── Detail: Search Results ────────────────────────────────────────── */

function SearchPanel({ response }: { response: PlaygroundInteraction }) {
  const source = (response.metadata?.source ?? "local") as string;
  const scores = (response.metadata?.scores ?? {}) as Record<string, number>;
  const rankedIds = (response.metadata?.ranked_ids ?? []) as string[];
  const webResults = (response.metadata?.web_results ?? []) as Array<{ title: string; link: string; snippet: string }>;

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wide">
            {source === "web" ? "Web Results" : "Ranked Results"}
          </h3>
          {source === "web" && (
            <span className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-bold bg-amber-100 text-amber-700 border border-amber-200">
              Google
            </span>
          )}
          {source === "local" && (
            <span className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-bold bg-teal-100 text-teal-700 border border-teal-200">
              Local
            </span>
          )}
        </div>
        <span className="text-xs text-gray-400">
          {source === "web" ? webResults.length : response.retrieved_contexts.length} results
        </span>
      </div>

      {/* No results */}
      {response.retrieved_contexts.length === 0 && (
        <p className="text-xs text-gray-400 italic">No results found</p>
      )}

      {/* Web results — show title, snippet, clickable URL */}
      {source === "web" && webResults.map((r, i) => (
        <div key={i} className="bg-amber-50/60 border border-amber-100 rounded-lg p-3 space-y-1.5">
          <div className="flex items-start gap-2">
            <span className="inline-flex items-center justify-center w-5 h-5 rounded bg-amber-500 text-white text-xs font-bold flex-shrink-0 mt-0.5">
              {i + 1}
            </span>
            <div className="min-w-0 flex-1">
              <p className="text-xs font-semibold text-amber-900 leading-snug">{r.title}</p>
              <a
                href={r.link}
                target="_blank"
                rel="noopener noreferrer"
                className="text-[11px] text-blue-600 hover:text-blue-800 hover:underline truncate block mt-0.5"
              >
                {r.link}
              </a>
            </div>
          </div>
          <p className="text-xs text-gray-600 leading-relaxed">{r.snippet}</p>
        </div>
      ))}

      {/* Local results — rank number, doc ID, score bar */}
      {source === "local" && response.retrieved_contexts.map((ctx, i) => {
        const docId = rankedIds[i] ?? "";
        const score = scores[docId] ?? null;
        const titleMatch = ctx.match(/^\[.*?\]\s*(.+?):\s*/);
        const title = titleMatch ? titleMatch[1] : `Result #${i + 1}`;
        const content = titleMatch ? ctx.slice(titleMatch[0].length) : ctx;
        return (
          <div key={i} className="bg-teal-50/60 border border-teal-100 rounded-lg p-3 space-y-1.5">
            <div className="flex items-start justify-between gap-2">
              <div className="flex items-center gap-2">
                <span className="inline-flex items-center justify-center w-5 h-5 rounded bg-teal-600 text-white text-xs font-bold flex-shrink-0">
                  {i + 1}
                </span>
                <span className="text-xs font-semibold text-teal-800">{title}</span>
              </div>
              {docId && <span className="text-xs font-mono text-teal-600 flex-shrink-0">{docId}</span>}
            </div>
            {score !== null && (
              <div className="flex items-center gap-2">
                <div className="flex-1 h-1.5 bg-teal-100 rounded-full overflow-hidden">
                  <div
                    className="h-full bg-teal-500 rounded-full transition-all duration-500"
                    style={{ width: `${Math.round(score * 100)}%` }}
                  />
                </div>
                <span className="text-xs font-mono text-teal-700 w-12 text-right">{score.toFixed(3)}</span>
              </div>
            )}
            <p className="text-xs text-gray-600 leading-relaxed line-clamp-3">{content}</p>
          </div>
        );
      })}
    </div>
  );
}

/* ─── Detail Panel Switch ───────────────────────────────────────────── */

function DetailPanel({
  systemType,
  response,
  onResetSession,
}: {
  systemType: string;
  response: PlaygroundInteraction | null;
  onResetSession: () => void;
}) {
  if (!response) {
    return (
      <div className="space-y-0">
        {systemType === "rag" && <DocumentUploadPanel />}
        <div className="flex items-center justify-center h-48 text-center px-6">
          <div>
            <div className="text-3xl mb-3 opacity-30">
              {systemType === "rag" ? "\u{1f50d}" : systemType === "agent" ? "\u{1f916}" : systemType === "chatbot" ? "\u{1f4ac}" : "\u{1f50e}"}
            </div>
            <p className="text-sm text-gray-400">Send a message to see</p>
            <p className="text-sm text-gray-400">
              {systemType === "rag" ? "retrieved contexts" : systemType === "agent" ? "tool calls" : systemType === "chatbot" ? "conversation history" : "ranked results"}
            </p>
          </div>
        </div>
      </div>
    );
  }

  switch (systemType) {
    case "rag":     return <><DocumentUploadPanel /><RagPanel response={response} /></>;
    case "agent":   return <AgentPanel response={response} />;
    case "chatbot": return <ChatbotPanel response={response} onReset={onResetSession} />;
    case "search":  return <SearchPanel response={response} />;
    default:        return null;
  }
}

/* ─── Main Page ─────────────────────────────────────────────────────── */

export default function PlaygroundPage() {
  const { data: systems, isLoading } = useSWR("playground-systems", () => api.playground.systems());

  const [activeSystem, setActiveSystem] = useState("rag");
  const [messagesMap, setMessagesMap] = useState<Record<string, Message[]>>({});
  const [responsesMap, setResponsesMap] = useState<Record<string, PlaygroundInteraction | null>>({});
  const [sessionIds, setSessionIds] = useState<Record<string, string | null>>({});
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const chatEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const messages = messagesMap[activeSystem] ?? [];
  const lastResponse = responsesMap[activeSystem] ?? null;
  const accent = SYSTEM_ACCENTS[activeSystem] ?? SYSTEM_ACCENTS.rag;
  const activeSystemData = systems?.find((s) => s.system_type === activeSystem);

  // Auto-scroll
  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  // Focus input on tab switch
  useEffect(() => {
    inputRef.current?.focus();
  }, [activeSystem]);

  const handleSend = useCallback(async () => {
    const query = input.trim();
    if (!query || loading) return;

    setInput("");
    setError(null);

    const userMsg: Message = { id: `u-${Date.now()}`, role: "user", content: query, timestamp: Date.now() };
    setMessagesMap((prev) => ({ ...prev, [activeSystem]: [...(prev[activeSystem] ?? []), userMsg] }));
    setLoading(true);

    try {
      const resp = await api.playground.interact({
        system_type: activeSystem,
        query,
        session_id: sessionIds[activeSystem] ?? undefined,
      });

      const aiMsg: Message = { id: `a-${Date.now()}`, role: "assistant", content: resp.answer, timestamp: Date.now() };
      setMessagesMap((prev) => ({ ...prev, [activeSystem]: [...(prev[activeSystem] ?? []), aiMsg] }));
      setResponsesMap((prev) => ({ ...prev, [activeSystem]: resp }));

      if (resp.session_id) {
        setSessionIds((prev) => ({ ...prev, [activeSystem]: resp.session_id }));
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong");
    } finally {
      setLoading(false);
    }
  }, [input, loading, activeSystem, sessionIds]);

  const handleResetSession = useCallback(async () => {
    const sid = sessionIds.chatbot;
    if (sid) {
      try { await api.playground.resetSession(sid); } catch { /* ignore */ }
    }
    setMessagesMap((prev) => ({ ...prev, chatbot: [] }));
    setResponsesMap((prev) => ({ ...prev, chatbot: null }));
    setSessionIds((prev) => ({ ...prev, chatbot: null }));
  }, [sessionIds]);

  if (isLoading || !systems) return <PageLoader />;

  return (
    <div className="flex flex-col h-screen">
      {/* ─── Header + Tabs ──────────────────────────────────────────── */}
      <div className="flex-shrink-0 bg-white border-b border-gray-200 px-6 pt-5 pb-0">
        <div className="flex items-end justify-between mb-4">
          <div>
            <h1 className="text-xl font-bold text-gray-900">Playground</h1>
            <p className="text-sm text-gray-500 mt-0.5">Interact with your AI systems before evaluating them</p>
          </div>
          {activeSystemData && (
            <p className="text-xs text-gray-400 max-w-xs text-right leading-relaxed">{activeSystemData.description}</p>
          )}
        </div>

        <div className="flex gap-1">
          {systems.map((sys) => {
            const ac = SYSTEM_ACCENTS[sys.system_type] ?? SYSTEM_ACCENTS.rag;
            const isActive = activeSystem === sys.system_type;
            return (
              <button
                key={sys.system_type}
                onClick={() => setActiveSystem(sys.system_type)}
                className={cn(
                  "flex items-center gap-1.5 px-4 py-2.5 text-sm font-medium rounded-t-lg transition-all relative",
                  isActive
                    ? `${ac.light} ${ac.text} border border-b-0 ${ac.border}`
                    : "text-gray-500 hover:text-gray-700 hover:bg-gray-50 border border-transparent"
                )}
              >
                <span className="text-base">{sys.icon}</span>
                {sys.name}
                {(messagesMap[sys.system_type]?.length ?? 0) > 0 && (
                  <span className={cn("w-1.5 h-1.5 rounded-full", ac.dot)} />
                )}
              </button>
            );
          })}
        </div>
      </div>

      {/* ─── Body: Chat + Detail ────────────────────────────────────── */}
      <div className="flex flex-1 min-h-0">
        {/* Chat Area */}
        <div className="flex-1 flex flex-col min-w-0">
          {/* Messages */}
          <div className="flex-1 overflow-y-auto px-6 py-4 space-y-4">
            {messages.length === 0 && !loading && (
              <div className="flex items-center justify-center h-full">
                <div className="text-center max-w-md">
                  <div className="text-5xl mb-4 opacity-20">
                    {activeSystemData?.icon ?? ""}
                  </div>
                  <p className="text-sm text-gray-500 mb-1">
                    {activeSystemData?.name ?? "AI System"}
                  </p>
                  <p className="text-xs text-gray-400 mb-6">
                    {activeSystemData?.description ?? "Send a message to get started"}
                  </p>
                  {/* Sample queries */}
                  <div className="flex flex-wrap gap-2 justify-center">
                    {(activeSystemData?.sample_queries ?? []).map((q, i) => (
                      <button
                        key={i}
                        onClick={() => { setInput(q); inputRef.current?.focus(); }}
                        className={cn(
                          "text-xs px-3 py-1.5 rounded-full border transition-colors",
                          accent.border, accent.text,
                          "hover:shadow-sm",
                          accent.light
                        )}
                      >
                        {q}
                      </button>
                    ))}
                  </div>
                </div>
              </div>
            )}

            {messages.map((msg) => (
              <ChatMessage key={msg.id} msg={msg} accentDot={accent.dot} />
            ))}

            {loading && <TypingIndicator dotColor={accent.dot} />}

            {error && (
              <div className="mx-auto max-w-md bg-red-50 border border-red-200 rounded-lg px-4 py-3 text-sm text-red-700">
                {error}
              </div>
            )}
            <div ref={chatEndRef} />
          </div>

          {/* Sample queries when there are already messages */}
          {messages.length > 0 && (
            <div className="flex-shrink-0 px-6 pb-2">
              <div className="flex gap-1.5 overflow-x-auto pb-1 scrollbar-none">
                {(activeSystemData?.sample_queries ?? []).map((q, i) => (
                  <button
                    key={i}
                    onClick={() => { setInput(q); inputRef.current?.focus(); }}
                    className="text-xs px-2.5 py-1 rounded-full border border-gray-200 text-gray-500 hover:text-gray-700 hover:border-gray-300 transition-colors whitespace-nowrap flex-shrink-0"
                  >
                    {q}
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Input Bar */}
          <div className="flex-shrink-0 px-6 pb-5 pt-2">
            <div className="flex gap-2">
              <input
                ref={inputRef}
                type="text"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); handleSend(); } }}
                placeholder={`Ask ${activeSystemData?.name ?? "the system"} something...`}
                disabled={loading}
                className={cn(
                  "flex-1 border border-gray-300 rounded-lg px-4 py-2.5 text-sm",
                  "focus:outline-none focus:ring-2 focus:border-transparent transition-shadow",
                  `focus:${accent.ring}`,
                  "disabled:opacity-50 disabled:cursor-not-allowed",
                  "placeholder:text-gray-400"
                )}
              />
              <button
                onClick={handleSend}
                disabled={loading || !input.trim()}
                className={cn(
                  "px-5 py-2.5 text-white text-sm font-medium rounded-lg transition-all",
                  "disabled:opacity-40 disabled:cursor-not-allowed",
                  accent.bg,
                  "hover:opacity-90 active:scale-[0.98]"
                )}
              >
                {loading ? (
                  <span className="inline-block w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                ) : (
                  "Send"
                )}
              </button>
            </div>
          </div>
        </div>

        {/* Detail Panel */}
        <div className="w-96 flex-shrink-0 border-l border-gray-200 bg-white overflow-y-auto">
          <div className="p-5">
            <DetailPanel
              systemType={activeSystem}
              response={lastResponse}
              onResetSession={handleResetSession}
            />
          </div>
        </div>
      </div>
    </div>
  );
}
