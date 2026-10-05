"use client"

import { useState, useMemo, useId } from "react"
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

const MAX_FORMAT_DEPTH = 6
const MAX_KEYS_DISPLAY = 50
const MAX_ARRAY_DISPLAY = 50
const MAX_STRINGIFY_LENGTH = 300

function safeTruncate(str: string, max = MAX_STRINGIFY_LENGTH): string {
  if (str.length <= max) return str
  return str.slice(0, max) + "… (+ " + (str.length - max) + " chars)"
}

function formatValue(val: any, indent = 0): React.ReactNode {
  if (indent > MAX_FORMAT_DEPTH) {
    return <span className="text-muted-foreground italic">… depth limit ({MAX_FORMAT_DEPTH})</span>
  }
  if (val === null) return <span className="text-muted-foreground">null</span>
  if (val === undefined) return <span className="text-muted-foreground">undefined</span>
  if (Array.isArray(val)) {
    if (val.length === 0) return <span className="text-muted-foreground">[]</span>
    if (val.length > MAX_ARRAY_DISPLAY) {
      const sliced = val.slice(0, MAX_ARRAY_DISPLAY)
      const remaining = val.length - MAX_ARRAY_DISPLAY
      if (val.every(v => typeof v === "number" || typeof v === "string" || typeof v === "boolean")) {
        return (
          <span>
            [{sliced.map(v => typeof v === "string" ? `"${v}"` : String(v)).join(", ")}]
            <span className="text-muted-foreground"> + {remaining} more</span>
          </span>
        )
      }
      return (
        <div className="ml-4 space-y-1">
          {sliced.map((v, i) => (
            <div key={`arr-${indent}-${i}`} className="flex gap-2">
              <span className="text-muted-foreground">[{i}]</span>
              {formatValue(v, indent + 1)}
            </div>
          ))}
          <div className="text-muted-foreground italic">… +{remaining} more items</div>
        </div>
      )
    }
    if (val.every(v => typeof v === "number" || typeof v === "string" || typeof v === "boolean")) {
      return <span>[{val.map(v => typeof v === "string" ? `"${v}"` : String(v)).join(", ")}]</span>
    }
    return (
      <div className="ml-4 space-y-1">
        {val.map((v, i) => (
          <div key={`arr-${indent}-${i}`} className="flex gap-2">
            <span className="text-muted-foreground">[{i}]</span>
            {formatValue(v, indent + 1)}
          </div>
        ))}
      </div>
    )
  }
  if (typeof val === "object") {
    const keys = Object.keys(val)
    if (keys.length === 0) return <span className="text-muted-foreground">{"{}"}</span>
    const displayKeys = keys.slice(0, MAX_KEYS_DISPLAY)
    const remaining = keys.length - displayKeys.length
    return (
      <div className="ml-4 space-y-1">
        {displayKeys.map(k => (
          <div key={`${k}-${indent}`} className="flex gap-2">
            <span className="font-mono text-sm">{k}:</span>
            {formatValue(val[k], indent + 1)}
          </div>
        ))}
        {remaining > 0 && <div className="text-muted-foreground italic text-xs">… +{remaining} more keys</div>}
      </div>
    )
  }
  if (typeof val === "string") return <span className="text-green-600 break-all">&quot;{val}&quot;</span>
  if (typeof val === "number") return <span className="text-blue-600">{Number.isFinite(val) ? val : String(val)}</span>
  if (typeof val === "boolean") return <span className="text-purple-600">{val ? "true" : "false"}</span>
  return <span className="break-all">{String(val)}</span>
}

// safelist: bg-blue-100 text-blue-700 bg-gray-100 text-gray-700 bg-amber-100 text-amber-700 bg-slate-100 text-slate-700 bg-orange-100 text-orange-700 bg-cyan-100 text-cyan-700 bg-green-100 text-green-700 bg-pink-100 text-pink-700 bg-yellow-100 text-yellow-700 bg-indigo-100 text-indigo-700 bg-violet-100 text-violet-700 bg-rose-100 text-rose-700 bg-lime-100 text-lime-700
const TYPE_BADGE_CLASSES: Record<string, string> = {
  room: "bg-blue-100 text-blue-700 border-blue-200",
  wall: "bg-gray-100 text-gray-700 border-gray-200",
  floor: "bg-amber-100 text-amber-700 border-amber-200",
  ceiling: "bg-slate-100 text-slate-700 border-slate-200",
  door: "bg-orange-100 text-orange-700 border-orange-200",
  window: "bg-cyan-100 text-cyan-700 border-cyan-200",
  furniture: "bg-green-100 text-green-700 border-green-200",
  decoration: "bg-pink-100 text-pink-700 border-pink-200",
  light: "bg-yellow-100 text-yellow-700 border-yellow-200",
  navigation_point: "bg-indigo-100 text-indigo-700 border-indigo-200",
  poi: "bg-violet-100 text-violet-700 border-violet-200",
  audio_zone: "bg-rose-100 text-rose-700 border-rose-200",
  trigger_zone: "bg-lime-100 text-lime-700 border-lime-200",
}

function formatPosition(pos: unknown): string {
  if (!Array.isArray(pos) || pos.length < 3) return "—"
  const [x, y, z] = pos
  const fmt = (n: unknown) => {
    if (typeof n !== "number" || !Number.isFinite(n)) return String(n ?? "—")
    // keep up to 2 decimals, trim trailing zeros
    return Number(n.toFixed(2)).toString()
  }
  return `[${fmt(x)} m, ${fmt(y)} m, ${fmt(z)} m]`
}

function formatPositionShort(pos: unknown): string {
  if (!Array.isArray(pos) || pos.length < 3) return "—"
  const fmt = (n: unknown) => {
    if (typeof n !== "number" || !Number.isFinite(n)) return String(n ?? "?")
    return Number(n.toFixed(2)).toString()
  }
  return `${fmt(pos[0])}, ${fmt(pos[1])}, ${fmt(pos[2])}`
}

function EntityRow({ entity, onEdit }: { entity: Record<string, any>; onEdit?: (e: Record<string, any>) => void }) {
  const typeBadge = TYPE_BADGE_CLASSES[entity.type] || "bg-gray-100 text-gray-700 border-gray-200"
  const size = entity.properties?.size
    ? ` ${Array.isArray(entity.properties.size) ? entity.properties.size.map((n: unknown) => typeof n === "number" ? Number(n.toFixed(2)) : n).join("×") + " m" : String(entity.properties.size)}`
    : ""

  const propertiesPreview = useMemo(() => {
    try {
      const raw = entity.properties || {}
      const str = JSON.stringify(raw)
      return safeTruncate(str, MAX_STRINGIFY_LENGTH)
    } catch {
      return "{… unstringifiable}"
    }
  }, [entity.properties])

  const positionLabel = useMemo(() => formatPositionShort(entity.position), [entity.position])

  return (
    <tr className="border-t hover:bg-muted/50">
      <td className="px-3 py-2 font-mono text-sm">{entity.id ?? "—"}</td>
      <td className="px-3 py-2"><Badge className={typeBadge} variant="secondary">{entity.type ?? "unknown"}</Badge></td>
      <td className="px-3 py-2">{entity.name ?? <span className="text-muted-foreground">—</span>}</td>
      <td className="px-3 py-2 font-mono text-xs" title={formatPosition(entity.position)} aria-label={`Position ${positionLabel} meters`}>
        [{positionLabel}]
      </td>
      <td className="px-3 py-2 text-xs text-muted-foreground">{size || "—"}</td>
      <td className="px-3 py-2 text-xs text-muted-foreground max-w-xs truncate" title={propertiesPreview}>
        {propertiesPreview}
      </td>
      <td className="px-3 py-2">
        {onEdit && (
          <Button
            variant="ghost"
            size="icon"
            type="button"
            onClick={() => onEdit(entity)}
            aria-label={`Edit entity ${entity.name || entity.id}`}
            title={`Edit ${entity.name || entity.id}`}
          >
            <Pencil className="h-4 w-4" aria-hidden="true" />
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
  const id = useId()
  const headerId = `collapsible-header-${id}`
  const contentId = `collapsible-content-${id}`

  const toggle = () => setOpen(v => !v)
  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault()
      toggle()
    }
  }

  return (
    <Card className="border">
      <CardHeader
        id={headerId}
        className="pb-2 cursor-pointer select-none focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 rounded-t-lg"
        role="button"
        tabIndex={0}
        aria-expanded={open}
        aria-controls={contentId}
        onClick={toggle}
        onKeyDown={onKeyDown}
      >
        <div className="flex items-center gap-3">
          <Icon className="h-5 w-5 text-muted-foreground" aria-hidden="true" />
          <div className="flex-1 text-left">
            <CardTitle className="text-base font-medium">{title}</CardTitle>
            <p className="text-xs text-muted-foreground">{description}</p>
          </div>
          <span className="text-muted-foreground" aria-hidden="true">{open ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}</span>
          <span className="sr-only">{open ? "Collapse" : "Expand"} {title}</span>
        </div>
      </CardHeader>
      {open && (
        <CardContent id={contentId} aria-labelledby={headerId} className="pt-0">
          {children}
        </CardContent>
      )}
    </Card>
  )
}

export function SpecViewer({ spec, onRegenerate, onBackToClarify, projectId, specId }: SpecViewerProps) {
  const [editingEntity, setEditingEntity] = useState<Record<string, any> | null>(null)
  const entities: Record<string, any>[] = useMemo(() => (spec && Array.isArray(spec.entities) ? spec.entities : []), [spec])

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
  const navigation = spec.navigation || {}
  const lighting = spec.lighting || {}
  const copilot = spec.copilot_policy || {}
  const performance = spec.performance_budget || {}

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-4">
        <div>
          <h3 className="font-semibold text-lg">{metadata.title || "Untitled Specification"}</h3>
          <p className="text-sm text-muted-foreground">
            Domain: <span className="capitalize">{domain}</span> | Version: {metadata.version || "1.0.0"}
          </p>
        </div>
        <div className="flex gap-2">
          {onBackToClarify && (
            <Button variant="outline" size="sm" type="button" onClick={onBackToClarify}>
              Back to Clarify
            </Button>
          )}
          {onRegenerate && (
            <Button variant="default" size="sm" type="button" onClick={onRegenerate}>
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
            <div className="flex gap-2"><span className="text-muted-foreground">title:</span> <span className="text-green-600 break-all">&quot;{metadata.title ?? "—"}&quot;</span></div>
            <div className="flex gap-2"><span className="text-muted-foreground">description:</span> <span className="text-green-600 break-all">&quot;{metadata.description ?? "—"}&quot;</span></div>
            <div className="flex gap-2"><span className="text-muted-foreground">version:</span> <span className="text-blue-600">{metadata.version ?? "—"}</span></div>
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
                <caption className="sr-only">Entities table with {entities.length} rows</caption>
                <thead>
                  <tr className="text-left text-muted-foreground border-b">
                    <th scope="col" className="px-3 py-2 font-medium">ID</th>
                    <th scope="col" className="px-3 py-2 font-medium">Type</th>
                    <th scope="col" className="px-3 py-2 font-medium">Name</th>
                    <th scope="col" className="px-3 py-2 font-medium">Position (m)</th>
                    <th scope="col" className="px-3 py-2 font-medium">Size</th>
                    <th scope="col" className="px-3 py-2 font-medium">Properties</th>
                    <th scope="col" className="px-3 py-2 font-medium"><span className="sr-only">Actions</span></th>
                  </tr>
                </thead>
                <tbody>
                  {entities.map((e: any, i: number) => <EntityRow key={e.id ? String(e.id) : `entity-fallback-${i}`} entity={e} onEdit={setEditingEntity} />)}
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
                    <div key={p.id ? String(p.id) : `nav-point-${i}`} className="flex items-center gap-3 text-sm p-2 bg-muted/50 rounded">
                      <Badge variant="secondary" className="font-mono">{p.id ?? `point-${i}`}</Badge>
                      <span>{p.name ?? "—"}</span>
                      <span className="text-muted-foreground font-mono text-xs" title={Array.isArray(p.position) ? formatPosition(p.position) : ""} aria-label="position meters">[{Array.isArray(p.position) ? formatPositionShort(p.position) : "—"}]</span>
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
                    <div key={`${path.from || path.from_point || "from"}-${path.to || path.to_point || "to"}-${i}`} className="flex items-center gap-3 text-sm p-2 bg-muted/50 rounded">
                      <span className="font-mono">{path.from || path.from_point || "—"}</span>
                      <span className="text-muted-foreground" aria-hidden="true">→</span>
                      <span className="font-mono">{path.to || path.to_point || "—"}</span>
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
            <div className="flex gap-2"><span className="text-muted-foreground">preset:</span> <Badge variant="secondary">{lighting.preset ?? "—"}</Badge></div>
            <div className="flex gap-2"><span className="text-muted-foreground">time_of_day:</span> <Badge variant="secondary">{lighting.time_of_day ?? "—"}</Badge></div>
            <div className="flex gap-2"><span className="text-muted-foreground">ambient_intensity:</span> <span className="text-blue-600">{lighting.ambient_intensity ?? "—"}</span></div>
            {lighting.sun_direction && (
              <div className="flex gap-2"><span className="text-muted-foreground">sun_direction:</span> <span>[{Array.isArray(lighting.sun_direction) ? lighting.sun_direction.map((n: number) => Number(n.toFixed(2))).join(", ") : String(lighting.sun_direction)}]</span></div>
            )}
            {lighting.custom_lights?.length > 0 && (
              <div>
                <div className="flex gap-2"><span className="text-muted-foreground">custom_lights:</span> <Badge>{lighting.custom_lights.length}</Badge></div>
                <div className="ml-4 space-y-1">
                  {lighting.custom_lights.map((l: any, i: number) => (
                    <div key={`${l.type || "light"}-${i}`} className="text-xs">
                      {l.type ?? "light"} @ [{Array.isArray(l.position) ? formatPositionShort(l.position) : "—"}] {l.color ? `rgb(${l.color.join(",")})` : ""} intensity={l.intensity ?? "—"}
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
            <div className="flex gap-2"><span className="text-muted-foreground">languages:</span> <span>{(copilot.languages || []).join(", ") || "—"}</span></div>
            <div className="flex gap-2"><span className="text-muted-foreground">default_language:</span> <span>{copilot.default_language ?? "—"}</span></div>
            <div className="flex gap-2"><span className="text-muted-foreground">personality:</span> <Badge variant="secondary">{copilot.personality ?? "—"}</Badge></div>
            <div className="flex gap-2"><span className="text-muted-foreground">allowed_actions:</span> <Badge>{(copilot.allowed_actions || []).length}</Badge></div>
            {copilot.knowledge_base && <div className="flex gap-2"><span className="text-muted-foreground">knowledge_base:</span> <span className="break-all">{copilot.knowledge_base}</span></div>}
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
              <div className="font-mono text-lg">{performance.target_fps ?? "—"}</div>
            </div>
            <div className="p-3 bg-muted/50 rounded">
              <div className="text-muted-foreground text-xs">Max Triangles</div>
              <div className="font-mono text-lg">{performance.max_triangles?.toLocaleString() ?? "—"}</div>
            </div>
            <div className="p-3 bg-muted/50 rounded">
              <div className="text-muted-foreground text-xs">Max Draw Calls</div>
              <div className="font-mono text-lg">{performance.max_draw_calls ?? "—"}</div>
            </div>
            <div className="p-3 bg-muted/50 rounded">
              <div className="text-muted-foreground text-xs">Texture Budget (MB)</div>
              <div className="font-mono text-lg">{performance.texture_budget_mb ?? "—"}</div>
            </div>
            <div className="p-3 bg-muted/50 rounded">
              <div className="text-muted-foreground text-xs">Max Entities</div>
              <div className="font-mono text-lg">{performance.max_entities ?? "—"}</div>
            </div>
            <div className="p-3 bg-muted/50 rounded">
              <div className="text-muted-foreground text-xs">LOD Distances</div>
              <div className="font-mono text-lg">[{performance.lod_distances?.join(", ") ?? "—"}]</div>
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
