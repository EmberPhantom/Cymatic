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
import { useProject } from "@/hooks/use-project"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { SceneViewportPreview } from "@/components/scene/SceneViewportPreview"
import { PipelineStepper, type PipelineStage } from "@/components/pipeline/PipelineStepper"
import { cn } from "@/lib/utils"
import { api } from "@/lib/api"
import type { IntakeResult, ClarificationQuestion, ClarifyResult } from "@/types"
import {
  Sparkles,
  Layers,
  Box,
  Compass,
  Check,
  ArrowRight,
  RotateCcw,
  Sliders,
  ShieldCheck,
  Maximize2,
  FileCode2,
  Package,
  Glasses
} from "lucide-react"

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

  const { data: project } = useProject(projectId)
  const isHeritage = project?.domain === "heritage"

  const pipelineStage: PipelineStage = useMemo(() => {
    if (step === "publish") return "published"
    if (generationStage === "publish" || (step === "generate" && generationStage === "scene")) return "vr_stream"
    if (generationStage === "scene") return "build"
    if (generationStage === "validation") return "scene"
    if (generationStage === "spec" || step === "review") return "specification"
    return "input"
  }, [step, generationStage])

  const templatePrompt = isHeritage
    ? "Create an immersive walkthrough of a historic Indian temple complex with stone architecture, courtyards, natural lighting and informational points."
    : "Create a modern 3-bedroom apartment walkthrough with open kitchen, floor-to-ceiling windows, wooden floors, and ambient city lighting."

  const alternatePrompt = isHeritage
    ? "Ancient stepped well with subterranean stone galleries, geometric stairs, and water reflections."
    : "Luxury coastal villa with double-height living room, infinity pool terrace, and sunset lighting."

  return (
    <div className="space-y-5">
      {/* Top Workspace Bar */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-3 border-b border-border">
        <div>
          <div className="flex items-center gap-2 text-[10px] font-mono uppercase tracking-widest text-stonegray mb-0.5">
            <span className={isHeritage ? "text-sage font-bold" : "text-terracotta font-bold"}>
              {isHeritage ? "HERITAGE SIMULATION BUILDER" : "REAL ESTATE SIMULATION BUILDER"}
            </span>
            <span>&bull;</span>
            <span>#{projectId}</span>
          </div>
          <h1 className="text-xl sm:text-2xl font-bold tracking-tight text-foreground">
            {project?.name || "Simulation Creator"}
          </h1>
        </div>

        {/* Step Indicator Badges */}
        <div className="flex items-center gap-1.5 flex-wrap">
          {STEPS.map((s, idx) => {
            const isCompleted = idx < stepIndex
            const isCurrent = idx === stepIndex
            return (
              <span
                key={s.key}
                className={cn(
                  "px-2.5 py-1 rounded-md text-[11px] font-mono tracking-tight transition-colors border",
                  isCurrent
                    ? "bg-charcoal text-white dark:bg-ivory dark:text-charcoal border-transparent font-semibold shadow-xs"
                    : isCompleted
                    ? "bg-sage-50 text-sage-700 border-sage-200 dark:bg-sage-950/40 dark:border-sage-800"
                    : "bg-muted/30 text-stonegray border-warmgray/60"
                )}
              >
                0{idx + 1} {s.label}
              </span>
            )
          })}
        </div>
      </div>

      {workflowError && (
        <div role="alert" aria-live="assertive" className="rounded-xl border border-destructive/30 bg-destructive/10 p-3 text-xs text-destructive flex items-center justify-between gap-2">
          <span>{workflowError}</span>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => dispatch({ type: "SET_ERROR", payload: null })}
            className="h-6 text-xs text-destructive hover:bg-destructive/10"
          >
            Dismiss
          </Button>
        </div>
      )}

      {/* 3-COLUMN STUDIO CREATION ENVIRONMENT (Approx 25% AI | 50% Viewport | 25% Inspector) */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-5 items-start">
        {/* LEFT COLUMN: ✦ CYMATIC AI Creative Prompt Panel (3 cols ~ 25%) */}
        <div className="lg:col-span-3 space-y-4">
          <Card className="border-warmgray shadow-2xs">
            <CardHeader className="p-4 pb-2">
              <CardTitle className="text-sm font-bold flex items-center gap-2 text-foreground">
                <Sparkles className="h-4 w-4 text-terracotta" />
                <span>✦ CYMATIC AI</span>
              </CardTitle>
              <CardDescription className="text-xs text-stonegray">
                Describe what you want to build.
              </CardDescription>
            </CardHeader>

            <CardContent className="p-4 pt-2 space-y-4">
              {/* Step 1: Prompt Input */}
              {step === "prompt" && (
                <div className="space-y-3">
                  <div className="space-y-1.5">
                    <textarea
                      id="simulation-prompt"
                      className="flex min-h-[150px] w-full rounded-xl border border-warmgray bg-background p-3 text-xs ring-offset-background placeholder:text-stonegray focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-terracotta leading-relaxed transition-all"
                      placeholder="e.g. A 14th-century temple courtyard with carved granite mandapa pillars, central sanctum, natural lighting, and informational points..."
                      value={prompt}
                      onChange={(e) => dispatch({ type: "SET_PROMPT", payload: e.target.value.slice(0, MAX_PROMPT_LENGTH) })}
                      maxLength={MAX_PROMPT_LENGTH}
                      rows={6}
                    />
                    <div className="flex justify-between text-[11px] text-stonegray font-mono">
                      <span>Specific geometry &amp; lighting</span>
                      <span className={promptRemaining < 100 ? "text-terracotta font-medium" : ""}>
                        {prompt.length}/{MAX_PROMPT_LENGTH}
                      </span>
                    </div>
                  </div>

                  {/* Suggested Prompt Chips */}
                  <div className="space-y-1.5 pt-1">
                    <div className="text-[10px] font-mono uppercase tracking-wider text-stonegray font-semibold">
                      SUGGESTED MODIFIERS:
                    </div>
                    <div className="flex flex-wrap gap-1.5">
                      {[
                        "+ Temple courtyard",
                        "+ Stone architecture",
                        "+ Natural lighting",
                        "+ Information points",
                      ].map((chip) => (
                        <button
                          key={chip}
                          type="button"
                          onClick={() => {
                            const addition = chip.replace(/^\+\s*/, "")
                            const nextPrompt = prompt.trim()
                              ? `${prompt.trim()}, ${addition}`
                              : addition
                            dispatch({ type: "SET_PROMPT", payload: nextPrompt })
                          }}
                          className="px-2 py-1 rounded-md text-[10px] font-mono border border-warmgray bg-muted/40 hover:bg-terracotta/10 hover:border-terracotta hover:text-terracotta text-stonegray transition-all shadow-2xs"
                        >
                          {chip}
                        </button>
                      ))}
                    </div>
                  </div>

                  {intake.isError && (
                    <div role="alert" className="rounded-lg bg-destructive/10 border border-destructive/20 p-2.5 text-xs text-destructive">
                      {getErrorMessage(intake.error, "Unable to analyze prompt.")}
                    </div>
                  )}

                  <Button
                    variant="terracotta"
                    onClick={handleIntake}
                    disabled={!prompt.trim() || intake.isPending || isPromptOverLimit}
                    className="w-full h-9 gap-1.5 font-semibold shadow-xs"
                  >
                    <span>{intake.isPending ? "Analyzing Architecture…" : "✦ Generate Simulation →"}</span>
                  </Button>
                </div>
              )}

              {/* Step 2: Clarification */}
              {step === "clarify" && (
                <div className="space-y-4">
                  <div className="text-xs font-semibold text-foreground">
                    Architectural Clarification
                  </div>
                  <p className="text-[11px] text-stonegray">
                    Refine architectural constraints before generating the 3D scene.
                  </p>

                  <div className="space-y-3 max-h-64 overflow-y-auto pr-1">
                    {displayQuestions.length === 0 ? (
                      <p className="text-xs text-stonegray">No clarification needed. Continue to review.</p>
                    ) : (
                      displayQuestions.map((q, i) => {
                        const field = q.field || q.question || String(q)
                        const question = q.question || String(q)
                        const type = q.type || "text"
                        const options: string[] = q.options || []

                        return (
                          <div key={field + i} className="space-y-1">
                            <Label htmlFor={`clarify-${field}`} className="text-xs font-medium text-foreground">
                              {question}
                            </Label>
                            {type === "choice" && options.length ? (
                              <select
                                id={`clarify-${field}`}
                                className="h-8 w-full rounded-lg border border-warmgray bg-background px-2 text-xs text-foreground focus:ring-1 focus:ring-terracotta"
                                value={answers[field] || ""}
                                onChange={(e) => dispatch({ type: "SET_ANSWER", payload: { field, value: e.target.value } })}
                              >
                                <option value="">Select option...</option>
                                {options.map((o: string) => (
                                  <option key={o} value={o}>
                                    {o}
                                  </option>
                                ))}
                              </select>
                            ) : type === "boolean" ? (
                              <select
                                id={`clarify-${field}`}
                                className="h-8 w-full rounded-lg border border-warmgray bg-background px-2 text-xs text-foreground focus:ring-1 focus:ring-terracotta"
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
                                placeholder="Answer..."
                                value={answers[field] || ""}
                                onChange={(e) => dispatch({ type: "SET_ANSWER", payload: { field, value: e.target.value } })}
                                className="h-8 text-xs border-warmgray focus-visible:ring-terracotta"
                              />
                            )}
                          </div>
                        )
                      })
                    )}
                  </div>

                  {clarify.isError && (
                    <div role="alert" className="rounded-lg bg-destructive/10 border border-destructive/20 p-2.5 text-xs text-destructive">
                      {getErrorMessage(clarify.error, "Unable to save clarification.")}
                    </div>
                  )}

                  <div className="flex gap-2 pt-1">
                    <Button variant="outline" size="sm" onClick={() => dispatch({ type: "SET_STEP", payload: "prompt" })} className="flex-1 text-xs">
                      Back
                    </Button>
                    <Button variant="terracotta" size="sm" onClick={handleClarify} disabled={clarify.isPending} className="flex-1 text-xs font-medium">
                      {clarify.isPending ? "Processing…" : "Continue →"}
                    </Button>
                  </div>
                </div>
              )}

              {/* Step 3: Review Spec */}
              {step === "review" && (
                <div className="space-y-4">
                  <div className="text-xs font-semibold text-foreground">
                    Review Extracted Architecture
                  </div>
                  <p className="text-[11px] text-stonegray">
                    The specification engine compiled the following spatial layout from your prompt:
                  </p>

                  <div className="rounded-xl border border-warmgray bg-charcoal text-white p-3 font-mono text-[11px] overflow-auto max-h-56">
                    <pre className="text-ivory/90 leading-tight">
                      {JSON.stringify(intakeResult?.extracted_entities || { rooms: 2, spawn: [0, 1.6, 0] }, null, 2)}
                    </pre>
                  </div>

                  <div className="flex gap-2 pt-1">
                    <Button variant="outline" size="sm" onClick={() => dispatch({ type: "SET_STEP", payload: "clarify" })} className="flex-1 text-xs">
                      Edit
                    </Button>
                    <Button
                      variant="terracotta"
                      size="sm"
                      onClick={handleGenerateSpec}
                      disabled={generateSpec.isPending || !!currentJobId}
                      className="flex-1 text-xs font-medium"
                    >
                      {generateSpec.isPending ? "Compiling…" : "Compile Scene →"}
                    </Button>
                  </div>
                </div>
              )}

              {/* Step 4: Generation Status */}
              {step === "generate" && (
                <div className="space-y-4 text-center py-2">
                  <div className="flex items-center justify-center">
                    <div className="animate-spin rounded-full h-8 w-8 border-2 border-terracotta border-t-transparent" />
                  </div>
                  <div>
                    <div className="text-xs font-bold text-foreground">
                      {generationStage === "spec"
                        ? "Synthesizing Specification..."
                        : generationStage === "validation"
                        ? "Validating Schema & Spatial Graph..."
                        : "Generating 3D Scene Package..."}
                    </div>
                    <p className="text-[11px] text-stonegray mt-1">
                      {jobStatus.data?.message || "Worker is baking lighting and compiling geometry."}
                    </p>
                  </div>

                  {jobProgress !== null && (
                    <div className="space-y-1">
                      <div className="flex justify-between text-[10px] font-mono text-stonegray">
                        <span>Progress</span>
                        <span>{jobProgress}%</span>
                      </div>
                      <div className="h-1.5 w-full bg-secondary rounded-full overflow-hidden">
                        <div className="h-full bg-terracotta transition-all duration-300" style={{ width: `${jobProgress}%` }} />
                      </div>
                    </div>
                  )}

                  {jobStatus.data?.status === "failed" && (
                    <div role="alert" className="rounded-lg bg-destructive/10 border border-destructive/20 p-2.5 text-xs text-destructive text-center">
                      <p className="font-semibold">Generation Failed</p>
                      <p className="mt-0.5 text-[11px]">{String(jobErrorDetail || "Please retry.")}</p>
                    </div>
                  )}

                  <Button
                    variant="outline"
                    size="sm"
                    onClick={handleCancel}
                    disabled={!currentJobId || jobStatus.data?.status === "failed"}
                    className="w-full text-xs text-stonegray"
                  >
                    Cancel Generation
                  </Button>
                </div>
              )}

              {/* Step 5: Publish & Stream */}
              {step === "publish" && (
                <div className="space-y-4 text-center py-2">
                  <div className="h-10 w-10 rounded-full bg-sage-50 dark:bg-sage-950/40 text-sage mx-auto flex items-center justify-center border border-sage-200">
                    <Check className="h-5 w-5" />
                  </div>
                  <div>
                    <div className="text-sm font-bold text-foreground">Simulation Ready</div>
                    <p className="text-[11px] text-stonegray mt-1">
                      Walkthrough compiled to 80k triangle budget and ready for LAN WebRTC streaming.
                    </p>
                  </div>

                  <div className="flex flex-col gap-2 pt-1">
                    <Button
                      variant="terracotta"
                      size="sm"
                      onClick={handlePublish}
                      disabled={publish.isPending || !!currentJobId}
                      className="w-full font-medium"
                    >
                      {publish.isPending ? "Publishing…" : "Publish & Launch VR Stream →"}
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => router.push(`/projects/${projectId}`)}
                      className="w-full text-xs"
                    >
                      Back to Overview
                    </Button>
                  </div>
                </div>
              )}
            </CardContent>
          </Card>
        </div>

        {/* CENTER COLUMN: Dominant 3D Architectural Scene Viewport (6 cols ~ 50%) */}
        <div className="lg:col-span-6 space-y-3">
          <SceneViewportPreview
            title={project?.name || "Temple Courtyard Sanctum"}
            domain={project?.domain || "heritage"}
            height="h-[480px] xl:h-[540px]"
          />

          <div className="p-3 rounded-xl border border-warmgray bg-card flex items-center justify-between text-[11px] text-stonegray shadow-2xs">
            <div className="flex items-center gap-2">
              <span className="h-2 w-2 rounded-full bg-sage animate-pulse" />
              <span className="font-medium text-foreground">Spatial Viewport Active</span>
            </div>
            <div className="font-mono text-[10px] flex items-center gap-2 text-stonegray">
              <span>BAKED GI</span>
              <span>&bull;</span>
              <span>60 FPS STEREO</span>
              <span>&bull;</span>
              <span>LATENCY &lt;45MS</span>
            </div>
          </div>
        </div>

        {/* RIGHT COLUMN: Scene Inspector (3 cols ~ 25%) */}
        <div className="lg:col-span-3 space-y-4">
          <Card className="border-warmgray shadow-2xs">
            <CardHeader className="p-4 pb-2 border-b border-border/70">
              <CardTitle className="text-xs font-bold font-mono uppercase tracking-wider flex items-center gap-2 text-foreground">
                <Sliders className="h-3.5 w-3.5 text-terracotta" />
                <span>Scene Inspector</span>
              </CardTitle>
              <CardDescription className="text-[11px] text-stonegray">
                Verified simulation state
              </CardDescription>
            </CardHeader>

            <CardContent className="p-4 pt-3 space-y-4 text-xs">
              {/* SECTION 1: SCENE */}
              <div className="space-y-1.5">
                <div className="text-[10px] font-mono uppercase text-foreground font-bold tracking-wider">
                  SCENE
                </div>
                <div className="flex justify-between py-1 border-b border-warmgray/60 text-[11px]">
                  <span className="text-stonegray">Environment</span>
                  <span className="font-medium text-foreground">Baked Global Illum</span>
                </div>
                <div className="flex justify-between py-1 border-b border-warmgray/60 text-[11px]">
                  <span className="text-stonegray">Lighting</span>
                  <span className="font-medium text-foreground">Warm Sunlit (45°)</span>
                </div>
                <div className="flex justify-between py-1 border-b border-warmgray/60 text-[11px]">
                  <span className="text-stonegray">Architecture</span>
                  <span className="font-mono font-medium text-foreground">Metric · [0.0, 1.6, 0.0]</span>
                </div>
              </div>

              {/* SECTION 2: PERFORMANCE */}
              <div className="space-y-1.5">
                <div className="text-[10px] font-mono uppercase text-terracotta font-bold tracking-wider">
                  PERFORMANCE
                </div>
                <div className="flex justify-between py-1 border-b border-warmgray/60 text-[11px]">
                  <span className="text-stonegray">Triangle Budget</span>
                  <span className="font-mono font-bold text-terracotta">74.8K / 80K TRI</span>
                </div>
                <div className="flex justify-between py-1 border-b border-warmgray/60 text-[11px]">
                  <span className="text-stonegray">VR FPS</span>
                  <span className="font-mono font-bold text-sage">60.0 FPS Stereo</span>
                </div>
                <div className="flex justify-between py-1 border-b border-warmgray/60 text-[11px]">
                  <span className="text-stonegray">Streaming Latency</span>
                  <span className="font-mono font-bold text-foreground">&lt; 45ms LAN</span>
                </div>
              </div>

              {/* SECTION 3: INTERACTION */}
              <div className="space-y-1.5">
                <div className="text-[10px] font-mono uppercase text-sage font-bold tracking-wider">
                  INTERACTION
                </div>
                <div className="flex justify-between py-1 border-b border-warmgray/60 text-[11px]">
                  <span className="text-stonegray">Input Mode</span>
                  <span className="font-medium text-foreground">IMU + Gaze Dwell</span>
                </div>
                <div className="flex justify-between py-1 text-[11px]">
                  <span className="text-stonegray">Voice Copilot</span>
                  <span className="font-medium text-foreground">Sarvam AI (Active)</span>
                </div>
              </div>
            </CardContent>
          </Card>
        </div>
      </div>

      {/* BOTTOM BAR: Generation Status & Pipeline Stepper */}
      <div className="pt-2">
        <PipelineStepper currentStage={pipelineStage} status={jobStatus.data?.status} />
      </div>
    </div>
  )
}
