"use client"

import { cn } from "@/lib/utils"

export interface BuilderStep {
  key: string
  label: string
}

interface BuilderStepsProps {
  steps: BuilderStep[]
  currentIndex: number
}

/**
 * Builder step indicator: an ordered list where the current step carries
 * `aria-current="step"` and completed steps are exposed to AT. Mirrors the
 * label/input association pattern used in apps/viewer (explicit, no
 * title-only semantics).
 */
export function BuilderSteps({ steps, currentIndex }: BuilderStepsProps) {
  return (
    <ol className="flex items-center gap-1.5 flex-wrap" aria-label="Build progress">
      {steps.map((s, idx) => {
        const isCompleted = idx < currentIndex
        const isCurrent = idx === currentIndex
        return (
          <li
            key={s.key}
            aria-current={isCurrent ? "step" : undefined}
            aria-label={`${s.label}${isCurrent ? " (current step)" : isCompleted ? " (completed)" : ""}`}
            className={cn(
              "px-2.5 py-1 rounded-md text-[11px] font-mono tracking-tight transition-colors border",
              isCurrent
                ? "bg-charcoal text-white dark:bg-ivory dark:text-charcoal border-transparent font-semibold shadow-sm"
                : isCompleted
                ? "bg-sage-50 text-sage-700 border-sage-200 dark:bg-sage-950/40 dark:border-sage-800"
                : "bg-muted/30 text-stonegray border-warmgray/60"
            )}
          >
            0{idx + 1} {s.label}
          </li>
        )
      })}
    </ol>
  )
}
