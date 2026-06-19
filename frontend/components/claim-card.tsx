"use client";

import { useState } from "react";
import type { ClaimDetail } from "@/lib/types";
import { getFailureType } from "@/lib/types";
import { parseJudgeReasoning } from "@/lib/utils";
import { VerdictBadge } from "@/components/verdict-badge";
import { FailureTypeBadge } from "@/components/failure-type-badge";

interface ClaimCardProps {
  claim: ClaimDetail;
}

const VERDICT_BORDER = {
  faithful: "border-l-green-500",
  partial: "border-l-yellow-500",
  unfaithful: "border-l-red-500",
  refusal: "border-l-gray-300",
} as const;

export function ClaimCard({ claim }: ClaimCardProps) {
  const failureType = getFailureType(claim);
  const { sourceQuote, explanation } = parseJudgeReasoning(
    claim.judge_reasoning
  );

  const isRefusal = claim.faithfulness_verdict === "refusal";
  const isLowConfidence =
    claim.attribution !== null && claim.attribution.confidence === "low";

  // Default: show source chunk expanded for non-faithful claims so evidence is immediately visible.
  // Refusal and low-confidence claims start collapsed (they're informational, not urgent).
  const [chunkExpanded, setChunkExpanded] = useState(
    !claim.is_faithful && !isRefusal && !isLowConfidence
  );

  const borderClass = VERDICT_BORDER[claim.faithfulness_verdict] ?? "border-l-gray-300";

  return (
    <div
      className={`bg-white border border-gray-200 border-l-4 rounded-lg overflow-hidden ${borderClass}`}
    >
      <div className="p-5">
        {/* Claim text + verdict badge */}
        <div className="flex items-start justify-between gap-4">
          <div className="flex items-start gap-3 min-w-0">
            <span className="flex-shrink-0 mt-0.5 w-5 h-5 rounded-full bg-gray-100 text-[11px] font-semibold text-gray-500 flex items-center justify-center">
              {claim.claim_index + 1}
            </span>
            <p className={`text-base font-medium leading-snug ${isRefusal ? "text-gray-500 italic" : "text-gray-900"}`}>
              {claim.claim_text}
            </p>
          </div>
          <div className="flex-shrink-0">
            <VerdictBadge
              verdict={claim.faithfulness_verdict}
              score={claim.faithfulness_score}
            />
          </div>
        </div>

        {/* Failure type badge — the critical distinction */}
        {failureType && (
          <div className="mt-3 ml-8">
            <FailureTypeBadge failureType={failureType} />
          </div>
        )}

        {/* Refusal explanation */}
        {isRefusal && (
          <div className="mt-3 ml-8 flex items-center gap-2 text-sm text-gray-400">
            <svg className="w-4 h-4 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            <span>LLM correctly declined — no relevant context was retrieved.</span>
          </div>
        )}

        {/* Attribution section */}
        {!isRefusal && (
          <div className="mt-4 ml-8">
            {claim.attribution ? (
              <div>
                <button
                  onClick={() => setChunkExpanded((v) => !v)}
                  className="flex items-center gap-1.5 text-sm text-gray-600 hover:text-gray-900 w-full text-left"
                >
                  <svg
                    className={`w-3.5 h-3.5 flex-shrink-0 transition-transform ${chunkExpanded ? "rotate-90" : ""}`}
                    fill="none"
                    stroke="currentColor"
                    viewBox="0 0 24 24"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={2}
                      d="M9 5l7 7-7 7"
                    />
                  </svg>
                  <span className="font-medium text-gray-700">
                    {claim.attribution.source_document}
                  </span>
                  <span className="text-gray-400">·</span>
                  <span className="text-gray-500">
                    chunk {claim.attribution.chunk_index}
                  </span>
                  <span className="text-gray-400">·</span>
                  <span className="text-gray-500">
                    {claim.attribution.attribution_score.toFixed(2)} similarity
                  </span>
                  {/* Low-confidence label — amber, visually grouped with "needs a look" signals */}
                  {isLowConfidence && (
                    <span className="ml-1 inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded text-[10px] font-semibold bg-yellow-50 text-yellow-700 border border-yellow-200">
                      Low confidence match
                    </span>
                  )}
                </button>

                {chunkExpanded && (
                  <blockquote className="mt-2 pl-3 border-l-2 border-gray-200 text-sm text-gray-600 italic leading-relaxed">
                    {claim.attribution.chunk_content}
                  </blockquote>
                )}
              </div>
            ) : (
              <div className="flex items-center gap-2 text-sm text-gray-400">
                <svg
                  className="w-4 h-4 flex-shrink-0"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <circle cx="12" cy="12" r="9" strokeWidth={1.5} />
                  <path
                    strokeLinecap="round"
                    strokeWidth={1.5}
                    d="M9 9l6 6m0-6l-6 6"
                  />
                </svg>
                <span>No source chunk was retrieved for this claim.</span>
              </div>
            )}
          </div>
        )}

        {/* Judge reasoning — always shown for attributed claims, hidden for refusals */}
        {!isRefusal && claim.judge_reasoning && (
          <div className="mt-4 ml-8 bg-gray-50 rounded-md px-4 py-3">
            <p className="text-[11px] font-semibold text-gray-400 uppercase tracking-wide mb-1.5">
              Judge reasoning
            </p>
            {sourceQuote && (
              <p className="text-sm text-gray-500 italic mb-1.5">
                &ldquo;{sourceQuote}&rdquo;
              </p>
            )}
            <p className="text-sm text-gray-800 leading-relaxed">{explanation}</p>
          </div>
        )}
      </div>
    </div>
  );
}
