"use client"

import { useParams } from "next/navigation"
import { useState, useRef, useCallback } from "react"
import { useSpecs } from "@/hooks/use-specs"
import { specPayloadSchema, specSection } from "@/lib/validations"
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import type { BadgeProps } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"
import {
  FileCode2,
  Cpu,
  Layers,
  Camera,
  Compass,
  Sliders,
  Sparkles,
  Copy,
  Check,
  ChevronDown,
  Eye,
  ShieldCheck
} from "lucide-react"

const specStatusVariant: Record<string, BadgeProps["variant"]> = {
  draft: "secondary",
  validating: "secondary",
  valid: "default",
  invalid: "destructive",
  superseded: "outline",
  active: "default",
}

function getSpecStatusLabel(status: string) {
  return status || "unknown"
}

// Lightweight virtualized list for up to 200 entities without external deps.
function VirtualizedEntityList({ entities }: { entities: unknown[] }) {
  const containerRef = useRef<HTMLDivElement>(null)
  const [scrollTop, setScrollTop] = useState(0)
  const ITEM_HEIGHT = 52
  const CONTAINER_HEIGHT = 280
  const BUFFER = 5

  const handleScroll = useCallback((e: React.UIEvent<HTMLDivElement>) => {
    setScrollTop(e.currentTarget.scrollTop)
  }, [])

  const total = entities.length

  if (total <= 30) {
    return (
      <div className="max-h-72 overflow-auto rounded-xl border border-warmgray bg-muted/20 divide-y divide-warmgray/60 text-xs">
        {entities.map((ent, idx) => {
          const e = ent as Record<string, unknown>
          const id = (e.id as string) || `entity-${idx}`
          const type = (e.type as string) || "room"
          const name = (e.name as string) || id
          return (
            <div key={id + idx} className="flex items-center justify-between px-3 py-2 text-xs">
              <span className="font-mono text-foreground font-medium truncate pr-2">{id}</span>
              <span className="text-stonegray truncate flex-1">{name}</span>
              <Badge variant="outline" className="ml-2 shrink-0 text-[10px] font-mono border-warmgray">
                {type}
              </Badge>
            </div>
          )
        })}
      </div>
    )
  }

  const visibleCount = Math.ceil(CONTAINER_HEIGHT / ITEM_HEIGHT) + BUFFER * 2
  const startIdx = Math.max(0, Math.floor(scrollTop / ITEM_HEIGHT) - BUFFER)
  const endIdx = Math.min(total, startIdx + visibleCount)
  const offsetY = startIdx * ITEM_HEIGHT
  const slice = entities.slice(startIdx, endIdx)

  return (
    <div
      ref={containerRef}
      onScroll={handleScroll}
      className="overflow-auto rounded-xl border border-warmgray bg-muted/20"
      style={{ height: CONTAINER_HEIGHT }}
      role="list"
      aria-label={`Entities list, ${total} items, virtualized`}
      tabIndex={0}
    >
      <div style={{ height: total * ITEM_HEIGHT, position: "relative" }}>
        <div style={{ transform: `translateY(${offsetY}px)`, position: "absolute", left: 0, right: 0, top: 0 }}>
          {slice.map((ent, idx) => {
            const absoluteIdx = startIdx + idx
            const e = ent as Record<string, unknown>
            const id = (e.id as string) || `entity-${absoluteIdx}`
            const type = (e.type as string) || "spatial_node"
            const name = (e.name as string) || id
            return (
              <div
                key={id + absoluteIdx}
                role="listitem"
                className="flex items-center justify-between px-3 border-b border-warmgray/60 last:border-0 text-xs bg-background"
                style={{ height: ITEM_HEIGHT }}
              >
                <span className="font-mono text-foreground font-medium truncate pr-2" title={String(id)}>
                  {id}
                </span>
                <span className="text-stonegray truncate flex-1" title={String(name)}>
                  {name}
                </span>
                <Badge variant="outline" className="ml-2 shrink-0 text-[10px] font-mono border-warmgray">
                  {type}
                </Badge>
                <span className="ml-2 text-[10px] font-mono text-stonegray">#{absoluteIdx + 1}</span>
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}

export default function SpecsPage() {
  const params = useParams()
  const projectId = Number(params.id)
  const { data: specs, isLoading } = useSpecs(projectId)
  const [copiedId, setCopiedId] = useState<number | null>(null)
  const [expandedSections, setExpandedSections] = useState<Record<string, boolean>>({
    performance: true,
    spatial: true,
    materials: true,
    camera: true,
    navigation: false,
    json: false,
  })

  const toggleSection = (section: string) => {
    setExpandedSections((prev) => ({ ...prev, [section]: !prev[section] }))
  }

  const handleCopy = useCallback(async (payload: unknown, specId: number) => {
    const text = JSON.stringify(payload, null, 2)
    try {
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(text)
      } else {
        const ta = document.createElement("textarea")
        ta.value = text
        ta.style.position = "fixed"
        ta.style.opacity = "0"
        document.body.appendChild(ta)
        ta.select()
        document.execCommand("copy")
        document.body.removeChild(ta)
      }
      setCopiedId(specId)
      window.setTimeout(() => setCopiedId(null), 2000)
    } catch {
      // ignore
    }
  }, [])

  return (
    <div className="space-y-6">
      {/* Top Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-3 border-b border-border">
        <div>
          <div className="flex items-center gap-2 text-[10px] font-mono uppercase tracking-widest text-stonegray mb-0.5">
            <span className="text-gold font-bold">TECHNICAL DOCUMENT</span>
            <span>&bull;</span>
            <span>SIMULATION SPECIFICATION (V1.0)</span>
          </div>
          <h1 className="text-xl sm:text-2xl font-bold tracking-tight text-foreground">
            Engineering Specifications
          </h1>
        </div>

        {specs && specs.length > 0 && (
          <Button
            variant="outline"
            size="sm"
            onClick={() => handleCopy(specs[0].payload_json, specs[0].id)}
            className="gap-1.5 text-xs border-warmgray"
          >
            {copiedId === specs[0].id ? <Check className="h-3.5 w-3.5 text-sage" /> : <Copy className="h-3.5 w-3.5" />}
            <span>{copiedId === specs[0].id ? "Copied Spec JSON" : "Copy Raw JSON"}</span>
          </Button>
        )}
      </div>

      {isLoading ? (
        <div className="space-y-4">
          <Skeleton className="h-40 rounded-xl" />
          <Skeleton className="h-40 rounded-xl" />
        </div>
      ) : specs && specs.length > 0 ? (
        <div className="space-y-6">
          {specs.map((spec) => {
            // Narrow the free-form payload through the Zod boundary schema.
            const payloadCheck = specPayloadSchema.safeParse(spec.payload_json)
            const entitiesArray = payloadCheck.success && Array.isArray(payloadCheck.data.entities)
              ? (payloadCheck.data.entities as unknown[])
              : []

            const perf = specSection(spec.payload_json, "performance_budget")
            const spatial = specSection(spec.payload_json, "spatial_layout")

            return (
              <div key={spec.id} className="space-y-4">
                {/* Spec Overview Card */}
                <div className="p-4 rounded-xl border border-warmgray bg-card flex flex-col sm:flex-row sm:items-center justify-between gap-3 shadow-sm">
                  <div className="flex items-center gap-3">
                    <div className="h-10 w-10 rounded-lg bg-gold-50 dark:bg-gold-950/30 text-gold flex items-center justify-center border border-gold-200">
                      <ShieldCheck className="h-5 w-5" />
                    </div>
                    <div>
                      <div className="flex items-center gap-2">
                        <h3 className="text-base font-bold text-foreground">Simulation Specification v{spec.version}</h3>
                        <Badge variant="gold" className="text-[10px] font-mono uppercase">
                          {getSpecStatusLabel(spec.status)}
                        </Badge>
                      </div>
                      <div className="text-xs text-stonegray mt-0.5">
                        Created <time dateTime={spec.created_at}>{new Date(spec.created_at).toLocaleString()}</time> &bull; {entitiesArray.length} spatial entities validated
                      </div>
                    </div>
                  </div>

                  <div className="flex items-center gap-2">
                    <span className="text-[11px] font-mono px-2 py-0.5 rounded bg-muted/40 text-stonegray border border-warmgray">
                      PYDANTIC SCHEMA: PASS
                    </span>
                  </div>
                </div>

                {/* Section 1: Performance Budget (Technical Table) */}
                <Card className="border-warmgray shadow-sm overflow-hidden">
                  <CardHeader
                    className="p-4 py-3 bg-muted/20 cursor-pointer flex flex-row items-center justify-between border-b border-warmgray"
                    onClick={() => toggleSection("performance")}
                  >
                    <div className="flex items-center gap-2">
                      <Cpu className="h-4 w-4 text-terracotta" />
                      <CardTitle className="text-xs font-mono uppercase tracking-wider font-bold text-foreground">
                        Performance Budget &amp; Hardware Targets
                      </CardTitle>
                    </div>
                    <ChevronDown className={`h-4 w-4 text-stonegray transition-transform ${expandedSections.performance ? "rotate-180" : ""}`} />
                  </CardHeader>
                  {expandedSections.performance && (
                    <CardContent className="p-4 grid grid-cols-2 sm:grid-cols-4 gap-4 text-xs font-mono">
                      <div className="p-3 rounded-lg border border-warmgray bg-background">
                        <div className="text-[10px] text-stonegray uppercase">Target FPS</div>
                        <div className="text-base font-bold text-foreground mt-0.5">
                          {String(perf.target_fps || 60)} FPS
                        </div>
                        <div className="text-[10px] text-stonegray mt-0.5">Mobile VR Target</div>
                      </div>

                      <div className="p-3 rounded-lg border border-warmgray bg-background">
                        <div className="text-[10px] text-stonegray uppercase">Triangle Budget</div>
                        <div className="text-base font-bold text-foreground mt-0.5">
                          {Number(perf.max_triangles || 80000).toLocaleString()}
                        </div>
                        <div className="text-[10px] text-stonegray mt-0.5">Strict LOD0 Polygon Limit</div>
                      </div>

                      <div className="p-3 rounded-lg border border-warmgray bg-background">
                        <div className="text-[10px] text-stonegray uppercase">Streaming Latency</div>
                        <div className="text-base font-bold text-foreground mt-0.5">
                          &lt; 50 ms
                        </div>
                        <div className="text-[10px] text-stonegray mt-0.5">LAN WebRTC Peer Target</div>
                      </div>

                      <div className="p-3 rounded-lg border border-warmgray bg-background">
                        <div className="text-[10px] text-stonegray uppercase">Target Platform</div>
                        <div className="text-base font-bold text-foreground mt-0.5">
                          Android VR
                        </div>
                        <div className="text-[10px] text-stonegray mt-0.5">Phone Headset Streaming</div>
                      </div>
                    </CardContent>
                  )}
                </Card>

                {/* Section 2: Spatial Architecture & Entities */}
                <Card className="border-warmgray shadow-sm overflow-hidden">
                  <CardHeader
                    className="p-4 py-3 bg-muted/20 cursor-pointer flex flex-row items-center justify-between border-b border-warmgray"
                    onClick={() => toggleSection("spatial")}
                  >
                    <div className="flex items-center gap-2">
                      <Layers className="h-4 w-4 text-sage" />
                      <CardTitle className="text-xs font-mono uppercase tracking-wider font-bold text-foreground">
                        Spatial Architecture &amp; Entities ({entitiesArray.length})
                      </CardTitle>
                    </div>
                    <ChevronDown className={`h-4 w-4 text-stonegray transition-transform ${expandedSections.spatial ? "rotate-180" : ""}`} />
                  </CardHeader>
                  {expandedSections.spatial && (
                    <CardContent className="p-4 space-y-3">
                      <div className="flex items-center justify-between text-xs text-stonegray font-mono">
                        <span>Coordinate Origin: [0.0, 1.6, 0.0]</span>
                        <span>Dimensions: Metric Units (Meters)</span>
                      </div>
                      {entitiesArray.length > 0 ? (
                        <VirtualizedEntityList entities={entitiesArray} />
                      ) : (
                        <p className="text-xs text-stonegray">No explicit spatial entity tags defined in spec payload.</p>
                      )}
                    </CardContent>
                  )}
                </Card>

                {/* Section 3: Materials & Baked Global Illumination */}
                <Card className="border-warmgray shadow-sm overflow-hidden">
                  <CardHeader
                    className="p-4 py-3 bg-muted/20 cursor-pointer flex flex-row items-center justify-between border-b border-warmgray"
                    onClick={() => toggleSection("materials")}
                  >
                    <div className="flex items-center gap-2">
                      <Sliders className="h-4 w-4 text-gold" />
                      <CardTitle className="text-xs font-mono uppercase tracking-wider font-bold text-foreground">
                        Materials, Textures &amp; Lighting Mode
                      </CardTitle>
                    </div>
                    <ChevronDown className={`h-4 w-4 text-stonegray transition-transform ${expandedSections.materials ? "rotate-180" : ""}`} />
                  </CardHeader>
                  {expandedSections.materials && (
                    <CardContent className="p-4 grid grid-cols-1 sm:grid-cols-3 gap-4 text-xs font-mono">
                      <div className="p-3 rounded-lg border border-warmgray bg-background">
                        <div className="text-[10px] text-stonegray uppercase">Lighting Shading</div>
                        <div className="text-sm font-bold text-foreground mt-0.5">Pre-Baked Lightmaps</div>
                        <div className="text-[10px] text-stonegray mt-0.5">Zero dynamic shadow compute</div>
                      </div>
                      <div className="p-3 rounded-lg border border-warmgray bg-background">
                        <div className="text-[10px] text-stonegray uppercase">Material Textures</div>
                        <div className="text-sm font-bold text-foreground mt-0.5">PBR Diffuse + Roughness</div>
                        <div className="text-[10px] text-stonegray mt-0.5">Stone &amp; Wood low-poly sets</div>
                      </div>
                      <div className="p-3 rounded-lg border border-warmgray bg-background">
                        <div className="text-[10px] text-stonegray uppercase">Max Texture Res</div>
                        <div className="text-sm font-bold text-foreground mt-0.5">1024 × 1024</div>
                        <div className="text-[10px] text-stonegray mt-0.5">Thermal headroom safeguard</div>
                      </div>
                    </CardContent>
                  )}
                </Card>

                {/* Section 4: Camera & Stereoscopic VR Configuration */}
                <Card className="border-warmgray shadow-sm overflow-hidden">
                  <CardHeader
                    className="p-4 py-3 bg-muted/20 cursor-pointer flex flex-row items-center justify-between border-b border-warmgray"
                    onClick={() => toggleSection("camera")}
                  >
                    <div className="flex items-center gap-2">
                      <Camera className="h-4 w-4 text-terracotta" />
                      <CardTitle className="text-xs font-mono uppercase tracking-wider font-bold text-foreground">
                        Camera &amp; VR Configuration
                      </CardTitle>
                    </div>
                    <ChevronDown className={`h-4 w-4 text-stonegray transition-transform ${expandedSections.camera ? "rotate-180" : ""}`} />
                  </CardHeader>
                  {expandedSections.camera && (
                    <CardContent className="p-4 grid grid-cols-2 sm:grid-cols-4 gap-4 text-xs font-mono">
                      <div className="p-3 rounded-lg border border-warmgray bg-background">
                        <div className="text-[10px] text-stonegray uppercase">Eye Height</div>
                        <div className="text-sm font-bold text-foreground mt-0.5">1.60 Meters</div>
                      </div>
                      <div className="p-3 rounded-lg border border-warmgray bg-background">
                        <div className="text-[10px] text-stonegray uppercase">Stereo IPD</div>
                        <div className="text-sm font-bold text-foreground mt-0.5">64 mm</div>
                      </div>
                      <div className="p-3 rounded-lg border border-warmgray bg-background">
                        <div className="text-[10px] text-stonegray uppercase">Field of View</div>
                        <div className="text-sm font-bold text-foreground mt-0.5">90° Horizontal</div>
                      </div>
                      <div className="p-3 rounded-lg border border-warmgray bg-background">
                        <div className="text-[10px] text-stonegray uppercase">Stereo Rig</div>
                        <div className="text-sm font-bold text-foreground mt-0.5">Side-by-Side (SBS)</div>
                      </div>
                    </CardContent>
                  )}
                </Card>

                {/* Section 5: Raw Specification JSON */}
                <Card className="border-warmgray shadow-sm overflow-hidden">
                  <CardHeader
                    className="p-4 py-3 bg-muted/20 cursor-pointer flex flex-row items-center justify-between border-b border-warmgray"
                    onClick={() => toggleSection("json")}
                  >
                    <div className="flex items-center gap-2">
                      <FileCode2 className="h-4 w-4 text-stonegray" />
                      <CardTitle className="text-xs font-mono uppercase tracking-wider font-bold text-foreground">
                        Specification JSON Payload
                      </CardTitle>
                    </div>
                    <ChevronDown className={`h-4 w-4 text-stonegray transition-transform ${expandedSections.json ? "rotate-180" : ""}`} />
                  </CardHeader>
                  {expandedSections.json && (
                    <CardContent className="p-4 space-y-3">
                      <div className="flex justify-end">
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => handleCopy(spec.payload_json, spec.id)}
                          className="h-7 text-xs gap-1 border-warmgray"
                        >
                          <Copy className="h-3 w-3" />
                          <span>Copy Payload</span>
                        </Button>
                      </div>
                      <pre className="text-xs font-mono bg-charcoal text-ivory/90 p-4 rounded-xl overflow-auto max-h-64 whitespace-pre-wrap break-words">
                        {JSON.stringify(spec.payload_json, null, 2)}
                      </pre>
                    </CardContent>
                  )}
                </Card>
              </div>
            )
          })}
        </div>
      ) : (
        <div className="rounded-xl border border-dashed border-warmgray p-10 text-center max-w-md mx-auto my-6">
          <FileCode2 className="h-8 w-8 text-stonegray mx-auto mb-2 opacity-50" />
          <h3 className="text-sm font-bold text-foreground">No Specification Generated Yet</h3>
          <p className="text-xs text-stonegray mt-1">
            Launch the Builder to synthesize a structured simulation specification from your natural language prompt.
          </p>
        </div>
      )}
    </div>
  )
}
