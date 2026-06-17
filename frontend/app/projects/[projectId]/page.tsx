"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { api, ApiError } from "@/lib/api";
import type { ProjectDetailResponse } from "@/lib/types";

function StatCard({
  label,
  value,
  sub,
  valueClass,
}: {
  label: string;
  value: string;
  sub?: string;
  valueClass?: string;
}) {
  return (
    <div className="bg-white border border-gray-200 rounded-lg p-5">
      <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">{label}</p>
      <p className={`mt-2 text-2xl font-semibold ${valueClass ?? "text-gray-900"}`}>
        {value}
      </p>
      {sub && <p className="mt-0.5 text-xs text-gray-400">{sub}</p>}
    </div>
  );
}

export default function ProjectOverviewPage() {
  const params = useParams();
  const projectId = params.projectId as string;
  const [project, setProject] = useState<ProjectDetailResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!projectId) return;
    api.projects
      .get(projectId)
      .then(setProject)
      .catch((err) =>
        setError(err instanceof ApiError ? err.message : "Failed to load project")
      )
      .finally(() => setLoading(false));
  }, [projectId]);

  function faithfulnessColor(score: number | null) {
    if (score === null) return "text-gray-400";
    if (score >= 0.8) return "text-green-600";
    if (score >= 0.5) return "text-yellow-600";
    return "text-red-600";
  }

  if (loading) {
    return (
      <div className="p-8 text-sm text-gray-500">Loading...</div>
    );
  }

  if (error) {
    return (
      <div className="p-8">
        <div className="bg-red-50 border border-red-200 rounded-md p-4 text-sm text-red-700">
          {error}
        </div>
      </div>
    );
  }

  if (!project) return null;

  const faithfulness = project.avg_faithfulness_7d;
  const faithfulnessDisplay =
    faithfulness !== null ? `${Math.round(faithfulness * 100)}%` : "No data";

  const unfaithfulRate = project.unfaithful_claim_rate;
  const unfaithfulDisplay =
    unfaithfulRate !== null
      ? `${Math.round(unfaithfulRate * 100)}%`
      : "No data";

  return (
    <div className="p-8">
      <div className="mb-6">
        <h1 className="text-xl font-semibold text-gray-900">{project.name}</h1>
        <p className="text-sm text-gray-500 mt-0.5">Project overview</p>
      </div>

      <div className="grid grid-cols-2 xl:grid-cols-4 gap-4 mb-8">
        <StatCard label="Total Traces" value={String(project.trace_count)} />
        <StatCard
          label="Avg Faithfulness (7d)"
          value={faithfulnessDisplay}
          sub="Higher is better"
          valueClass={faithfulnessColor(faithfulness)}
        />
        <StatCard
          label="Unfaithful Claim Rate"
          value={unfaithfulDisplay}
          sub="Lower is better"
          valueClass={
            unfaithfulRate === null
              ? "text-gray-400"
              : unfaithfulRate < 0.2
              ? "text-green-600"
              : unfaithfulRate < 0.5
              ? "text-yellow-600"
              : "text-red-600"
          }
        />
        <StatCard
          label="Problem Documents"
          value={String(project.top_problem_documents.length)}
          sub="With unfaithful claims"
        />
      </div>

      {project.top_problem_documents.length > 0 && (
        <div className="bg-white border border-gray-200 rounded-lg">
          <div className="px-5 py-4 border-b border-gray-100">
            <h2 className="text-sm font-semibold text-gray-900">
              Top Problem Documents
            </h2>
            <p className="text-xs text-gray-500 mt-0.5">
              Sources most frequently cited in unfaithful claims
            </p>
          </div>
          <div className="divide-y divide-gray-100">
            {project.top_problem_documents.map((doc, i) => (
              <div key={i} className="px-5 py-3 flex items-center justify-between">
                <p className="text-sm text-gray-700 truncate max-w-lg" title={doc.source}>
                  {doc.source}
                </p>
                <span className="ml-4 flex-shrink-0 text-sm font-medium text-red-600">
                  {doc.unfaithful_claims} unfaithful claim{doc.unfaithful_claims !== 1 ? "s" : ""}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {project.top_problem_documents.length === 0 && project.trace_count > 0 && (
        <div className="bg-green-50 border border-green-200 rounded-lg p-5 text-sm text-green-700">
          No problem documents detected. All claims are being faithfully attributed to their sources.
        </div>
      )}

      {project.trace_count === 0 && (
        <div className="bg-white border border-gray-200 rounded-lg p-8">
          <h2 className="text-sm font-semibold text-gray-900 mb-1">
            Get started
          </h2>
          <p className="text-sm text-gray-500 mb-6">
            Follow these steps to start diagnosing your RAG pipeline.
          </p>
          <ol className="space-y-6">
            <li className="flex gap-4">
              <span className="flex-shrink-0 w-6 h-6 rounded-full bg-indigo-100 text-indigo-700 text-xs font-semibold flex items-center justify-center mt-0.5">
                1
              </span>
              <div>
                <p className="text-sm font-medium text-gray-900">
                  Create an API key
                </p>
                <p className="text-sm text-gray-500 mt-0.5">
                  Go to{" "}
                  <a
                    href={`/projects/${projectId}/settings/api-keys`}
                    className="text-indigo-600 hover:text-indigo-800 underline"
                  >
                    API Keys
                  </a>{" "}
                  and generate a key for this project.
                </p>
              </div>
            </li>
            <li className="flex gap-4">
              <span className="flex-shrink-0 w-6 h-6 rounded-full bg-indigo-100 text-indigo-700 text-xs font-semibold flex items-center justify-center mt-0.5">
                2
              </span>
              <div className="min-w-0 w-full">
                <p className="text-sm font-medium text-gray-900">
                  Send your first trace
                </p>
                <p className="text-sm text-gray-500 mt-0.5 mb-2">
                  Replace{" "}
                  <code className="font-mono bg-gray-100 px-1 rounded text-xs">
                    YOUR_API_KEY
                  </code>{" "}
                  with the key you just created:
                </p>
                <pre className="bg-gray-50 border border-gray-200 rounded-md p-3 text-xs text-gray-700 overflow-x-auto whitespace-pre">
{`curl -X POST http://localhost:8000/ingest \\
  -H "Authorization: Bearer YOUR_API_KEY" \\
  -H "Content-Type: application/json" \\
  -d '{
    "query": "What is the refund policy?",
    "chunks": [{
      "content": "Refunds are processed within 30 days.",
      "source": "policy.pdf",
      "chunk_index": 0
    }],
    "response": "Your refund will be processed in 30 days."
  }'`}
                </pre>
              </div>
            </li>
            <li className="flex gap-4">
              <span className="flex-shrink-0 w-6 h-6 rounded-full bg-indigo-100 text-indigo-700 text-xs font-semibold flex items-center justify-center mt-0.5">
                3
              </span>
              <div>
                <p className="text-sm font-medium text-gray-900">
                  Come back here
                </p>
                <p className="text-sm text-gray-500 mt-0.5">
                  After a few seconds, this page will show your trace stats. Go
                  to{" "}
                  <a
                    href={`/projects/${projectId}/traces`}
                    className="text-indigo-600 hover:text-indigo-800 underline"
                  >
                    Traces
                  </a>{" "}
                  to see the per-claim attribution breakdown.
                </p>
              </div>
            </li>
          </ol>
        </div>
      )}
    </div>
  );
}
