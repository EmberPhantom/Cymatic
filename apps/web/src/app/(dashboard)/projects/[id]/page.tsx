"use client"

import { useEffect, useState, useMemo } from "react"
import { useParams, notFound, usePathname } from "next/navigation"
import Link from "next/link"
import { useProject } from "@/hooks/use-project"
import { useSpecs } from "@/hooks/use-specs"
import { useAssets } from "@/hooks/use-assets"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import type { BadgeProps } from "@/components/ui/badge"
import { Skeleton } from "@/components/ui/skeleton"
import { SceneViewportPreview } from "@/components/scene/SceneViewportPreview"
import { PipelineStepper, type PipelineStage } from "@/components/pipeline/PipelineStepper"
import { countSpecEntities } from "@/lib/validations"
import { isActivePath, routes } from "@/lib/routes"
import {
  Sparkles,
  Glasses,
  FileCode2,
  Package,
  Compass,
  ArrowRight,
  Layers,
  Cpu,
  Radio,
  ExternalLink
} from "lucide-react"

const tabs: Array<{ label: string; icon: typeof Compass; href: (id: number) => string; exact?: boolean }> = [
  { label: "Overview", icon: Compass, href: (id: number) => routes.project(id), exact: true },
  { label: "Builder", icon: Sparkles, href: (id: number) => routes.builder(id) },
  { label: "Specs", icon: FileCode2, href: (id: number) => routes.specs(id) },
  { label: "Assets", icon: Package, href: (id: number) => routes.assets(id) },
  { label: "Stream", icon: Glasses, href: (id: number) => routes.stream(id) },
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

  // Real data from backend endpoints
  const { data: specs, isLoading: specsLoading } = useSpecs(Number.isNaN(projectId) ? 0 : projectId)
  const { data: assets, isLoading: assetsLoading } = useAssets(Number.isNaN(projectId) ? 0 : projectId)

  const [displayDate, setDisplayDate] = useState<string>("")
  useEffect(() => {
    if (project?.created_at) {
      setDisplayDate(new Date(project.created_at).toLocaleDateString(undefined, {
        month: "short",
        day: "numeric",
        year: "numeric",
      }))
    }
  }, [project?.created_at])

  // Determine current pipeline stage from real backend state
  const pipelineStage: PipelineStage = useMemo(() => {
    if (!project) return "input"
    if (project.status === "published") return "published"
    if (project.status === "scene_ready") return "vr_stream"
    if (project.status === "scene_generating") return "build"
    if (project.status === "spec_ready") return "scene"
    if (project.status === "spec_generating") return "specification"
    return "input"
  }, [project])

  if (Number.isNaN(projectId)) notFound()

  if (isLoading)
    return (
      <div className="space-y-4 pt-2">
        <Skeleton className="h-8 w-1/3 rounded-lg" />
        <Skeleton className="h-4 w-1/4 rounded-lg" />
        <div className="grid grid-cols-1 sm:grid-cols-4 gap-3 pt-3">
          <Skeleton className="h-24 rounded-xl" />
          <Skeleton className="h-24 rounded-xl" />
          <Skeleton className="h-24 rounded-xl" />
          <Skeleton className="h-24 rounded-xl" />
        </div>
      </div>
    )

  if (isError)
    return (
      <div className="rounded-xl border border-warmgray p-6 text-center max-w-sm mx-auto my-6">
        <p className="font-semibold text-xs text-destructive">Unable to load project</p>
        <p className="text-xs text-stonegray mt-1">{(error as Error)?.message || "Please retry."}</p>
      </div>
    )

  if (!project) return null

  const isHeritage = project.domain === "heritage"
  const latestSpec = specs && specs.length > 0 ? specs[0] : null
  const specVersion = latestSpec ? `v${latestSpec.version}` : null
  const entityCount = latestSpec ? countSpecEntities(latestSpec.payload_json) : 0
  const assetCount = assets?.length ?? 0
  const isStreamReady = project.status === "published" || project.status === "scene_ready"

  return (
    <div className="space-y-5">
      {/* Top Project Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-3 border-b border-border">
        <div>
          <div className="flex items-center gap-2 text-[10px] font-mono uppercase tracking-widest text-stonegray mb-1.5 font-medium">
            <span>PROJECT #{projectId}</span>
            <span>&bull;</span>
            <span>{displayDate || project.created_at.slice(0, 10)}</span>
          </div>

          <div className="flex items-center gap-3 flex-wrap">
            <h1 className="text-2xl sm:text-3xl font-bold tracking-tight text-foreground">
              {project.name}
            </h1>

            {/* Prominent Domain & Status Badges */}
            <div className="flex items-center gap-1.5">
              <Badge
                variant={isHeritage ? "sage" : "terracotta"}
                className="text-[10px] font-mono uppercase tracking-wider px-2.5 py-0.5 font-semibold shadow-sm"
              >
                {isHeritage ? "Heritage Site" : "Real Estate"}
              </Badge>

              <Badge
                variant={statusVariant[project.status] ?? "outline"}
                className="text-[10px] font-mono capitalize px-2 py-0.5"
              >
                {project.status.replace("_", " ")}
              </Badge>
            </div>
          </div>
        </div>

        <div className="flex items-center gap-2">
          {isStreamReady && (
            <Link href={routes.stream(projectId)}>
              <Button variant="outline" size="sm" className="gap-1.5 text-xs h-8">
                <Glasses className="h-3.5 w-3.5 text-stonegray" />
                <span>VR Stream</span>
              </Button>
            </Link>
          )}

          <Link href={routes.builder(projectId)}>
            <Button variant="terracotta" size="sm" className="gap-1.5 text-xs font-medium h-8 shadow-sm">
              <Sparkles className="h-3.5 w-3.5" />
              <span>Launch Builder →</span>
            </Button>
          </Link>
        </div>
      </div>

      {/* Navigation Subtabs */}
      <nav className="flex gap-1 border-b border-border overflow-x-auto" aria-label="Project sections">
        {tabs.map((tab) => {
          const href = tab.href(projectId)
          const isActive = isActivePath(pathname, href, { exact: tab.exact })
          const IconComponent = tab.icon
          return (
            <Link
              key={tab.label}
              href={href}
              aria-current={isActive ? "page" : undefined}
              className={`px-3 py-2 text-xs font-medium transition-colors flex items-center gap-1.5 border-b-2 whitespace-nowrap ${
                isActive
                  ? "border-terracotta text-foreground font-semibold"
                  : "border-transparent text-stonegray hover:text-foreground hover:bg-muted/40"
              }`}
            >
              <IconComponent className={`h-3.5 w-3.5 ${isActive ? "text-terracotta" : "text-stonegray"}`} />
              <span>{tab.label}</span>
            </Link>
          )
        })}
      </nav>

      {/* 6-Stage Pipeline Stepper */}
      <PipelineStepper currentStage={pipelineStage} status={project.status} />

      {/* Main Interactive Overview Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-5 items-start">
        {/* Left 8 Cols: Interactive 3D Simulation Viewport */}
        <div className="lg:col-span-8 space-y-3">
          <SceneViewportPreview
            title={project.name}
            domain={project.domain}
            height="h-96 sm:h-[400px]"
          />

          <div className="flex items-center justify-between p-3 rounded-xl border border-border bg-card text-xs text-stonegray">
            <div className="flex items-center gap-2">
              <span className="h-2 w-2 rounded-full bg-sage animate-pulse" />
              <span className="font-medium text-foreground">Interactive Simulation Viewport</span>
            </div>
            <div className="flex items-center gap-3 font-mono text-[11px]">
              <span>ENTITIES: <strong className="text-foreground">{entityCount}</strong></span>
              <span>ASSETS: <strong className="text-foreground">{assetCount}</strong></span>
            </div>
          </div>
        </div>

        {/* Right 4 Cols: Technical Simulation Telemetry & Direct Actions */}
        <div className="lg:col-span-4 space-y-3">
          {/* Spec State */}
          <div className="p-3.5 rounded-xl border border-border bg-card shadow-sm space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-[10px] font-mono uppercase text-stonegray">SPECIFICATION</span>
              <FileCode2 className="h-3.5 w-3.5 text-stonegray" />
            </div>
            <div className="text-sm font-bold text-foreground">
              {specsLoading ? "Checking…" : latestSpec ? `Specification ${specVersion}` : "Pending Generation"}
            </div>
            <div className="flex items-center justify-between text-xs pt-1 border-t border-border/80">
              <span className="text-stonegray">{entityCount} Entities</span>
              <Link href={latestSpec ? routes.specs(projectId) : routes.builder(projectId)}>
                <span className="text-xs text-terracotta font-semibold hover:underline">
                  {latestSpec ? "Inspect Spec →" : "Generate in Builder →"}
                </span>
              </Link>
            </div>
          </div>

          {/* Scene State */}
          <div className="p-3.5 rounded-xl border border-border bg-card shadow-sm space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-[10px] font-mono uppercase text-stonegray">SCENE GRAPH</span>
              <Layers className="h-3.5 w-3.5 text-stonegray" />
            </div>
            <div className="text-sm font-bold text-foreground">
              {isStreamReady ? "Geometry & Lighting Compiled" : "Scene Graph Not Built"}
            </div>
            <div className="flex items-center justify-between text-xs pt-1 border-t border-border/80">
              <span className="text-stonegray">80k Tri Budget</span>
              <Link href={routes.builder(projectId)}>
                <span className="text-xs text-terracotta font-semibold hover:underline">
                  Open Builder →
                </span>
              </Link>
            </div>
          </div>

          {/* Asset State */}
          <div className="p-3.5 rounded-xl border border-border bg-card shadow-sm space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-[10px] font-mono uppercase text-stonegray">STORAGE ASSETS</span>
              <Package className="h-3.5 w-3.5 text-stonegray" />
            </div>
            <div className="text-sm font-bold text-foreground">
              {assetsLoading ? "Loading…" : `${assetCount} MinIO Assets`}
            </div>
            <div className="flex items-center justify-between text-xs pt-1 border-t border-border/80">
              <span className="text-stonegray">GLB &amp; Textures</span>
              <Link href={routes.assets(projectId)}>
                <span className="text-xs text-terracotta font-semibold hover:underline">
                  Manage Assets →
                </span>
              </Link>
            </div>
          </div>

          {/* Stream State */}
          <div className="p-3.5 rounded-xl border border-border bg-card shadow-sm space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-[10px] font-mono uppercase text-stonegray">VR STREAM</span>
              <Radio className="h-3.5 w-3.5 text-stonegray" />
            </div>
            <div className="text-sm font-bold text-foreground">
              {isStreamReady ? "Stereoscopic Rig Active" : "Stream Offline"}
            </div>
            <div className="flex items-center justify-between text-xs pt-1 border-t border-border/80">
              <span className="text-stonegray">WebRTC LAN</span>
              <Link href={isStreamReady ? routes.stream(projectId) : routes.builder(projectId)}>
                <span className="text-xs text-terracotta font-semibold hover:underline">
                  {isStreamReady ? "Launch Stream →" : "Build Simulation →"}
                </span>
              </Link>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
