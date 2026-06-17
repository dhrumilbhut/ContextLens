"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { api, ApiError } from "@/lib/api";
import type { ClustersResponse, QueryClusterItem } from "@/lib/types";

function faithfulnessColor(score: number): string {
  if (score >= 0.8) return "text-green-600";
  if (score >= 0.5) return "text-yellow-600";
  return "text-red-600";
}

function unfaithfulRateColor(rate: number): string {
  if (rate <= 0.2) return "text-green-600";
  if (rate <= 0.5) return "text-yellow-600";
  return "text-red-600";
}

function ClusterCard({ cluster }: { cluster: QueryClusterItem }) {
  return (
    <div className="bg-white border border-gray-200 rounded-lg p-5">
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <p className="text-sm font-semibold text-gray-900 capitalize leading-snug">
            {cluster.label}
          </p>
          <p className="text-xs text-gray-400 mt-0.5">
            {cluster.trace_count} trace{cluster.trace_count !== 1 ? "s" : ""}
          </p>
        </div>
        <div className="flex gap-6 flex-shrink-0 text-right">
          <div>
            <p className="text-xs text-gray-400 uppercase tracking-wide mb-0.5">
              Avg faithfulness
            </p>
            <p
              className={`text-base font-semibold ${faithfulnessColor(cluster.avg_faithfulness)}`}
            >
              {Math.round(cluster.avg_faithfulness * 100)}%
            </p>
          </div>
          <div>
            <p className="text-xs text-gray-400 uppercase tracking-wide mb-0.5">
              Unfaithful rate
            </p>
            <p
              className={`text-base font-semibold ${unfaithfulRateColor(cluster.unfaithful_rate)}`}
            >
              {Math.round(cluster.unfaithful_rate * 100)}%
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}

export default function ClustersPage() {
  const params = useParams();
  const projectId = params.projectId as string;

  const [data, setData] = useState<ClustersResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!projectId) return;
    api.clusters
      .list(projectId)
      .then(setData)
      .catch((err) =>
        setError(
          err instanceof ApiError ? err.message : "Failed to load clusters"
        )
      )
      .finally(() => setLoading(false));
  }, [projectId]);

  if (loading) {
    return <div className="p-8 text-sm text-gray-500">Loading...</div>;
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

  const clusters = data?.clusters ?? [];

  return (
    <div className="p-8">
      <div className="mb-6">
        <h1 className="text-xl font-semibold text-gray-900">Query Clusters</h1>
        <p className="text-sm text-gray-500 mt-0.5">
          Semantically similar queries grouped by topic. Recomputed every 6 hours.
          Requires at least {10} processed traces.
        </p>
      </div>

      {clusters.length === 0 && (
        <div className="bg-white border border-gray-200 rounded-lg p-10 text-center">
          <p className="text-sm font-medium text-gray-900">No clusters yet</p>
          <p className="mt-1 text-sm text-gray-500">
            Clustering runs automatically once you have at least 10 processed
            traces. Check back after the next scheduled run (every 6 hours),
            or trigger it manually via the Celery task.
          </p>
        </div>
      )}

      {clusters.length > 0 && (
        <div className="grid gap-3">
          {clusters.map((cluster) => (
            <ClusterCard key={cluster.id} cluster={cluster} />
          ))}
        </div>
      )}
    </div>
  );
}
