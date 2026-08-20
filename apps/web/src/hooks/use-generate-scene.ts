import { useMutation } from "@tanstack/react-query"
import { api } from "@/lib/api"
import type { JobStatus } from "@/types"

export function useGenerateScene(projectId: number) {
  return useMutation<JobStatus>({
    mutationFn: async () => {
      const res = await api.post(`/v1/projects/${projectId}/generate-scene`)
      return res.data
    },
  })
}
