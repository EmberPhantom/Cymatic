"use client"

import React from "react"
import { cn } from "@/lib/utils"

export type PipelineStage = "input" | "specification" | "scene" | "build" | "vr_stream" | "published"

interface PipelineStepperProps {
  currentStage: PipelineStage
  status?: string
  className?: string
}

const STAGES: { id: PipelineStage; label: string; number: string; desc: string }[] = [
  { id: "input", label: "Input", number: "01", desc: "Natural prompt" },
  { id: "specification", label: "Specification", number: "02", desc: "Schema validation" },
  { id: "scene", label: "Scene", number: "03", desc: "Spatial graph" },
  { id: "build", label: "Build", number: "04", desc: "80k tri & baked GI" },
  { id: "vr_stream", label: "VR Stream", number: "05", desc: "WebRTC LAN" },
  { id: "published", label: "Published", number: "06", desc: "Live walkthrough" },
]

export function PipelineStepper({ currentStage, status, className }: PipelineStepperProps) {
  const currentIdx = STAGES.findIndex((s) => s.id === currentStage)
  const isFailed = status === "failed"

  return (
    <div className={cn("w-full p-4 rounded-xl border border-warmgray bg-card shadow-sm", className)}>
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <span className="h-2 w-2 rounded-full bg-terracotta" />
          <span className="text-[10px] font-mono uppercase tracking-widest text-stonegray font-semibold">
            SIMULATION PIPELINE
          </span>
        </div>
        <span className="text-[11px] font-mono text-terracotta font-semibold">
          {isFailed ? "Pipeline Interrupted" : `Stage ${currentIdx >= 0 ? currentIdx + 1 : 1} of 6 // ${STAGES[currentIdx]?.label.toUpperCase() || "READY"}`}
        </span>
      </div>

      {/* Connected Stepper Flow */}
      <div className="relative">
        {/* Horizontal Connecting Track Behind Circles (visible on md+) */}
        <div className="hidden lg:block absolute top-[18px] left-[40px] right-[40px] h-[2px] bg-warmgray/80 -z-0" />

        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-2.5 relative z-10">
          {STAGES.map((stage, idx) => {
            const isCompleted = currentIdx > idx
            const isCurrent = currentIdx === idx
            const isPending = currentIdx < idx

            return (
              <div
                key={stage.id}
                className={cn(
                  "flex flex-col p-2.5 rounded-lg border transition-all duration-200 bg-card group",
                  isCurrent && !isFailed
                    ? "border-terracotta shadow-sm ring-1 ring-terracotta/40"
                    : isCompleted
                    ? "border-sage/50 text-foreground"
                    : isFailed && isCurrent
                    ? "border-destructive bg-destructive/10 text-destructive"
                    : "border-warmgray/70 text-stonegray hover:border-foreground/30"
                )}
              >
                <div className="flex items-center justify-between gap-1 mb-2">
                  <span className="text-[10px] font-mono font-bold tracking-tight text-stonegray">
                    {stage.number}
                  </span>

                  {/* Exact symbols: Completed: ✓, Current: ●, Pending: ○ */}
                  {isCompleted ? (
                    <span className="h-5 w-5 rounded-full bg-sage text-white flex items-center justify-center text-[11px] font-bold shadow-sm">
                      ✓
                    </span>
                  ) : isCurrent ? (
                    <span className="relative flex h-5 w-5 items-center justify-center">
                      <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-terracotta opacity-75" />
                      <span className="relative inline-flex rounded-full h-5 w-5 bg-terracotta text-white items-center justify-center text-[10px] font-bold shadow-sm">
                        ●
                      </span>
                    </span>
                  ) : (
                    <span className="h-5 w-5 rounded-full border border-warmgray text-stonegray flex items-center justify-center text-[11px] font-normal">
                      ○
                    </span>
                  )}
                </div>

                <div
                  className={cn(
                    "text-xs font-bold tracking-tight",
                    isCurrent ? "text-terracotta" : isCompleted ? "text-foreground" : "text-stonegray"
                  )}
                >
                  {stage.label}
                </div>
                <div className="text-[10px] text-stonegray truncate mt-0.5 font-mono">
                  {stage.desc}
                </div>
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}
