import { useQuery } from "@tanstack/react-query"
import { z } from "zod"
import { api } from "@/lib/api"
import { queryKeys } from "@/lib/queryKeys"
import { PayloadValidationError } from "@/lib/validations"
import type { SimulationSpec } from "@/types"

// Envelope guard: spec rows keep `payload_json` as unknown (narrowed by
// consumers via specEntities / specSection), but the row shape itself is
// validated so malformed rows surface a typed error instead of UB downstream.
const simulationSpecSchema = z
  .object({
    id: z.number(),
    project_id: z.number(),
    version: z.number(),
    payload_json: z.unknown(),
    status: z.string(),
    created_at: z.string(),
    updated_at: z.string().optional(),
  })
  .catchall(z.unknown())

export function useSpecs(projectId: number) {
  return useQuery<SimulationSpec[]>({
    queryKey: queryKeys.specs.list(projectId),
    queryFn: async () => {
      const res = await api.get(`/v1/projects/${projectId}/specs`)
      const raw = res.data.specs ?? res.data
      const parsed = z.array(simulationSpecSchema).safeParse(raw)
      if (!parsed.success) {
        throw new PayloadValidationError(
          "Invalid specs response",
          parsed.error.issues.map((i) => `${i.path.join(".") || "(root)"}: ${i.message}`),
        )
      }
      return parsed.data as SimulationSpec[]
    },
  })
}
