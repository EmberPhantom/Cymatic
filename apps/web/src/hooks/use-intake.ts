import { useMutation } from "@tanstack/react-query"
import { api, LONG_REQUEST_TIMEOUT_MS } from "@/lib/api"
import type { IntakeResult } from "@/types"

export function useIntake(projectId: number) {
  return useMutation<IntakeResult, Error, { prompt: string; context?: Record<string, any> }>({
    mutationFn: async ({ prompt, context }) => {
      const res = await api.post(
        `/v1/projects/${projectId}/intake`,
        { prompt, context: context ?? {} },
        { timeout: LONG_REQUEST_TIMEOUT_MS },
      )
      return res.data
    },
  })
}
