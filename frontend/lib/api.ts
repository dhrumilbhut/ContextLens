import type {
  ApiKeyCreateResponse,
  ApiKeyListResponse,
  ClustersResponse,
  DocumentsProblemsResponse,
  ProjectCreateResponse,
  ProjectDetailResponse,
  ProjectListResponse,
  TraceDetailResponse,
  TraceListResponse,
  UsageResponse,
} from "./types";

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function apiRequest<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers: { "Content-Type": "application/json", ...options.headers },
  });

  if (!response.ok) {
    const error = await response
      .json()
      .catch(() => ({ detail: "Unknown error" }));
    throw new ApiError(
      response.status,
      error.detail || error.error || "Request failed",
    );
  }

  if (response.status === 204) return undefined as T;
  return response.json();
}

export const api = {
  projects: {
    list: () => apiRequest<ProjectListResponse>("/projects"),
    get: (id: string) =>
      apiRequest<ProjectDetailResponse>(`/projects/${id}`),
    create: (data: { name: string; description?: string }) =>
      apiRequest<ProjectCreateResponse>("/projects", {
        method: "POST",
        body: JSON.stringify(data),
      }),
    delete: (id: string) =>
      apiRequest<{ message: string }>(`/projects/${id}`, {
        method: "DELETE",
      }),
  },
  apiKeys: {
    list: (projectId: string) =>
      apiRequest<ApiKeyListResponse>(`/projects/${projectId}/api-keys`),
    create: (projectId: string, name: string) =>
      apiRequest<ApiKeyCreateResponse>(`/projects/${projectId}/api-keys`, {
        method: "POST",
        body: JSON.stringify({ name }),
      }),
    revoke: (projectId: string, keyId: string) =>
      apiRequest<{ message: string }>(
        `/projects/${projectId}/api-keys/${keyId}`,
        { method: "DELETE" },
      ),
  },
  traces: {
    list: (
      projectId: string,
      params?: {
        limit?: number;
        offset?: number;
        status?: string;
        min_faithfulness?: number;
      },
    ) => {
      const query = new URLSearchParams();
      if (params?.limit !== undefined)
        query.set("limit", String(params.limit));
      if (params?.offset !== undefined)
        query.set("offset", String(params.offset));
      if (params?.status) query.set("status", params.status);
      if (params?.min_faithfulness !== undefined)
        query.set("min_faithfulness", String(params.min_faithfulness));
      const qs = query.toString();
      return apiRequest<TraceListResponse>(
        `/projects/${projectId}/traces${qs ? `?${qs}` : ""}`,
      );
    },
    get: (projectId: string, traceId: string) =>
      apiRequest<TraceDetailResponse>(
        `/projects/${projectId}/traces/${traceId}`,
      ),
  },
  clusters: {
    list: (projectId: string) =>
      apiRequest<ClustersResponse>(`/projects/${projectId}/clusters`),
  },
  documents: {
    problems: (projectId: string, days = 7, limit = 20) =>
      apiRequest<DocumentsProblemsResponse>(
        `/projects/${projectId}/documents/problems?days=${days}&limit=${limit}`,
      ),
  },
  usage: {
    get: (projectId: string) =>
      apiRequest<UsageResponse>(`/projects/${projectId}/usage`),
  },
};
