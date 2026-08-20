import { useMutation, useQueryClient } from "@tanstack/react-query"
import { api } from "@/lib/api"

export function useUploadAsset(projectId: number) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (file: File) => {
      const formData = new FormData()
      formData.append("file", file)
      formData.append("project_id", String(projectId))
      const res = await api.post("/v1/assets/upload", formData, {
        headers: { "Content-Type": "multipart/form-data" },
      })
      return res.data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["assets", projectId] })
    },
  })
}
