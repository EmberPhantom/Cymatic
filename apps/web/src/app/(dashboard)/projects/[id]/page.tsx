"use client"

import { useParams, notFound } from "next/navigation"
import Link from "next/link"
import { useProject } from "@/hooks/use-project"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Skeleton } from "@/components/ui/skeleton"

const tabs = [
  { label: "Builder", href: "builder" },
  { label: "Specs", href: "specs" },
  { label: "Assets", href: "assets" },
  { label: "Stream", href: "stream" },
]

export default function ProjectDetailPage() {
  const params = useParams()
  const projectId = Number(params.id)
  if (Number.isNaN(projectId)) notFound()
  const { data: project, isLoading, isError, error } = useProject(projectId)

  if (isLoading) return <div className="space-y-4"><Skeleton className="h-8 w-1/3" /><Skeleton className="h-4 w-1/2" /></div>
  if (isError) return <div className="rounded-md border border-destructive/30 bg-destructive/5 p-6 text-center"><p className="font-medium text-destructive">Unable to load project</p><p className="text-sm text-muted-foreground mt-1">{(error as Error)?.message}</p></div>
  if (!project) return null

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-2xl font-bold">{project.name}</h2>
          <p className="text-muted-foreground flex items-center gap-2 mt-1">
            <Badge variant="secondary">{project.domain}</Badge>
            <Badge variant="outline">{project.status}</Badge>
            <span className="text-sm">ID: {projectId}</span>
          </p>
        </div>
        <Link href={`/projects/${projectId}/builder`}>
          <Button>Open Builder</Button>
        </Link>
      </div>
      <div className="flex gap-1 border-b mb-6">
        {tabs.map((tab) => (
          <Link
            key={tab.href}
            href={`/projects/${projectId}/${tab.href}`}
            className="px-4 py-2 text-sm font-medium text-muted-foreground hover:text-foreground border-b-2 border-transparent hover:border-primary transition-colors aria-[current=page]:border-primary aria-[current=page]:text-foreground"
          >
            {tab.label}
          </Link>
        ))}
      </div>
      <div className="py-4 text-muted-foreground">Select a tab to view details. Created {new Date(project.created_at).toLocaleString()}.</div>
    </div>
  )
}
