import { useQuery } from "@tanstack/react-query"
import { api } from "@/lib/api"
import type { JobStatus } from "@/types"

export function useJobStatus(jobId: string | null, enabled = false) {
  return useQuery<JobStatus>({
    queryKey: ["job", jobId],
    queryFn: async () => {
      const res = await api.get(`/v1/jobs/${jobId}/status`)
      return res.data
    },
    enabled: enabled && !!jobId,
    refetchInterval: (query) => {
      const status = query.state.data?.status
      if (status === "completed" || status === "failed") return false
      return 2000
    },
  })
}
