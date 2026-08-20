import { useMutation, useQueryClient } from "@tanstack/react-query"
import { api } from "@/lib/api"
import type { Project } from "@/types"

export function useCreateProject() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (data: { name: string; domain: string; category?: string }) => {
      const res = await api.post("/v1/projects", data)
      return res.data as Project
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["projects"] })
    },
  })
}
