import { useMutation, useQuery } from "@tanstack/react-query"
import { api } from "@/lib/api"
import { queryKeys } from "@/lib/queryKeys"
import type { PlanningSheet } from "@/types"

export interface PlanSheetResponse {
  id: number
  project_id: number
  version: number
  status: string
  run_id?: string | null
  sheet: PlanningSheet
}

export function useBuildPlan(projectId: number | null) {
  return useMutation<PlanSheetResponse, Error, { run_id: string }>({
    mutationFn: async ({ run_id }) => {
      if (projectId === null || Number.isNaN(projectId)) throw new Error("Invalid project id")
      const res = await api.post(`/v1/projects/${projectId}/plan`, { run_id })
      return res.data
    },
  })
}

export function useApprovePlan(projectId: number | null) {
  return useMutation<PlanSheetResponse, Error, { sheetId: number }>({
    mutationFn: async ({ sheetId }) => {
      if (projectId === null || Number.isNaN(projectId)) throw new Error("Invalid project id")
      const res = await api.post(`/v1/projects/${projectId}/plan/${sheetId}/approve`)
      return res.data
    },
  })
}

export function usePlanSheet(projectId: number, enabled = true) {
  return useQuery<PlanSheetResponse>({
    queryKey: [...queryKeys.projects.detail(projectId), "plan"],
    queryFn: async () => {
      const res = await api.get(`/v1/projects/${projectId}/plan`)
      return res.data
    },
    enabled,
    retry: false,
  })
}
