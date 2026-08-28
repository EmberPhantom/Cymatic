"use client";

import { useState } from "react"
import { useRouter } from "next/navigation"
import Link from "next/link"
import { useProjects } from "@/hooks/use-projects"
import { useCreateProject } from "@/hooks/use-create-project"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog"

export default function DashboardPage() {
  const router = useRouter()
  const { data: projects, isLoading, isError, error, refetch } = useProjects()
  const createProject = useCreateProject()
  const [showNewProject, setShowNewProject] = useState(false)
  const [name, setName] = useState("")
  const [domain, setDomain] = useState("real_estate")

  const handleCreate = async () => {
    if (!name.trim()) return
    try {
      const project = await createProject.mutateAsync({ name, domain })
      setShowNewProject(false)
      setName("")
      router.push(`/dashboard/projects/${project.id}/builder`)
    } catch {
      // The mutation error is rendered below.
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
                <Label>Project Name</Label>
                <Input placeholder="My Property" value={name} onChange={(e) => setName(e.target.value)} />
              </div>
              <div className="space-y-2">
                <Label>Domain</Label>
                <select
                  className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                  value={domain}
                  onChange={(e) => setDomain(e.target.value)}
                >
                  <option value="real_estate">Real Estate</option>
                  <option value="heritage">Heritage</option>
                </select>
              </div>
              <Button onClick={handleCreate} className="w-full" disabled={createProject.isPending}>
                {createProject.isPending ? "Creating..." : "Create"}
              </Button>
            </div>
          </DialogContent>
        </Dialog>
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
            <Card key={i} className="animate-pulse">
              <CardHeader><div className="h-5 bg-gray-200 rounded w-1/2" /></CardHeader>
              <CardContent><div className="h-4 bg-gray-200 rounded w-3/4" /></CardContent>
            </Card>
          ))}
        </div>
      ) : projects && projects.length > 0 ? (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {projects.map((project) => (
            <Link key={project.id} href={`/dashboard/projects/${project.id}`}>
              <Card className="hover:shadow-md transition-shadow cursor-pointer h-full">
                <CardHeader>
                  <CardTitle className="text-lg">{project.name}</CardTitle>
                  <CardDescription className="flex items-center gap-2">
                    <span className="inline-flex items-center rounded-full bg-blue-50 px-2 py-1 text-xs font-medium text-blue-700 ring-1 ring-inset ring-blue-700/10">
                      {project.domain}
                    </span>
                    <span className="inline-flex items-center rounded-full bg-gray-50 px-2 py-1 text-xs font-medium text-gray-600 ring-1 ring-inset ring-gray-500/10">
                      {project.status}
                    </span>
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  <p className="text-sm text-muted-foreground">
                    Created {new Date(project.created_at).toLocaleDateString()}
                  </p>
                </CardContent>
              </Card>
            </Link>
          ))}
        </div>
      ) : (
        <div className="text-center py-12">
          <p className="text-muted-foreground">No projects yet. Create one to get started.</p>
        </div>
      )}
    </div>
  )
}
