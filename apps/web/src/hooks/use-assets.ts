import { useQuery } from "@tanstack/react-query"
import { api } from "@/lib/api"
import { queryKeys } from "@/lib/queryKeys"
import type { Asset } from "@/types"

export function useAssets(projectId: number) {
  return useQuery<Asset[]>({
    queryKey: queryKeys.assets.list(projectId),
    queryFn: async () => {
      const res = await api.get(`/v1/assets/projects/${projectId}`)
      return res.data.assets || res.data
    },
  })
}
