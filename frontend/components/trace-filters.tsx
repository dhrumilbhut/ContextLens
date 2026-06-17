"use client";

interface TraceFiltersProps {
  status: string;
  minFaithfulness: string;
  onStatusChange: (value: string) => void;
  onMinFaithfulnessChange: (value: string) => void;
}

export function TraceFilters({
  status,
  minFaithfulness,
  onStatusChange,
  onMinFaithfulnessChange,
}: TraceFiltersProps) {
  return (
    <div className="flex items-center gap-4 flex-wrap">
      <div className="flex items-center gap-2">
        <label className="text-sm font-medium text-gray-600">Status</label>
        <select
          value={status}
          onChange={(e) => onStatusChange(e.target.value)}
          className="text-sm border border-gray-300 rounded-md px-2.5 py-1.5 focus:outline-none focus:ring-2 focus:ring-indigo-500 bg-white"
        >
          <option value="">All</option>
          <option value="pending">Pending</option>
          <option value="processing">Processing</option>
          <option value="processed">Processed</option>
          <option value="failed">Failed</option>
        </select>
      </div>

      <div className="flex items-center gap-2">
        <label className="text-sm font-medium text-gray-600">
          Min faithfulness
        </label>
        <input
          type="number"
          min="0"
          max="1"
          step="0.05"
          value={minFaithfulness}
          onChange={(e) => onMinFaithfulnessChange(e.target.value)}
          placeholder="0.0"
          className="text-sm border border-gray-300 rounded-md px-2.5 py-1.5 w-20 focus:outline-none focus:ring-2 focus:ring-indigo-500"
        />
      </div>

      {(status || minFaithfulness) && (
        <button
          onClick={() => {
            onStatusChange("");
            onMinFaithfulnessChange("");
          }}
          className="text-sm text-gray-500 hover:text-gray-700"
        >
          Clear filters
        </button>
      )}
    </div>
  );
}
