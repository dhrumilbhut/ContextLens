"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { api, ApiError } from "@/lib/api";
import { NavSidebar } from "@/components/nav-sidebar";

export default function ProjectLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const params = useParams();
  const projectId = params.projectId as string;
  const [projectName, setProjectName] = useState<string>("");

  useEffect(() => {
    if (!projectId) return;
    api.projects
      .get(projectId)
      .then((data) => setProjectName(data.name))
      .catch(() => setProjectName("Project"));
  }, [projectId]);

  return (
    <div className="flex min-h-screen bg-gray-50">
      <NavSidebar projectId={projectId} projectName={projectName || "Loading..."} />
      <div className="flex-1 overflow-auto">{children}</div>
    </div>
  );
}
