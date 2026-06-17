"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { api, ApiError } from "@/lib/api";
import type { DocumentProblemItem } from "@/lib/types";

const DAYS_OPTIONS = [
  { label: "Last 7 days", value: 7 },
  { label: "Last 30 days", value: 30 },
  { label: "Last 90 days", value: 90 },
];

function unfaithfulRateColor(rate: number): string {
  if (rate <= 0.2) return "text-green-600";
  if (rate <= 0.5) return "text-yellow-600";
  return "text-red-600";
}

function faithfulnessColor(score: number): string {
  if (score >= 0.8) return "text-green-600";
  if (score >= 0.5) return "text-yellow-600";
  return "text-red-600";
}

export default function DocumentsPage() {
  const params = useParams();
  const projectId = params.projectId as string;

  const [documents, setDocuments] = useState<DocumentProblemItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [days, setDays] = useState(7);

  useEffect(() => {
    if (!projectId) return;
    setLoading(true);
    setError(null);
    api.documents
      .problems(projectId, days)
      .then((data) => setDocuments(data.documents))
      .catch((err) =>
        setError(
          err instanceof ApiError ? err.message : "Failed to load documents"
        )
      )
      .finally(() => setLoading(false));
  }, [projectId, days]);

  return (
    <div className="p-8">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-xl font-semibold text-gray-900">
            Problem Documents
          </h1>
          <p className="text-sm text-gray-500 mt-0.5">
            Source documents ranked by unfaithful claims. Retrieval failures
            are not included — this view shows documents that were retrieved but
            misrepresented by the LLM.
          </p>
        </div>
        <select
          value={days}
          onChange={(e) => setDays(Number(e.target.value))}
          className="text-sm border border-gray-300 rounded-md px-2.5 py-1.5 focus:outline-none focus:ring-2 focus:ring-indigo-500 bg-white"
        >
          {DAYS_OPTIONS.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>
      </div>

      {loading && (
        <div className="text-sm text-gray-500 py-8 text-center">
          Loading...
        </div>
      )}

      {error && (
        <div className="bg-red-50 border border-red-200 rounded-md p-4 text-sm text-red-700">
          {error}
        </div>
      )}

      {!loading && !error && documents.length === 0 && (
        <div className="bg-white border border-gray-200 rounded-lg p-10 text-center">
          <p className="text-sm font-medium text-gray-900">
            No problem documents in this period.
          </p>
          <p className="mt-1 text-sm text-gray-500">
            Either everything is working well, or there isn&apos;t enough data
            yet.
          </p>
        </div>
      )}

      {!loading && !error && documents.length > 0 && (
        <div className="bg-white border border-gray-200 rounded-lg overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-100 bg-gray-50 text-left">
                <th className="px-5 py-3 text-xs font-medium text-gray-500 uppercase tracking-wide">
                  Source document
                </th>
                <th className="px-5 py-3 text-xs font-medium text-gray-500 uppercase tracking-wide">
                  Total claims
                </th>
                <th className="px-5 py-3 text-xs font-medium text-gray-500 uppercase tracking-wide">
                  Unfaithful claims
                </th>
                <th className="px-5 py-3 text-xs font-medium text-gray-500 uppercase tracking-wide">
                  Unfaithful rate
                </th>
                <th className="px-5 py-3 text-xs font-medium text-gray-500 uppercase tracking-wide">
                  Avg faithfulness
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {documents.map((doc) => (
                <tr key={doc.source_document} className="hover:bg-gray-50">
                  <td className="px-5 py-3 font-medium text-gray-900">
                    {doc.source_document}
                  </td>
                  <td className="px-5 py-3 text-gray-600">
                    {doc.total_claims}
                  </td>
                  <td className="px-5 py-3">
                    <span className="text-base font-semibold text-red-600">
                      {doc.unfaithful_claims}
                    </span>
                  </td>
                  <td
                    className={`px-5 py-3 font-medium ${unfaithfulRateColor(doc.unfaithful_rate)}`}
                  >
                    {Math.round(doc.unfaithful_rate * 100)}%
                  </td>
                  <td
                    className={`px-5 py-3 font-medium ${faithfulnessColor(doc.avg_faithfulness)}`}
                  >
                    {Math.round(doc.avg_faithfulness * 100)}%
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
