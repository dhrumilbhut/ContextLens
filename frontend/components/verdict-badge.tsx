interface VerdictBadgeProps {
  verdict: "faithful" | "partial" | "unfaithful";
  score?: number;
}

const VERDICT_STYLES = {
  faithful: "bg-green-100 text-green-800",
  partial: "bg-yellow-100 text-yellow-800",
  unfaithful: "bg-red-100 text-red-800",
};

const VERDICT_LABELS = {
  faithful: "Faithful",
  partial: "Partial",
  unfaithful: "Unfaithful",
};

const VERDICT_ICONS = {
  faithful: "✓",
  partial: "⚠",
  unfaithful: "✗",
};

export function VerdictBadge({ verdict, score }: VerdictBadgeProps) {
  return (
    <span
      className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-semibold ${VERDICT_STYLES[verdict]}`}
    >
      <span>{VERDICT_ICONS[verdict]}</span>
      {VERDICT_LABELS[verdict]}
      {score !== undefined && (
        <span className="opacity-70">{score.toFixed(2)}</span>
      )}
    </span>
  );
}
