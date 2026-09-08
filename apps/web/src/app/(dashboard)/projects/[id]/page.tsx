"use client"

import { useEffect, useState } from "react"
import { useParams, notFound, usePathname } from "next/navigation"
import Link from "next/link"
import { useProject } from "@/hooks/use-project"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import type { BadgeProps } from "@/components/ui/badge"
import { Skeleton } from "@/components/ui/skeleton"

const tabs = [
  { label: "Builder", href: "builder" },
  { label: "Specs", href: "specs" },
  { label: "Assets", href: "assets" },
  { label: "Stream", href: "stream" },
]

const domainLabel: Record<string, string> = { real_estate: "Real Estate", heritage: "Heritage" }
const statusVariant: Record<string, BadgeProps["variant"]> = {
  draft: "secondary",
  spec_generating: "secondary",
  spec_ready: "default",
  scene_generating: "secondary",
  scene_ready: "default",
  published: "default",
  failed: "destructive",
}

export default function ProjectDetailPage() {
  const params = useParams()
  const pathname = usePathname()
  const projectId = Number(params.id)
  const { data: project, isLoading, isError, error } = useProject(Number.isNaN(projectId) ? null : projectId)

  const [displayDate, setDisplayDate] = useState<string>("")
  useEffect(() => {
    if (project?.created_at) {
      setDisplayDate(new Date(project.created_at).toLocaleString())
    }
  }, [project?.created_at])

  if (Number.isNaN(projectId)) notFound()

  if (isLoading)
    return (
      <div className="space-y-4">
        <Skeleton className="h-8 w-1/3" />
        <Skeleton className="h-4 w-1/2" />
      </div>
    )
  if (isError)
    return (
      <div className="rounded-md border border-destructive/30 bg-destructive/5 p-6 text-center">
        <p className="font-medium text-destructive">Unable to load project</p>
        <p className="text-sm text-muted-foreground mt-1">{(error as Error)?.message}</p>
      </div>
    )
  if (!project) return null

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-2xl font-bold">{project.name}</h2>
          <p className="text-muted-foreground flex items-center gap-2 mt-1 flex-wrap">
            <Badge variant="secondary">{domainLabel[project.domain] ?? project.domain}</Badge>
            <Badge variant={statusVariant[project.status] ?? "outline"}>{project.status}</Badge>
            <span className="text-sm">ID: {projectId}</span>
          </p>
        </div>
        <Link href={`/projects/${projectId}/builder`}>
          <Button>Open Builder</Button>
        </Link>
      </div>
      <nav className="flex gap-1 border-b mb-6" aria-label="Project sections">
        {tabs.map((tab) => {
          const href = `/projects/${projectId}/${tab.href}`
          const isActive = pathname === href
          return (
            <Link
              key={tab.href}
              href={href}
              aria-current={isActive ? "page" : undefined}
              className="px-4 py-2 text-sm font-medium text-muted-foreground hover:text-foreground border-b-2 border-transparent hover:border-primary transition-colors aria-[current=page]:border-primary aria-[current=page]:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 rounded-sm"
            >
              {tab.label}
            </Link>
          )
        })}
      </nav>
      <div className="py-4 text-muted-foreground">
        Select a tab to view details. Created{" "}
        {project.created_at ? (
          <time dateTime={project.created_at} suppressHydrationWarning>
            {displayDate || project.created_at.slice(0, 10)}
          </time>
        ) : (
          "—"
        )}
        .
      </div>
    </div>
  )
}
