// Builder workflow state, extracted from the builder page so the reducer and
// hydration logic are unit-testable without rendering the page.
//
// Two correctness rules live here:
// 1. HYDRATE never synthesizes a fake full-shape IntakeResult from a bare
//    `{ run_id }` — run_id-only payloads must be refetched from
//    GET /v1/projects/{id}/generation-runs/{runId} (see intakeFromGenerationRun).
// 2. A hydrated `currentJobId` must be verified live before the 5-minute
//    timeout window resumes; dead/GC'd jobs reset to review (see
//    resolveHydratedJob / stepAfterDeadJob).
import type { ClarifyResult, IntakeResult } from "@/types"

export type Step = "prompt" | "clarify" | "review" | "generate" | "publish"
export type GenerationStage = "spec" | "validation" | "scene" | "publish"

export const BUILDER_STEPS: { key: Step; label: string }[] = [
  { key: "prompt", label: "Enter Prompt" },
  { key: "clarify", label: "Clarification" },
  { key: "review", label: "Review Spec" },
  { key: "generate", label: "Generate" },
  { key: "publish", label: "Publish" },
]

export const GENERATION_STAGES: GenerationStage[] = ["spec", "validation", "scene", "publish"]

export const MAX_PROMPT_LENGTH = 5000

export type BuilderState = {
  step: Step
  prompt: string
  intakeResult: IntakeResult | null
  clarifyResult: ClarifyResult | null
  answers: Record<string, string>
  currentJobId: string | null
  generationStage: GenerationStage
  workflowError: string | null
}

export type BuilderAction =
  | { type: "SET_PROMPT"; payload: string }
  | { type: "SET_STEP"; payload: Step }
  | { type: "SET_INTAKE_RESULT"; payload: IntakeResult | null }
  | { type: "SET_CLARIFY_RESULT"; payload: ClarifyResult | null }
  | { type: "SET_ANSWERS"; payload: Record<string, string> }
  | { type: "SET_ANSWER"; payload: { field: string; value: string } }
  | { type: "SET_JOB"; payload: string | null }
  | { type: "SET_STAGE"; payload: GenerationStage }
  | { type: "SET_ERROR"; payload: string | null }
  | { type: "SET_WORKFLOW"; payload: Partial<Pick<BuilderState, "step" | "generationStage" | "currentJobId" | "workflowError">> }
  | { type: "HYDRATE"; payload: Partial<BuilderState> }
  | { type: "RESET_JOB" }

export const initialBuilderState: BuilderState = {
  step: "prompt",
  prompt: "",
  intakeResult: null,
  clarifyResult: null,
  answers: {},
  currentJobId: null,
  generationStage: "spec",
  workflowError: null,
}

export function builderReducer(state: BuilderState, action: BuilderAction): BuilderState {
  switch (action.type) {
    case "SET_PROMPT":
      return { ...state, prompt: action.payload.slice(0, MAX_PROMPT_LENGTH) }
    case "SET_STEP":
      return { ...state, step: action.payload }
    case "SET_INTAKE_RESULT":
      return { ...state, intakeResult: action.payload }
    case "SET_CLARIFY_RESULT":
      return { ...state, clarifyResult: action.payload }
    case "SET_ANSWERS":
      return { ...state, answers: action.payload }
    case "SET_ANSWER":
      return { ...state, answers: { ...state.answers, [action.payload.field]: action.payload.value } }
    case "SET_JOB":
      return { ...state, currentJobId: action.payload }
    case "SET_STAGE":
      return { ...state, generationStage: action.payload }
    case "SET_ERROR":
      return { ...state, workflowError: action.payload }
    case "SET_WORKFLOW":
      return { ...state, ...action.payload }
    case "HYDRATE":
      return { ...state, ...action.payload }
    case "RESET_JOB":
      return { ...state, currentJobId: null }
    default:
      return state
  }
}

/** True only for a full-shape intake (never for a bare `{ run_id }`). */
export function isFullIntakeResult(value: unknown): value is IntakeResult {
  if (!value || typeof value !== "object") return false
  const v = value as Record<string, unknown>
  return typeof v.run_id === "string" && typeof v.detected_domain === "string" && typeof v.objective === "string"
}

export type SanitizedHydration = {
  /** Safe partial state to HYDRATE immediately. Never contains a fake intake. */
  hydrate: Partial<BuilderState>
  /** run_id that still needs a full-intake refetch (storage had run_id-only or nothing). */
  pendingRunIdFetch: string | null
}

/**
 * Validates raw sessionStorage/URL hydration input. A `{ run_id }`-only
 * payload is NOT promoted to an IntakeResult — it is returned via
 * `pendingRunIdFetch` so the caller refetches the full intake from the API.
 */
export function sanitizeHydratedState(parsed: unknown, urlRunId: string | null): SanitizedHydration {
  const hydrate: Partial<BuilderState> = {}
  let pendingRunIdFetch: string | null = null

  if (parsed && typeof parsed === "object") {
    const p = parsed as Partial<BuilderState>
    if (typeof p.prompt === "string") hydrate.prompt = p.prompt.slice(0, MAX_PROMPT_LENGTH)
    if (isFullIntakeResult(p.intakeResult)) {
      hydrate.intakeResult = p.intakeResult
    } else if (p.intakeResult && typeof p.intakeResult === "object") {
      // run_id-only (or otherwise partial) stored intake: must refetch, never synthesize.
      const runId = (p.intakeResult as { run_id?: unknown }).run_id
      if (typeof runId === "string" && runId) pendingRunIdFetch = runId
    }
    if (p.clarifyResult && typeof p.clarifyResult === "object") {
      hydrate.clarifyResult = p.clarifyResult as ClarifyResult
    }
    if (p.answers && typeof p.answers === "object") hydrate.answers = p.answers as Record<string, string>
    if (typeof p.currentJobId === "string" || p.currentJobId === null) {
      hydrate.currentJobId = p.currentJobId as string | null
    }
    if (p.step && BUILDER_STEPS.some((s) => s.key === p.step)) hydrate.step = p.step as Step
    if (p.generationStage && (GENERATION_STAGES as string[]).includes(p.generationStage as string)) {
      hydrate.generationStage = p.generationStage as GenerationStage
    }
  }

  // URL ?run_id= with no full intake anywhere: refetch it, never synthesize.
  if (urlRunId && !hydrate.intakeResult) {
    pendingRunIdFetch = pendingRunIdFetch ?? urlRunId
  }

  return { hydrate, pendingRunIdFetch }
}

export type GenerationRunResponse = {
  id: string
  intake?: Record<string, unknown> | null
  clarification?: Record<string, unknown> | null
  [key: string]: unknown
}

/**
 * Rebuilds a full IntakeResult from GET generation-runs/{runId}. Returns null
 * when the stored run has no usable intake (caller must then drop the stale
 * run_id and surface an error, never render a fake object).
 */
export function intakeFromGenerationRun(run: GenerationRunResponse | null | undefined): IntakeResult | null {
  if (!run || typeof run.id !== "string") return null
  const intake = run.intake
  if (!intake || typeof intake !== "object") return null
  const candidate = { ...intake, run_id: run.id }
  return isFullIntakeResult(candidate) ? candidate : null
}

// ---------------------------------------------------------------------------
// Hydrated job liveness: GET /v1/jobs/{id}/status result -> live or dead?
// Live  = job still exists and is pending/queued/running/retry/completed
//         (completed resumes via the normal workflow-continuation effect).
// Dead  = 404/GC'd, failed, or cancelled -> reset to review, never the
//         "Generation Interrupted" limbo.
// Any other fetch outcome (network error, unknown shape) is treated as live
// (fail-open): the existing 5-minute timeout interval still bounds the wait.
// ---------------------------------------------------------------------------
const LIVE_JOB_STATUSES = new Set(["pending", "queued", "running", "retry", "completed"])
const TERMINAL_DEAD_STATUSES = new Set(["failed", "cancelled"])

export function resolveHydratedJob(status: unknown, fetchFailed: boolean, notFound: boolean): "live" | "dead" {
  if (notFound) return "dead"
  if (typeof status === "string") {
    if (LIVE_JOB_STATUSES.has(status)) return "live"
    if (TERMINAL_DEAD_STATUSES.has(status)) return "dead"
    // Unknown status string: fail-open, keep polling.
    return "live"
  }
  // No usable status and no 404 (e.g. network blip): fail-open.
  void fetchFailed
  return "live"
}

/** Where to land after a dead hydrated job: review when a plan/intake exists. */
export function stepAfterDeadJob(hasIntake: boolean): Step {
  return hasIntake ? "review" : "prompt"
}
