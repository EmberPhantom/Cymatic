import { useQuery } from "@tanstack/react-query"
import { api } from "@/lib/api"
import type { SimulationSpec } from "@/types"

export function useSpecs(projectId: number) {
  return useQuery<SimulationSpec[]>({
    queryKey: ["specs", projectId],
    queryFn: async () => {
      const res = await api.get(`/v1/projects/${projectId}/specs`)
      return res.data.specs || res.data
    },
  })
}
