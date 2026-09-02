"use client"

import { useParams } from "next/navigation"
import Link from "next/link"
import { Button } from "@/components/ui/button"

const tabs = [
  { label: "Specs", href: "specs" },
  { label: "Assets", href: "assets" },
  { label: "Stream", href: "stream" },
]

export default function ProjectDetailPage() {
  const params = useParams()
  const projectId = params.id

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-2xl font-bold">Project Details</h2>
          <p className="text-muted-foreground">ID: {projectId}</p>
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
            className="px-4 py-2 text-sm font-medium text-muted-foreground hover:text-foreground border-b-2 border-transparent hover:border-primary transition-colors"
          >
            {tab.label}
          </Link>
        ))}
      </div>
      <div className="py-4 text-muted-foreground">
        Select a tab to view details.
      </div>
    </div>
  )
}
