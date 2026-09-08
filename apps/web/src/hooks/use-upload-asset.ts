import { useMutation, useQueryClient } from "@tanstack/react-query"
import { api } from "@/lib/api"
import { config } from "@/lib/config"
import { queryKeys } from "@/lib/queryKeys"

export function useUploadAsset(projectId: number) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (file: File, context: unknown) => {
      const signal = (context as { signal?: AbortSignal } | undefined)?.signal
      if (file.size > config.maxUploadMB * 1024 * 1024)
        throw new Error(`File too large (max ${config.maxUploadMB}MB)`)
      const lower = file.name.toLowerCase()
      const mime = file.type || ""
      let type: string
      if (mime.startsWith("image/")) type = "image"
      else if (mime.startsWith("audio/")) type = "audio"
      else if (/\.(glb|gltf|fbx|obj)$/i.test(lower) || mime.includes("model") || mime === "model/gltf-binary")
        type = "model_3d"
      else if (/\.(png|jpg|jpeg|webp|hdr|exr)$/i.test(lower)) type = "texture"
      else type = "other"
      const init = await api.post(
        "/v1/assets/upload/init",
        {
          filename: file.name,
          content_type: mime || "application/octet-stream",
          type,
          project_id: projectId,
        },
        { signal } as unknown as Record<string, unknown>,
      )
      const putRes = await fetch(init.data.upload_url, {
        method: "PUT",
        body: file,
        headers: { "Content-Type": mime || "application/octet-stream" },
        signal,
      })
      if (!putRes.ok) throw new Error(`Asset upload failed (${putRes.status})`)
      const complete = await api.post(
        "/v1/assets/upload/complete",
        { asset_id: init.data.asset_id, size: file.size },
        { signal } as unknown as Record<string, unknown>,
      )
      return complete.data
    },
    onMutate: async (file: File) => {
      await queryClient.cancelQueries({ queryKey: queryKeys.assets.list(projectId) })
      // transaction: snapshot previous assets for potential rollback
      const previous = queryClient.getQueryData(queryKeys.assets.list(projectId))
      // progress could be tracked via external store; placeholder for transaction handling
      return { fileName: file.name, previous }
    },
    onError: (_err, _file, context) => {
      // rollback transaction if needed
      if (context?.previous) {
        queryClient.setQueryData(queryKeys.assets.list(projectId), context.previous)
      }
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.assets.list(projectId) })
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.assets.all(projectId) })
    },
  })
}
