"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { api, ApiError } from "@/lib/api";
import type { ApiKeyListItem } from "@/lib/types";
import { formatDate } from "@/lib/utils";
import { ApiKeyCreateModal } from "@/components/api-key-create-modal";
import { ConfirmDialog } from "@/components/confirm-dialog";

export default function ApiKeysPage() {
  const params = useParams();
  const projectId = params.projectId as string;

  const [keys, setKeys] = useState<ApiKeyListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showCreate, setShowCreate] = useState(false);
  const [revokeTarget, setRevokeTarget] = useState<ApiKeyListItem | null>(null);
  const [revoking, setRevoking] = useState(false);
  const [revokeError, setRevokeError] = useState<string | null>(null);

  function loadKeys() {
    if (!projectId) return;
    setLoading(true);
    setError(null);
    api.apiKeys
      .list(projectId)
      .then((data) => setKeys(data.api_keys))
      .catch((err) =>
        setError(err instanceof ApiError ? err.message : "Failed to load API keys")
      )
      .finally(() => setLoading(false));
  }

  useEffect(() => {
    loadKeys();
  }, [projectId]);

  async function handleRevoke() {
    if (!revokeTarget) return;
    setRevoking(true);
    setRevokeError(null);
    try {
      await api.apiKeys.revoke(projectId, revokeTarget.id);
      setRevokeTarget(null);
      loadKeys();
    } catch (err) {
      setRevokeError(
        err instanceof ApiError ? err.message : "Failed to revoke key"
      );
    } finally {
      setRevoking(false);
    }
  }

  function formatNullableDate(dateStr: string | null) {
    if (!dateStr) return "Never";
    return formatDate(dateStr);
  }

  return (
    <div className="p-8">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-xl font-semibold text-gray-900">API Keys</h1>
          <p className="text-sm text-gray-500 mt-0.5">
            Use these keys to authenticate the ContextLens SDK.
          </p>
        </div>
        <button
          onClick={() => setShowCreate(true)}
          className="px-4 py-2 text-sm font-medium text-white bg-indigo-600 rounded-md hover:bg-indigo-700"
        >
          Create key
        </button>
      </div>

      {loading && (
        <div className="text-sm text-gray-500 py-8 text-center">Loading...</div>
      )}

      {error && (
        <div className="bg-red-50 border border-red-200 rounded-md p-4 text-sm text-red-700 mb-4">
          {error}
        </div>
      )}

      {!loading && !error && keys.length === 0 && (
        <div className="bg-white border border-gray-200 rounded-lg p-8 text-center">
          <p className="text-sm font-medium text-gray-900">No API keys yet</p>
          <p className="mt-1 text-sm text-gray-500">
            Create a key to authenticate the SDK with this project.
          </p>
          <button
            onClick={() => setShowCreate(true)}
            className="mt-4 px-4 py-2 text-sm font-medium text-white bg-indigo-600 rounded-md hover:bg-indigo-700"
          >
            Create your first key
          </button>
        </div>
      )}

      {!loading && keys.length > 0 && (
        <div className="bg-white border border-gray-200 rounded-lg overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-100 bg-gray-50 text-left">
                <th className="px-5 py-3 text-xs font-medium text-gray-500 uppercase tracking-wide">
                  Name
                </th>
                <th className="px-5 py-3 text-xs font-medium text-gray-500 uppercase tracking-wide">
                  Key prefix
                </th>
                <th className="px-5 py-3 text-xs font-medium text-gray-500 uppercase tracking-wide">
                  Last used
                </th>
                <th className="px-5 py-3 text-xs font-medium text-gray-500 uppercase tracking-wide">
                  Status
                </th>
                <th className="px-5 py-3" />
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {keys.map((key) => (
                <tr key={key.id} className={key.revoked_at ? "opacity-50" : ""}>
                  <td className="px-5 py-3 font-medium text-gray-900">
                    {key.name}
                  </td>
                  <td className="px-5 py-3 font-mono text-gray-600">
                    {key.key_prefix}...
                  </td>
                  <td className="px-5 py-3 text-gray-500">
                    {formatNullableDate(key.last_used_at)}
                  </td>
                  <td className="px-5 py-3">
                    {key.revoked_at ? (
                      <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-red-100 text-red-700">
                        Revoked {formatNullableDate(key.revoked_at)}
                      </span>
                    ) : (
                      <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-green-100 text-green-700">
                        Active
                      </span>
                    )}
                  </td>
                  <td className="px-5 py-3 text-right">
                    {!key.revoked_at && (
                      <button
                        onClick={() => setRevokeTarget(key)}
                        className="text-sm text-red-600 hover:text-red-700 font-medium"
                      >
                        Revoke
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {revokeError && (
        <div className="mt-4 bg-red-50 border border-red-200 rounded-md p-4 text-sm text-red-700">
          {revokeError}
        </div>
      )}

      {showCreate && (
        <ApiKeyCreateModal
          projectId={projectId}
          onClose={() => setShowCreate(false)}
          onCreated={loadKeys}
        />
      )}

      <ConfirmDialog
        open={!!revokeTarget}
        title="Revoke API key"
        description={`Are you sure you want to revoke "${revokeTarget?.name}"? Any SDK instances using this key will stop working immediately.`}
        confirmLabel="Revoke key"
        onConfirm={handleRevoke}
        onCancel={() => {
          setRevokeTarget(null);
          setRevokeError(null);
        }}
        loading={revoking}
      />
    </div>
  );
}
