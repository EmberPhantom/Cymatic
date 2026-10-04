"use client"

import { useState, useEffect, useId } from "react"
import { X, Save, Loader2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { usePatchEntity } from "@/hooks/use-edit-spec"
import type { EntityPatch } from "@/hooks/use-edit-spec"
import { getErrorMessage } from "@/lib/errors"

interface EntityEditorProps {
  projectId: number
  specId: number
  entity: Record<string, any> | null
  onClose: () => void
  onSave: () => void
}

const ENTITY_TYPES = [
  "room", "wall", "floor", "ceiling", "door", "window",
  "furniture", "decoration", "light", "navigation_point",
  "poi", "audio_zone", "trigger_zone"
]

export const WINDOW_PROP_CANONICAL = "has_window"
const WINDOW_PROP_LEGACY = "has_windows"

const COMMON_PROPERTIES = [
  "size", "material", "color", "has_doors", WINDOW_PROP_CANONICAL,
  "is_outdoor", "furnished", "style", "has_narration",
  "has_collider", "description", "floor_material"
]

/**
 * Backend canonical key is `has_window` (singular); `has_windows` is a
 * legacy alias accepted on read only. Normalize read input to the canonical
 * key (canonical wins when both are present); callers write `has_window`.
 */
export function normalizeWindowProps(props: Record<string, unknown>): Record<string, unknown> {
  if (!(WINDOW_PROP_LEGACY in props)) return props
  const { [WINDOW_PROP_LEGACY]: _legacy, ...rest } = props
  if (WINDOW_PROP_CANONICAL in rest) return rest
  return { ...rest, [WINDOW_PROP_CANONICAL]: _legacy }
}

function parseNumericInput(value: string): number | null {
  const trimmed = value.trim()
  if (trimmed === "") return 0
  // strict finite number check; disallow empty whitespace -> 0, Infinity -> not finite
  const num = Number(trimmed)
  if (!Number.isFinite(num)) return null
  // Additionally guard strings like "123abc" which Number gives NaN -> null
  // Use regex to ensure the whole trimmed string is a valid number representation
  if (!/^[-+]?(\d+(\.\d*)?|\.\d+)([eE][-+]?\d+)?$/.test(trimmed)) {
    // Allow boolean strings to be handled elsewhere, but for position/scale we only want numbers
    return null
  }
  return num
}

export function EntityEditor({ projectId, specId, entity, onClose, onSave }: EntityEditorProps) {
  const [position, setPosition] = useState<[number, number, number]>([0, 0, 0])
  const [rotation, setRotation] = useState<[number, number, number]>([0, 0, 0])
  const [scale, setScale] = useState<[number, number, number]>([1, 1, 1])
  const [entityType, setEntityType] = useState("")
  const [entityName, setEntityName] = useState("")
  const [properties, setProperties] = useState<Record<string, any>>({})
  const [propertyKeys, setPropertyKeys] = useState<string[]>([])
  const [propertyValues, setPropertyValues] = useState<Record<string, string>>({})
  const [isSaving, setIsSaving] = useState(false)
  const baseId = useId()

  const patchEntity = usePatchEntity(projectId)

  useEffect(() => {
    if (entity) {
      setPosition(entity.position ? [...entity.position] as [number, number, number] : [0, 0, 0])
      setRotation(entity.rotation ? [...entity.rotation] as [number, number, number] : [0, 0, 0])
      setScale(entity.scale ? [...entity.scale] as [number, number, number] : [1, 1, 1])
      setEntityType(entity.type || "")
      setEntityName(entity.name || "")
      // Read both `has_window` (canonical) and legacy `has_windows`.
      const normalized = normalizeWindowProps(entity.properties || {})
      setProperties(normalized)
      const keys = Object.keys(normalized)
      setPropertyKeys(keys)
      const vals: Record<string, string> = {}
      keys.forEach(k => { vals[k] = String(normalized?.[k] ?? "") })
      setPropertyValues(vals)
    }
  }, [entity])

  const handlePositionChange = (index: number, value: string) => {
    const parsed = parseNumericInput(value)
    if (parsed !== null) {
      const newPos = [...position] as [number, number, number]
      newPos[index] = parsed
      setPosition(newPos)
    } else if (value.trim() === "") {
      // allow clearing to 0 without stuck input
      const newPos = [...position] as [number, number, number]
      newPos[index] = 0
      setPosition(newPos)
    }
  }

  const handleRotationChange = (index: number, value: string) => {
    const parsed = parseNumericInput(value)
    if (parsed !== null) {
      const newRot = [...rotation] as [number, number, number]
      newRot[index] = parsed
      setRotation(newRot)
    } else if (value.trim() === "") {
      const newRot = [...rotation] as [number, number, number]
      newRot[index] = 0
      setRotation(newRot)
    }
  }

  const handleScaleChange = (index: number, value: string) => {
    const parsed = parseNumericInput(value)
    if (parsed !== null) {
      const newScale = [...scale] as [number, number, number]
      newScale[index] = parsed
      setScale(newScale)
    } else if (value.trim() === "") {
      const newScale = [...scale] as [number, number, number]
      newScale[index] = 1
      setScale(newScale)
    }
  }

  const addProperty = () => {
    const newKey = `property_${Date.now()}`
    setPropertyKeys(prev => [...prev, newKey])
    setPropertyValues(prev => ({ ...prev, [newKey]: "" }))
  }

  const removeProperty = (key: string) => {
    setPropertyKeys(prev => prev.filter(k => k !== key))
    setPropertyValues(prev => {
      const { [key]: _removed, ...rest } = prev
      return rest
    })
  }

  const handlePropertyChange = (key: string, value: string) => {
    setPropertyValues(prev => ({ ...prev, [key]: value }))
  }

  const handlePropertyKeyRename = (oldKey: string, newKeyRaw: string) => {
    const newKey = newKeyRaw.trim()
    // Empty or duplicate keys are not allowed; keep old if invalid
    if (!newKey || newKey === oldKey) return
    if (propertyKeys.includes(newKey)) return
    setPropertyKeys(prev => prev.map(k => k === oldKey ? newKey : k))
    setPropertyValues(prev => {
      const next: Record<string, string> = {}
      // copy all except oldKey, add newKey with old value
      for (const k of Object.keys(prev)) {
        if (k === oldKey) continue
        next[k] = prev[k]
      }
      next[newKey] = prev[oldKey] ?? ""
      return next
    })
  }

  const buildPatch = (): EntityPatch => {
    const props: Record<string, any> = {}
    propertyKeys.forEach(key => {
      const raw = propertyValues[key]
      const val = typeof raw === "string" ? raw : String(raw ?? "")
      const trimmed = val.trim()
      if (trimmed === "true") props[key] = true
      else if (trimmed === "false") props[key] = false
      else if (trimmed !== "" && /^[-+]?(\d+(\.\d*)?|\.\d+)([eE][-+]?\d+)?$/.test(trimmed) && Number.isFinite(Number(trimmed))) {
        // strict numeric conversion without coercing whitespace / hex via Number
        props[key] = Number(trimmed)
      } else {
        props[key] = val
      }
    })
    // Write the canonical key; a legacy `has_windows` edit is folded in.
    const properties = normalizeWindowProps(props)
    return {
      position,
      rotation,
      scale,
      properties,
    }
  }

  const handleSave = async () => {
    if (!entity) return
    setIsSaving(true)
    try {
      const patch = buildPatch()
      await patchEntity.mutateAsync({ specId, entityId: entity.id, patch })
      onSave()
      onClose()
    } catch (error: unknown) {
      const msg = getErrorMessage(error, "Failed to save entity")
      // eslint-disable-next-line no-alert
      alert(msg)
    } finally {
      setIsSaving(false)
    }
  }

  if (!entity) return null

  // IDs for labeling
  const idEntityId = `${baseId}-entity-id`
  const idEntityName = `${baseId}-entity-name`
  const idEntityType = `${baseId}-entity-type`

  return (
    <Dialog open={!!entity} onOpenChange={(open) => { if (!open) onClose() }}>
      <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto" aria-describedby={`${baseId}-dialog-desc`}>
        <DialogHeader>
          <DialogTitle>Edit Entity: {entity.name} ({entity.id})</DialogTitle>
          <DialogDescription id={`${baseId}-dialog-desc`} className="sr-only">
            Edit transform and properties for entity {entity.id}. Press Escape to close.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-4 py-4">
          {/* Basic Info */}
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Basic Information</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-1">
                  <Label htmlFor={idEntityId}>Entity ID</Label>
                  <Input
                    id={idEntityId}
                    value={entity.id}
                    readOnly
                    aria-readonly="true"
                    tabIndex={0}
                    className="bg-muted"
                    onFocus={e => e.currentTarget.select()}
                  />
                  <p className="text-xs text-muted-foreground">ID is read-only</p>
                </div>
                <div className="space-y-1">
                  <Label htmlFor={idEntityType}>Type</Label>
                  <Select value={entityType} onValueChange={setEntityType}>
                    <SelectTrigger id={idEntityType} aria-label="Entity type">
                      <SelectValue placeholder="Select type" />
                    </SelectTrigger>
                    <SelectContent>
                      {ENTITY_TYPES.map(t => <SelectItem key={t} value={t}>{t}</SelectItem>)}
                    </SelectContent>
                  </Select>
                </div>
              </div>
              <div className="space-y-1">
                <Label htmlFor={idEntityName}>Name</Label>
                <Input
                  id={idEntityName}
                  value={entityName}
                  onChange={e => setEntityName(e.target.value)}
                  autoComplete="off"
                />
              </div>
            </CardContent>
          </Card>

          {/* Transform */}
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Transform</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <div>
                <Label id={`${baseId}-pos-label`}>Position (x, y, z) in meters</Label>
                <div className="flex gap-2" aria-labelledby={`${baseId}-pos-label`}>
                  <Input
                    type="number"
                    inputMode="decimal"
                    step="any"
                    placeholder="0.0"
                    aria-label="Position X in meters"
                    value={position[0]}
                    onChange={e => handlePositionChange(0, e.target.value)}
                  />
                  <Input
                    type="number"
                    inputMode="decimal"
                    step="any"
                    placeholder="0.0"
                    aria-label="Position Y in meters"
                    value={position[1]}
                    onChange={e => handlePositionChange(1, e.target.value)}
                  />
                  <Input
                    type="number"
                    inputMode="decimal"
                    step="any"
                    placeholder="0.0"
                    aria-label="Position Z in meters"
                    value={position[2]}
                    onChange={e => handlePositionChange(2, e.target.value)}
                  />
                </div>
              </div>
              <div>
                <Label id={`${baseId}-rot-label`}>Rotation (x, y, z degrees)</Label>
                <div className="flex gap-2" aria-labelledby={`${baseId}-rot-label`}>
                  <Input
                    type="number"
                    inputMode="decimal"
                    step="any"
                    placeholder="0.0"
                    aria-label="Rotation X in degrees"
                    value={rotation[0]}
                    onChange={e => handleRotationChange(0, e.target.value)}
                  />
                  <Input
                    type="number"
                    inputMode="decimal"
                    step="any"
                    placeholder="0.0"
                    aria-label="Rotation Y in degrees"
                    value={rotation[1]}
                    onChange={e => handleRotationChange(1, e.target.value)}
                  />
                  <Input
                    type="number"
                    inputMode="decimal"
                    step="any"
                    placeholder="0.0"
                    aria-label="Rotation Z in degrees"
                    value={rotation[2]}
                    onChange={e => handleRotationChange(2, e.target.value)}
                  />
                </div>
              </div>
              <div>
                <Label id={`${baseId}-scale-label`}>Scale (x, y, z)</Label>
                <div className="flex gap-2" aria-labelledby={`${baseId}-scale-label`}>
                  <Input
                    type="number"
                    inputMode="decimal"
                    step="any"
                    placeholder="1.0"
                    aria-label="Scale X"
                    value={scale[0]}
                    onChange={e => handleScaleChange(0, e.target.value)}
                  />
                  <Input
                    type="number"
                    inputMode="decimal"
                    step="any"
                    placeholder="1.0"
                    aria-label="Scale Y"
                    value={scale[1]}
                    onChange={e => handleScaleChange(1, e.target.value)}
                  />
                  <Input
                    type="number"
                    inputMode="decimal"
                    step="any"
                    placeholder="1.0"
                    aria-label="Scale Z"
                    value={scale[2]}
                    onChange={e => handleScaleChange(2, e.target.value)}
                  />
                </div>
              </div>
            </CardContent>
          </Card>

          {/* Properties */}
          <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0">
              <CardTitle className="text-base">Properties</CardTitle>
              <Button variant="outline" size="sm" type="button" onClick={addProperty} aria-label="Add new property">
                Add Property
              </Button>
            </CardHeader>
            <CardContent>
              {propertyKeys.length === 0 ? (
                <p className="text-sm text-muted-foreground">No properties defined. Click &quot;Add Property&quot; to add custom properties.</p>
              ) : (
                <div className="space-y-2" role="list" aria-label="Entity properties">
                  {propertyKeys.map((key) => (
                    <div key={key} className="flex items-center gap-2" role="listitem">
                      <Input
                        placeholder="Key"
                        aria-label={`Property key ${key}`}
                        value={key}
                        onChange={e => handlePropertyKeyRename(key, e.target.value)}
                        onBlur={e => {
                          // if user cleared key, revert to previous? keep as-is but prevent empty
                          if (e.target.value.trim() === "") {
                            // revert: no empty keys, remove? For now keep previous value
                          }
                        }}
                        className="w-40"
                      />
                      <Input
                        placeholder="Value"
                        aria-label={`Property value for ${key}`}
                        value={propertyValues[key] || ""}
                        onChange={e => handlePropertyChange(key, e.target.value)}
                        className="flex-1"
                      />
                      <Button
                        variant="ghost"
                        size="icon"
                        type="button"
                        onClick={() => removeProperty(key)}
                        aria-label={`Remove property ${key}`}
                      >
                        <X className="h-4 w-4" aria-hidden="true" />
                      </Button>
                    </div>
                  ))}
                </div>
              )}
              <div className="mt-3 pt-2 border-t">
                <Label className="text-xs text-muted-foreground">Common properties for {entity.type || "this type"}:</Label>
                <div className="flex flex-wrap gap-1 mt-1">
                  {COMMON_PROPERTIES
                    .filter(p => !propertyKeys.includes(p))
                    .map(p => (
                      <Button
                        key={p}
                        variant="outline"
                        size="sm"
                        type="button"
                        onClick={() => {
                          setPropertyKeys(prev => [...prev, p])
                          setPropertyValues(prev => ({ ...prev, [p]: "" }))
                        }}
                        aria-label={`Add common property ${p}`}
                      >
                        {p}
                      </Button>
                    ))}
                </div>
              </div>
            </CardContent>
          </Card>

          {/* Actions */}
          <div className="flex justify-end gap-2 pt-4 border-t">
            <Button variant="outline" type="button" onClick={onClose} disabled={isSaving}>
              Cancel
            </Button>
            <Button type="button" onClick={handleSave} disabled={isSaving} aria-busy={isSaving}>
              {isSaving ? <Loader2 className="h-4 w-4 mr-2 animate-spin" aria-hidden="true" /> : <Save className="h-4 w-4 mr-2" aria-hidden="true" />} Save Changes
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  )
}
