import { useMutation } from "@tanstack/react-query"
import { api, LONG_REQUEST_TIMEOUT_MS } from "@/lib/api"
import type { ClarifyResult } from "@/types"

export function useClarify(projectId: number) {
  return useMutation<ClarifyResult, Error, { answers: Record<string, string>; run_id?: string; current_intake?: Record<string, any> }>({
    mutationFn: async ({ answers, run_id, current_intake }) => {
      const res = await api.post(
        `/v1/projects/${projectId}/clarify`,
        { answers, run_id, current_intake },
        { timeout: LONG_REQUEST_TIMEOUT_MS },
      )
      return res.data
    },
  })
}
