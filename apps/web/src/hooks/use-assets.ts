import { useQuery } from "@tanstack/react-query"
import { api } from "@/lib/api"
import type { Asset } from "@/types"

export function useAssets(projectId: number) {
  return useQuery<Asset[]>({
    queryKey: ["assets", projectId],
    queryFn: async () => {
      const res = await api.get(`/v1/projects/${projectId}/assets`)
      return res.data.assets || res.data
    },
  })
}
