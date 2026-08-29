"use client"

/* The polling effect intentionally depends on stable workflow state, not mutation object identities. */
/* eslint-disable react-hooks/exhaustive-deps */

import { useState, useEffect } from "react"
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
import type { IntakeResult, ClarificationQuestion } from "@/types"

type Step = "prompt" | "clarify" | "review" | "generate" | "publish"

const STEPS: { key: Step; label: string }[] = [
  { key: "prompt", label: "Enter Prompt" },
  { key: "clarify", label: "Clarification" },
  { key: "review", label: "Review Spec" },
  { key: "generate", label: "Generate" },
  { key: "publish", label: "Publish" },
]

export default function BuilderPage() {
  const params = useParams()
  const router = useRouter()
  const projectId = Number(params.id)

  const [step, setStep] = useState<Step>("prompt")
  const [prompt, setPrompt] = useState("")
  const [intakeResult, setIntakeResult] = useState<IntakeResult | null>(null)
  const [clarifyResult, setClarifyResult] = useState<any>(null)
  const [answers, setAnswers] = useState<Record<string, string>>({})
  const [currentJobId, setCurrentJobId] = useState<string | null>(null)
  const [generationStage, setGenerationStage] = useState<"spec" | "validation" | "scene" | "publish">("spec")
  const [workflowError, setWorkflowError] = useState<string | null>(null)

  const intake = useIntake(projectId)
  const clarify = useClarify(projectId)
  const generateSpec = useGenerateSpec(projectId)
  const validateSpec = useValidateSpec(projectId)
  const generateScene = useGenerateScene(projectId)
  const publish = usePublish(projectId)

  const jobStatus = useJobStatus(currentJobId, !!currentJobId)

  // Mutation objects are intentionally excluded: changing them would restart the active job.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => {
    const status = jobStatus.data?.status
    if (!currentJobId || !status || ["queued", "running", "retry"].includes(status)) return
    if (status === "failed" || status === "cancelled") {
      setWorkflowError(jobStatus.data?.error || "The workflow step failed. Please retry.")
      setCurrentJobId(null)
      return
    }
    if (status !== "completed") return
    let active = true
    const continueWorkflow = async () => {
      try {
        setWorkflowError(null)
        if (generationStage === "spec") {
          const result = await validateSpec.mutateAsync()
          if (active) { setGenerationStage("validation"); setCurrentJobId(result.job_id) }
        } else if (generationStage === "validation") {
          const result = await generateScene.mutateAsync()
          if (active) { setGenerationStage("scene"); setCurrentJobId(result.job_id) }
        } else if (generationStage === "scene" && active) {
          setCurrentJobId(null)
          setStep("publish")
        } else if (generationStage === "publish" && active) {
          router.replace(`/dashboard/projects/${projectId}/stream`)
        }
      } catch (error: any) {
        if (active) {
          setWorkflowError(error?.response?.data?.detail || error?.message || "The workflow could not continue.")
          setCurrentJobId(null)
        }
      }
    }
    void continueWorkflow()
    return () => { active = false }
  }, [currentJobId, jobStatus.data?.status, generationStage])

/* eslint-enable react-hooks/exhaustive-deps */

  const stepIndex = STEPS.findIndex((s) => s.key === step)

  // Step handlers
  const handleIntake = async () => {
    if (!prompt.trim()) return
    try {
      setWorkflowError(null)
      const result = await intake.mutateAsync({ prompt })
      setIntakeResult(result)
      setStep(result.missing_fields.length > 0 ? "clarify" : "review")
    } catch (error: any) {
      setWorkflowError(error?.response?.data?.detail || error?.message || "Unable to analyze the prompt.")
    }
  }

  const handleClarify = async () => {
    try {
      setWorkflowError(null)
      const result = await clarify.mutateAsync({ answers, run_id: intakeResult?.run_id, current_intake: intakeResult || {} })
      setClarifyResult(result)
      if (result.ready_for_generation || result.remaining_questions.length === 0) setStep("review")
      else setWorkflowError("Please answer the remaining required questions.")
    } catch (error: any) {
      setWorkflowError(error?.response?.data?.detail || error?.message || "Unable to save clarification answers.")
    }
  }

  const handleGenerateSpec = async () => {
    try {
      setWorkflowError(null)
      const result = await generateSpec.mutateAsync({ prompt, run_id: intakeResult?.run_id, clarification_answers: answers })
      setGenerationStage("spec")
      setCurrentJobId(result.job_id)
      setStep("generate")
    } catch (error: any) {
      setWorkflowError(error?.response?.data?.detail || error?.message || "Unable to start specification generation.")
    }
  }

  const handlePublish = async () => {
    try {
      setWorkflowError(null)
      const result = await publish.mutateAsync()
      setGenerationStage("publish")
      setCurrentJobId(result.job_id)
    } catch (error: any) {
      setWorkflowError(error?.response?.data?.detail || error?.message || "Unable to publish the simulation.")
    }
  }

  return (
    <div className="max-w-3xl mx-auto">
      <div className="mb-6">
        <p className="text-sm text-muted-foreground">Project {projectId}</p>
        <h2 className="text-2xl font-bold">Create Simulation</h2>
        <p className="text-muted-foreground">Build a validated simulation package ready for streaming.</p>
      </div>
      {workflowError && <div className="mb-4 rounded-md bg-destructive/15 p-3 text-sm text-destructive">{workflowError}</div>}
      {/* Step indicator */}
      <div className="flex items-center mb-8">
        {STEPS.map((s, i) => (
          <div key={s.key} className="flex items-center">
            <div className={`flex items-center justify-center w-8 h-8 rounded-full text-sm font-medium ${
              i <= stepIndex ? "bg-primary text-primary-foreground" : "bg-gray-200 text-gray-500"
            }`}>
              {i + 1}
            </div>
            <span className={`ml-2 text-sm ${i <= stepIndex ? "text-foreground" : "text-muted-foreground"}`}>
              {s.label}
            </span>
            {i < STEPS.length - 1 && <div className="w-8 h-px bg-gray-300 mx-4" />}
          </div>
        ))}
      </div>

      {/* Step 1: Prompt */}
      {step === "prompt" && (
        <Card>
          <CardHeader>
            <CardTitle>Describe Your Simulation</CardTitle>
            <CardDescription>Enter a natural language description of the walkthrough you want to create</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-2">
              <Label>Prompt</Label>
              <textarea
                className="flex min-h-[120px] w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                placeholder="e.g., A modern 3-bedroom apartment with open kitchen, floor-to-ceiling windows, and city view..."
                value={prompt}
                onChange={(e) => setPrompt(e.target.value)}
              />
            </div>
            {intake.isError && (
              <div className="rounded-md bg-destructive/15 p-3 text-sm text-destructive">
                {intake.error.message}
              </div>
            )}
            <Button onClick={handleIntake} disabled={!prompt.trim() || intake.isPending}>
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
            {intakeResult.suggested_questions.map((q, i) => (
              <div key={i} className="space-y-2">
                <Label>{q}</Label>
                <Input
                  placeholder="Your answer..."
                  value={answers[q] || ""}
                  onChange={(e) => setAnswers({ ...answers, [q]: e.target.value })}
                />
              </div>
            ))}
            {clarify.isError && (
              <div className="rounded-md bg-destructive/15 p-3 text-sm text-destructive">
                {clarify.error.message}
              </div>
            )}
            <div className="flex gap-2">
              <Button variant="outline" onClick={() => setStep("prompt")}>Back</Button>
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
            <p className="text-sm text-muted-foreground">The worker will create and validate the structured Simulation Specification before building the scene.</p>
            <div className="flex gap-2">
              <Button variant="outline" onClick={() => setStep("clarify")}>Back</Button>
              <Button onClick={handleGenerateSpec} disabled={generateSpec.isPending}>
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
            <CardDescription>{generationStage === "spec" ? "Creating the structured specification..." : generationStage === "validation" ? "Validating the specification..." : "Generating the 3D scene package..."}</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex items-center justify-center py-8">
              <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary" />
            </div>
            <p className="text-center text-sm text-muted-foreground">
              {jobStatus.data?.message || "The worker is processing your request."}
            </p>
            {jobStatus.data?.status === "failed" && (
              <div className="rounded-md bg-destructive/15 p-3 text-sm text-destructive text-center">
                Generation failed. Please try again.
              </div>
            )}
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
              <div className="text-6xl mb-4">🎉</div>
              <h3 className="text-lg font-semibold">Simulation Ready!</h3>
              <p className="text-muted-foreground mt-2">Your walkthrough has been generated and is ready to stream.</p>
            </div>
            <div className="flex gap-2 justify-center">
              <Button variant="outline" onClick={() => router.push(`/dashboard/projects/${projectId}`)}>
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
