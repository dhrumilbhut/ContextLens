"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

interface NavSidebarProps {
  projectId: string;
  projectName: string;
}

export function NavSidebar({ projectId, projectName }: NavSidebarProps) {
  const pathname = usePathname();

  const links = [
    { label: "Overview", href: `/projects/${projectId}` },
    { label: "Traces", href: `/projects/${projectId}/traces` },
    { label: "Clusters", href: `/projects/${projectId}/clusters` },
    { label: "Documents", href: `/projects/${projectId}/documents` },
    { label: "API Keys", href: `/projects/${projectId}/settings/api-keys` },
    { label: "Usage", href: `/projects/${projectId}/settings/usage` },
  ];

  function isActive(href: string) {
    if (href === `/projects/${projectId}`) {
      return pathname === href;
    }
    return pathname.startsWith(href);
  }

  return (
    <aside className="w-52 flex-shrink-0 border-r border-gray-200 bg-white min-h-screen">
      <div className="p-4 border-b border-gray-200">
        <Link
          href="/dashboard"
          className="text-xs font-medium text-gray-500 hover:text-gray-700 flex items-center gap-1"
        >
          <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
          </svg>
          All projects
        </Link>
        <p className="mt-2 text-sm font-semibold text-gray-900 truncate" title={projectName}>
          {projectName}
        </p>
      </div>
      <nav className="p-2">
        {links.map((link) => (
          <Link
            key={link.href}
            href={link.href}
            className={`flex items-center px-3 py-2 rounded-md text-sm font-medium transition-colors ${
              isActive(link.href)
                ? "bg-indigo-50 text-indigo-700"
                : "text-gray-600 hover:bg-gray-50 hover:text-gray-900"
            }`}
          >
            {link.label}
          </Link>
        ))}
      </nav>
    </aside>
  );
}
