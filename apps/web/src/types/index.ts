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
}

export interface ClarifyResult {
  updated_fields: Record<string, any>
  ready_for_generation: boolean
  completion_percentage: number
  remaining_questions: ClarificationQuestion[]
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
  id: string
  filename: string
  content_type: string
  size: number
  url: string
  created_at: string
}

export type Domain = "real_estate" | "heritage"
