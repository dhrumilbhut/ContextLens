"use client";

import { useState } from "react";
import { api, ApiError } from "@/lib/api";
import type { ApiKeyCreateResponse } from "@/lib/types";

interface ApiKeyCreateModalProps {
  projectId: string;
  onClose: () => void;
  onCreated: () => void;
}

export function ApiKeyCreateModal({
  projectId,
  onClose,
  onCreated,
}: ApiKeyCreateModalProps) {
  const [step, setStep] = useState<"form" | "show">("form");
  const [name, setName] = useState("");
  const [createdKey, setCreatedKey] = useState<ApiKeyCreateResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!name.trim()) return;
    setLoading(true);
    setError(null);
    try {
      const result = await api.apiKeys.create(projectId, name.trim());
      setCreatedKey(result);
      setStep("show");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to create key");
    } finally {
      setLoading(false);
    }
  }

  async function handleCopy() {
    if (!createdKey) return;
    await navigator.clipboard.writeText(createdKey.key);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  function handleDone() {
    onCreated();
    onClose();
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div className="absolute inset-0 bg-black/40" onClick={step === "form" ? onClose : undefined} />
      <div className="relative bg-white rounded-lg shadow-xl w-full max-w-md mx-4 p-6">
        {step === "form" ? (
          <>
            <h2 className="text-base font-semibold text-gray-900">
              Create API Key
            </h2>
            <form onSubmit={handleSubmit} className="mt-4">
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Key name
              </label>
              <input
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="e.g. Local Dev Key"
                autoFocus
                className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
              />
              {error && (
                <p className="mt-2 text-sm text-red-600">{error}</p>
              )}
              <div className="mt-6 flex justify-end gap-3">
                <button
                  type="button"
                  onClick={onClose}
                  className="px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-md hover:bg-gray-50"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={loading || !name.trim()}
                  className="px-4 py-2 text-sm font-medium text-white bg-indigo-600 rounded-md hover:bg-indigo-700 disabled:opacity-50"
                >
                  {loading ? "Creating..." : "Create"}
                </button>
              </div>
            </form>
          </>
        ) : (
          <>
            <div className="flex items-start gap-3 mb-4">
              <div className="flex-shrink-0 w-8 h-8 bg-amber-100 rounded-full flex items-center justify-center">
                <svg className="w-4 h-4 text-amber-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                </svg>
              </div>
              <div>
                <h2 className="text-base font-semibold text-gray-900">
                  Copy your API key now
                </h2>
                <p className="text-sm text-gray-500 mt-0.5">
                  It won&apos;t be shown again.
                </p>
              </div>
            </div>

            <div className="bg-gray-950 rounded-md p-4 flex items-center justify-between gap-3">
              <code className="text-green-400 text-sm font-mono break-all">
                {createdKey?.key}
              </code>
              <button
                onClick={handleCopy}
                className="flex-shrink-0 px-3 py-1.5 text-xs font-medium text-gray-300 bg-gray-800 rounded hover:bg-gray-700 transition-colors"
              >
                {copied ? "Copied!" : "Copy"}
              </button>
            </div>

            <div className="mt-6 flex justify-end">
              <button
                onClick={handleDone}
                className="px-4 py-2 text-sm font-medium text-white bg-indigo-600 rounded-md hover:bg-indigo-700"
              >
                Done
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
