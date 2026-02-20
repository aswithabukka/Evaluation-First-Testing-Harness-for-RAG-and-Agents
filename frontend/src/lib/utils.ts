import { clsx, type ClassValue } from "clsx";

export function cn(...inputs: ClassValue[]) {
  return clsx(inputs);
}

export function formatScore(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  return value.toFixed(3);
}

export function formatPercent(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  return `${(value * 100).toFixed(1)}%`;
}

export function formatDate(iso: string): string {
  return new Date(iso).toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function formatDuration(ms: number | null | undefined): string {
  if (!ms) return "—";
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

export function statusColor(status: string): string {
  const map: Record<string, string> = {
    pending: "text-yellow-600 bg-yellow-50",
    running: "text-blue-600 bg-blue-50",
    completed: "text-green-600 bg-green-50",
    failed: "text-red-600 bg-red-50",
    gate_blocked: "text-orange-600 bg-orange-50",
  };
  return map[status] ?? "text-gray-600 bg-gray-50";
}

export function passColor(passed: boolean): string {
  return passed
    ? "text-green-700 bg-green-50 border-green-200"
    : "text-red-700 bg-red-50 border-red-200";
}

export function metricColor(value: number | null, threshold = 0.7): string {
  if (value === null || value === undefined) return "text-gray-400";
  return value >= threshold ? "text-green-600" : "text-red-600";
}

export function truncate(str: string, maxLen = 80): string {
  return str.length > maxLen ? str.slice(0, maxLen) + "…" : str;
}
