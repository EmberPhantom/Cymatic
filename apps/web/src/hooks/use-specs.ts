import { useQuery } from "@tanstack/react-query"
import { api } from "@/lib/api"
import { queryKeys } from "@/lib/queryKeys"
import type { SimulationSpec } from "@/types"

export function useSpecs(projectId: number) {
  return useQuery<SimulationSpec[]>({
    queryKey: queryKeys.specs.list(projectId),
    queryFn: async () => {
      const res = await api.get(`/v1/projects/${projectId}/specs`)
      return res.data.specs || res.data
    },
  })
}
