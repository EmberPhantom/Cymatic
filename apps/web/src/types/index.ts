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
  payload_json: Record<string, any>
  status: string
  created_at: string
  updated_at?: string
}

export interface IntakeResult {
  detected_domain: string
  objective: string
  missing_fields: string[]
  suggested_questions: string[]
  extracted_entities: Record<string, any>
  confidence: number
  run_id?: string
}

export interface ClarifyResult {
  updated_fields: Record<string, any>
  ready_for_generation: boolean
  completion_percentage: number
  remaining_questions: ClarificationQuestion[]
  run_id?: string
}

export interface ClarificationQuestion {
  field: string
  question: string
  type: string
  options: string[]
  required: boolean
  depends_on?: string
}

export interface ValidationResult {
  valid: boolean
  errors: string[]
  warnings: string[]
}

export interface JobStatus {
  job_id: string
  status: string
  message?: string
  result?: Record<string, any>
  error?: string
  progress?: number
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
export type JobStatusType = "queued" | "running" | "retry" | "validating_spec" | "generating_scene" | "completed" | "failed" | "cancelled"

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
