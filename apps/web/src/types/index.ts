export interface User {
  id: number
  email: string
  name: string
  role: string
  organization_id: number
  is_active: boolean
}

export interface Project {
  id: number
  organization_id: number
  name: string
  domain: string
  category?: string
  status: string
  created_by: number
  created_at: string
  updated_at?: string
}

export interface SimulationSpec {
  id: number
  project_id: number
  version: number
  // Free-form backend JSON: keep as `unknown`, narrow via
  // parseSpecPayloadOrThrow / specEntities / specSection in @/lib/validations.
  payload_json: unknown
  status: string
  created_at: string
  updated_at?: string
}

export interface IntakeResult {
  detected_domain: string
  objective: string
  missing_fields: string[]
  suggested_questions: string[]
  // Free-form backend JSON: narrow via parseIntakeResultOrThrow /
  // asEntityRecord in @/lib/validations.
  extracted_entities: unknown
  confidence: number
  analyser_mode?: "llm" | "slm" | "fallback" | string
  run_id?: string
}

export interface ClarifyResult {
  // Free-form backend JSON: narrow via parseClarifyResultOrThrow /
  // asEntityRecord in @/lib/validations.
  updated_fields: unknown
  ready_for_generation: boolean
  completion_percentage: number
  remaining_questions: ClarificationQuestion[]
  analyser_mode?: "llm" | "fallback" | string
  run_id?: string
}

export interface ClarificationQuestion {
  field: string
  question: string
  type: string
  options: string[]
  required: boolean
  depends_on?: string
  evidence_span?: string | null
  unit?: string | null
  min_value?: number | null
  max_value?: number | null
  multi?: boolean
}

export interface PlanDimension {
  value: number
  unit: "mm" | "cm" | "m"
}

export interface PlanSpace {
  id: string
  kind: "room" | "poi"
  name: string
  size?: {
    width?: PlanDimension
    depth?: PlanDimension
    height?: PlanDimension
  }
  colors?: { hex: string; name?: string }[]
  materials?: { name: string; finish?: string }[]
  lighting?: { preset?: string; notes?: string }
  features?: string[]
}

export interface PlanningSheet {
  objective: string
  domain: "real_estate" | "heritage"
  version?: string
  spaces?: PlanSpace[]
  style?: Record<string, string>
  constraints?: Record<string, unknown>
  open_questions?: string[]
  research_refs?: { title: string; source: string; url?: string; snippet?: string }[]
  analyser_mode?: string
}

export interface ValidationResult {
  valid: boolean
  errors: string[]
  warnings: string[]
}

export interface JobStatus {
  job_id: string
  job_type?: string
  status: string
  message?: string
  result?: Record<string, any>
  error?: string
  progress?: number
  retry_count?: number
  run_id?: string | null
  updated_at?: string | null
}

export interface GenerationRun {
  id: string
  project_id: number
  stage: string
  status: string
  progress: number
  intake?: Record<string, any>
  clarification: Record<string, any>
  error?: Record<string, any>
  result?: Record<string, any>
  created_at: string
  updated_at?: string
}

export interface StreamSession {
  id: string
  project_id: number
  user_id: number
  device_info: Record<string, any>
  status: string
  started_at: string
  ended_at?: string
}

export interface Asset {
  id: number
  organization_id: number
  project_id?: number
  type: string
  storage_key: string
  status: string
  metadata_json: Record<string, any>
  filename?: string
  content_type?: string
  size?: number
  created_at: string
}

export type Domain = "real_estate" | "heritage"

export type ProjectStatus = "draft" | "spec_generating" | "spec_ready" | "scene_generating" | "scene_ready" | "published" | "failed"
export type SpecStatus = "draft" | "validating" | "valid" | "invalid" | "superseded"
export type JobStatusType = "pending" | "queued" | "running" | "retry" | "completed" | "failed" | "cancelled"

export interface Paginated<T> {
  items: T[]
  total: number
  skip: number
  limit: number
}

export interface ApiError {
  detail: string | { loc: string[]; msg: string; type: string }[]
  status?: number
}
