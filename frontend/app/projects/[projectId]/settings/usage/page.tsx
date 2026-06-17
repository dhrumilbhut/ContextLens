"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";
import { api, ApiError } from "@/lib/api";
import type { UsageResponse } from "@/lib/types";

function formatChartDate(dateStr: string): string {
  const [, month, day] = dateStr.split("-");
  const months = [
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
  ];
  return `${months[parseInt(month) - 1]} ${parseInt(day)}`;
}

export default function UsagePage() {
  const params = useParams();
  const projectId = params.projectId as string;

  const [usage, setUsage] = useState<UsageResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!projectId) return;
    api.usage
      .get(projectId)
      .then(setUsage)
      .catch((err) =>
        setError(err instanceof ApiError ? err.message : "Failed to load usage")
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

  if (!usage) return null;

  const { today, last_7_days } = usage;
  const limit = today.processing_limit;
  const processed = today.traces_processed;
  const pct = limit > 0 ? Math.min(processed / limit, 1) : 0;
  const pctLabel =
    limit > 0 ? `${(pct * 100).toFixed(1)}%` : "No limit set";

  const chartData = [...last_7_days]
    .reverse()
    .map((d) => ({
      date: formatChartDate(d.date),
      traces: d.traces_processed,
    }));

  return (
    <div className="p-8 max-w-2xl">
      <div className="mb-8">
        <h1 className="text-xl font-semibold text-gray-900">Usage</h1>
        <p className="text-sm text-gray-500 mt-0.5">
          Daily trace processing against your configured limit.
        </p>
      </div>

      {/* Today section */}
      <div className="bg-white border border-gray-200 rounded-lg p-6 mb-6">
        <h2 className="text-sm font-semibold text-gray-700 mb-4">Today</h2>

        {today.limit_reached && (
          <div className="mb-4 bg-amber-50 border border-amber-200 rounded-md p-4">
            <p className="text-sm font-semibold text-amber-800">
              Daily processing limit reached
            </p>
            <p className="text-sm text-amber-700 mt-0.5">
              New traces are still being accepted but will not be processed
              until the limit resets at midnight UTC. To raise the limit, set{" "}
              <code className="font-mono bg-amber-100 px-1 rounded">
                DAILY_PROCESSING_LIMIT
              </code>{" "}
              in your <code className="font-mono bg-amber-100 px-1 rounded">.env</code>{" "}
              and restart the containers.
            </p>
          </div>
        )}

        <div className="flex items-baseline justify-between mb-2">
          <span className="text-2xl font-semibold text-gray-900">
            {processed.toLocaleString()}
          </span>
          <span className="text-sm text-gray-500">
            {limit > 0 ? `/ ${limit.toLocaleString()} limit` : "No limit"}
          </span>
        </div>
        <div className="text-xs text-gray-400 mb-3">
          traces processed · {pctLabel}
        </div>

        <div className="bg-gray-100 rounded-full h-2.5 w-full overflow-hidden">
          <div
            className={`h-2.5 rounded-full transition-all ${
              pct >= 1
                ? "bg-red-500"
                : pct >= 0.8
                ? "bg-amber-500"
                : "bg-indigo-500"
            }`}
            style={{ width: `${pct * 100}%` }}
          />
        </div>

        <div className="mt-4 flex items-center justify-between text-sm text-gray-500">
          <span>
            {today.traces_ingested.toLocaleString()} ingested today
          </span>
          <span className="text-xs text-gray-400">
            Resets at midnight UTC
          </span>
        </div>
      </div>

      {/* Last 7 days chart */}
      <div className="bg-white border border-gray-200 rounded-lg p-6">
        <h2 className="text-sm font-semibold text-gray-700 mb-4">
          Last 7 days
        </h2>
        {chartData.length === 0 ? (
          <p className="text-sm text-gray-400 text-center py-8">
            No data yet.
          </p>
        ) : (
          <ResponsiveContainer width="100%" height={200}>
            <BarChart
              data={chartData}
              margin={{ top: 4, right: 4, left: -16, bottom: 0 }}
            >
              <CartesianGrid
                strokeDasharray="3 3"
                vertical={false}
                stroke="#f0f0f0"
              />
              <XAxis
                dataKey="date"
                tick={{ fontSize: 11, fill: "#9ca3af" }}
                axisLine={false}
                tickLine={false}
              />
              <YAxis
                tick={{ fontSize: 11, fill: "#9ca3af" }}
                axisLine={false}
                tickLine={false}
                allowDecimals={false}
              />
              <Tooltip
                contentStyle={{
                  fontSize: 12,
                  borderRadius: 6,
                  border: "1px solid #e5e7eb",
                }}
                cursor={{ fill: "#f9fafb" }}
                formatter={(value: number) => [
                  value.toLocaleString(),
                  "Traces processed",
                ]}
              />
              <Bar dataKey="traces" fill="#6366f1" radius={[3, 3, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        )}
      </div>
    </div>
  );
}
