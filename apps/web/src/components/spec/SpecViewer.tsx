"use client"

import { useState } from "react"
import { ChevronDown, ChevronRight, FolderOpen, FileText, Lightbulb, Navigation, Cpu, Bot, Settings, Edit, Pencil } from "lucide-react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Separator } from "@/components/ui/separator"
import { EntityEditor } from "@/components/spec/EntityEditor"

interface SpecViewerProps {
  spec: Record<string, any> | null
  onRegenerate?: () => void
  onBackToClarify?: () => void
  projectId?: number
  specId?: number
}

const SECTION_CONFIG: Record<string, { icon: any; label: string; description: string }> = {
  metadata: { icon: FileText, label: "Metadata", description: "Title, description, version, tags" },
  entities: { icon: FolderOpen, label: "Entities", description: "Rooms, furniture, lights, POIs" },
  navigation: { icon: Navigation, label: "Navigation", description: "Points, paths, start position" },
  lighting: { icon: Lightbulb, label: "Lighting", description: "Preset, time of day, custom lights" },
  copilot_policy: { icon: Bot, label: "Copilot Policy", description: "Languages, personality, actions" },
  performance_budget: { icon: Cpu, label: "Performance Budget", description: "FPS, triangles, draw calls, textures" },
}

function formatValue(val: any, indent = 0): React.ReactNode {
  if (val === null) return <span className="text-muted-foreground">null</span>
  if (val === undefined) return <span className="text-muted-foreground">undefined</span>
  if (Array.isArray(val)) {
    if (val.length === 0) return "[]"
    if (val.every(v => typeof v === "number" || typeof v === "string" || typeof v === "boolean")) {
      return `[${val.map(v => typeof v === "string" ? `"${v}"` : String(v)).join(", ")}]`
    }
    return (
      <div className="ml-4 space-y-1">
        {val.map((v, i) => (
          <div key={i} className="flex gap-2">
            <span className="text-muted-foreground">[{i}]</span>
            {formatValue(v, indent + 1)}
          </div>
        ))}
      </div>
    )
  }
  if (typeof val === "object") {
    const keys = Object.keys(val)
    if (keys.length === 0) return "{}"
    return (
      <div className="ml-4 space-y-1">
        {keys.map(k => (
          <div key={k} className="flex gap-2">
            <span className="font-mono text-sm">{k}:</span>
            {formatValue(val[k], indent + 1)}
          </div>
        ))}
      </div>
    )
  }
  if (typeof val === "string") return <span className="text-green-600">"{val}"</span>
  if (typeof val === "number") return <span className="text-blue-600">{val}</span>
  if (typeof val === "boolean") return <span className="text-purple-600">{val ? "true" : "false"}</span>
  return String(val)
}

function EntityRow({ entity, onEdit }: { entity: Record<string, any>; onEdit?: (e: Record<string, any>) => void }) {
  const typeColors: Record<string, string> = {
    room: "bg-blue-100 text-blue-700",
    wall: "bg-gray-100 text-gray-700",
    floor: "bg-amber-100 text-amber-700",
    ceiling: "bg-slate-100 text-slate-700",
    door: "bg-orange-100 text-orange-700",
    window: "bg-cyan-100 text-cyan-700",
    furniture: "bg-green-100 text-green-700",
    decoration: "bg-pink-100 text-pink-700",
    light: "bg-yellow-100 text-yellow-700",
    navigation_point: "bg-indigo-100 text-indigo-700",
    poi: "bg-violet-100 text-violet-700",
    audio_zone: "bg-rose-100 text-rose-700",
    trigger_zone: "bg-lime-100 text-lime-700",
  }
  const typeBadge = typeColors[entity.type] || "bg-gray-100 text-gray-700"
  const pos = entity.position || [0, 0, 0]
  const size = entity.properties?.size ? ` ${entity.properties.size.join("×")}` : ""
  return (
    <tr className="border-t hover:bg-muted/50">
      <td className="px-3 py-2 font-mono text-sm">{entity.id}</td>
      <td className="px-3 py-2"><Badge className={typeBadge} variant="secondary">{entity.type}</Badge></td>
      <td className="px-3 py-2">{entity.name}</td>
      <td className="px-3 py-2 font-mono text-xs">[{pos[0]}, {pos[1]}, {pos[2]}]</td>
      <td className="px-3 py-2 text-xs text-muted-foreground">{size}</td>
      <td className="px-3 py-2 text-xs text-muted-foreground max-w-xs truncate">{JSON.stringify(entity.properties || {})}</td>
      <td className="px-3 py-2">
        {onEdit && (
          <Button variant="ghost" size="icon" onClick={() => onEdit(entity)} title="Edit entity">
            <Pencil className="h-4 w-4" />
          </Button>
        )}
      </td>
    </tr>
  )
}

function CollapsibleSection({ 
  title, 
  icon: Icon, 
  description, 
  children, 
  defaultOpen = false 
}: { 
  title: string
  icon: React.ComponentType<{ className?: string }>
  description: string
  children: React.ReactNode
  defaultOpen?: boolean
}) {
  const [open, setOpen] = useState(defaultOpen)
  return (
    <Card className="border">
      <CardHeader className="pb-2" onClick={() => setOpen(!open)} style={{ cursor: "pointer" }}>
        <div className="flex items-center gap-3">
          <Icon className="h-5 w-5 text-muted-foreground" />
          <div className="flex-1">
            <CardTitle className="text-base font-medium">{title}</CardTitle>
            <p className="text-xs text-muted-foreground">{description}</p>
          </div>
          <span className="text-muted-foreground">{open ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}</span>
        </div>
      </CardHeader>
      {open && <CardContent className="pt-0">{children}</CardContent>}
    </Card>
  )
}

export function SpecViewer({ spec, onRegenerate, onBackToClarify, projectId, specId }: SpecViewerProps) {
  const [editingEntity, setEditingEntity] = useState<Record<string, any> | null>(null)

  if (!spec) {
    return (
      <Card>
        <CardContent className="py-8 text-center text-muted-foreground">
          No specification available. Generate a spec first.
        </CardContent>
      </Card>
    )
  }

  const domain = spec.domain || "real_estate"
  const metadata = spec.metadata || {}
  const entities = spec.entities || []
  const navigation = spec.navigation || {}
  const lighting = spec.lighting || {}
  const copilot = spec.copilot_policy || {}
  const performance = spec.performance_budget || {}

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="font-semibold text-lg">{metadata.title || "Untitled Specification"}</h3>
          <p className="text-sm text-muted-foreground">
            Domain: <span className="capitalize">{domain}</span> | Version: {metadata.version || "1.0.0"}
          </p>
        </div>
        <div className="flex gap-2">
          {onBackToClarify && (
            <Button variant="outline" size="sm" onClick={onBackToClarify}>
              Back to Clarify
            </Button>
          )}
          {onRegenerate && (
            <Button variant="default" size="sm" onClick={onRegenerate}>
              Regenerate
            </Button>
          )}
        </div>
      </div>

      <Separator />

      <div className="space-y-3">
        <CollapsibleSection
          icon={FileText}
          title="Metadata"
          description="Title, description, version, tags"
          defaultOpen={true}
        >
          <div className="space-y-2 font-mono text-sm">
            <div className="flex gap-2"><span className="text-muted-foreground">title:</span> <span className="text-green-600">"{metadata.title}"</span></div>
            <div className="flex gap-2"><span className="text-muted-foreground">description:</span> <span className="text-green-600">"{metadata.description}"</span></div>
            <div className="flex gap-2"><span className="text-muted-foreground">version:</span> <span className="text-blue-600">{metadata.version}</span></div>
            <div className="flex gap-2"><span className="text-muted-foreground">author:</span> <span>{metadata.author || "—"}</span></div>
            <div className="flex gap-2"><span className="text-muted-foreground">tags:</span> <span>{(metadata.tags || []).join(", ") || "—"}</span></div>
            <div className="flex gap-2"><span className="text-muted-foreground">created_at:</span> <span>{metadata.created_at ? new Date(metadata.created_at).toLocaleString() : "—"}</span></div>
          </div>
        </CollapsibleSection>

        <CollapsibleSection
          icon={FolderOpen}
          title={`Entities (${entities.length})`}
          description="Rooms, furniture, lights, POIs"
          defaultOpen={true}
        >
          {entities.length > 0 ? (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-muted-foreground border-b">
                    <th className="px-3 py-2">ID</th>
                    <th className="px-3 py-2">Type</th>
                    <th className="px-3 py-2">Name</th>
                    <th className="px-3 py-2">Position</th>
                    <th className="px-3 py-2">Size</th>
                    <th className="px-3 py-2">Properties</th>
                    <th className="px-3 py-2"></th>
                  </tr>
                </thead>
                <tbody>
                  {entities.map((e: any, i: number) => <EntityRow key={e.id || i} entity={e} onEdit={setEditingEntity} />)}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">No entities defined</p>
          )}
        </CollapsibleSection>

        <CollapsibleSection
          icon={Navigation}
          title="Navigation"
          description="Points, paths, start position"
        >
          <div className="space-y-4">
            <div>
              <h4 className="font-medium text-sm mb-2">Points ({navigation.points?.length || 0})</h4>
              {navigation.points?.length > 0 ? (
                <div className="space-y-1">
                  {navigation.points.map((p: any, i: number) => (
                    <div key={p.id || i} className="flex items-center gap-3 text-sm p-2 bg-muted/50 rounded">
                      <Badge variant="secondary" className="font-mono">{p.id}</Badge>
                      <span>{p.name}</span>
                      <span className="text-muted-foreground font-mono text-xs">[{p.position?.join(", ")}]</span>
                      <span className="text-xs text-muted-foreground">→ {p.connections?.join(", ") || "none"}</span>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-sm text-muted-foreground">No navigation points</p>
              )}
            </div>
            <div>
              <h4 className="font-medium text-sm mb-2">Paths ({navigation.paths?.length || 0})</h4>
              {navigation.paths?.length > 0 ? (
                <div className="space-y-1">
                  {navigation.paths.map((path: any, i: number) => (
                    <div key={i} className="flex items-center gap-3 text-sm p-2 bg-muted/50 rounded">
                      <span className="font-mono">{path.from || path.from_point}</span>
                      <span className="text-muted-foreground">→</span>
                      <span className="font-mono">{path.to || path.to_point}</span>
                      <Badge variant="outline" className="text-xs">{path.type || "walk"}</Badge>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-sm text-muted-foreground">No navigation paths</p>
              )}
            </div>
            <div className="text-sm">
              <span className="text-muted-foreground">Default start: </span>
              <span className="font-mono">{navigation.default_start_point || "—"}</span>
            </div>
          </div>
        </CollapsibleSection>

        <CollapsibleSection
          icon={Lightbulb}
          title="Lighting"
          description="Preset, time of day, custom lights"
        >
          <div className="space-y-2 font-mono text-sm">
            <div className="flex gap-2"><span className="text-muted-foreground">preset:</span> <Badge variant="secondary">{lighting.preset}</Badge></div>
            <div className="flex gap-2"><span className="text-muted-foreground">time_of_day:</span> <Badge variant="secondary">{lighting.time_of_day}</Badge></div>
            <div className="flex gap-2"><span className="text-muted-foreground">ambient_intensity:</span> <span className="text-blue-600">{lighting.ambient_intensity}</span></div>
            {lighting.sun_direction && (
              <div className="flex gap-2"><span className="text-muted-foreground">sun_direction:</span> <span>[{lighting.sun_direction.join(", ")}]</span></div>
            )}
            {lighting.custom_lights?.length > 0 && (
              <div>
                <div className="flex gap-2"><span className="text-muted-foreground">custom_lights:</span> <Badge>{lighting.custom_lights.length}</Badge></div>
                <div className="ml-4 space-y-1">
                  {lighting.custom_lights.map((l: any, i: number) => (
                    <div key={i} className="text-xs">
                      {l.type} @ [{l.position?.join(", ")}] {l.color ? `rgb(${l.color.join(",")})` : ""} intensity={l.intensity}
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </CollapsibleSection>

        <CollapsibleSection
          icon={Bot}
          title="Copilot Policy"
          description="Languages, personality, actions"
        >
          <div className="space-y-2 font-mono text-sm">
            <div className="flex gap-2"><span className="text-muted-foreground">enabled:</span> <span className={copilot.enabled ? "text-green-600" : "text-red-600"}>{copilot.enabled ? "true" : "false"}</span></div>
            <div className="flex gap-2"><span className="text-muted-foreground">languages:</span> <span>{(copilot.languages || []).join(", ")}</span></div>
            <div className="flex gap-2"><span className="text-muted-foreground">default_language:</span> <span>{copilot.default_language}</span></div>
            <div className="flex gap-2"><span className="text-muted-foreground">personality:</span> <Badge variant="secondary">{copilot.personality}</Badge></div>
            <div className="flex gap-2"><span className="text-muted-foreground">allowed_actions:</span> <Badge>{(copilot.allowed_actions || []).length}</Badge></div>
            {copilot.knowledge_base && <div className="flex gap-2"><span className="text-muted-foreground">knowledge_base:</span> <span>{copilot.knowledge_base}</span></div>}
          </div>
        </CollapsibleSection>

        <CollapsibleSection
          icon={Cpu}
          title="Performance Budget"
          description="FPS, triangles, draw calls, textures"
        >
          <div className="grid grid-cols-2 md:grid-cols-3 gap-3 text-sm">
            <div className="p-3 bg-muted/50 rounded">
              <div className="text-muted-foreground text-xs">Target FPS</div>
              <div className="font-mono text-lg">{performance.target_fps}</div>
            </div>
            <div className="p-3 bg-muted/50 rounded">
              <div className="text-muted-foreground text-xs">Max Triangles</div>
              <div className="font-mono text-lg">{performance.max_triangles?.toLocaleString()}</div>
            </div>
            <div className="p-3 bg-muted/50 rounded">
              <div className="text-muted-foreground text-xs">Max Draw Calls</div>
              <div className="font-mono text-lg">{performance.max_draw_calls}</div>
            </div>
            <div className="p-3 bg-muted/50 rounded">
              <div className="text-muted-foreground text-xs">Texture Budget (MB)</div>
              <div className="font-mono text-lg">{performance.texture_budget_mb}</div>
            </div>
            <div className="p-3 bg-muted/50 rounded">
              <div className="text-muted-foreground text-xs">Max Entities</div>
              <div className="font-mono text-lg">{performance.max_entities}</div>
            </div>
            <div className="p-3 bg-muted/50 rounded">
              <div className="text-muted-foreground text-xs">LOD Distances</div>
              <div className="font-mono text-lg">[{performance.lod_distances?.join(", ")}]</div>
            </div>
          </div>
        </CollapsibleSection>
      </div>

      {editingEntity && projectId && specId && (
        <EntityEditor
          projectId={projectId}
          specId={specId}
          entity={editingEntity}
          onClose={() => setEditingEntity(null)}
          onSave={() => setEditingEntity(null)}
        />
      )}
    </div>
  )
}