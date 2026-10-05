import { useMutation } from "@tanstack/react-query"
import { api } from "@/lib/api"
import type { JobStatus } from "@/types"

export function useGenerateSpec(projectId: number | null) {
  return useMutation<JobStatus, Error, { prompt: string; run_id?: string; clarification_answers?: Record<string, any> }>({
    mutationFn: async ({ prompt, run_id, clarification_answers }) => {
      if (projectId === null || Number.isNaN(projectId)) throw new Error("Invalid project id")
      const res = await api.post(`/v1/projects/${projectId}/generate-spec`, { prompt, run_id, clarification_answers })
      return res.data
    },
  })
}
