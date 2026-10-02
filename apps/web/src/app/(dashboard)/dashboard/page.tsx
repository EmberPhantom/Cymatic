"use client"

import { useState, useMemo, useDeferredValue, useEffect, useRef } from "react"
import { useRouter } from "next/navigation"
import Link from "next/link"
import { useProjects } from "@/hooks/use-projects"
import { useCreateProject } from "@/hooks/use-create-project"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
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
import { cn } from "@/lib/utils"
import { getErrorMessage } from "@/lib/errors"
import { api } from "@/lib/api"
import { queryKeys } from "@/lib/queryKeys"
import { useQueryClient } from "@tanstack/react-query"
import type { Project } from "@/types"
import {
  Plus,
  Search,
  LayoutGrid,
  List,
  Trash2,
  X,
  ChevronLeft,
  ChevronRight,
  Glasses,
  FileCode2,
  Sparkles
} from "lucide-react"

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

function FormattedDate({ date }: { date: string }) {
  const [formatted, setFormatted] = useState<string>("")
  useEffect(() => {
    setFormatted(new Date(date).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" }))
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
  const { data: projects, isLoading, isError, refetch } = useProjects()
  const createProject = useCreateProject()
  const [showNewProject, setShowNewProject] = useState(false)
  const [name, setName] = useState("")
  const [domain, setDomain] = useState<"real_estate" | "heritage">("real_estate")
  const [search, setSearch] = useState("")
  const [activeFilter, setActiveFilter] = useState<"all" | "real_estate" | "heritage" | "published">("all")
  const [sortBy, setSortBy] = useState<"newest" | "oldest" | "name">("newest")
  const [viewMode, setViewMode] = useState<"grid" | "table">("grid")
  const [page, setPage] = useState(1)
  const pageSize = 9

  const searchInputRef = useRef<HTMLInputElement>(null)

  const [deleteTarget, setDeleteTarget] = useState<Project | null>(null)
  const [deleteError, setDeleteError] = useState<string | null>(null)
  const [isDeleting, setIsDeleting] = useState(false)

  const deferredSearch = useDeferredValue(search)
  const isSearchStale = search !== deferredSearch

  // Keyboard shortcut '/' to focus search
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "/" && document.activeElement !== searchInputRef.current && !showNewProject) {
        e.preventDefault()
        searchInputRef.current?.focus()
      }
    }
    window.addEventListener("keydown", handleKeyDown)
    return () => window.removeEventListener("keydown", handleKeyDown)
  }, [showNewProject])

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
      // Handled in mutation state
    }
  }

  // Real KPI metrics dynamically computed
  const kpis = useMemo(() => {
    if (!projects) return { total: 0, published: 0, realEstate: 0, heritage: 0 }
    const total = projects.length
    const published = projects.filter((p) => p.status === "published" || p.status === "scene_ready").length
    const realEstate = projects.filter((p) => p.domain === "real_estate").length
    const heritage = projects.filter((p) => p.domain === "heritage").length
    return { total, published, realEstate, heritage }
  }, [projects])

  // Filtering & Sorting
  const filtered = useMemo(() => {
    if (!projects) return []
    let list = [...projects]
    if (deferredSearch) {
      const q = deferredSearch.toLowerCase()
      list = list.filter((p) => p.name.toLowerCase().includes(q))
    }
    if (activeFilter === "real_estate") {
      list = list.filter((p) => p.domain === "real_estate")
    } else if (activeFilter === "heritage") {
      list = list.filter((p) => p.domain === "heritage")
    } else if (activeFilter === "published") {
      list = list.filter((p) => p.status === "published" || p.status === "scene_ready")
    }

    list.sort((a, b) => {
      if (sortBy === "name") return a.name.localeCompare(b.name)
      if (sortBy === "oldest") return new Date(a.created_at).getTime() - new Date(b.created_at).getTime()
      return new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
    })

    return list
  }, [projects, deferredSearch, activeFilter, sortBy])

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
      setDeleteError(getErrorMessage(err, "Delete failed. Please try again."))
    } finally {
      setIsDeleting(false)
    }
  }

  return (
    <div className="space-y-5">
      {/* Top Header & New Project Action */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-3 border-b border-border">
        <div>
          <h1 className="text-xl sm:text-2xl font-bold tracking-tight text-foreground">Simulation Projects</h1>
          <p className="text-xs text-stonegray mt-0.5">
            Architecture and heritage spatial walkthroughs.
          </p>
        </div>

        <Dialog open={showNewProject} onOpenChange={setShowNewProject}>
          <DialogTrigger asChild>
            <Button variant="terracotta" size="sm" className="gap-1.5 font-medium shadow-xs h-8 text-xs">
              <Plus className="h-3.5 w-3.5" />
              <span>New Simulation</span>
            </Button>
          </DialogTrigger>

          <DialogContent className="sm:max-w-md border-warmgray">
            <DialogHeader>
              <DialogTitle className="text-base font-bold text-foreground">New Simulation Project</DialogTitle>
              <DialogDescription className="text-xs text-stonegray">
                Initialize a structured spatial simulation for real estate or cultural heritage.
              </DialogDescription>
            </DialogHeader>

            <div className="space-y-4 mt-2">
              <div className="space-y-1.5">
                <Label htmlFor="project-name" className="text-xs font-medium text-foreground">Project Name</Label>
                <Input
                  id="project-name"
                  placeholder="e.g. Hampi Mandapa Sanctuary"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  className="h-9 text-xs border-warmgray focus-visible:ring-terracotta"
                />
              </div>

              <div className="space-y-1.5">
                <Label className="text-xs font-medium text-foreground">Domain</Label>
                <div className="grid grid-cols-2 gap-2">
                  <button
                    type="button"
                    onClick={() => setDomain("real_estate")}
                    className={`p-3 rounded-lg border text-xs text-left transition-all ${
                      domain === "real_estate"
                        ? "border-terracotta bg-terracotta-50/50 dark:bg-terracotta-950/20 font-medium text-foreground shadow-xs ring-1 ring-terracotta/40"
                        : "border-border text-stonegray hover:text-foreground hover:bg-muted/40"
                    }`}
                  >
                    <div className="font-semibold text-foreground">Real Estate</div>
                    <div className="text-[11px] text-stonegray mt-0.5 leading-tight">Villas, apartments &amp; architectural interiors</div>
                  </button>

                  <button
                    type="button"
                    onClick={() => setDomain("heritage")}
                    className={`p-3 rounded-lg border text-xs text-left transition-all ${
                      domain === "heritage"
                        ? "border-sage bg-sage-50/50 dark:bg-sage-950/20 font-medium text-foreground shadow-xs ring-1 ring-sage/40"
                        : "border-border text-stonegray hover:text-foreground hover:bg-muted/40"
                    }`}
                  >
                    <div className="font-semibold text-foreground">Heritage</div>
                    <div className="text-[11px] text-stonegray mt-0.5 leading-tight">Courtyards, temples &amp; archaeological monuments</div>
                  </button>
                </div>
              </div>

              <Button
                onClick={handleCreate}
                variant="terracotta"
                size="sm"
                className="w-full font-medium"
                disabled={createProject.isPending || !name.trim()}
              >
                {createProject.isPending ? "Initializing…" : "Create Simulation"}
              </Button>
            </div>
          </DialogContent>
        </Dialog>
      </div>

      {/* Interactive Filter Pills & Search Bar */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pt-1">
        {/* Interactive Filter Chips */}
        <div className="flex items-center gap-1.5 overflow-x-auto pb-1 sm:pb-0">
          <button
            type="button"
            onClick={() => {
              setActiveFilter("all")
              setPage(1)
            }}
            className={`px-3 py-1 text-xs font-medium rounded-lg transition-all flex items-center gap-1.5 border whitespace-nowrap ${
              activeFilter === "all"
                ? "bg-charcoal text-white dark:bg-ivory dark:text-charcoal border-transparent font-semibold shadow-xs"
                : "border-border text-stonegray hover:text-foreground hover:bg-muted/40"
            }`}
          >
            <span>All Projects</span>
            <span className="font-mono text-[10px] opacity-75">({kpis.total})</span>
          </button>

          <button
            type="button"
            onClick={() => {
              setActiveFilter("real_estate")
              setPage(1)
            }}
            className={`px-3 py-1 text-xs font-medium rounded-lg transition-all flex items-center gap-1.5 border whitespace-nowrap ${
              activeFilter === "real_estate"
                ? "bg-terracotta text-white border-transparent font-semibold shadow-xs"
                : "border-border text-stonegray hover:text-foreground hover:bg-muted/40"
            }`}
          >
            <span>Real Estate</span>
            <span className="font-mono text-[10px] opacity-75">({kpis.realEstate})</span>
          </button>

          <button
            type="button"
            onClick={() => {
              setActiveFilter("heritage")
              setPage(1)
            }}
            className={`px-3 py-1 text-xs font-medium rounded-lg transition-all flex items-center gap-1.5 border whitespace-nowrap ${
              activeFilter === "heritage"
                ? "bg-sage text-white border-transparent font-semibold shadow-xs"
                : "border-border text-stonegray hover:text-foreground hover:bg-muted/40"
            }`}
          >
            <span>Heritage</span>
            <span className="font-mono text-[10px] opacity-75">({kpis.heritage})</span>
          </button>

          <button
            type="button"
            onClick={() => {
              setActiveFilter("published")
              setPage(1)
            }}
            className={`px-3 py-1 text-xs font-medium rounded-lg transition-all flex items-center gap-1.5 border whitespace-nowrap ${
              activeFilter === "published"
                ? "bg-gold text-white border-transparent font-semibold shadow-xs"
                : "border-border text-stonegray hover:text-foreground hover:bg-muted/40"
            }`}
          >
            <span>Ready / Stream</span>
            <span className="font-mono text-[10px] opacity-75">({kpis.published})</span>
          </button>
        </div>

        {/* Search, Sort & View Mode */}
        <div className="flex items-center gap-2">
          <div className="relative w-full sm:w-56">
            <Search className="absolute left-2.5 top-2 h-3.5 w-3.5 text-stonegray pointer-events-none" />
            <Input
              ref={searchInputRef}
              placeholder="Search simulations... (/)"
              value={search}
              onChange={(e) => {
                setSearch(e.target.value)
                setPage(1)
              }}
              className="pl-8 pr-7 h-7 text-xs border-border focus-visible:ring-terracotta"
              aria-label="Search projects"
            />
            {search && (
              <button
                onClick={() => {
                  setSearch("")
                  setPage(1)
                }}
                className="absolute right-2 top-1.5 text-stonegray hover:text-foreground"
                aria-label="Clear search"
              >
                <X className="h-3.5 w-3.5" />
              </button>
            )}
          </div>

          <select
            value={sortBy}
            onChange={(e) => setSortBy(e.target.value as "newest" | "oldest" | "name")}
            className="h-7 rounded-lg border border-border bg-background px-2 text-xs text-stonegray focus:ring-1 focus:ring-terracotta"
            aria-label="Sort projects"
          >
            <option value="newest">Newest</option>
            <option value="oldest">Oldest</option>
            <option value="name">Name (A-Z)</option>
          </select>

          <div className="flex items-center rounded-lg border border-border p-0.5 bg-muted/20">
            <button
              onClick={() => setViewMode("grid")}
              className={`p-1 rounded transition-colors ${
                viewMode === "grid" ? "bg-card text-foreground shadow-2xs" : "text-stonegray hover:text-foreground"
              }`}
              title="Grid View"
              aria-label="Grid view"
            >
              <LayoutGrid className="h-3.5 w-3.5" />
            </button>
            <button
              onClick={() => setViewMode("table")}
              className={`p-1 rounded transition-colors ${
                viewMode === "table" ? "bg-card text-foreground shadow-2xs" : "text-stonegray hover:text-foreground"
              }`}
              title="Table View"
              aria-label="Table view"
            >
              <List className="h-3.5 w-3.5" />
            </button>
          </div>
        </div>
      </div>

      {createProject.isError && (
        <div className="rounded-lg bg-destructive/10 border border-destructive/20 p-3 text-xs text-destructive" role="alert">
          Unable to create project. Please retry.
        </div>
      )}

      {/* Projects Display */}
      {isError ? (
        <div className="rounded-xl border border-warmgray p-6 text-center max-w-sm mx-auto my-6">
          <p className="font-semibold text-xs text-destructive">Failed to load projects</p>
          <Button className="mt-3" variant="outline" size="sm" onClick={() => refetch()}>
            Retry
          </Button>
        </div>
      ) : isLoading ? (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {[1, 2, 3].map((i) => (
            <Card key={i} className="border-warmgray">
              <div className="h-28 bg-muted/40 animate-pulse rounded-t-xl" />
              <CardHeader className="space-y-2 p-4">
                <Skeleton className="h-4 w-3/4 rounded" />
                <Skeleton className="h-3 w-1/2 rounded" />
              </CardHeader>
              <CardContent className="p-4 pt-0">
                <Skeleton className="h-8 w-full rounded" />
              </CardContent>
            </Card>
          ))}
        </div>
      ) : filtered.length > 0 ? (
        <>
          {viewMode === "grid" ? (
            <div
              className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4"
              aria-busy={isSearchStale}
              aria-live="polite"
            >
              {paginated.map((project) => {
                const isHeritage = project.domain === "heritage"
                const isStreamReady = project.status === "published" || project.status === "scene_ready"

                return (
                  <Card
                    key={project.id}
                    className="flex h-full flex-col border border-border bg-card hover:border-foreground/40 hover:shadow-xs transition-all duration-200 overflow-hidden group"
                  >
                    {/* Blueprint Preview Bar */}
                    <div className="h-24 relative bg-charcoal text-white flex items-center justify-center overflow-hidden border-b border-border">
                      <div
                        className="absolute inset-0 opacity-20 pointer-events-none"
                        style={{
                          backgroundImage:
                            "linear-gradient(to right, rgba(229, 225, 216, 0.4) 1px, transparent 1px), linear-gradient(to bottom, rgba(229, 225, 216, 0.4) 1px, transparent 1px)",
                          backgroundSize: "16px 16px",
                        }}
                      />

                      <svg viewBox="0 0 200 65" className="w-full h-full p-2 opacity-85 pointer-events-none">
                        <polygon
                          points="20,55 100,62 180,55 100,47"
                          fill={isHeritage ? "rgba(111, 125, 104, 0.2)" : "rgba(166, 90, 58, 0.2)"}
                          stroke={isHeritage ? "#6F7D68" : "#A65A3A"}
                          strokeWidth="1"
                          strokeDasharray="2 2"
                        />
                        <polygon
                          points="50,50 100,56 150,50 100,42"
                          fill={isHeritage ? "rgba(184, 148, 82, 0.3)" : "rgba(166, 90, 58, 0.3)"}
                          stroke={isHeritage ? "#B89452" : "#A65A3A"}
                          strokeWidth="1.2"
                        />
                        <line x1="50" y1="50" x2="50" y2="24" stroke="#E5E1D8" strokeWidth="1.5" />
                        <line x1="100" y1="56" x2="100" y2="30" stroke="#E5E1D8" strokeWidth="1.5" />
                        <line x1="150" y1="50" x2="150" y2="24" stroke="#E5E1D8" strokeWidth="1.5" />
                        <polygon points="50,24 100,30 150,24 100,16" fill="rgba(229, 225, 216, 0.3)" stroke="#E5E1D8" strokeWidth="1.2" />
                      </svg>

                      {/* Domain Badge & ID */}
                      <div className="absolute top-2 left-2.5 flex items-center gap-1.5 z-10">
                        <Badge
                          variant={isHeritage ? "sage" : "terracotta"}
                          className="text-[9px] font-mono tracking-wider uppercase px-2 py-0"
                        >
                          {domainLabel[project.domain] ?? project.domain}
                        </Badge>
                      </div>

                      <div className="absolute top-2 right-2.5 flex items-center gap-1 z-10">
                        <span className="text-[10px] font-mono text-stonegray-300 bg-black/50 px-1.5 py-0.5 rounded border border-white/10">
                          #{project.id}
                        </span>
                      </div>

                      <div className="absolute bottom-1.5 left-2.5 text-[9px] font-mono text-ivory/80">
                        {isStreamReady ? "VR STREAM READY" : "SIMULATION DRAFT"}
                      </div>
                    </div>

                    <CardHeader className="p-4 pb-2 flex-1 space-y-2">
                      <div className="flex items-start justify-between gap-2">
                        <Link
                          href={`/projects/${project.id}`}
                          className="min-w-0 flex-1 hover:text-terracotta transition-colors"
                        >
                          <CardTitle className="text-base font-bold truncate text-foreground tracking-tight group-hover:text-terracotta transition-colors">
                            {project.name}
                          </CardTitle>
                        </Link>

                        <Button
                          variant="ghost"
                          size="sm"
                          className="h-6 w-6 p-0 text-stonegray hover:text-destructive shrink-0"
                          onClick={() => {
                            setDeleteTarget(project)
                            setDeleteError(null)
                          }}
                          aria-label={`Delete ${project.name}`}
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                        </Button>
                      </div>

                      {/* Domain & Status row */}
                      <div className="flex items-center gap-2 flex-wrap">
                        <Badge
                          variant={isHeritage ? "sage" : "terracotta"}
                          className="text-[10px] font-mono tracking-wider uppercase px-2 py-0.5"
                        >
                          {domainLabel[project.domain] ?? project.domain}
                        </Badge>
                        <Badge
                          variant={statusVariant[project.status] ?? "outline"}
                          className="text-[10px] font-mono capitalize px-2 py-0.5"
                        >
                          {project.status.replace("_", " ")}
                        </Badge>
                      </div>

                      {/* Last Updated */}
                      <div className="text-[11px] text-stonegray flex items-center gap-1 font-mono">
                        <span>Updated:</span>
                        <FormattedDate date={project.created_at} />
                      </div>
                    </CardHeader>

                    {/* Quick Launch Actions */}
                    <CardContent className="p-4 pt-1 space-y-2">
                      <div className="flex items-center gap-2 pt-1 border-t border-border/70">
                        <Link href={`/projects/${project.id}/builder`} className="flex-1">
                          <Button
                            size="sm"
                            variant="terracotta"
                            className="w-full h-8 text-xs font-semibold gap-1.5 shadow-2xs"
                          >
                            <Sparkles className="h-3.5 w-3.5" />
                            <span>Builder →</span>
                          </Button>
                        </Link>

                        {isStreamReady ? (
                          <Link href={`/projects/${project.id}/stream`}>
                            <Button size="sm" variant="outline" className="h-8 text-xs px-2.5 gap-1 border-border hover:border-foreground/30" title="Stream VR">
                              <Glasses className="h-3.5 w-3.5 text-sage" />
                              <span>Stream</span>
                            </Button>
                          </Link>
                        ) : (
                          <Link href={`/projects/${project.id}/specs`}>
                            <Button size="sm" variant="ghost" className="h-8 text-xs px-2.5 text-stonegray hover:text-foreground" title="View Specifications">
                              <FileCode2 className="h-3.5 w-3.5" />
                              <span>Specs</span>
                            </Button>
                          </Link>
                        )}
                      </div>
                    </CardContent>
                  </Card>
                )
              })}
            </div>
          ) : (
            /* TABLE VIEW */
            <div className="rounded-xl border border-border bg-card overflow-hidden">
              <table className="w-full text-left text-xs">
                <thead className="bg-muted/40 border-b border-border text-[11px] font-medium text-stonegray">
                  <tr>
                    <th className="py-2.5 px-3">Project</th>
                    <th className="py-2.5 px-3">Domain</th>
                    <th className="py-2.5 px-3">Status</th>
                    <th className="py-2.5 px-3">Created</th>
                    <th className="py-2.5 px-3 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {paginated.map((project) => (
                    <tr key={project.id} className="hover:bg-muted/30 transition-colors">
                      <td className="py-2.5 px-3 font-medium text-foreground">
                        <Link href={`/projects/${project.id}`} className="hover:underline">
                          {project.name}
                        </Link>
                      </td>
                      <td className="py-2.5 px-3 text-stonegray">
                        {domainLabel[project.domain] ?? project.domain}
                      </td>
                      <td className="py-2.5 px-3">
                        <Badge variant={statusVariant[project.status] ?? "outline"} className="text-[10px] capitalize">
                          {project.status.replace("_", " ")}
                        </Badge>
                      </td>
                      <td className="py-2.5 px-3 text-stonegray">
                        <FormattedDate date={project.created_at} />
                      </td>
                      <td className="py-2.5 px-3 text-right">
                        <div className="flex items-center justify-end gap-1">
                          <Link href={`/projects/${project.id}/builder`}>
                            <Button size="sm" variant="ghost" className="h-6 text-xs px-2">
                              Builder
                            </Button>
                          </Link>
                          <Button
                            variant="ghost"
                            size="sm"
                            className="h-6 w-6 p-0 text-stonegray hover:text-destructive"
                            onClick={() => {
                              setDeleteTarget(project)
                              setDeleteError(null)
                            }}
                            aria-label={`Delete ${project.name}`}
                          >
                            <Trash2 className="h-3 w-3" />
                          </Button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {/* Arrow-Only Directional Pagination */}
          <nav className="flex items-center justify-between pt-3" aria-label="Pagination">
            <p id="projects-count" className="text-xs text-stonegray">
              Showing {paginated.length} of {filtered.length} simulations
            </p>

            <div className="flex gap-1 items-center">
              <Button
                variant="outline"
                size="sm"
                className="h-7 w-7 p-0"
                disabled={page <= 1}
                onClick={() => setPage((p) => p - 1)}
                aria-label="Previous page"
                title="Previous page"
              >
                <ChevronLeft className="h-4 w-4" />
              </Button>
              <span className="text-xs font-mono text-stonegray px-2">
                {page} / {totalPages}
              </span>
              <Button
                variant="outline"
                size="sm"
                className="h-7 w-7 p-0"
                disabled={page >= totalPages}
                onClick={() => setPage((p) => p + 1)}
                aria-label="Next page"
                title="Next page"
              >
                <ChevronRight className="h-4 w-4" />
              </Button>
            </div>
          </nav>
        </>
      ) : (
        /* Empty State */
        <div className="rounded-xl border border-dashed border-border p-8 text-center max-w-sm mx-auto my-8">
          <p className="text-sm font-medium text-foreground">No simulations found</p>
          <p className="text-xs text-stonegray mt-1">
            {search || activeFilter !== "all"
              ? "Adjust your search filters."
              : "Create your first simulation to get started."}
          </p>
          <Button
            variant="terracotta"
            size="sm"
            className="mt-4 text-xs font-medium"
            onClick={() => setShowNewProject(true)}
          >
            Create Simulation
          </Button>
        </div>
      )}

      {/* Delete Confirmation Dialog */}
      <AlertDialog open={!!deleteTarget} onOpenChange={(open) => !open && setDeleteTarget(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle className="text-sm font-semibold">Delete simulation?</AlertDialogTitle>
            <AlertDialogDescription className="text-xs">
              {deleteTarget ? `Permanently delete "${deleteTarget.name}". This cannot be undone.` : "This action cannot be undone."}
            </AlertDialogDescription>
          </AlertDialogHeader>

          {deleteError && (
            <p className="text-xs text-destructive" role="alert">
              {deleteError}
            </p>
          )}

          <AlertDialogFooter>
            <AlertDialogCancel onClick={() => setDeleteError(null)} disabled={isDeleting} className="h-8 text-xs">
              Cancel
            </AlertDialogCancel>
            <AlertDialogAction
              onClick={(e) => {
                e.preventDefault()
                void handleDelete()
              }}
              disabled={isDeleting}
              className="h-8 text-xs bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              {isDeleting ? "Deleting…" : "Delete"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}
