import { useMutation, useQueryClient } from "@tanstack/react-query"
import { api } from "@/lib/api"

export function useUploadAsset(projectId: number) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (file: File) => {
      if (file.size > 50 * 1024 * 1024) throw new Error("File too large (max 50MB)")
      const lower = file.name.toLowerCase()
      let type: string
      if (file.type.startsWith("image/")) type = "image"
      else if (file.type.startsWith("audio/")) type = "audio"
      else if (/\.(glb|gltf|fbx|obj)$/i.test(lower) || file.type.includes("model") || file.type === "model/gltf-binary") type = "model_3d"
      else if (/\.(png|jpg|jpeg|webp|hdr|exr)$/i.test(lower)) type = "texture"
      else type = "other"
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
