"use client";

import { useState, useMemo } from "react"
import { useRouter } from "next/navigation"
import Link from "next/link"
import { useProjects } from "@/hooks/use-projects"
import { useCreateProject } from "@/hooks/use-create-project"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog"
import { Badge } from "@/components/ui/badge"
import { Skeleton } from "@/components/ui/skeleton"
import { api } from "@/lib/api"
import { useQueryClient } from "@tanstack/react-query"

const domainLabel: Record<string, string> = { real_estate: "Real Estate", heritage: "Heritage" }
const statusVariant: Record<string, "default" | "secondary" | "outline"> = { draft: "secondary", spec_ready: "default", published: "default", failed: "destructive" as any }

export default function DashboardPage() {
  const router = useRouter()
  const queryClient = useQueryClient()
  const { data: projects, isLoading, isError, error, refetch } = useProjects()
  const createProject = useCreateProject()
  const [showNewProject, setShowNewProject] = useState(false)
  const [name, setName] = useState("")
  const [domain, setDomain] = useState("real_estate")
  const [search, setSearch] = useState("")
  const [filterDomain, setFilterDomain] = useState<string>("all")
  const [page, setPage] = useState(1)
  const pageSize = 9

  const handleCreate = async () => {
    if (!name.trim()) return
    try {
      const project = await createProject.mutateAsync({ name, domain })
      setShowNewProject(false)
      setName("")
      router.push(`/projects/${project.id}/builder`)
    } catch {
      // The mutation error is rendered below.
    }
  }

  const filtered = useMemo(() => {
    if (!projects) return []
    let list = [...projects]
    if (search) list = list.filter((p) => p.name.toLowerCase().includes(search.toLowerCase()))
    if (filterDomain !== "all") list = list.filter((p) => p.domain === filterDomain)
    return list
  }, [projects, search, filterDomain])

  const paginated = useMemo(() => {
    const start = (page - 1) * pageSize
    return filtered.slice(start, start + pageSize)
  }, [filtered, page])

  const totalPages = Math.max(1, Math.ceil(filtered.length / pageSize))

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-2xl font-bold">Projects</h2>
          <p className="text-muted-foreground">Manage your simulations</p>
        </div>
        <Dialog open={showNewProject} onOpenChange={setShowNewProject}>
          <DialogTrigger asChild>
            <Button>New Project</Button>
          </DialogTrigger>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Create Project</DialogTitle>
              <DialogDescription>Start a new simulation project</DialogDescription>
            </DialogHeader>
            <div className="space-y-4 mt-4">
              <div className="space-y-2">
                <Label htmlFor="project-name">Project Name</Label>
                <Input id="project-name" placeholder="My Property" value={name} onChange={(e) => setName(e.target.value)} autoFocus />
              </div>
              <div className="space-y-2">
                <Label htmlFor="project-domain">Domain</Label>
                <select
                  id="project-domain"
                  className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                  value={domain}
                  onChange={(e) => setDomain(e.target.value)}
                >
                  <option value="real_estate">Real Estate</option>
                  <option value="heritage">Heritage</option>
                </select>
              </div>
              <Button onClick={handleCreate} className="w-full" disabled={createProject.isPending || !name.trim()}>
                {createProject.isPending ? "Creating..." : "Create"}
              </Button>
            </div>
          </DialogContent>
        </Dialog>
      </div>

      <div className="flex gap-2 mb-4">
        <Input placeholder="Search projects..." value={search} onChange={(e) => { setSearch(e.target.value); setPage(1) }} className="max-w-sm" />
        <select value={filterDomain} onChange={(e) => { setFilterDomain(e.target.value); setPage(1) }} className="flex h-10 rounded-md border border-input bg-background px-3 py-2 text-sm">
          <option value="all">All domains</option>
          <option value="real_estate">Real Estate</option>
          <option value="heritage">Heritage</option>
        </select>
      </div>

      {createProject.isError && (
        <div className="mb-4 rounded-md bg-destructive/15 p-3 text-sm text-destructive">
          Unable to create the project. Please try again.
        </div>
      )}

      {isError ? (
        <div className="rounded-lg border border-destructive/30 bg-destructive/5 p-6 text-center">
          <p className="font-medium text-destructive">Unable to load your projects</p>
          <p className="mt-1 text-sm text-muted-foreground">{error instanceof Error ? error.message : "Please try again."}</p>
          <Button className="mt-4" variant="outline" onClick={() => refetch()}>Retry</Button>
        </div>
      ) : isLoading ? (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {[1, 2, 3].map((i) => (
            <Card key={i}>
              <CardHeader><Skeleton className="h-5 w-1/2" /></CardHeader>
              <CardContent><Skeleton className="h-4 w-3/4" /></CardContent>
            </Card>
          ))}
        </div>
      ) : filtered.length > 0 ? (
        <>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {paginated.map((project) => (
              <div key={project.id} className="relative">
                <Link href={`/projects/${project.id}`}>
                  <Card className="hover:shadow-md transition-shadow cursor-pointer h-full">
                    <CardHeader>
                      <CardTitle className="text-lg">{project.name}</CardTitle>
                      <CardDescription className="flex items-center gap-2">
                        <Badge variant="secondary">{domainLabel[project.domain] ?? project.domain}</Badge>
                        <Badge variant={statusVariant[project.status] ?? "outline"}>{project.status}</Badge>
                      </CardDescription>
                    </CardHeader>
                    <CardContent>
                      <p className="text-sm text-muted-foreground">Created {new Date(project.created_at).toLocaleDateString()}</p>
                    </CardContent>
                  </Card>
                </Link>
                <Button
                  variant="ghost"
                  size="sm"
                  className="absolute top-2 right-2 h-7 text-xs"
                  onClick={async (e) => {
                    e.preventDefault()
                    if (!confirm(`Delete "${project.name}"?`)) return
                    try { await api.delete(`/v1/projects/${project.id}`); queryClient.invalidateQueries({ queryKey: ["projects"] }) } catch (err: any) { alert(err?.response?.data?.detail || "Delete failed") }
                  }}
                >
                  Delete
                </Button>
              </div>
            ))}
          </div>
          <div className="flex items-center justify-between mt-6">
            <p className="text-sm text-muted-foreground">Showing {paginated.length} of {filtered.length} projects</p>
            <div className="flex gap-2">
              <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>Previous</Button>
              <span className="flex items-center text-sm px-2">Page {page} of {totalPages}</span>
              <Button variant="outline" size="sm" disabled={page >= totalPages} onClick={() => setPage((p) => p + 1)}>Next</Button>
            </div>
          </div>
        </>
      ) : (
        <div className="text-center py-12">
          <p className="text-muted-foreground">{search || filterDomain !== "all" ? "No projects match your filters." : "No projects yet. Create one to get started."}</p>
        </div>
      )}
    </div>
  )
}
