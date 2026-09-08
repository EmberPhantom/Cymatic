import { useQuery } from "@tanstack/react-query"
import { api } from "@/lib/api"
import { queryKeys } from "@/lib/queryKeys"
import type { JobStatus } from "@/types"

export function useJobStatus(jobId: string | null, _enabled = false) {
  return useQuery<JobStatus>({
    queryKey: jobId ? queryKeys.jobs.detail(jobId) : queryKeys.jobs.all,
    queryFn: async () => {
      const res = await api.get(`/v1/jobs/${jobId}/status`)
      return res.data
    },
    enabled: !!jobId,
    refetchInterval: ((data: any) => (data?.status === "completed" ? false : 2000)) as unknown as number | false | ((query: unknown) => number | false | undefined),
  })
}
