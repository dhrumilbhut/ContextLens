"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { api, ApiError } from "@/lib/api";
import type { ProjectListItem } from "@/lib/types";
import { EmptyState } from "@/components/empty-state";

export default function DashboardPage() {
  const router = useRouter();
  const [projects, setProjects] = useState<ProjectListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.projects
      .list()
      .then((data) => setProjects(data.projects))
      .catch((err) =>
        setError(err instanceof ApiError ? err.message : "Failed to load projects")
      )
      .finally(() => setLoading(false));
  }, []);

  function faithfulnessColor(score: number | null) {
    if (score === null) return "text-gray-400";
    if (score >= 0.8) return "text-green-600";
    if (score >= 0.5) return "text-yellow-600";
    return "text-red-600";
  }

  function faithfulnessLabel(score: number | null) {
    if (score === null) return "No data";
    return `${Math.round(score * 100)}%`;
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="bg-white border-b border-gray-200 px-6 py-4 flex items-center justify-between">
        <div>
          <h1 className="text-lg font-semibold text-gray-900">ContextLens</h1>
          <p className="text-xs text-gray-500">RAG Hallucination Diagnostics</p>
        </div>
        <Link
          href="/projects/new"
          className="px-4 py-2 text-sm font-medium text-white bg-indigo-600 rounded-md hover:bg-indigo-700"
        >
          New Project
        </Link>
      </header>

      <main className="max-w-5xl mx-auto px-6 py-8">
        <div className="flex items-center justify-between mb-6">
          <h2 className="text-xl font-semibold text-gray-900">Projects</h2>
        </div>

        {loading && (
          <div className="text-sm text-gray-500 py-8 text-center">Loading...</div>
        )}

        {error && (
          <div className="bg-red-50 border border-red-200 rounded-md p-4 text-sm text-red-700">
            {error}
          </div>
        )}

        {!loading && !error && projects.length === 0 && (
          <EmptyState
            title="No projects yet"
            description="Create your first project to start diagnosing hallucinations in your RAG pipeline."
            action={
              <Link
                href="/projects/new"
                className="px-4 py-2 text-sm font-medium text-white bg-indigo-600 rounded-md hover:bg-indigo-700"
              >
                Create your first project
              </Link>
            }
          />
        )}

        {!loading && !error && projects.length > 0 && (
          <div className="grid gap-4">
            {projects.map((project) => (
              <Link
                key={project.id}
                href={`/projects/${project.id}`}
                className="bg-white border border-gray-200 rounded-lg p-5 hover:border-indigo-300 hover:shadow-sm transition-all"
              >
                <div className="flex items-start justify-between">
                  <div>
                    <h3 className="text-base font-medium text-gray-900">
                      {project.name}
                    </h3>
                    {project.description && (
                      <p className="mt-0.5 text-sm text-gray-500">
                        {project.description}
                      </p>
                    )}
                  </div>
                  <div className="text-right ml-4 flex-shrink-0">
                    <p
                      className={`text-lg font-semibold ${faithfulnessColor(
                        project.avg_faithfulness
                      )}`}
                    >
                      {faithfulnessLabel(project.avg_faithfulness)}
                    </p>
                    <p className="text-xs text-gray-400">avg faithfulness</p>
                  </div>
                </div>
                <div className="mt-3 flex items-center gap-4 text-sm text-gray-500">
                  <span>{project.trace_count} traces</span>
                  <span>
                    Created{" "}
                    {new Date(project.created_at).toLocaleDateString("en-US", {
                      month: "short",
                      day: "numeric",
                      year: "numeric",
                    })}
                  </span>
                </div>
              </Link>
            ))}
          </div>
        )}
      </main>
    </div>
  );
}
