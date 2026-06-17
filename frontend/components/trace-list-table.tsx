import Link from "next/link";
import type { TraceListItem } from "@/lib/types";
import { formatRelativeTime, formatPercent } from "@/lib/utils";

interface TraceListTableProps {
  traces: TraceListItem[];
  projectId: string;
}

const STATUS_STYLES: Record<string, string> = {
  pending: "bg-gray-100 text-gray-600",
  processing: "bg-blue-100 text-blue-700",
  processed: "bg-green-100 text-green-700",
  failed: "bg-red-100 text-red-700",
};

function faithfulnessColor(score: number | null): string {
  if (score === null) return "text-gray-400";
  if (score >= 0.8) return "text-green-600";
  if (score >= 0.5) return "text-yellow-600";
  return "text-red-600";
}

export function TraceListTable({ traces, projectId }: TraceListTableProps) {
  return (
    <div className="bg-white border border-gray-200 rounded-lg overflow-hidden">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-gray-100 bg-gray-50 text-left">
            <th className="px-5 py-3 text-xs font-medium text-gray-500 uppercase tracking-wide">
              Query
            </th>
            <th className="px-5 py-3 text-xs font-medium text-gray-500 uppercase tracking-wide">
              Status
            </th>
            <th className="px-5 py-3 text-xs font-medium text-gray-500 uppercase tracking-wide">
              Claims
            </th>
            <th className="px-5 py-3 text-xs font-medium text-gray-500 uppercase tracking-wide">
              Faithful
            </th>
            <th className="px-5 py-3 text-xs font-medium text-gray-500 uppercase tracking-wide">
              Avg faithfulness
            </th>
            <th className="px-5 py-3 text-xs font-medium text-gray-500 uppercase tracking-wide">
              Created
            </th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-100">
          {traces.map((trace) => (
            <tr
              key={trace.id}
              className="hover:bg-gray-50 cursor-pointer"
            >
              <td className="px-5 py-3">
                <Link
                  href={`/projects/${projectId}/traces/${trace.id}`}
                  className="block text-gray-900 hover:text-indigo-600"
                >
                  <span
                    className="block max-w-xs truncate"
                    title={trace.query_text}
                  >
                    {trace.query_text}
                  </span>
                </Link>
              </td>
              <td className="px-5 py-3">
                <span
                  className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${STATUS_STYLES[trace.status] ?? "bg-gray-100 text-gray-600"}`}
                >
                  {trace.status}
                </span>
              </td>
              <td className="px-5 py-3 text-gray-600">
                {trace.claim_count}
              </td>
              <td className="px-5 py-3 text-gray-600">
                {trace.status === "processed"
                  ? `${trace.faithful_claim_count}/${trace.claim_count}`
                  : "—"}
              </td>
              <td
                className={`px-5 py-3 font-medium ${faithfulnessColor(trace.avg_faithfulness)}`}
              >
                {trace.status === "processed"
                  ? formatPercent(trace.avg_faithfulness)
                  : "—"}
              </td>
              <td
                className="px-5 py-3 text-gray-500"
                title={new Date(trace.created_at).toLocaleString()}
              >
                {formatRelativeTime(trace.created_at)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
