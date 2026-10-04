import { z } from "zod"

export const loginSchema = z.object({
  email: z.string().email("Invalid email address"),
  password: z.string().min(6, "Password must be at least 6 characters"),
})

export const registerSchema = z.object({
  name: z.string().min(2, "Name must be at least 2 characters"),
  email: z.string().email("Invalid email address"),
  password: z.string().min(6, "Password must be at least 6 characters"),
})

export const projectSchema = z.object({
  name: z.string().min(2, "Name must be at least 2 characters").max(100),
  domain: z.enum(["real_estate", "heritage"]),
})

export const promptSchema = z.object({
  prompt: z.string().min(10, "Prompt must be at least 10 characters").max(5000, "Prompt too long"),
})

export type LoginFormData = z.infer<typeof loginSchema>
export type RegisterFormData = z.infer<typeof registerSchema>
export type ProjectFormData = z.infer<typeof projectSchema>
export type PromptFormData = z.infer<typeof promptSchema>

// ---------------------------------------------------------------------------
// API-boundary payloads (Phase C-Web P1: kill `any`-propagation).
//
// The backend returns `payload_json` / `extracted_entities` / `updated_fields`
// as free-form JSON. Wire types keep these as `unknown`; every consumer must
// narrow through the schemas below. `safeParse` at the boundary, typed error
// on mismatch — never a blind cast.
// ---------------------------------------------------------------------------

/** Typed error raised when an API payload fails schema validation. */
export class PayloadValidationError extends Error {
  readonly issues: string[]
  constructor(message: string, issues: string[] = []) {
    super(issues.length > 0 ? `${message}: ${issues.join("; ")}` : message)
    this.name = "PayloadValidationError"
    this.issues = issues
  }
}

function toIssues(error: z.ZodError): string[] {
  return error.issues.map((i) => `${i.path.join(".") || "(root)"}: ${i.message}`)
}

/** A single spatial entity inside a spec payload (lenient: extra keys kept). */
export const specEntitySchema = z
  .object({
    id: z.string(),
    type: z.string(),
  })
  .catchall(z.unknown())

/** `SimulationSpec.payload_json` shape (entities + known budget/layout blocks). */
export const specPayloadSchema = z
  .object({
    entities: z.array(z.unknown()).optional(),
    performance_budget: z.record(z.string(), z.unknown()).optional(),
    spatial_layout: z.record(z.string(), z.unknown()).optional(),
  })
  .catchall(z.unknown())

export type SpecPayload = z.infer<typeof specPayloadSchema>

export const clarificationQuestionSchema = z
  .object({
    field: z.string(),
    question: z.string(),
    type: z.string(),
    options: z.array(z.string()),
    required: z.boolean(),
  })
  .catchall(z.unknown())

/** `POST intake` response shape. */
export const intakeResultSchema = z
  .object({
    detected_domain: z.string(),
    objective: z.string(),
    missing_fields: z.array(z.string()),
    suggested_questions: z.array(z.string()),
    extracted_entities: z.unknown(),
    confidence: z.number(),
    analyser_mode: z.string().optional(),
    run_id: z.string().optional(),
  })
  .catchall(z.unknown())

export type IntakeResultValidated = z.infer<typeof intakeResultSchema>

/** `POST clarify` response shape. */
export const clarifyResultSchema = z
  .object({
    updated_fields: z.unknown(),
    ready_for_generation: z.boolean(),
    completion_percentage: z.number(),
    remaining_questions: z.array(clarificationQuestionSchema),
    analyser_mode: z.string().optional(),
    run_id: z.string().optional(),
  })
  .catchall(z.unknown())

export type ClarifyResultValidated = z.infer<typeof clarifyResultSchema>

export function parseSpecPayloadOrThrow(payload: unknown): SpecPayload {
  const parsed = specPayloadSchema.safeParse(payload)
  if (!parsed.success) throw new PayloadValidationError("Invalid spec payload", toIssues(parsed.error))
  return parsed.data
}

export function parseIntakeResultOrThrow(data: unknown): IntakeResultValidated {
  const parsed = intakeResultSchema.safeParse(data)
  if (!parsed.success) throw new PayloadValidationError("Invalid intake result", toIssues(parsed.error))
  return parsed.data
}

export function parseClarifyResultOrThrow(data: unknown): ClarifyResultValidated {
  const parsed = clarifyResultSchema.safeParse(data)
  if (!parsed.success) throw new PayloadValidationError("Invalid clarify result", toIssues(parsed.error))
  return parsed.data
}

/** Validated read of the `entities` array; malformed payloads yield []. */
export function specEntities(payload: unknown): unknown[] {
  const parsed = specPayloadSchema.safeParse(payload)
  if (!parsed.success) return []
  return Array.isArray(parsed.data.entities) ? parsed.data.entities : []
}

export function countSpecEntities(payload: unknown): number {
  return specEntities(payload).length
}

/** Validated read of a spec payload section (`performance_budget`, ...). */
export function specSection(payload: unknown, key: string): Record<string, unknown> {
  const parsed = specPayloadSchema.safeParse(payload)
  if (!parsed.success) return {}
  const section = (parsed.data as Record<string, unknown>)[key]
  return typeof section === "object" && section !== null
    ? (section as Record<string, unknown>)
    : {}
}

/** Narrow a free-form entities/fields blob to a record; anything else is {}. */
export function asEntityRecord(value: unknown): Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {}
}
