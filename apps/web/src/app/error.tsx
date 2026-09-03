"use client"

import { useEffect } from "react"
import { Button } from "@/components/ui/button"

export default function Error({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  useEffect(() => {
    console.error(error)
  }, [error])

  return (
    <div className="flex min-h-screen flex-col items-center justify-center p-8 text-center">
      <h2 className="text-2xl font-bold">Something went wrong</h2>
      <p className="text-sm text-muted-foreground mt-2 max-w-md">{error.message || "Unexpected error"}</p>
      <Button onClick={() => reset()} className="mt-6">Try again</Button>
    </div>
  )
}
