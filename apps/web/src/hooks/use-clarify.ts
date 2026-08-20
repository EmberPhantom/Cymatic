import { useMutation } from "@tanstack/react-query"
import { api } from "@/lib/api"
import type { ClarifyResult } from "@/types"

export function useClarify(projectId: number) {
  return useMutation<ClarifyResult, Error, { answers: Record<string, string> }>({
    mutationFn: async ({ answers }) => {
      const res = await api.post(`/v1/projects/${projectId}/clarify`, { answers })
      return res.data
    },
  })
}
