import { useMutation } from "@tanstack/react-query"
import { api } from "@/lib/api"
import type { IntakeResult } from "@/types"

export function useIntake(projectId: number) {
  return useMutation<IntakeResult, Error, { prompt: string; context?: Record<string, any> }>({
    mutationFn: async ({ prompt, context }) => {
      const res = await api.post(`/v1/projects/${projectId}/intake`, { prompt, context: context ?? {} })
      return res.data
    },
  })
}
