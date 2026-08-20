import { useMutation } from "@tanstack/react-query"
import { api } from "@/lib/api"
import type { JobStatus } from "@/types"

export function useGenerateSpec(projectId: number) {
  return useMutation<JobStatus, Error, { prompt: string }>({
    mutationFn: async ({ prompt }) => {
      const res = await api.post(`/v1/projects/${projectId}/generate-spec`, { prompt })
      return res.data
    },
  })
}
