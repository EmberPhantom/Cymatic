"use client"

import { useParams } from "next/navigation"
import { useState, useRef, useCallback } from "react"
import { useSpecs } from "@/hooks/use-specs"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import type { BadgeProps } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"

const specStatusVariant: Record<string, BadgeProps["variant"]> = {
  draft: "secondary",
  validating: "secondary",
  valid: "default",
  invalid: "destructive",
  superseded: "outline",
  // legacy fallback
  active: "default",
}

function getSpecStatusLabel(status: string) {
  return status || "unknown"
}

// Lightweight virtualized list for up to 200 entities without external deps.
// Renders only visible window; falls back to full render for < 30 items.
function VirtualizedEntityList({ entities }: { entities: unknown[] }) {
  const containerRef = useRef<HTMLDivElement>(null)
  const [scrollTop, setScrollTop] = useState(0)
  const ITEM_HEIGHT = 56
  const CONTAINER_HEIGHT = 320
  const BUFFER = 5

  const handleScroll = useCallback((e: React.UIEvent<HTMLDivElement>) => {
    setScrollTop(e.currentTarget.scrollTop)
  }, [])

  const total = entities.length

  // For small lists, avoid virtualization complexity
  if (total <= 30) {
    return (
      <div className="max-h-80 overflow-auto rounded border bg-muted/50">
        {entities.map((ent, idx) => {
          const e = ent as Record<string, unknown>
          const id = (e.id as string) || `entity-${idx}`
          const type = (e.type as string) || "unknown"
          const name = (e.name as string) || id
          return (
            <div key={id + idx} className="flex items-center justify-between px-3 py-2 border-b last:border-0 text-xs">
              <span className="font-mono truncate pr-2">{id}</span>
              <span className="text-muted-foreground truncate">{name}</span>
              <Badge variant="outline" className="ml-2 shrink-0 text-[10px]">
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
      className="overflow-auto rounded border bg-muted/50"
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
            const type = (e.type as string) || "unknown"
            const name = (e.name as string) || id
            return (
              <div
                key={id + absoluteIdx}
                role="listitem"
                className="flex items-center justify-between px-3 border-b last:border-0 text-xs bg-background"
                style={{ height: ITEM_HEIGHT }}
              >
                <span className="font-mono truncate pr-2" title={String(id)}>
                  {id}
                </span>
                <span className="text-muted-foreground truncate flex-1" title={String(name)}>
                  {name}
                </span>
                <Badge variant="outline" className="ml-2 shrink-0 text-[10px]">
                  {type}
                </Badge>
                <span className="ml-2 text-[10px] text-muted-foreground">#{absoluteIdx + 1}</span>
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
  const [copyFeedback, setCopyFeedback] = useState<string | null>(null)
  const [expandedId, setExpandedId] = useState<number | null>(null)

  const handleCopy = useCallback(async (payload: unknown, specId: number) => {
    const text = JSON.stringify(payload, null, 2)
    try {
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(text)
      } else {
        // fallback
        const ta = document.createElement("textarea")
        ta.value = text
        ta.style.position = "fixed"
        ta.style.opacity = "0"
        document.body.appendChild(ta)
        ta.select()
        document.execCommand("copy")
        document.body.removeChild(ta)
      }
      setCopyFeedback(`Spec ${specId} JSON copied`)
      window.setTimeout(() => setCopyFeedback(null), 2000)
    } catch {
      setCopyFeedback("Copy failed")
      window.setTimeout(() => setCopyFeedback(null), 2000)
    }
  }, [])

  return (
    <div>
      <h3 className="text-lg font-semibold mb-4">Specifications</h3>

      {/* aria-live for copy feedback */}
      <div aria-live="polite" aria-atomic="true" className="sr-only" role="status">
        {copyFeedback || ""}
      </div>
      {copyFeedback && (
        <div role="status" className="mb-3 rounded-md bg-green-50 p-2 text-sm text-green-700 border border-green-200">
          {copyFeedback}
        </div>
      )}

      {isLoading ? (
        <div className="space-y-3">
          {[1, 2].map((i) => (
            <Card key={i}>
              <CardHeader className="pb-2">
                <Skeleton className="h-5 w-24" />
              </CardHeader>
              <CardContent className="space-y-2">
                <Skeleton className="h-4 w-1/3" />
                <Skeleton className="h-20 w-full" />
              </CardContent>
            </Card>
          ))}
        </div>
      ) : specs && specs.length > 0 ? (
        <div className="space-y-3">
          {specs.map((spec) => {
            const variant = specStatusVariant[spec.status] ?? "outline"
            const payload = spec.payload_json as Record<string, unknown> | null
            const entitiesArray = (payload && Array.isArray((payload as Record<string, unknown>).entities) ? ((payload as Record<string, unknown>).entities as unknown[]) : []) as unknown[]
            const isExpanded = expandedId === spec.id
            return (
              <Card key={spec.id}>
                <CardHeader className="pb-2">
                  <CardTitle className="text-base flex items-center justify-between">
                    <span>Spec v{spec.version}</span>
                    <Badge variant={variant}>{getSpecStatusLabel(spec.status)}</Badge>
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-3">
                  <p className="text-sm text-muted-foreground">
                    Created: <time dateTime={spec.created_at}>{new Date(spec.created_at).toLocaleString()}</time>
                    {entitiesArray.length > 0 && <span className="ml-2">· {entitiesArray.length} entities</span>}
                  </p>

                  {entitiesArray.length > 0 && (
                    <div>
                      <p className="text-xs font-medium text-muted-foreground mb-1">
                        Entities {entitiesArray.length > 30 ? "(virtualized)" : ""} — {entitiesArray.length} total
                      </p>
                      <VirtualizedEntityList entities={entitiesArray} />
                    </div>
                  )}

                  <details
                    className="mt-2"
                    open={isExpanded || undefined}
                    onToggle={(e) => {
                      const open = (e.currentTarget as HTMLDetailsElement).open
                      setExpandedId(open ? spec.id : null)
                    }}
                  >
                    <summary className="text-sm text-primary cursor-pointer hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring rounded-sm px-1 -mx-1">
                      View JSON
                    </summary>
                    <div className="mt-2 space-y-2">
                      <div className="flex justify-end">
                        <Button variant="outline" size="sm" onClick={() => handleCopy(spec.payload_json, spec.id)} aria-label={`Copy spec ${spec.version} JSON`}>
                          Copy JSON
                        </Button>
                      </div>
                      <pre className="text-xs bg-muted p-3 rounded overflow-auto max-h-48 max-w-full whitespace-pre-wrap break-words">
                        {JSON.stringify(spec.payload_json, null, 2)}
                      </pre>
                    </div>
                  </details>
                </CardContent>
              </Card>
            )
          })}
        </div>
      ) : (
        <p className="text-muted-foreground">No specs yet. Use the builder to generate one.</p>
      )}
    </div>
  )
}
