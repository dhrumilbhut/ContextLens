"use client";

import { useEffect, useState, useCallback } from "react";
import { useParams } from "next/navigation";
import { api, ApiError } from "@/lib/api";
import type { TraceListItem } from "@/lib/types";
import { TraceListTable } from "@/components/trace-list-table";
import { TraceFilters } from "@/components/trace-filters";
import { EmptyState } from "@/components/empty-state";

const PAGE_SIZE = 50;

export default function TracesPage() {
  const params = useParams();
  const projectId = params.projectId as string;

  const [traces, setTraces] = useState<TraceListItem[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState("");
  const [minFaithfulness, setMinFaithfulness] = useState("");
  const [offset, setOffset] = useState(0);

  const load = useCallback(
    async (currentOffset: number) => {
      if (!projectId) return;
      setLoading(true);
      setError(null);
      try {
        const params: {
          limit: number;
          offset: number;
          status?: string;
          min_faithfulness?: number;
        } = { limit: PAGE_SIZE, offset: currentOffset };
        if (statusFilter) params.status = statusFilter;
        if (minFaithfulness !== "" && !isNaN(Number(minFaithfulness))) {
          params.min_faithfulness = Number(minFaithfulness);
        }
        const data = await api.traces.list(projectId, params);
        setTraces(data.traces);
        setTotal(data.total);
      } catch (err) {
        setError(
          err instanceof ApiError ? err.message : "Failed to load traces"
        );
      } finally {
        setLoading(false);
      }
    },
    [projectId, statusFilter, minFaithfulness]
  );

  useEffect(() => {
    setOffset(0);
    load(0);
  }, [load]);

  function handleFilterChange(
    newStatus: string,
    newMinFaithfulness: string
  ) {
    setStatusFilter(newStatus);
    setMinFaithfulness(newMinFaithfulness);
    setOffset(0);
  }

  return (
    <div className="p-8">
      <div className="mb-6">
        <h1 className="text-xl font-semibold text-gray-900">Traces</h1>
        <p className="text-sm text-gray-500 mt-0.5">
          Every query sent through your RAG pipeline.
        </p>
      </div>

      <div className="mb-4">
        <TraceFilters
          status={statusFilter}
          minFaithfulness={minFaithfulness}
          onStatusChange={(v) => handleFilterChange(v, minFaithfulness)}
          onMinFaithfulnessChange={(v) => handleFilterChange(statusFilter, v)}
        />
      </div>

      {loading && (
        <div className="text-sm text-gray-500 py-8 text-center">Loading...</div>
      )}

      {error && (
        <div className="bg-red-50 border border-red-200 rounded-md p-4 text-sm text-red-700">
          {error}
        </div>
      )}

      {!loading && !error && traces.length === 0 && (
        <EmptyState
          title="No traces yet"
          description="Send your first trace using the ContextLens SDK or curl."
          action={
            <div className="text-left max-w-xl">
              <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">
                Example curl command
              </p>
              <pre className="bg-gray-950 text-green-400 text-xs rounded-md p-4 overflow-x-auto leading-relaxed">
                {`curl -X POST http://localhost:8000/ingest \\
  -H "Authorization: Bearer cl_your_key_here" \\
  -H "Content-Type: application/json" \\
  -d '{
    "query": "What is the refund policy?",
    "chunks": [{
      "content": "Refunds must be requested within 30 days.",
      "source": "refund-policy.pdf",
      "chunk_index": 0,
      "retriever_score": 0.89
    }],
    "response": "You can get a refund within 30 days.",
    "latency_ms": 1100
  }'`}
              </pre>
            </div>
          }
        />
      )}

      {!loading && !error && traces.length > 0 && (
        <>
          <TraceListTable traces={traces} projectId={projectId} />

          <div className="mt-4 flex items-center justify-between text-sm text-gray-500">
            <span>
              {total} trace{total !== 1 ? "s" : ""} total
            </span>
            {total > PAGE_SIZE && (
              <div className="flex items-center gap-2">
                <button
                  disabled={offset === 0}
                  onClick={() => {
                    const prev = Math.max(0, offset - PAGE_SIZE);
                    setOffset(prev);
                    load(prev);
                  }}
                  className="px-3 py-1.5 border border-gray-300 rounded text-sm disabled:opacity-40 hover:bg-gray-50"
                >
                  Previous
                </button>
                <span>
                  {Math.floor(offset / PAGE_SIZE) + 1} /{" "}
                  {Math.ceil(total / PAGE_SIZE)}
                </span>
                <button
                  disabled={offset + PAGE_SIZE >= total}
                  onClick={() => {
                    const next = offset + PAGE_SIZE;
                    setOffset(next);
                    load(next);
                  }}
                  className="px-3 py-1.5 border border-gray-300 rounded text-sm disabled:opacity-40 hover:bg-gray-50"
                >
                  Next
                </button>
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
}
