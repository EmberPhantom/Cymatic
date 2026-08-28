import { useMutation, useQueryClient } from "@tanstack/react-query"
import { api } from "@/lib/api"

export function useUploadAsset(projectId: number) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (file: File) => {
      const type = file.type.startsWith("image/") ? "image" : file.type.startsWith("audio/") ? "audio" : file.type.includes("model") || /\.(glb|gltf|fbx|obj)$/i.test(file.name) ? "model" : "document"
      const init = await api.post("/v1/assets/upload/init", {
        filename: file.name,
        content_type: file.type || "application/octet-stream",
        type,
        project_id: projectId,
      })
      await fetch(init.data.upload_url, { method: "PUT", body: file, headers: { "Content-Type": file.type || "application/octet-stream" } }).then(async (response) => {
        if (!response.ok) throw new Error(`Asset upload failed (${response.status})`)
      })
      const complete = await api.post("/v1/assets/upload/complete", { asset_id: init.data.asset_id, size: file.size })
      return complete.data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["assets", projectId] })
    },
  })
}
