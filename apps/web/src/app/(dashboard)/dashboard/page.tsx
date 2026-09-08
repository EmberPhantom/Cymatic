"use client";

import { useState, useMemo, useDeferredValue, useEffect } from "react"
import { useRouter } from "next/navigation"
import Link from "next/link"
import { useProjects } from "@/hooks/use-projects"
import { useCreateProject } from "@/hooks/use-create-project"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog"
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog"
import { Badge } from "@/components/ui/badge"
import type { BadgeProps } from "@/components/ui/badge"
import { Skeleton } from "@/components/ui/skeleton"
import { api } from "@/lib/api"
import { queryKeys } from "@/lib/queryKeys"
import { useQueryClient } from "@tanstack/react-query"
import type { Project } from "@/types"

const domainLabel: Record<string, string> = { real_estate: "Real Estate", heritage: "Heritage" }
const statusVariant: Record<string, BadgeProps["variant"]> = {
  draft: "secondary",
  spec_ready: "default",
  published: "default",
  failed: "destructive",
}

function FormattedDate({ date }: { date: string }) {
  const [formatted, setFormatted] = useState<string>("")
  useEffect(() => {
    setFormatted(new Date(date).toLocaleDateString())
  }, [date])
  return (
    <time dateTime={date} suppressHydrationWarning>
      {formatted || date.slice(0, 10)}
    </time>
  )
}

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

  const [deleteTarget, setDeleteTarget] = useState<Project | null>(null)
  const [deleteError, setDeleteError] = useState<string | null>(null)
  const [isDeleting, setIsDeleting] = useState(false)

  const deferredSearch = useDeferredValue(search)
  const isSearchStale = search !== deferredSearch

  const handleCreate = async () => {
    const trimmed = name.trim()
    if (!trimmed) return
    try {
      const project = await createProject.mutateAsync({ name: trimmed, domain })
      await queryClient.invalidateQueries({ queryKey: queryKeys.projects.all })
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
    if (deferredSearch) {
      const q = deferredSearch.toLowerCase()
      list = list.filter((p) => p.name.toLowerCase().includes(q))
    }
    if (filterDomain !== "all") list = list.filter((p) => p.domain === filterDomain)
    return list
  }, [projects, deferredSearch, filterDomain])

  const paginated = useMemo(() => {
    const start = (page - 1) * pageSize
    return filtered.slice(start, start + pageSize)
  }, [filtered, page])

  const totalPages = Math.max(1, Math.ceil(filtered.length / pageSize))

  useEffect(() => {
    if (page > totalPages) setPage(totalPages)
  }, [page, totalPages])

  const handleDelete = async () => {
    if (!deleteTarget) return
    setIsDeleting(true)
    setDeleteError(null)
    try {
      await api.delete(`/v1/projects/${deleteTarget.id}`)
      await queryClient.invalidateQueries({ queryKey: queryKeys.projects.all })
      setDeleteTarget(null)
    } catch (err: unknown) {
      const e = err as { response?: { data?: { detail?: string } } }
      setDeleteError(e?.response?.data?.detail || "Delete failed. Please try again.")
    } finally {
      setIsDeleting(false)
    }
  }

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
                <Input id="project-name" placeholder="My Property" value={name} onChange={(e) => setName(e.target.value)} />
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
        <Input
          placeholder="Search projects..."
          value={search}
          onChange={(e) => {
            setSearch(e.target.value)
            setPage(1)
          }}
          className="max-w-sm"
          aria-label="Search projects"
          aria-describedby="projects-count"
        />
        <select
          value={filterDomain}
          onChange={(e) => {
            setFilterDomain(e.target.value)
            setPage(1)
          }}
          className="flex h-10 rounded-md border border-input bg-background px-3 py-2 text-sm"
          aria-label="Filter by domain"
        >
          <option value="all">All domains</option>
          <option value="real_estate">Real Estate</option>
          <option value="heritage">Heritage</option>
        </select>
      </div>

      {createProject.isError && (
        <div className="mb-4 rounded-md bg-destructive/15 p-3 text-sm text-destructive" role="alert">
          Unable to create the project. Please try again.
        </div>
      )}

      {isError ? (
        <div className="rounded-lg border border-destructive/30 bg-destructive/5 p-6 text-center">
          <p className="font-medium text-destructive">Unable to load your projects</p>
          <p className="mt-1 text-sm text-muted-foreground">{error instanceof Error ? error.message : "Please try again."}</p>
          <Button className="mt-4" variant="outline" onClick={() => refetch()}>
            Retry
          </Button>
        </div>
      ) : isLoading ? (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {[1, 2, 3].map((i) => (
            <Card key={i}>
              <CardHeader>
                <Skeleton className="h-5 w-1/2" />
              </CardHeader>
              <CardContent>
                <Skeleton className="h-4 w-3/4" />
              </CardContent>
            </Card>
          ))}
        </div>
      ) : filtered.length > 0 ? (
        <>
          <div
            className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4"
            aria-busy={isSearchStale}
            aria-live="polite"
          >
            {paginated.map((project) => (
              <Card key={project.id} className="flex h-full flex-col hover:shadow-md transition-shadow">
                <CardHeader className="flex-1">
                  <div className="flex items-start justify-between gap-2">
                    <Link
                      href={`/projects/${project.id}`}
                      className="min-w-0 flex-1 rounded-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
                    >
                      <CardTitle className="truncate text-lg transition-colors hover:text-primary">{project.name}</CardTitle>
                    </Link>
                    <Button
                      variant="ghost"
                      size="sm"
                      className="h-7 shrink-0 text-xs"
                      onClick={() => {
                        setDeleteTarget(project)
                        setDeleteError(null)
                      }}
                      aria-label={`Delete project ${project.name}`}
                    >
                      Delete
                    </Button>
                  </div>
                  <CardDescription className="flex items-center gap-2 flex-wrap">
                    <Badge variant="secondary">{domainLabel[project.domain] ?? project.domain}</Badge>
                    <Badge variant={statusVariant[project.status] ?? "outline"}>{project.status}</Badge>
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  <Link
                    href={`/projects/${project.id}`}
                    className="block rounded-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
                    aria-label={`View project ${project.name}`}
                  >
                    <p className="text-sm text-muted-foreground">
                      Created <FormattedDate date={project.created_at} />
                    </p>
                  </Link>
                </CardContent>
              </Card>
            ))}
          </div>
          <nav className="flex items-center justify-between mt-6" aria-label="Projects pagination">
            <p id="projects-count" className="text-sm text-muted-foreground" aria-live="polite" aria-atomic="true">
              Showing {paginated.length} of {filtered.length} projects
            </p>
            <div className="flex gap-2 items-center">
              <Button
                variant="outline"
                size="sm"
                disabled={page <= 1}
                onClick={() => setPage((p) => p - 1)}
                aria-label="Go to previous page"
              >
                Previous
              </Button>
              <span className="flex items-center text-sm px-2" aria-live="polite" aria-atomic="true">
                Page {page} of {totalPages}
              </span>
              <Button
                variant="outline"
                size="sm"
                disabled={page >= totalPages}
                onClick={() => setPage((p) => p + 1)}
                aria-label="Go to next page"
              >
                Next
              </Button>
            </div>
          </nav>
        </>
      ) : (
        <div className="text-center py-12" aria-live="polite" aria-atomic="true">
          <p className="text-muted-foreground">
            {search || filterDomain !== "all" ? "No projects match your filters." : "No projects yet. Create one to get started."}
          </p>
        </div>
      )}

      <AlertDialog open={!!deleteTarget} onOpenChange={(open) => !open && setDeleteTarget(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete project?</AlertDialogTitle>
            <AlertDialogDescription>
              {deleteTarget ? `This will permanently delete "${deleteTarget.name}". This action cannot be undone.` : "This action cannot be undone."}
            </AlertDialogDescription>
          </AlertDialogHeader>
          {deleteError && (
            <p className="text-sm text-destructive" role="alert">
              {deleteError}
            </p>
          )}
          <AlertDialogFooter>
            <AlertDialogCancel onClick={() => setDeleteError(null)} disabled={isDeleting}>
              Cancel
            </AlertDialogCancel>
            <AlertDialogAction
              onClick={(e) => {
                e.preventDefault()
                void handleDelete()
              }}
              disabled={isDeleting}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              {isDeleting ? "Deleting..." : "Delete"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}
