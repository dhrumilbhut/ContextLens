"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { api, ApiError } from "@/lib/api";
import type { TraceDetailResponse, ClaimDetail } from "@/lib/types";
import { getFailureType } from "@/lib/types";
import { formatFullDateTime, formatLatency } from "@/lib/utils";
import { ClaimCard } from "@/components/claim-card";

const STATUS_STYLES: Record<string, string> = {
  pending: "bg-gray-100 text-gray-600",
  processing: "bg-blue-100 text-blue-700",
  processed: "bg-green-100 text-green-700",
  failed: "bg-red-100 text-red-700",
};

function SummaryBar({ claims }: { claims: ClaimDetail[] }) {
  const total = claims.length;
  const faithful = claims.filter((c) => c.is_faithful).length;
  const generation = claims.filter(
    (c) => getFailureType(c) === "generation"
  ).length;
  const retrieval = claims.filter(
    (c) => getFailureType(c) === "retrieval"
  ).length;

  if (total === 0) return null;

  return (
    <div className="flex items-center gap-1.5 flex-wrap text-sm font-medium mb-6">
      <span className="text-gray-700">{total} claim{total !== 1 ? "s" : ""}</span>
      <span className="text-gray-300">·</span>
      <span className="text-green-600">{faithful} faithful</span>
      {generation > 0 && (
        <>
          <span className="text-gray-300">·</span>
          <span className="text-purple-600">
            {generation} generation failure{generation !== 1 ? "s" : ""}
          </span>
        </>
      )}
      {retrieval > 0 && (
        <>
          <span className="text-gray-300">·</span>
          <span className="text-orange-600">
            {retrieval} retrieval failure{retrieval !== 1 ? "s" : ""}
          </span>
        </>
      )}
    </div>
  );
}

export default function TraceDetailPage() {
  const params = useParams();
  const projectId = params.projectId as string;
  const traceId = params.traceId as string;

  const [trace, setTrace] = useState<TraceDetailResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notFound, setNotFound] = useState(false);

  useEffect(() => {
    if (!projectId || !traceId) return;
    api.traces
      .get(projectId, traceId)
      .then(setTrace)
      .catch((err) => {
        if (err instanceof ApiError && err.status === 404) {
          setNotFound(true);
        } else {
          setError(
            err instanceof ApiError ? err.message : "Failed to load trace"
          );
        }
      })
      .finally(() => setLoading(false));
  }, [projectId, traceId]);

  if (loading) {
    return <div className="p-8 text-sm text-gray-500">Loading...</div>;
  }

  if (notFound) {
    return (
      <div className="p-8">
        <Link
          href={`/projects/${projectId}/traces`}
          className="text-sm text-gray-500 hover:text-gray-700 flex items-center gap-1 mb-6"
        >
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
          </svg>
          Back to traces
        </Link>
        <div className="bg-white border border-gray-200 rounded-lg p-8 text-center">
          <p className="text-sm font-medium text-gray-900">Trace not found</p>
          <p className="mt-1 text-sm text-gray-500">
            This trace does not exist or belongs to a different project.
          </p>
        </div>
      </div>
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

  if (!trace) return null;

  return (
    <div className="p-8 max-w-4xl">
      {/* Back + header row */}
      <div className="mb-6">
        <Link
          href={`/projects/${projectId}/traces`}
          className="text-sm text-gray-500 hover:text-gray-700 flex items-center gap-1 mb-4"
        >
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
          </svg>
          Back to traces
        </Link>

        <div className="flex items-center gap-3 flex-wrap">
          <span
            className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${STATUS_STYLES[trace.status] ?? "bg-gray-100 text-gray-600"}`}
          >
            {trace.status}
          </span>
          <span className="text-sm text-gray-500">
            {formatFullDateTime(trace.created_at)}
          </span>
          {trace.latency_ms !== null && (
            <span className="text-sm text-gray-400">
              {formatLatency(trace.latency_ms)} response time
            </span>
          )}
        </div>
      </div>

      {/* Query + Response */}
      <div className="grid gap-4 mb-8">
        <div>
          <p className="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-1.5">
            Query
          </p>
          <div className="bg-white border border-gray-200 rounded-lg px-5 py-4">
            <p className="text-sm text-gray-900 leading-relaxed">
              {trace.query_text}
            </p>
          </div>
        </div>

        <div>
          <p className="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-1.5">
            Response
          </p>
          <div className="bg-white border border-gray-200 rounded-lg px-5 py-4">
            <p className="text-sm text-gray-900 leading-relaxed whitespace-pre-wrap">
              {trace.llm_response}
            </p>
          </div>
        </div>
      </div>

      {/* Claims section */}
      {trace.status === "processed" && trace.claims.length > 0 ? (
        <>
          <SummaryBar claims={trace.claims} />
          <div className="space-y-3">
            {trace.claims.map((claim) => (
              <ClaimCard key={claim.id} claim={claim} />
            ))}
          </div>
        </>
      ) : trace.status === "processed" && trace.claims.length === 0 ? (
        <div className="bg-white border border-gray-200 rounded-lg p-6 text-center text-sm text-gray-500">
          No claims were extracted from this trace.
        </div>
      ) : trace.status === "pending" || trace.status === "processing" ? (
        <div className="bg-blue-50 border border-blue-200 rounded-lg p-5 text-sm text-blue-700">
          <p className="font-medium">Processing in progress</p>
          <p className="mt-0.5 text-blue-600">
            Claims are being extracted and scored. Refresh the page in a few
            seconds.
          </p>
        </div>
      ) : trace.status === "failed" ? (
        <div className="bg-red-50 border border-red-200 rounded-lg p-5 text-sm text-red-700">
          <p className="font-medium">Processing failed</p>
          <p className="mt-0.5 text-red-600">
            This trace could not be processed. Check the worker logs.
          </p>
        </div>
      ) : null}
    </div>
  );
}
