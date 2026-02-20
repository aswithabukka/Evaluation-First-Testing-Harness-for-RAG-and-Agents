import { SummaryCards } from "@/components/dashboard/SummaryCards";
import { RecentRunsTable } from "@/components/dashboard/RecentRunsTable";

export default function DashboardPage() {
  return (
    <div className="p-6 space-y-6 max-w-6xl mx-auto">
      <div>
        <h1 className="text-xl font-bold text-gray-900">Dashboard</h1>
        <p className="text-sm text-gray-500 mt-0.5">
          Overview of evaluation runs and quality metrics
        </p>
      </div>
      <SummaryCards />
      <RecentRunsTable />
    </div>
  );
}
