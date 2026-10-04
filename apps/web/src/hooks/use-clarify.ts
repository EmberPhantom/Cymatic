import { useMutation } from "@tanstack/react-query"
import { api, API_ORIGIN, LONG_REQUEST_TIMEOUT_MS } from "@/lib/api"
import { parseClarifyResultOrThrow } from "@/lib/validations"
import type { ClarifyResult } from "@/types"

export function useClarify(projectId: number | null) {
  return useMutation<ClarifyResult, Error, { answers: Record<string, string>; run_id?: string; current_intake?: Record<string, unknown> }>({
    mutationFn: async ({ answers, run_id, current_intake }) => {
      if (projectId === null || Number.isNaN(projectId)) throw new Error("Invalid project id")
      const res = await api.post(
        `${API_ORIGIN}/v1/projects/${projectId}/clarify`,
        { answers, run_id, current_intake },
        { timeout: LONG_REQUEST_TIMEOUT_MS },
      )
      // Narrow the free-form backend JSON at the API boundary.
      return parseClarifyResultOrThrow(res.data) as ClarifyResult
    },
  })
}
