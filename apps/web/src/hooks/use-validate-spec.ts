import { useMutation } from "@tanstack/react-query"
import { api } from "@/lib/api"
import type { ValidationResult } from "@/types"

export function useValidateSpec(projectId: number) {
  return useMutation<ValidationResult>({
    mutationFn: async () => {
      const res = await api.post(`/v1/projects/${projectId}/validate-spec`)
      return res.data
    },
  })
}
