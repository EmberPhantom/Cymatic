import { useMutation, useQuery } from "@tanstack/react-query"
import { api } from "@/lib/api"
import type { SimulationSpec } from "@/types"

export interface EditOperation {
  operation: "move" | "rotate" | "scale" | "change_material" | "delete" | "duplicate" | "add_entity"
  entity_id: string
  params: Record<string, any>
}

export interface EditRequest {
  operations: EditOperation[]
}

export interface EditResponse {
  success: boolean
  message: string
  spec_id?: number
  new_version?: number
}

export interface EntityPatch {
  position?: number[]
  rotation?: number[]
  scale?: number[]
  properties?: Record<string, any>
}

export function useEditSpec(projectId: number) {
  return useMutation<EditResponse, Error, { specId: number; request: EditRequest }>({
    mutationFn: async ({ specId, request }) => {
      const res = await api.post(`/v1/projects/${projectId}/specs/${specId}/edit`, request)
      return res.data
    },
  })
}

export function usePatchEntity(projectId: number) {
  return useMutation<any, Error, { specId: number; entityId: string; patch: EntityPatch }>({
    mutationFn: async ({ specId, entityId, patch }) => {
      const res = await api.patch(`/v1/projects/${projectId}/specs/${specId}/entities/${entityId}`, patch)
      return res.data
    },
  })
}

export function useValidateSpecEdits(projectId: number) {
  return useMutation<any, Error, { specId: number }>({
    mutationFn: async ({ specId }) => {
      const res = await api.post(`/v1/projects/${projectId}/specs/${specId}/validate`)
      return res.data
    },
  })
}

export function useDeleteSpec(projectId: number) {
  return useMutation<any, Error, { specId: number }>({
    mutationFn: async ({ specId }) => {
      const res = await api.delete(`/v1/projects/${projectId}/specs/${specId}`)
      return res.data
    },
  })
}

export function useGetSpec(projectId: number, specId: number) {
  return useQuery<SimulationSpec>({
    queryKey: ["spec", projectId, specId],
    queryFn: async () => {
      const res = await api.get(`/v1/projects/${projectId}/specs/${specId}`)
      return res.data
    },
    enabled: !!specId,
  })
}