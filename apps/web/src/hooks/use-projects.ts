import { useQuery } from "@tanstack/react-query"
import { api } from "@/lib/api"
import type { Project } from "@/types"

export function useProjects() {
  return useQuery<Project[]>({
    queryKey: ["projects"],
    queryFn: async () => {
      const res = await api.get("/v1/projects")
      return res.data.projects || res.data
    },
  })
}
