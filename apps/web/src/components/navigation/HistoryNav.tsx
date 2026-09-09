"use client"

import { useRouter } from "next/navigation"
import { useCallback } from "react"
import { Button } from "@/components/ui/button"
import { routes } from "@/lib/routes"
import { ChevronLeft, ChevronRight } from "lucide-react"

/**
 * Browser-history navigation only (Back / Forward).
 * Arrows only per design requirements.
 */
export function HistoryNav({ className }: { className?: string }) {
  const router = useRouter()

  const goBack = useCallback(() => {
    if (typeof window !== "undefined" && window.history.length > 1) {
      router.back()
    } else {
      router.replace(routes.dashboard)
    }
  }, [router])

  const goForward = useCallback(() => {
    router.forward()
  }, [router])

  return (
    <div className={className ?? "flex items-center gap-1"} role="group" aria-label="History navigation">
      <Button
        type="button"
        variant="ghost"
        size="sm"
        className="h-8 w-8 p-0 rounded-md"
        onClick={goBack}
        aria-label="Go back"
        title="Go back"
      >
        <ChevronLeft className="h-4 w-4" />
      </Button>
      <Button
        type="button"
        variant="ghost"
        size="sm"
        className="h-8 w-8 p-0 rounded-md"
        onClick={goForward}
        aria-label="Go forward"
        title="Go forward"
      >
        <ChevronRight className="h-4 w-4" />
      </Button>
    </div>
  )
}
