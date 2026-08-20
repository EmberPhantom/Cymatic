import { useMutation } from "@tanstack/react-query"
import { api } from "@/lib/api"
import type { IntakeResult } from "@/types"

export function useIntake(projectId: number) {
  return useMutation<IntakeResult, Error, { prompt: string }>({
    mutationFn: async ({ prompt }) => {
      const res = await api.post(`/v1/projects/${projectId}/intake`, { prompt })
      return res.data
    },
  })
}
