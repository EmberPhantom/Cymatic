import { useQuery } from "@tanstack/react-query"
import { api } from "@/lib/api"
import { queryKeys } from "@/lib/queryKeys"
import type { Project } from "@/types"

export function useProjects() {
  return useQuery<Project[]>({
    queryKey: queryKeys.projects.lists(),
    queryFn: async () => {
      const res = await api.get("/v1/projects")
      return res.data.projects || res.data
    },
  })
}
