"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";

const nav = [
  { href: "/dashboard", label: "Dashboard", icon: "▦" },
  { href: "/test-sets", label: "Test Sets", icon: "⊞" },
  { href: "/runs", label: "Eval Runs", icon: "▶" },
  { href: "/metrics", label: "Metrics", icon: "↗" },
];

export function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="w-56 flex-shrink-0 bg-white border-r border-gray-200 min-h-screen flex flex-col">
      <div className="px-5 py-5 border-b border-gray-100">
        <span className="text-sm font-bold tracking-tight text-brand-700">
          RAG Eval Harness
        </span>
      </div>
      <nav className="flex-1 px-3 py-4 space-y-1">
        {nav.map((item) => (
          <Link
            key={item.href}
            href={item.href}
            className={cn(
              "flex items-center gap-2.5 px-3 py-2 rounded-md text-sm font-medium transition-colors",
              pathname.startsWith(item.href)
                ? "bg-brand-50 text-brand-700"
                : "text-gray-600 hover:bg-gray-100 hover:text-gray-900"
            )}
          >
            <span className="text-base">{item.icon}</span>
            {item.label}
          </Link>
        ))}
      </nav>
      <div className="px-5 py-3 border-t border-gray-100 text-xs text-gray-400">
        v1.0.0
      </div>
    </aside>
  );
}
