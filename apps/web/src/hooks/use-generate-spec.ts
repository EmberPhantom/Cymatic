import { useMutation } from "@tanstack/react-query"
import { api } from "@/lib/api"
import type { JobStatus } from "@/types"

export function useGenerateSpec(projectId: number) {
  return useMutation<JobStatus, Error, { prompt: string; run_id?: string; clarification_answers?: Record<string, any> }>({
    mutationFn: async ({ prompt, run_id, clarification_answers }) => {
      const res = await api.post(`/v1/projects/${projectId}/generate-spec`, { prompt, run_id, clarification_answers })
      return res.data
    },
  })
}
