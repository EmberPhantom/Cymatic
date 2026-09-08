import { useQuery } from "@tanstack/react-query"
import { api } from "@/lib/api"
import { queryKeys } from "@/lib/queryKeys"
import type { Project } from "@/types"

export function useProject(projectId: number | null) {
  return useQuery<Project>({
    queryKey: projectId ? queryKeys.projects.detail(projectId) : queryKeys.projects.all,
    queryFn: async () => {
      if (!projectId || Number.isNaN(projectId)) throw new Error("Invalid project id")
      const res = await api.get(`/v1/projects/${projectId}`)
      return res.data
    },
    enabled: !!projectId && !Number.isNaN(projectId),
  })
}
