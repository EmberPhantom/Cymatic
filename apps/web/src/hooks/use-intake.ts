import { useMutation } from "@tanstack/react-query"
import { api, API_ORIGIN, LONG_REQUEST_TIMEOUT_MS } from "@/lib/api"
import { parseIntakeResultOrThrow } from "@/lib/validations"
import type { IntakeResult } from "@/types"

export function useIntake(projectId: number | null) {
  return useMutation<IntakeResult, Error, { prompt: string; context?: Record<string, unknown> }>({
    mutationFn: async ({ prompt, context }) => {
      if (projectId === null || Number.isNaN(projectId)) throw new Error("Invalid project id")
      const res = await api.post(
        `${API_ORIGIN}/v1/projects/${projectId}/intake`,
        { prompt, context: context ?? {} },
        { timeout: LONG_REQUEST_TIMEOUT_MS },
      )
      // Narrow the free-form backend JSON at the API boundary.
      return parseIntakeResultOrThrow(res.data) as IntakeResult
    },
  })
}
