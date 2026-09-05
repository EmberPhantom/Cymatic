"use client"

import { useState, useEffect } from "react"
import { X, Save, Loader2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { usePatchEntity } from "@/hooks/use-edit-spec"
import type { EntityPatch } from "@/hooks/use-edit-spec"

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

const COMMON_PROPERTIES = [
  "size", "material", "color", "has_doors", "has_windows",
  "is_outdoor", "furnished", "style", "has_narration",
  "has_collider", "description", "floor_material"
]

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

  const patchEntity = usePatchEntity(projectId)

  useEffect(() => {
    if (entity) {
      setPosition(entity.position ? [...entity.position] as [number, number, number] : [0, 0, 0])
      setRotation(entity.rotation ? [...entity.rotation] as [number, number, number] : [0, 0, 0])
      setScale(entity.scale ? [...entity.scale] as [number, number, number] : [1, 1, 1])
      setEntityType(entity.type || "")
      setEntityName(entity.name || "")
      setProperties(entity.properties || {})
      const keys = Object.keys(entity.properties || {})
      setPropertyKeys(keys)
      const vals: Record<string, string> = {}
      keys.forEach(k => { vals[k] = String(entity.properties?.[k] ?? "") })
      setPropertyValues(vals)
    }
  }, [entity])

  const handlePositionChange = (index: number, value: string) => {
    const num = parseFloat(value)
    if (!isNaN(num)) {
      const newPos = [...position]
      newPos[index] = num
      setPosition(newPos as [number, number, number])
    }
  }

  const handleRotationChange = (index: number, value: string) => {
    const num = parseFloat(value)
    if (!isNaN(num)) {
      const newRot = [...rotation]
      newRot[index] = num
      setRotation(newRot as [number, number, number])
    }
  }

  const handleScaleChange = (index: number, value: string) => {
    const num = parseFloat(value)
    if (!isNaN(num)) {
      const newScale = [...scale]
      newScale[index] = num
      setScale(newScale as [number, number, number])
    }
  }

  const addProperty = () => {
    const newKey = `property_${Date.now()}`
    setPropertyKeys([...propertyKeys, newKey])
    setPropertyValues({ ...propertyValues, [newKey]: "" })
  }

  const removeProperty = (key: string) => {
    const newKeys = propertyKeys.filter(k => k !== key)
    setPropertyKeys(newKeys)
    const newVals = { ...propertyValues }
    delete newVals[key]
    setPropertyValues(newVals)
  }

  const handlePropertyChange = (key: string, value: string) => {
    setPropertyValues({ ...propertyValues, [key]: value })
  }

  const buildPatch = (): EntityPatch => {
    const props: Record<string, any> = {}
    propertyKeys.forEach(key => {
      const val = propertyValues[key]
      // Try to parse as number/boolean
      if (val === "true") props[key] = true
      else if (val === "false") props[key] = false
      else if (!isNaN(Number(val)) && val !== "") props[key] = Number(val)
      else props[key] = val
    })
    return {
      position,
      rotation,
      scale,
      properties: props,
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
    } catch (error: any) {
      alert(error?.response?.data?.detail || error?.message || "Failed to save entity")
    } finally {
      setIsSaving(false)
    }
  }

  if (!entity) return null

  return (
    <Dialog open={true} onOpenChange={onClose}>
      <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Edit Entity: {entity.name} ({entity.id})</DialogTitle>
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
                  <Label>Entity ID</Label>
                  <Input value={entity.id} disabled />
                </div>
                <div className="space-y-1">
                  <Label>Type</Label>
                  <Select value={entityType} onValueChange={setEntityType}>
                    <SelectTrigger>
                      <SelectValue placeholder="Select type" />
                    </SelectTrigger>
                    <SelectContent>
                      {ENTITY_TYPES.map(t => <SelectItem key={t} value={t}>{t}</SelectItem>)}
                    </SelectContent>
                  </Select>
                </div>
              </div>
              <div className="space-y-1">
                <Label>Name</Label>
                <Input value={entityName} onChange={e => setEntityName(e.target.value)} />
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
                <Label>Position (x, y, z)</Label>
                <div className="flex gap-2">
                  <Input placeholder="X" value={position[0]} onChange={e => handlePositionChange(0, e.target.value)} />
                  <Input placeholder="Y" value={position[1]} onChange={e => handlePositionChange(1, e.target.value)} />
                  <Input placeholder="Z" value={position[2]} onChange={e => handlePositionChange(2, e.target.value)} />
                </div>
              </div>
              <div>
                <Label>Rotation (x, y, z degrees)</Label>
                <div className="flex gap-2">
                  <Input placeholder="X" value={rotation[0]} onChange={e => handleRotationChange(0, e.target.value)} />
                  <Input placeholder="Y" value={rotation[1]} onChange={e => handleRotationChange(1, e.target.value)} />
                  <Input placeholder="Z" value={rotation[2]} onChange={e => handleRotationChange(2, e.target.value)} />
                </div>
              </div>
              <div>
                <Label>Scale (x, y, z)</Label>
                <div className="flex gap-2">
                  <Input placeholder="X" value={scale[0]} onChange={e => handleScaleChange(0, e.target.value)} />
                  <Input placeholder="Y" value={scale[1]} onChange={e => handleScaleChange(1, e.target.value)} />
                  <Input placeholder="Z" value={scale[2]} onChange={e => handleScaleChange(2, e.target.value)} />
                </div>
              </div>
            </CardContent>
          </Card>

          {/* Properties */}
          <Card>
            <CardHeader className="flex flex-row items-center justify-between">
              <CardTitle className="text-base">Properties</CardTitle>
              <Button variant="outline" size="sm" onClick={addProperty}>
                Add Property
              </Button>
            </CardHeader>
            <CardContent>
              {propertyKeys.length === 0 ? (
                <p className="text-sm text-muted-foreground">No properties defined. Click "Add Property" to add custom properties.</p>
              ) : (
                <div className="space-y-2">
                  {propertyKeys.map((key, index) => (
                    <div key={key} className="flex items-center gap-2">
                      <Input
                        placeholder="Key"
                        value={key}
                        onChange={e => {
                          const newKey = e.target.value
                          if (newKey !== key) {
                            setPropertyKeys(propertyKeys.map(k => k === key ? newKey : k))
                            setPropertyValues({ ...propertyValues, [newKey]: propertyValues[key] })
                            delete propertyValues[key]
                          }
                        }}
                        className="w-40"
                      />
                      <Input
                        placeholder="Value"
                        value={propertyValues[key] || ""}
                        onChange={e => handlePropertyChange(key, e.target.value)}
                        className="flex-1"
                      />
                      <Button variant="ghost" size="icon" onClick={() => removeProperty(key)}>
                        <X className="h-4 w-4" />
                      </Button>
                    </div>
                  ))}
                </div>
              )}
              <div className="mt-2 pt-2 border-t">
                <Label className="text-xs text-muted-foreground">Common properties for {entity.type || "this type"}:</Label>
                <div className="flex flex-wrap gap-1 mt-1">
                  {COMMON_PROPERTIES
                    .filter(p => !propertyKeys.includes(p))
                    .map(p => (
                      <Button
                        key={p}
                        variant="outline"
                        size="sm"
                        onClick={() => {
                          setPropertyKeys([...propertyKeys, p])
                          setPropertyValues({ ...propertyValues, [p]: "" })
                        }}
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
            <Button variant="outline" onClick={onClose} disabled={isSaving}>
              Cancel
            </Button>
            <Button onClick={handleSave} disabled={isSaving}>
              {isSaving ? <Loader2 className="h-4 w-4 mr-2 animate-spin" /> : <> <Save className="h-4 w-4 mr-2" /> Save Changes </>}
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  )
}