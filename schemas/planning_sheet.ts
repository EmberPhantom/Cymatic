// Shared Planning Sheet Schemas (TypeScript) — mirrors schemas/planning_sheet.py
// The planning agent's frozen output: reviewed source of truth for generation.

export type PlanningDomain = "real_estate" | "heritage"
export type LengthUnit = "mm" | "cm" | "m"

export interface Dimension {
  value: number
  unit: LengthUnit
}

export interface SpaceSize {
  width?: Dimension
  depth?: Dimension
  height?: Dimension
}

export interface PlanColor {
  hex: string // #rrggbb
  name?: string
}

export interface PlanMaterial {
  name: string
  finish?: string
  palette?: PlanColor[]
}

export interface SpaceLighting {
  preset?: string
  notes?: string
}

export interface PlanSpace {
  id: string
  kind: "room" | "poi"
  name: string
  size?: SpaceSize
  colors?: PlanColor[]
  materials?: PlanMaterial[]
  lighting?: SpaceLighting
  features?: string[]
}

export interface ResearchRef {
  title: string
  source: string
  url?: string
  snippet?: string
}

export interface PlanningSheet {
  objective: string
  domain: PlanningDomain
  version?: string
  spaces?: PlanSpace[]
  style?: Record<string, string>
  constraints?: Record<string, unknown>
  open_questions?: string[]
  research_refs?: ResearchRef[]
  analyser_mode?: string
}

export type SheetStatus = "draft" | "approved" | "superseded"
