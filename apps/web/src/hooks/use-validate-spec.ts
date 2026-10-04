import { useMutation } from "@tanstack/react-query"
import { api } from "@/lib/api"
import type { JobStatus } from "@/types"

export function useValidateSpec(projectId: number | null) {
  return useMutation<JobStatus>({
    mutationFn: async () => {
      if (projectId === null || Number.isNaN(projectId)) throw new Error("Invalid project id")
      const res = await api.post(`/v1/projects/${projectId}/validate-spec`)
      return res.data
    },
  })
}
