"use client"

interface GenerationProgressProps {
  /** 0-100, or null when progress is indeterminate/unknown. */
  progress: number | null
  label?: string
}

/**
 * Determinate job progress with a real `progressbar` role (the page's
 * spinner region uses `role="status"` with an aria-label next to it).
 */
export function GenerationProgress({ progress, label = "Generation progress" }: GenerationProgressProps) {
  if (progress === null) return null
  return (
    <div className="space-y-1">
      <div className="flex justify-between text-[10px] font-mono text-stonegray">
        <span>Progress</span>
        <span aria-hidden="true">{progress}%</span>
      </div>
      <div
        role="progressbar"
        aria-label={label}
        aria-valuenow={progress}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuetext={`${progress} percent`}
        className="h-1.5 w-full bg-secondary rounded-full overflow-hidden"
      >
        <div className="h-full bg-terracotta transition-all duration-300" style={{ width: `${progress}%` }} />
      </div>
    </div>
  )
}
