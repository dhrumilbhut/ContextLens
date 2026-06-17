interface FailureTypeBadgeProps {
  failureType: "retrieval" | "generation" | null;
}

function RetrievalIcon() {
  return (
    <svg
      className="w-4 h-4 flex-shrink-0"
      fill="none"
      stroke="currentColor"
      viewBox="0 0 24 24"
    >
      {/* Magnifying glass with X */}
      <circle cx="11" cy="11" r="7" strokeWidth={2} />
      <path strokeLinecap="round" strokeWidth={2} d="M16.5 16.5l4 4" />
      <path strokeLinecap="round" strokeWidth={1.8} d="M9 9l4 4m0-4l-4 4" />
    </svg>
  );
}

function GenerationIcon() {
  return (
    <svg
      className="w-4 h-4 flex-shrink-0"
      fill="none"
      stroke="currentColor"
      viewBox="0 0 24 24"
    >
      {/* Document with alert marker */}
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth={2}
        d="M9 12h6m-3-3v6M5 5h10a2 2 0 012 2v10a2 2 0 01-2 2H5a2 2 0 01-2-2V7a2 2 0 012-2z"
      />
    </svg>
  );
}

export function FailureTypeBadge({ failureType }: FailureTypeBadgeProps) {
  if (!failureType) return null;

  if (failureType === "retrieval") {
    return (
      <div className="flex items-start gap-2 px-3 py-2 bg-orange-50 border border-orange-200 rounded-md">
        <span className="text-orange-600 mt-0.5">
          <RetrievalIcon />
        </span>
        <div>
          <p className="text-xs font-semibold text-orange-800">
            Retrieval Failure
          </p>
          <p className="text-xs text-orange-700 mt-0.5">
            No matching document was found in the retrieved context. Fix the
            retriever — this source was never fetched.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex items-start gap-2 px-3 py-2 bg-purple-50 border border-purple-200 rounded-md">
      <span className="text-purple-600 mt-0.5">
        <GenerationIcon />
      </span>
      <div>
        <p className="text-xs font-semibold text-purple-800">
          Generation Failure
        </p>
        <p className="text-xs text-purple-700 mt-0.5">
          The source document was retrieved but the response didn&apos;t
          accurately reflect it. Fix the prompt or the LLM configuration.
        </p>
      </div>
    </div>
  );
}
