"use client"

import { useEffect, useRef, useReducer, useMemo, useCallback } from "react"
import { useParams, useRouter } from "next/navigation"
import { useIntake } from "@/hooks/use-intake"
import { useClarify } from "@/hooks/use-clarify"
import { useGenerateSpec } from "@/hooks/use-generate-spec"
import { useValidateSpec } from "@/hooks/use-validate-spec"
import { useGenerateScene } from "@/hooks/use-generate-scene"
import { usePublish } from "@/hooks/use-publish"
import { useJobStatus } from "@/hooks/use-job-status"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { api } from "@/lib/api"
import type { IntakeResult, ClarificationQuestion, ClarifyResult } from "@/types"

type Step = "prompt" | "clarify" | "review" | "generate" | "publish"
type GenerationStage = "spec" | "validation" | "scene" | "publish"

const STEPS: { key: Step; label: string }[] = [
  { key: "prompt", label: "Enter Prompt" },
  { key: "clarify", label: "Clarification" },
  { key: "review", label: "Review Spec" },
  { key: "generate", label: "Generate" },
  { key: "publish", label: "Publish" },
]

const MAX_PROMPT_LENGTH = 5000
const JOB_TIMEOUT_MS = 5 * 60 * 1000

// ---------------------------------------------------------------------------
// Reducer: consolidates the 9 previous useState calls into a single atomic
// workflow state to prevent out-of-sync step vs generationStage vs currentJobId.
// ---------------------------------------------------------------------------
type BuilderState = {
  step: Step
  prompt: string
  intakeResult: IntakeResult | null
  clarifyResult: ClarifyResult | null
  answers: Record<string, string>
  currentJobId: string | null
  generationStage: GenerationStage
  workflowError: string | null
}

type BuilderAction =
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

const initialState: BuilderState = {
  step: "prompt",
  prompt: "",
  intakeResult: null,
  clarifyResult: null,
  answers: {},
  currentJobId: null,
  generationStage: "spec",
  workflowError: null,
}

function builderReducer(state: BuilderState, action: BuilderAction): BuilderState {
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

function getErrorMessage(error: unknown, fallback: string): string {
  const anyErr = error as Record<string, unknown> | null
  // axios shape: error.response.data.detail can be string | {msg}[] | object
  const resp = (anyErr as { response?: { data?: { detail?: unknown } } } | null)?.response
  const detail = resp?.data?.detail
  if (typeof detail === "string" && detail.trim()) return detail
  if (Array.isArray(detail)) {
    const msgs = detail
      .map((d) => {
        if (typeof d === "string") return d
        if (d && typeof d === "object" && "msg" in (d as Record<string, unknown>)) return String((d as { msg: unknown }).msg)
        return ""
      })
      .filter(Boolean)
      .join("; ")
    if (msgs) return msgs
  }
  if (detail && typeof detail === "object") {
    try {
      return JSON.stringify(detail)
    } catch {
      // ignore
    }
  }
  // error.error is used by JobStatus
  if (anyErr && typeof (anyErr as { error?: unknown }).error === "string") return String((anyErr as { error: string }).error)
  if (anyErr && typeof (anyErr as { message?: unknown }).message === "string") return String((anyErr as { message: string }).message)
  return fallback
}

export default function BuilderPage() {
  const params = useParams()
  const router = useRouter()
  const projectId = Number(params.id)

  const [state, dispatch] = useReducer(builderReducer, initialState)
  const { step, prompt, intakeResult, clarifyResult, answers, currentJobId, generationStage, workflowError } = state

  // jobStartedAt as ref to avoid infinite loop on React 19 strict double mount
  const jobStartedAtRef = useRef<number | null>(null)
  const hasHydratedRef = useRef(false)

  const intake = useIntake(projectId)
  const clarify = useClarify(projectId)
  const generateSpec = useGenerateSpec(projectId)
  const validateSpec = useValidateSpec(projectId)
  const generateScene = useGenerateScene(projectId)
  const publish = usePublish(projectId)

  const jobStatus = useJobStatus(currentJobId, !!currentJobId)

  // keep mutation fns stable for workflow continuation (avoid effect restarts on object identity change)
  const validateSpecRef = useRef(validateSpec.mutateAsync)
  const generateSceneRef = useRef(generateScene.mutateAsync)
  useEffect(() => {
    validateSpecRef.current = validateSpec.mutateAsync
  }, [validateSpec.mutateAsync])
  useEffect(() => {
    generateSceneRef.current = generateScene.mutateAsync
  }, [generateScene.mutateAsync])

  // ---------------------------------------------------------------------------
  // Persist across refresh: sessionStorage + URL ?run_id=
  // ---------------------------------------------------------------------------
  const storageKey = `builder:${projectId}`

  // hydrate once on mount
  useEffect(() => {
    if (hasHydratedRef.current) return
    hasHydratedRef.current = true
    if (typeof window === "undefined") return
    try {
      const raw = window.sessionStorage.getItem(storageKey)
      const urlParams = new URLSearchParams(window.location.search)
      const urlRunId = urlParams.get("run_id")
      let parsed: Partial<BuilderState> | null = null
      if (raw) {
        try {
          parsed = JSON.parse(raw) as Partial<BuilderState>
        } catch {
          parsed = null
        }
      }
      // URL takes precedence for run_id if mismatch, but we still hydrate other fields from storage
      if (parsed) {
        const hydrate: Partial<BuilderState> = {}
        if (typeof parsed.prompt === "string") hydrate.prompt = parsed.prompt.slice(0, MAX_PROMPT_LENGTH)
        if (parsed.intakeResult && typeof parsed.intakeResult === "object") hydrate.intakeResult = parsed.intakeResult as IntakeResult
        if (parsed.clarifyResult && typeof parsed.clarifyResult === "object") hydrate.clarifyResult = parsed.clarifyResult as ClarifyResult
        if (parsed.answers && typeof parsed.answers === "object") hydrate.answers = parsed.answers as Record<string, string>
        if (typeof parsed.currentJobId === "string" || parsed.currentJobId === null) hydrate.currentJobId = parsed.currentJobId as string | null
        if (parsed.step && (STEPS as readonly { key: string }[]).some((s) => s.key === parsed.step)) hydrate.step = parsed.step as Step
        if (parsed.generationStage && ["spec", "validation", "scene", "publish"].includes(parsed.generationStage as string))
          hydrate.generationStage = parsed.generationStage as GenerationStage
        // if URL run_id present and differs, prefer URL run_id by keeping intakeResult.run_id as urlRunId if needed
        if (urlRunId && hydrate.intakeResult && (hydrate.intakeResult as IntakeResult).run_id !== urlRunId) {
          // keep storage intakeResult but ensure URL consistency; do not override storage blindly
          // if storage has no run_id, synthesize
          if (!(hydrate.intakeResult as IntakeResult).run_id) {
            ;(hydrate.intakeResult as IntakeResult).run_id = urlRunId
          }
        } else if (urlRunId && !hydrate.intakeResult) {
          hydrate.intakeResult = { run_id: urlRunId } as unknown as IntakeResult
        }
        if (Object.keys(hydrate).length > 0) {
          dispatch({ type: "HYDRATE", payload: hydrate })
        }
      } else if (urlRunId) {
        // no storage but URL has run_id -> minimal hydrate to allow resume
        dispatch({ type: "HYDRATE", payload: { intakeResult: { run_id: urlRunId } as unknown as IntakeResult } })
      }
    } catch {
      // ignore hydration errors
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId])

  // persist on change
  useEffect(() => {
    if (!hasHydratedRef.current) return
    if (typeof window === "undefined") return
    try {
      const toPersist: Record<string, unknown> = {
        prompt,
        intakeResult,
        clarifyResult,
        answers,
        currentJobId,
        step,
        generationStage,
      }
      window.sessionStorage.setItem(storageKey, JSON.stringify(toPersist))
      // sync run_id to URL
      const runId = intakeResult?.run_id ?? clarifyResult?.run_id ?? null
      if (runId) {
        const url = new URL(window.location.href)
        if (url.searchParams.get("run_id") !== runId) {
          url.searchParams.set("run_id", runId)
          window.history.replaceState(null, "", url.toString())
        }
      }
    } catch {
      // quota or serialization error -> ignore
    }
  }, [prompt, intakeResult, clarifyResult, answers, currentJobId, step, generationStage, storageKey])

  // ---------------------------------------------------------------------------
  // jobStartedAt ref sync + interval timeout check (not only on status change)
  // ---------------------------------------------------------------------------
  useEffect(() => {
    if (!currentJobId) {
      jobStartedAtRef.current = null
      return
    }
    // set start time on new job
    if (jobStartedAtRef.current === null) {
      jobStartedAtRef.current = Date.now()
    }
    const intervalId = window.setInterval(() => {
      if (jobStartedAtRef.current && Date.now() - jobStartedAtRef.current > JOB_TIMEOUT_MS) {
        dispatch({ type: "SET_ERROR", payload: "Job timed out after 5 minutes. Please retry." })
        dispatch({ type: "SET_JOB", payload: null })
        jobStartedAtRef.current = null
        window.clearInterval(intervalId)
      }
    }, 1000)
    return () => window.clearInterval(intervalId)
  }, [currentJobId])

  // ---------------------------------------------------------------------------
  // Workflow continuation: spec -> validation -> scene -> publish
  // Controlled deps avoid mutation object identity causing restarts; refs hold latest mutateAsync.
  // ---------------------------------------------------------------------------
  useEffect(() => {
    const status = jobStatus.data?.status as string | undefined
    if (!currentJobId || !status) return

    // terminal failure / cancel
    if (status === "failed" || status === "cancelled") {
      const detail = (jobStatus.data as unknown as { error?: string })?.error
      dispatch({ type: "SET_ERROR", payload: detail || getErrorMessage(jobStatus.data, "The workflow step failed. Please retry.") })
      dispatch({ type: "SET_JOB", payload: null })
      return
    }

    // still in progress -> do not continue; timeout interval handles stalled jobs
    if (["queued", "running", "retry", "validating_spec", "generating_scene", "pending"].includes(status)) return

    // completed -> chain next stage
    if (status !== "completed") return

    let cancelled = false
    const continueWorkflow = async () => {
      try {
        dispatch({ type: "SET_ERROR", payload: null })
        if (generationStage === "spec") {
          const result = await validateSpecRef.current()
          if (!cancelled) {
            dispatch({ type: "SET_WORKFLOW", payload: { generationStage: "validation", currentJobId: result.job_id, workflowError: null } })
            jobStartedAtRef.current = Date.now()
          }
        } else if (generationStage === "validation") {
          const result = await generateSceneRef.current()
          if (!cancelled) {
            dispatch({ type: "SET_WORKFLOW", payload: { generationStage: "scene", currentJobId: result.job_id, workflowError: null } })
            jobStartedAtRef.current = Date.now()
          }
        } else if (generationStage === "scene") {
          if (!cancelled) {
            dispatch({ type: "SET_WORKFLOW", payload: { currentJobId: null, step: "publish" } })
            jobStartedAtRef.current = null
          }
        } else if (generationStage === "publish") {
          if (!cancelled) {
            dispatch({ type: "SET_JOB", payload: null })
            jobStartedAtRef.current = null
            router.replace(`/projects/${projectId}/stream`)
          }
        }
      } catch (error: unknown) {
        if (!cancelled) {
          dispatch({ type: "SET_ERROR", payload: getErrorMessage(error, "The workflow could not continue.") })
          dispatch({ type: "SET_JOB", payload: null })
          jobStartedAtRef.current = null
        }
      }
    }
    void continueWorkflow()
    return () => {
      cancelled = true
    }
  }, [currentJobId, jobStatus.data, generationStage, projectId, router])

  const stepIndex = STEPS.findIndex((s) => s.key === step)

  // ---------------------------------------------------------------------------
  // Derived questions without fragile heuristic: use backend field directly
  // ---------------------------------------------------------------------------
  const displayQuestions: ClarificationQuestion[] = useMemo(() => {
    if (clarifyResult?.remaining_questions?.length) {
      return clarifyResult.remaining_questions
    }
    if (!intakeResult?.suggested_questions?.length) return []
    return intakeResult.suggested_questions.map((q) => {
      // suggested_questions is string[] per IntakeResult; handle both string and object defensively
      if (typeof q === "string") {
        return {
          field: q,
          question: q,
          type: "text",
          options: [],
          required: true,
        } as ClarificationQuestion
      }
      const obj = q as unknown as Record<string, unknown>
      const field = (obj.field as string) || (obj.question as string) || String(q)
      const question = (obj.question as string) || String(q)
      const type = (obj.type as string) || "text"
      const options = Array.isArray(obj.options) ? (obj.options as string[]) : []
      const required = typeof obj.required === "boolean" ? (obj.required as boolean) : true
      return { field, question, type, options, required } as ClarificationQuestion
    })
  }, [clarifyResult, intakeResult])

  // ---------------------------------------------------------------------------
  // Handlers
  // ---------------------------------------------------------------------------
  const handleIntake = useCallback(async () => {
    const trimmed = prompt.trim()
    if (!trimmed) return
    // enforce maxLength even if bypassed
    const safePrompt = trimmed.slice(0, MAX_PROMPT_LENGTH)
    if (safePrompt !== trimmed) {
      dispatch({ type: "SET_PROMPT", payload: safePrompt })
    }
    try {
      dispatch({ type: "SET_ERROR", payload: null })
      const result = await intake.mutateAsync({ prompt: safePrompt })
      dispatch({ type: "SET_INTAKE_RESULT", payload: result })
      // Fix step logic: consider both missing_fields and suggested_questions
      // Backend stage is "clarification" iff missing_fields non-empty, but suggested_questions may also indicate need.
      // Use both for robustness: if either array has items -> clarify.
      const hasMissing = Array.isArray(result.missing_fields) && result.missing_fields.length > 0
      const hasQuestions = Array.isArray(result.suggested_questions) && result.suggested_questions.length > 0
      const needsClarify = hasMissing || hasQuestions
      dispatch({ type: "SET_STEP", payload: needsClarify ? "clarify" : "review" })
    } catch (error: unknown) {
      dispatch({ type: "SET_ERROR", payload: getErrorMessage(error, "Unable to analyze the prompt.") })
    }
  }, [prompt, intake])

  const handleClarify = useCallback(async () => {
    try {
      dispatch({ type: "SET_ERROR", payload: null })
      const result = await clarify.mutateAsync({
        answers,
        run_id: intakeResult?.run_id,
        current_intake: (intakeResult as unknown as Record<string, unknown>) || {},
      })
      dispatch({ type: "SET_CLARIFY_RESULT", payload: result as ClarifyResult })
      if (result.ready_for_generation || result.remaining_questions.length === 0) dispatch({ type: "SET_STEP", payload: "review" })
      else dispatch({ type: "SET_ERROR", payload: "Please answer the remaining required questions." })
    } catch (error: unknown) {
      dispatch({ type: "SET_ERROR", payload: getErrorMessage(error, "Unable to save clarification answers.") })
    }
  }, [answers, clarify, intakeResult])

  const handleGenerateSpec = useCallback(async () => {
    try {
      dispatch({ type: "SET_ERROR", payload: null })
      const result = await generateSpec.mutateAsync({
        prompt: prompt.slice(0, MAX_PROMPT_LENGTH),
        run_id: intakeResult?.run_id,
        clarification_answers: answers,
      })
      dispatch({
        type: "SET_WORKFLOW",
        payload: { generationStage: "spec", currentJobId: result.job_id, step: "generate", workflowError: null },
      })
      jobStartedAtRef.current = Date.now()
    } catch (error: unknown) {
      dispatch({ type: "SET_ERROR", payload: getErrorMessage(error, "Unable to start specification generation.") })
    }
  }, [prompt, intakeResult, answers, generateSpec])

  const handlePublish = useCallback(async () => {
    try {
      dispatch({ type: "SET_ERROR", payload: null })
      const result = await publish.mutateAsync()
      dispatch({ type: "SET_WORKFLOW", payload: { generationStage: "publish", currentJobId: result.job_id } })
      jobStartedAtRef.current = Date.now()
    } catch (error: unknown) {
      dispatch({ type: "SET_ERROR", payload: getErrorMessage(error, "Unable to publish the simulation.") })
    }
  }, [publish])

  const handleCancel = useCallback(async () => {
    if (!currentJobId) return
    try {
      // best effort: try backend cancel endpoint (queue.cancel_job) if exposed
      await api.post(`/v1/jobs/${currentJobId}/cancel`).catch(() => null)
    } finally {
      dispatch({ type: "SET_ERROR", payload: "Job cancelled." })
      dispatch({ type: "SET_JOB", payload: null })
      jobStartedAtRef.current = null
    }
  }, [currentJobId])

  const promptRemaining = MAX_PROMPT_LENGTH - prompt.length
  const isPromptOverLimit = prompt.length > MAX_PROMPT_LENGTH

  // progress for aria-live generation stage
  const jobProgressRaw = (jobStatus.data as unknown as { progress?: unknown } | undefined)?.progress
  const jobProgress =
    typeof jobProgressRaw === "number" ? Math.max(0, Math.min(100, Math.round(jobProgressRaw))) : null
  const jobErrorDetail =
    (jobStatus.data as unknown as { error?: unknown } | undefined)?.error ||
    (jobStatus.error as unknown as string | undefined) ||
    null

  return (
    <div className="max-w-3xl mx-auto">
      <div className="mb-6">
        <p className="text-sm text-muted-foreground">Project {projectId}</p>
        <h2 className="text-2xl font-bold">Create Simulation</h2>
        <p className="text-muted-foreground">Build a validated simulation package ready for streaming.</p>
      </div>

      {workflowError && (
        <div role="alert" aria-live="assertive" className="mb-4 rounded-md bg-destructive/15 p-3 text-sm text-destructive">
          {workflowError}
        </div>
      )}

      {/* Step indicator: a11y with progressbar + aria-current */}
      <nav aria-label="Build steps" className="mb-8">
        <div
          role="progressbar"
          aria-valuenow={stepIndex + 1}
          aria-valuemin={1}
          aria-valuemax={STEPS.length}
          aria-valuetext={`Step ${stepIndex + 1} of ${STEPS.length}: ${STEPS[stepIndex]?.label ?? step}`}
          className="sr-only"
        />
        <ol className="flex items-center">
          {STEPS.map((s, i) => {
            const isCompleted = i < stepIndex
            const isCurrent = i === stepIndex
            const isUpcoming = i > stepIndex
            return (
              <li key={s.key} className="flex items-center" aria-current={isCurrent ? "step" : undefined}>
                <div
                  className={`flex items-center justify-center w-8 h-8 rounded-full text-sm font-medium ${
                    isCompleted || isCurrent ? "bg-primary text-primary-foreground" : "bg-gray-200 text-gray-500"
                  }`}
                  aria-hidden="true"
                >
                  {i + 1}
                </div>
                <span
                  className={`ml-2 text-sm ${isCurrent ? "text-foreground font-semibold" : isCompleted ? "text-foreground" : "text-muted-foreground"}`}
                >
                  {s.label}
                </span>
                {i < STEPS.length - 1 && (
                  <div className={`w-8 h-px mx-4 ${isCompleted ? "bg-primary" : "bg-gray-300"}`} aria-hidden="true" />
                )}
                {/* screen reader step status */}
                <span className="sr-only">
                  {isCurrent ? " (current)" : isCompleted ? " (completed)" : isUpcoming ? " (upcoming)" : ""}
                </span>
              </li>
            )
          })}
        </ol>
      </nav>

      {/* Step 1: Prompt */}
      {step === "prompt" && (
        <Card>
          <CardHeader>
            <CardTitle>Describe Your Simulation</CardTitle>
            <CardDescription>Enter a natural language description of the walkthrough you want to create</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="simulation-prompt">Prompt</Label>
              <textarea
                id="simulation-prompt"
                className="flex min-h-[120px] w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                placeholder="e.g., A modern 3-bedroom apartment with open kitchen, floor-to-ceiling windows, and city view..."
                value={prompt}
                onChange={(e) => dispatch({ type: "SET_PROMPT", payload: e.target.value.slice(0, MAX_PROMPT_LENGTH) })}
                maxLength={MAX_PROMPT_LENGTH}
                aria-describedby="prompt-help prompt-count"
                aria-invalid={isPromptOverLimit || undefined}
                rows={5}
              />
              <div className="flex justify-between text-xs">
                <span id="prompt-help" className="text-muted-foreground">
                  Max {MAX_PROMPT_LENGTH} characters. Be specific for better results.
                </span>
                <span
                  id="prompt-count"
                  aria-live="polite"
                  className={promptRemaining < 100 ? "text-amber-600 font-medium" : "text-muted-foreground"}
                >
                  {prompt.length}/{MAX_PROMPT_LENGTH}
                </span>
              </div>
            </div>
            {intake.isError && (
              <div role="alert" className="rounded-md bg-destructive/15 p-3 text-sm text-destructive">
                {getErrorMessage(intake.error, "Unable to analyze the prompt.")}
              </div>
            )}
            <Button onClick={handleIntake} disabled={!prompt.trim() || intake.isPending || isPromptOverLimit}>
              {intake.isPending ? "Analyzing..." : "Analyze Prompt"}
            </Button>
          </CardContent>
        </Card>
      )}

      {/* Step 2: Clarification */}
      {step === "clarify" && intakeResult && (
        <Card>
          <CardHeader>
            <CardTitle>Clarification</CardTitle>
            <CardDescription>Answer a few questions to refine your simulation</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {displayQuestions.length === 0 ? (
              <p className="text-sm text-muted-foreground">No clarification needed. Continue to review.</p>
            ) : (
              displayQuestions.map((q, i) => {
                const field = q.field || q.question || String(q)
                const question = q.question || String(q)
                const type = q.type || "text"
                const options: string[] = q.options || []
                return (
                  <div key={field + i} className="space-y-2">
                    <Label htmlFor={`clarify-${field}`}>
                      {question} {q.required === false ? "(optional)" : ""}
                    </Label>
                    {type === "choice" && options.length ? (
                      <select
                        id={`clarify-${field}`}
                        className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                        value={answers[field] || ""}
                        onChange={(e) => dispatch({ type: "SET_ANSWER", payload: { field, value: e.target.value } })}
                      >
                        <option value="">Select...</option>
                        {options.map((o: string) => (
                          <option key={o} value={o}>
                            {o}
                          </option>
                        ))}
                      </select>
                    ) : type === "boolean" ? (
                      <select
                        id={`clarify-${field}`}
                        className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                        value={answers[field] || ""}
                        onChange={(e) => dispatch({ type: "SET_ANSWER", payload: { field, value: e.target.value } })}
                      >
                        <option value="">Select...</option>
                        <option value="yes">Yes</option>
                        <option value="no">No</option>
                      </select>
                    ) : (
                      <Input
                        id={`clarify-${field}`}
                        placeholder="Your answer..."
                        value={answers[field] || ""}
                        onChange={(e) => dispatch({ type: "SET_ANSWER", payload: { field, value: e.target.value } })}
                      />
                    )}
                  </div>
                )
              })
            )}
            {clarify.isError && (
              <div role="alert" className="rounded-md bg-destructive/15 p-3 text-sm text-destructive">
                {getErrorMessage(clarify.error, "Unable to save clarification answers.")}
              </div>
            )}
            <div className="flex gap-2">
              <Button variant="outline" onClick={() => dispatch({ type: "SET_STEP", payload: "prompt" })}>
                Back
              </Button>
              <Button onClick={handleClarify} disabled={clarify.isPending}>
                {clarify.isPending ? "Processing..." : "Continue"}
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Step 3: Review Spec */}
      {step === "review" && (
        <Card>
          <CardHeader>
            <CardTitle>Review Specification</CardTitle>
            <CardDescription>Review the generated simulation specification</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {intakeResult && (
              <div className="rounded-md bg-muted p-4 text-sm font-mono overflow-auto max-h-64">
                <pre>{JSON.stringify(intakeResult.extracted_entities, null, 2)}</pre>
              </div>
            )}
            {clarifyResult && (
              <div className="rounded-md bg-muted p-4 text-sm font-mono overflow-auto max-h-64">
                <pre>{JSON.stringify(clarifyResult.updated_fields ?? clarifyResult, null, 2)}</pre>
              </div>
            )}
            <p className="text-sm text-muted-foreground">
              The worker will create and validate the structured Simulation Specification before building the scene.
            </p>
            <div className="flex gap-2">
              <Button variant="outline" onClick={() => dispatch({ type: "SET_STEP", payload: "clarify" })}>
                Back
              </Button>
              <Button onClick={handleGenerateSpec} disabled={generateSpec.isPending || !!currentJobId}>
                {generateSpec.isPending ? "Generating..." : "Generate Specification"}
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Step 4: Generate */}
      {step === "generate" && (
        <Card>
          <CardHeader>
            <CardTitle>Building Simulation</CardTitle>
            <CardDescription>
              {generationStage === "spec"
                ? "Creating the structured specification..."
                : generationStage === "validation"
                  ? "Validating the specification..."
                  : "Generating the 3D scene package..."}
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {/* spinner with aria */}
            <div className="flex items-center justify-center py-8" role="status" aria-live="polite" aria-busy={!!currentJobId}>
              <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary" aria-hidden="true" />
              <span className="sr-only">Building simulation, please wait</span>
            </div>

            {/* progress % + bar */}
            <div className="space-y-2" aria-live="polite" aria-atomic="true">
              <div className="flex items-center justify-between text-sm">
                <p className="text-muted-foreground">{jobStatus.data?.message || "The worker is processing your request."}</p>
                {jobProgress !== null && <span className="font-medium tabular-nums">{jobProgress}%</span>}
              </div>
              {jobProgress !== null && (
                <div
                  role="progressbar"
                  aria-valuenow={jobProgress}
                  aria-valuemin={0}
                  aria-valuemax={100}
                  aria-label="Generation progress"
                  className="h-2 w-full overflow-hidden rounded-full bg-secondary"
                >
                  <div
                    className="h-full bg-primary transition-all duration-500 ease-out"
                    style={{ width: `${jobProgress}%` }}
                  />
                </div>
              )}
              {jobProgress === null && currentJobId && (
                <div
                  role="progressbar"
                  aria-valuenow={undefined}
                  aria-valuemin={0}
                  aria-valuemax={100}
                  aria-label="Generation progress indeterminate"
                  className="h-2 w-full overflow-hidden rounded-full bg-secondary"
                >
                  <div className="h-full w-1/3 animate-pulse bg-primary/60" style={{ width: "100%" }} />
                </div>
              )}
            </div>

            {jobStatus.data?.status === "failed" && (
              <div role="alert" className="rounded-md bg-destructive/15 p-3 text-sm text-destructive text-center">
                <p className="font-medium">Generation failed.</p>
                {jobErrorDetail ? (
                  <p className="mt-1 opacity-90 break-words">{String(jobErrorDetail)}</p>
                ) : (
                  <p className="mt-1 opacity-90">Please try again.</p>
                )}
              </div>
            )}
            {workflowError && jobStatus.data?.status !== "failed" && (
              <div role="alert" className="rounded-md bg-destructive/15 p-3 text-sm text-destructive text-center">
                {workflowError}
              </div>
            )}

            <div className="flex justify-center gap-2">
              <Button
                variant="outline"
                onClick={handleCancel}
                disabled={!currentJobId || jobStatus.data?.status === "failed"}
                aria-label="Cancel generation"
              >
                Cancel
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Step 5: Publish */}
      {step === "publish" && (
        <Card>
          <CardHeader>
            <CardTitle>Publish</CardTitle>
            <CardDescription>Your simulation is ready to stream</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="text-center py-8">
              <div className="text-6xl mb-4" aria-hidden="true">
                🎉
              </div>
              <h3 className="text-lg font-semibold">Simulation Ready!</h3>
              <p className="text-muted-foreground mt-2">Your walkthrough has been generated and is ready to stream.</p>
            </div>

            {/* if publish job is running, show progress similarly */}
            {currentJobId && (
              <div className="space-y-2" aria-live="polite" aria-busy="true">
                <div className="flex items-center justify-center py-4" role="status">
                  <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary" aria-hidden="true" />
                  <span className="sr-only">Publishing simulation</span>
                </div>
                <p className="text-center text-sm text-muted-foreground">
                  {jobStatus.data?.message || "Publishing..."}
                </p>
                {jobProgress !== null && (
                  <div
                    role="progressbar"
                    aria-valuenow={jobProgress}
                    aria-valuemin={0}
                    aria-valuemax={100}
                    aria-label="Publish progress"
                    className="h-2 w-full overflow-hidden rounded-full bg-secondary"
                  >
                    <div className="h-full bg-primary transition-all" style={{ width: `${jobProgress}%` }} />
                  </div>
                )}
                <div className="flex justify-center">
                  <Button variant="outline" onClick={handleCancel} disabled={!currentJobId}>
                    Cancel
                  </Button>
                </div>
              </div>
            )}

            <div className="flex gap-2 justify-center">
              <Button variant="outline" onClick={() => router.push(`/projects/${projectId}`)}>
                Back to Project
              </Button>
              <Button onClick={handlePublish} disabled={publish.isPending || !!currentJobId}>
                {publish.isPending ? "Publishing..." : "Publish & Stream"}
              </Button>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  )
}
