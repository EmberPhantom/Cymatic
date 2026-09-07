"use client"

import React from "react"
import { Check, Loader2, X, AlertTriangle } from "lucide-react"
import { cn } from "@/lib/utils"

interface ProgressStepperProps {
  currentStage: PipelineStage
  completedStages: PipelineStage[]
  className?: string
}

type PipelineStage = 
  | "intake"
  | "clarification"
  | "research"
  | "architect"
  | "composer"
  | "domain_expert"
  | "asset_selection"
  | "validation"
  | "scene_package"

const STAGE_CONFIG: Record<PipelineStage, { label: string; description: string; order: number }> = {
  intake: { label: "Intake", description: "Analyzing prompt", order: 1 },
  clarification: { label: "Clarify", description: "Refining requirements", order: 2 },
  research: { label: "Research", description: "Gathering references", order: 3 },
  architect: { label: "Architect", description: "Creating specification", order: 4 },
  composer: { label: "Composer", description: "Laying out scene", order: 5 },
  domain_expert: { label: "Domain Check", description: "Validating compliance", order: 6 },
  asset_selection: { label: "Assets", description: "Selecting 3D assets", order: 7 },
  validation: { label: "Validation", description: "Final schema check", order: 8 },
  scene_package: { label: "Scene Package", description: "Building GLB bundle", order: 9 },
}

const ALL_STAGES: PipelineStage[] = [
  "intake",
  "clarification",
  "research",
  "architect",
  "composer",
  "domain_expert",
  "asset_selection",
  "validation",
  "scene_package",
]

export function ProgressStepper({ currentStage, completedStages = [], className }: ProgressStepperProps) {
  const currentIndex = ALL_STAGES.indexOf(currentStage)
  const isComplete = currentIndex === -1 || completedStages.includes(currentStage)

  return (
    <div className={cn("space-y-3", className)}>
      {ALL_STAGES.map((stage, index) => {
        const config = STAGE_CONFIG[stage]
        const isCompleted = completedStages.includes(stage)
        const isCurrent = stage === currentStage && !isComplete
        const isPending = index > currentIndex || (index === currentIndex && isComplete)

        let status: "completed" | "current" | "pending" = "pending"
        if (isCompleted) status = "completed"
        else if (isCurrent) status = "current"

        return (
          <div key={stage} className="flex items-start gap-3">
            <div className="relative flex items-center justify-center w-8 h-8 flex-shrink-0">
              {/* Connecting line */}
              {index < ALL_STAGES.length - 1 && (
                <div
                  className={cn(
                    "absolute left-1/2 top-full w-px h-full -translate-x-1/2",
                    isCompleted || isCurrent ? "bg-primary" : "bg-gray-200"
                  )}
                />
              )}

              <div
                className={cn(
                  "relative z-10 flex items-center justify-center w-6 h-6 rounded-full border-2 font-medium text-xs transition-all",
                  status === "completed"
                    ? "bg-primary border-primary text-primary-foreground"
                    : status === "current"
                    ? "bg-primary border-primary text-primary-foreground animate-pulse"
                    : "bg-background border-gray-300 text-gray-400"
                )}
              >
                {status === "completed" ? <Check className="h-4 w-4" /> : config.order}
              </div>
            </div>

            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2">
                <span className={cn("font-medium text-sm", status === "current" ? "text-primary" : "")}>
                  {config.label}
                </span>
                {status === "current" && (
                  <Loader2 className="h-3 w-3 text-primary animate-spin" aria-hidden="true" />
                )}
                {status === "completed" && <Check className="h-3 w-3 text-green-500" />}
              </div>
              <p className="text-xs text-muted-foreground truncate">{config.description}</p>
            </div>
          </div>
        )
      })}

      {/* Overall progress bar */}
      <div className="mt-4">
        <div className="flex justify-between text-xs text-muted-foreground mb-1">
          <span>Overall Progress</span>
          <span>
            {Math.round(((completedStages.length + (isComplete && currentIndex !== -1 ? 1 : 0)) / ALL_STAGES.length) * 100)}%
          </span>
        </div>
        <div className="h-2 bg-gray-200 rounded-full overflow-hidden">
          <div
            className={cn(
              "h-full bg-primary transition-all duration-300",
              isComplete ? "bg-green-500" : ""
            )}
            style={{
              width: `${((completedStages.length + (isComplete && currentIndex !== -1 ? 1 : 0)) / ALL_STAGES.length) * 100}%`,
            }}
          />
        </div>
      </div>
    </div>
  )
}

export function StageStatusBadge({ stage }: { stage: PipelineStage }) {
  const config = STAGE_CONFIG[stage]
  return (
    <span className="inline-flex items-center gap-1 px-2 py-1 rounded-full text-xs font-medium bg-primary/10 text-primary">
      {config.label}
    </span>
  )
}