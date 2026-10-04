"use client"

import { useEffect, useRef, useReducer, useMemo, useCallback, useState } from "react"
import { useParams, useRouter } from "next/navigation"
import { useIntake } from "@/hooks/use-intake"
import { useClarify } from "@/hooks/use-clarify"
import { useGenerateSpec } from "@/hooks/use-generate-spec"
import { useBuildPlan, useApprovePlan, type PlanSheetResponse } from "@/hooks/use-plan"
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
import { getErrorMessage } from "@/lib/errors"
import { parseProjectId } from "@/lib/project-id"
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

import {
  builderReducer,
  initialBuilderState as initialState,
  BUILDER_STEPS as STEPS,
  sanitizeHydratedState,
  intakeFromGenerationRun,
  resolveHydratedJob,
  stepAfterDeadJob,
  MAX_PROMPT_LENGTH,
  type BuilderState,
} from "@/lib/builder-state"

type Step = BuilderState["step"]
type GenerationStage = BuilderState["generationStage"]

const JOB_TIMEOUT_MS = 5 * 60 * 1000

// ---------------------------------------------------------------------------
// Reducer + hydration helpers live in @/lib/builder-state (unit-tested).
// ---------------------------------------------------------------------------

export default function BuilderPage() {
  const params = useParams()
  const router = useRouter()
  // Guard the route param: an invalid id renders a local error state below
  // and never fires intake/clarify/generate hooks (same NaN pattern as
  // use-project.ts). Mutation hooks throw on null projectId as a second net.
  const projectId = parseProjectId(params.id)

  const [state, dispatch] = useReducer(builderReducer, initialState)
  const { step, prompt, intakeResult, clarifyResult, answers, currentJobId, generationStage, workflowError } = state

  // jobStartedAt as ref to avoid infinite loop on React 19 strict double mount
  const jobStartedAtRef = useRef<number | null>(null)
  const hasHydratedRef = useRef(false)

  const intake = useIntake(projectId)
  const clarify = useClarify(projectId)
  const generateSpec = useGenerateSpec(projectId)
  const buildPlan = useBuildPlan(projectId)
  const approvePlan = useApprovePlan(projectId)
  const [planSheet, setPlanSheet] = useState<PlanSheetResponse | null>(null)
  const planRunIdRef = useRef<string | null>(null)
  const validateSpec = useValidateSpec(projectId)
  const generateScene = useGenerateScene(projectId)
  const publish = usePublish(projectId)

  const jobStatus = useJobStatus(currentJobId, !!currentJobId)
  const { data: project } = useProject(projectId)

  // keep mutation fns stable for workflow continuation (avoid effect restarts on object identity change)
  const validateSpecRef = useRef(validateSpec.mutateAsync)
  const generateSceneRef = useRef(generateScene.mutateAsync)
  const approvePlanRef = useRef(approvePlan.mutateAsync)
  useEffect(() => {
    validateSpecRef.current = validateSpec.mutateAsync
  }, [validateSpec.mutateAsync])
  useEffect(() => {
    generateSceneRef.current = generateScene.mutateAsync
  }, [generateScene.mutateAsync])
  useEffect(() => {
    approvePlanRef.current = approvePlan.mutateAsync
  }, [approvePlan.mutateAsync])

  // ---------------------------------------------------------------------------
  // Persist across refresh: sessionStorage + URL ?run_id=
  // ---------------------------------------------------------------------------
  const storageKey = `builder:${projectId}`

  // hydrate once on mount
  useEffect(() => {
    if (hasHydratedRef.current) return
    hasHydratedRef.current = true
    if (typeof window === "undefined") return
    if (projectId === null) return
    let cancelled = false
    try {
      const raw = window.sessionStorage.getItem(storageKey)
      const urlParams = new URLSearchParams(window.location.search)
      const urlRunId = urlParams.get("run_id")
      let parsed: unknown = null
      if (raw) {
        try {
          parsed = JSON.parse(raw) as unknown
        } catch {
          parsed = null
        }
      }
      // Validated hydration: run_id-only payloads are NEVER promoted to a
      // full IntakeResult (no `as unknown as IntakeResult` casts) — they are
      // refetched from GET generation-runs/{runId} below.
      const { hydrate, pendingRunIdFetch } = sanitizeHydratedState(parsed, urlRunId)
      if (Object.keys(hydrate).length > 0) {
        dispatch({ type: "HYDRATE", payload: hydrate })
      }

      // Dead job rehydration: verify a restored currentJobId is still live
      // (single status poll) before the 5-minute window resumes. A dead/GC'd
      // job resets to review instead of the "Generation Interrupted" limbo.
      const hydratedJobId = hydrate.currentJobId
      if (typeof hydratedJobId === "string" && hydratedJobId) {
        api
          .get(`/v1/jobs/${encodeURIComponent(hydratedJobId)}/status`)
          .then((res) => {
            if (cancelled) return
            const status = (res.data as { status?: unknown } | undefined)?.status
            if (resolveHydratedJob(status, false, false) === "dead") {
              dispatch({ type: "RESET_JOB" })
              jobStartedAtRef.current = null
              dispatch({
                type: "SET_STEP",
                payload: stepAfterDeadJob(!!hydrate.intakeResult || !!pendingRunIdFetch),
              })
              dispatch({
                type: "SET_ERROR",
                payload: "The previous job is no longer running (it finished or expired). Your plan is kept — review and compile again.",
              })
            }
          })
          .catch((err: unknown) => {
            if (cancelled) return
            const httpStatus = (err as { response?: { status?: number } })?.response?.status
            if (resolveHydratedJob(undefined, true, httpStatus === 404) === "dead") {
              dispatch({ type: "RESET_JOB" })
              jobStartedAtRef.current = null
              dispatch({
                type: "SET_STEP",
                payload: stepAfterDeadJob(!!hydrate.intakeResult || !!pendingRunIdFetch),
              })
              dispatch({
                type: "SET_ERROR",
                payload: "The previous job is no longer available (it expired). Your plan is kept — review and compile again.",
              })
            }
            // fail-open on network blips: keep polling, timeout bounds the wait
          })
      }

      // run_id-only hydration: refetch the full intake result from the run.
      if (pendingRunIdFetch) {
        api
          .get(`/v1/projects/${projectId}/generation-runs/${encodeURIComponent(pendingRunIdFetch)}`)
          .then((res) => {
            if (cancelled) return
            const rebuilt = intakeFromGenerationRun(res.data)
            if (rebuilt) {
              dispatch({ type: "SET_INTAKE_RESULT", payload: rebuilt })
            } else {
              dispatch({ type: "SET_INTAKE_RESULT", payload: null })
              dispatch({
                type: "SET_ERROR",
                payload: "The previous session's details could not be restored. Please describe your idea again.",
              })
            }
          })
          .catch(() => {
            if (cancelled) return
            dispatch({ type: "SET_INTAKE_RESULT", payload: null })
            dispatch({
              type: "SET_ERROR",
              payload: "The previous session's details could not be restored. Please describe your idea again.",
            })
          })
      }
    } catch {
      // ignore hydration errors
    }
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId])

  // persist on change
  useEffect(() => {
    if (!hasHydratedRef.current) return
    if (typeof window === "undefined") return
    if (projectId === null) return
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
    // NOTE: Job statuses are only pending/queued/running/retry/completed/failed/
    // cancelled. Run stages like validating_spec/generating_scene live on
    // GenerationRun and must not block the job chain here.
    if (["queued", "running", "retry", "pending"].includes(status)) return

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
  // Derived questions: backend clarify returns canonical {field,...}; intake
  // returns string[] which we map to canonical fields so answers resolve.
  // ---------------------------------------------------------------------------
  const displayQuestions: ClarificationQuestion[] = useMemo(() => {
    if (clarifyResult?.remaining_questions?.length) {
      return clarifyResult.remaining_questions
    }
    if (!intakeResult?.suggested_questions?.length) return []
    const textToField: Record<string, string> = {
      "what architectural style do you prefer?": "style",
      "how many bedrooms and bathrooms do you need?": "bedrooms",
      "what's the approximate square footage?": "square_footage",
      "what's your budget range?": "budget",
      "how many floors/levels?": "floors",
      "do you need outdoor spaces? (garden, balcony, pool, etc.)": "outdoor_spaces",
      "any specific rooms required? (home office, gym, theater, etc.)": "special_rooms",
      "furnished or unfurnished?": "furnished",
      "what type of heritage site? (temple, palace, courtyard, monument, etc.)": "site_type",
      "what historical period or culture?": "historical_period",
      "what key points of interest should be highlighted?": "key_pois",
      "do you need guided narration? in what language(s)?": "narration",
      "what's the approximate area/scale?": "scale",
      "any specific architectural features to emphasize?": "focus",
      "indoor, outdoor, or mixed experience?": "indoor_outdoor",
      "educational focus or pure exploration?": "focus",
    }
    return intakeResult.suggested_questions.map((q) => {
      // suggested_questions is string[] per IntakeResult; handle both string and object defensively
      if (typeof q === "string") {
        const canonical = textToField[q.trim().toLowerCase()] ?? q
        // Numeric fields keep number semantics (with units/bounds) even when
        // the intake round only yields plain strings.
        const numberMeta: Record<string, { unit?: string; min_value?: number; max_value?: number }> = {
          bedrooms: { unit: "count", min_value: 1, max_value: 20 },
          bathrooms: { unit: "count", min_value: 1, max_value: 20 },
          square_footage: { unit: "sqft", min_value: 100, max_value: 100000 },
          floors: { unit: "count", min_value: 1, max_value: 10 },
        }
        const meta = numberMeta[canonical]
        return {
          field: canonical,
          question: q,
          type: meta ? "number" : "text",
          options: [],
          required: true,
          ...(meta ?? {}),
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
    if (projectId === null) return
    const trimmed = prompt.trim()
    if (!trimmed) return
    // enforce maxLength even if bypassed
    const safePrompt = trimmed.slice(0, MAX_PROMPT_LENGTH)
    if (safePrompt !== trimmed) {
      dispatch({ type: "SET_PROMPT", payload: safePrompt })
    }
    try {
      dispatch({ type: "SET_ERROR", payload: null })
      const result = await intake.mutateAsync({
        prompt: safePrompt,
        context: { project_domain: project?.domain },
      })
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
  }, [prompt, intake, project?.domain, projectId])

  const handleClarify = useCallback(async () => {
    if (projectId === null) return
    try {
      dispatch({ type: "SET_ERROR", payload: null })
      // Send the freshest known entities as base: prior clarify updated_fields
      // win over the original intake, so multi-round clarification accumulates
      // instead of resetting to round 1.
      const baseEntities = {
        ...(intakeResult?.extracted_entities ?? {}),
        ...(clarifyResult?.updated_fields ?? {}),
      }
      const result = await clarify.mutateAsync({
        answers,
        run_id: intakeResult?.run_id ?? clarifyResult?.run_id,
        current_intake: { ...(intakeResult ?? {}), extracted_entities: baseEntities },
      })
      dispatch({ type: "SET_CLARIFY_RESULT", payload: result as ClarifyResult })
      if (result.ready_for_generation || result.remaining_questions.length === 0) dispatch({ type: "SET_STEP", payload: "review" })
      else dispatch({ type: "SET_ERROR", payload: "Please answer the remaining required questions." })
    } catch (error: unknown) {
      dispatch({ type: "SET_ERROR", payload: getErrorMessage(error, "Unable to save clarification answers.") })
    }
  }, [answers, clarify, intakeResult, clarifyResult, projectId])

  const handleGenerateSpec = useCallback(async () => {
    if (projectId === null) return
    try {
      dispatch({ type: "SET_ERROR", payload: null })
      // Approval gate: freeze the reviewed plan sheet before generating.
      // Fail-open on plan errors (sheet is advisory until the job split
      // makes plan_sheet_id the generation input).
      const runId = intakeResult?.run_id ?? clarifyResult?.run_id
      if (runId && planSheet?.run_id === runId && planSheet.status !== "approved") {
        try {
          const approved = await approvePlanRef.current({ sheetId: planSheet.id })
          setPlanSheet(approved)
        } catch {
          // proceed to generation anyway; approval is advisory for now
        }
      }
      // Prefer LLM-normalized clarify fields over raw text inputs.
      const clarificationAnswers = {
        ...answers,
        ...(clarifyResult?.updated_fields ?? {}),
      }
      const result = await generateSpec.mutateAsync({
        prompt: prompt.slice(0, MAX_PROMPT_LENGTH),
        run_id: intakeResult?.run_id ?? clarifyResult?.run_id,
        clarification_answers: clarificationAnswers,
      })
      dispatch({
        type: "SET_WORKFLOW",
        payload: { generationStage: "spec", currentJobId: result.job_id, step: "generate", workflowError: null },
      })
      jobStartedAtRef.current = Date.now()
    } catch (error: unknown) {
      dispatch({ type: "SET_ERROR", payload: getErrorMessage(error, "Unable to start specification generation.") })
    }
  }, [prompt, intakeResult, clarifyResult, answers, generateSpec, planSheet, projectId])

  const handlePublish = useCallback(async () => {
    if (projectId === null) return
    try {
      dispatch({ type: "SET_ERROR", payload: null })
      const result = await publish.mutateAsync()
      dispatch({ type: "SET_WORKFLOW", payload: { generationStage: "publish", currentJobId: result.job_id } })
      jobStartedAtRef.current = Date.now()
    } catch (error: unknown) {
      dispatch({ type: "SET_ERROR", payload: getErrorMessage(error, "Unable to publish the simulation.") })
    }
  }, [publish, projectId])

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

  // ---------------------------------------------------------------------------
  // Planning sheet: build once per run when reaching review. The sheet is the
  // presentable, approvable plan (spaces, style, open items) — never raw JSON.
  // ---------------------------------------------------------------------------
  const reviewRunId = intakeResult?.run_id ?? clarifyResult?.run_id ?? null
  useEffect(() => {
    if (step !== "review" || !reviewRunId) return
    if (planRunIdRef.current === reviewRunId) return
    planRunIdRef.current = reviewRunId
    setPlanSheet(null)
    buildPlan
      .mutateAsync({ run_id: reviewRunId })
      .then((sheet) => setPlanSheet(sheet))
      .catch(() => {
        planRunIdRef.current = null
      })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [step, reviewRunId])

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
                  <div className="flex items-center gap-2">
                    <div className="text-xs font-semibold text-foreground">
                      Architectural Clarification
                    </div>
                    {(clarifyResult?.analyser_mode === "fallback" || intakeResult?.analyser_mode === "fallback") && (
                      <span title="AI analyser unavailable — showing basic questions referencing your idea. Check LLM router health.">
                        <Badge variant="outline" className="text-[10px]">Basic questions (offline mode)</Badge>
                      </span>
                    )}
                    {(clarifyResult?.analyser_mode === "llm" || (intakeResult?.analyser_mode === "llm" && !clarifyResult)) && (
                      <span title="Questions generated from your idea by the AI analyser.">
                        <Badge variant="outline" className="text-[10px]">AI-grounded questions</Badge>
                      </span>
                    )}
                  </div>
                  <p className="text-[11px] text-stonegray">
                    Refine architectural constraints before generating the 3D scene.
                  </p>

                  {displayQuestions.length > 0 && (
                    <div className="space-y-1">
                      <div className="flex justify-between text-[10px] font-mono text-stonegray">
                        <span>
                          Answered {displayQuestions.filter((q) => (answers[q.field || q.question] || "").trim() !== "").length} of {displayQuestions.length}
                        </span>
                        {typeof clarifyResult?.completion_percentage === "number" && (
                          <span>{Math.round(clarifyResult.completion_percentage * 100)}%</span>
                        )}
                      </div>
                      <div className="h-1.5 w-full bg-secondary rounded-full overflow-hidden">
                        <div
                          className="h-full bg-terracotta transition-all duration-300"
                          style={{
                            width: `${Math.round(
                              (displayQuestions.filter((q) => (answers[q.field || q.question] || "").trim() !== "").length /
                                displayQuestions.length) *
                                100
                            )}%`,
                          }}
                        />
                      </div>
                    </div>
                  )}

                  <div className="space-y-3 max-h-64 overflow-y-auto pr-1">
                    {displayQuestions.length === 0 ? (
                      <p className="text-xs text-stonegray">No clarification needed. Continue to review.</p>
                    ) : (
                      displayQuestions
                        .filter((q) => {
                          // Reactive depends_on: hide e.g. languages when narration is declined.
                          if (!q.depends_on) return true
                          const dep = (answers[q.depends_on] || "").trim().toLowerCase()
                          if (!dep) return true
                          return !["no", "false", "none", "n"].includes(dep)
                        })
                        .map((q, i) => {
                        const field = q.field || q.question || String(q)
                        const question = q.question || String(q)
                        const type = q.type || "text"
                        const options: string[] = q.options || []
                        const current = answers[field] || ""
                        const setAnswer = (value: string) =>
                          dispatch({ type: "SET_ANSWER", payload: { field, value } })
                        const selectedMulti = current
                          .split(",")
                          .map((s) => s.trim())
                          .filter(Boolean)
                        const toggleMulti = (opt: string) => {
                          const next = selectedMulti.includes(opt)
                            ? selectedMulti.filter((s) => s !== opt)
                            : [...selectedMulti, opt]
                          setAnswer(next.join(", "))
                        }

                        return (
                          <div key={field + i} className="space-y-1">
                            <Label htmlFor={`clarify-${field}`} className="text-xs font-medium text-foreground">
                              {question}
                              {q.required === false && (
                                <span className="ml-1 font-normal text-stonegray">(optional)</span>
                              )}
                            </Label>
                            {q.evidence_span && (
                              <p className="text-[10px] italic text-stonegray">
                                Based on: “{q.evidence_span}”
                              </p>
                            )}
                            {type === "number" ? (
                              <div className="flex items-center gap-1.5">
                                <Input
                                  id={`clarify-${field}`}
                                  type="number"
                                  inputMode="numeric"
                                  min={q.min_value ?? undefined}
                                  max={q.max_value ?? undefined}
                                  placeholder="Enter a number..."
                                  value={current}
                                  onChange={(e) => setAnswer(e.target.value)}
                                  className="h-8 text-xs border-warmgray focus-visible:ring-terracotta"
                                />
                                {q.unit && (
                                  <span className="text-[10px] font-mono text-stonegray whitespace-nowrap">
                                    {q.unit}
                                  </span>
                                )}
                              </div>
                            ) : type === "choice" && options.length && q.multi ? (
                              <div className="flex flex-wrap gap-1.5">
                                {options.map((o: string) => {
                                  const active = selectedMulti.includes(o)
  // Invalid project id: render a local error state. No intake/clarify/
  // generate hook can fire — useProject is disabled on null, mutation hooks
  // throw on null, and every handler above early-returns.
  if (projectId === null) {
    return (
      <div className="space-y-5">
        <div role="alert" className="rounded-xl border border-destructive/30 bg-destructive/10 p-4 text-sm text-destructive">
          <p className="font-semibold">Invalid project id</p>
          <p className="mt-1 text-xs">
            The URL does not contain a valid project id, so the builder cannot load. Check the link and try again.
          </p>
          <Button variant="outline" size="sm" onClick={() => router.push("/dashboard")} className="mt-3 text-xs">
            Back to Dashboard
          </Button>
        </div>
      </div>
    )
  }

  return (
                                    <button
                                      key={o}
                                      type="button"
                                      onClick={() => toggleMulti(o)}
                                      className={cn(
                                        "rounded-full border px-2.5 py-1 text-[11px] transition-colors",
                                        active
                                          ? "border-terracotta bg-terracotta/10 font-medium"
                                          : "border-warmgray hover:border-terracotta/50"
                                      )}
                                    >
                                      {o}
                                    </button>
                                  )
                                })}
                              </div>
                            ) : type === "choice" && options.length ? (
                              <div className="flex flex-wrap gap-1.5">
                                {options.map((o: string) => (
                                  <button
                                    key={o}
                                    type="button"
                                    onClick={() => setAnswer(o)}
                                    className={cn(
                                      "rounded-full border px-2.5 py-1 text-[11px] transition-colors",
                                      current === o
                                        ? "border-terracotta bg-terracotta/10 font-medium"
                                        : "border-warmgray hover:border-terracotta/50"
                                    )}
                                  >
                                    {o}
                                  </button>
                                ))}
                              </div>
                            ) : type === "boolean" ? (
                              <div className="flex gap-1.5">
                                {(["yes", "no"] as const).map((o) => (
                                  <button
                                    key={o}
                                    type="button"
                                    onClick={() => setAnswer(o)}
                                    className={cn(
                                      "flex-1 rounded-lg border px-2 py-1.5 text-xs capitalize transition-colors",
                                      current.toLowerCase() === o
                                        ? "border-terracotta bg-terracotta/10 font-medium"
                                        : "border-warmgray hover:border-terracotta/50"
                                    )}
                                  >
                                    {o === "yes" ? "Yes" : "No"}
                                  </button>
                                ))}
                              </div>
                            ) : (
                              <Input
                                id={`clarify-${field}`}
                                placeholder="Answer..."
                                value={current}
                                onChange={(e) => setAnswer(e.target.value)}
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
                  <div className="flex items-center justify-between">
                    <div className="text-xs font-semibold text-foreground">
                      Review Extracted Architecture
                    </div>
                    {intakeResult?.analyser_mode && (
                      <span
                        className={cn(
                          "rounded-full border px-2 py-0.5 text-[10px] font-medium",
                          intakeResult.analyser_mode === "fallback"
                            ? "border-amber-500/40 bg-amber-500/10 text-amber-600 dark:text-amber-400"
                            : "border-sage-200 bg-sage-50 text-sage dark:border-sage-900 dark:bg-sage-950/40"
                        )}
                        title={
                          intakeResult.analyser_mode === "fallback"
                            ? "Basic offline analysis — no AI provider reachable. Answers you give will still improve the spec."
                            : intakeResult.analyser_mode === "slm"
                            ? "Analysed on-device by the local model (offline)."
                            : "Analysed by the AI provider."
                        }
                      >
                        {intakeResult.analyser_mode === "fallback"
                          ? "Basic analysis"
                          : intakeResult.analyser_mode === "slm"
                          ? "On-device AI"
                          : "AI analysed"}
                      </span>
                    )}
                  </div>
                  <p className="text-[11px] text-stonegray">
                    Review the plan the agent gathered from your prompt. Approve it to generate the 3D scene.
                  </p>

                  {planSheet?.sheet ? (
                    <div className="space-y-3">
                      <div className="rounded-xl border border-warmgray p-3">
                        <div className="flex items-center justify-between gap-2">
                          <div className="text-xs font-semibold text-foreground capitalize">
                            {planSheet.sheet.domain === "heritage" ? "Heritage walkthrough" : "Real estate walkthrough"}
                          </div>
                          <span
                            className={cn(
                              "rounded-full border px-2 py-0.5 text-[10px] font-medium",
                              planSheet.status === "approved"
                                ? "border-sage-200 bg-sage-50 text-sage dark:border-sage-900 dark:bg-sage-950/40"
                                : "border-warmgray text-stonegray"
                            )}
                          >
                            Plan v{planSheet.version} · {planSheet.status}
                          </span>
                        </div>
                        <p className="mt-1 text-[11px] text-stonegray line-clamp-3">{planSheet.sheet.objective}</p>
                      </div>

                      {(planSheet.sheet.spaces?.length ?? 0) > 0 && (
                        <div>
                          <div className="text-[11px] font-semibold text-foreground mb-1">
                            Spaces ({planSheet.sheet.spaces?.length})
                          </div>
                          <ul className="space-y-1 max-h-32 overflow-y-auto pr-1">
                            {planSheet.sheet.spaces?.map((s) => (
                              <li
                                key={s.id}
                                className="flex items-center justify-between rounded-lg border border-warmgray/60 px-2 py-1 text-[11px]"
                              >
                                <span className="font-medium">{s.name}</span>
                                <span className="text-stonegray capitalize">{s.kind}</span>
                              </li>
                            ))}
                          </ul>
                        </div>
                      )}

                      {planSheet.sheet.style && Object.keys(planSheet.sheet.style).length > 0 && (
                        <div>
                          <div className="text-[11px] font-semibold text-foreground mb-1">Style</div>
                          <div className="flex flex-wrap gap-1.5">
                            {Object.entries(planSheet.sheet.style).map(([k, v]) => (
                              <span
                                key={k}
                                className="rounded-full bg-secondary px-2 py-0.5 text-[10px] text-foreground"
                              >
                                {k}: {v}
                              </span>
                            ))}
                          </div>
                        </div>
                      )}

                      {(planSheet.sheet.open_questions?.length ?? 0) > 0 && (
                        <p className="text-[10px] italic text-stonegray">
                          Still open: {planSheet.sheet.open_questions?.slice(0, 3).join(" · ")}
                          {(planSheet.sheet.open_questions?.length ?? 0) > 3 &&
                            ` +${(planSheet.sheet.open_questions?.length ?? 0) - 3} more`}
                        </p>
                      )}
                    </div>
                  ) : buildPlan.isPending ? (
                    <div className="rounded-xl border border-dashed border-warmgray p-4 text-center">
                      <p className="text-[11px] text-stonegray">Preparing your plan…</p>
                    </div>
                  ) : intakeResult?.extracted_entities && Object.keys(intakeResult.extracted_entities).length > 0 ? (
                    <div className="rounded-xl border border-warmgray bg-charcoal text-white p-3 font-mono text-[11px] overflow-auto max-h-56">
                      <pre className="text-ivory/90 leading-tight">
                        {JSON.stringify(intakeResult.extracted_entities, null, 2)}
                      </pre>
                    </div>
                  ) : (
                    <div className="rounded-xl border border-dashed border-warmgray p-4 text-center">
                      <p className="text-[11px] text-stonegray">
                        No concrete fragments detected in your prompt yet — nothing is made up. Answer the
                        clarification questions so the spec is built from your input.
                      </p>
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => dispatch({ type: "SET_STEP", payload: "clarify" })}
                        className="mt-2 text-xs"
                      >
                        Answer Questions →
                      </Button>
                    </div>
                  )}

                  <div className="flex gap-2 pt-1">
                    <Button variant="outline" size="sm" onClick={() => dispatch({ type: "SET_STEP", payload: "clarify" })} className="flex-1 text-xs">
                      Edit
                    </Button>
                    <Button
                      variant="terracotta"
                      size="sm"
                      onClick={handleGenerateSpec}
                      disabled={generateSpec.isPending || approvePlan.isPending || buildPlan.isPending || !!currentJobId}
                      className="flex-1 text-xs font-medium"
                    >
                      {generateSpec.isPending || approvePlan.isPending
                        ? "Compiling…"
                        : buildPlan.isPending
                        ? "Preparing plan…"
                        : planSheet?.status === "approved"
                        ? "Compile Scene →"
                        : "Approve & Compile →"}
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

                  {(workflowError || (jobStatus.isError && currentJobId)) && jobStatus.data?.status !== "failed" && (
                    <div role="alert" className="rounded-lg bg-destructive/10 border border-destructive/20 p-2.5 text-xs text-destructive text-center">
                      <p className="font-semibold">Generation Interrupted</p>
                      <p className="mt-0.5 text-[11px]">
                        {String(
                          workflowError ||
                            "Lost track of the job (it may have expired). Your plan is kept — go back and compile again."
                        )}
                      </p>
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => {
                          dispatch({ type: "SET_ERROR", payload: null })
                          dispatch({ type: "SET_JOB", payload: null })
                          jobStartedAtRef.current = null
                          dispatch({ type: "SET_STEP", payload: intakeResult ? "review" : "prompt" })
                        }}
                        className="mt-2 text-xs"
                      >
                        Back to Review →
                      </Button>
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
