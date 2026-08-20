import { useMutation } from "@tanstack/react-query"
import { api } from "@/lib/api"

export function usePublish(projectId: number) {
  return useMutation<{ status: string }>({
    mutationFn: async () => {
      const res = await api.post(`/v1/projects/${projectId}/publish`)
      return res.data
    },
  })
}
