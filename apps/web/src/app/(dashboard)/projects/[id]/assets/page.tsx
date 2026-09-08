"use client"

import { useParams } from "next/navigation"
import { useRef, useState, useCallback } from "react"
import { useAssets } from "@/hooks/use-assets"
import { useUploadAsset } from "@/hooks/use-upload-asset"
import { config } from "@/lib/config"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"

function getAssetVisual(asset: { type?: string; content_type?: string; metadata_json?: Record<string, unknown>; filename?: string; storage_key?: string }) {
  const meta = (asset.metadata_json || {}) as Record<string, unknown>
  const ctype = (asset.content_type as string) || (meta.content_type as string) || (meta.original_content_type as string) || ""
  const lowerCtype = ctype.toLowerCase()
  const filename = (asset.filename as string) || (meta.original_filename as string) || (meta.filename as string) || (asset.storage_key?.split("/").pop() as string) || "asset"
  const lowerName = filename.toLowerCase()
  const type = (asset.type as string) || ""

  // image
  if (lowerCtype.startsWith("image/") || /\.(png|jpg|jpeg|webp|hdr|exr|gif|bmp)$/i.test(lowerName)) {
    return { kind: "image" as const, icon: "🖼️", label: "Image", filename, ctype }
  }
  // audio
  if (lowerCtype.startsWith("audio/") || type === "audio" || /\.(mp3|wav|ogg|m4a|flac)$/i.test(lowerName)) {
    return { kind: "audio" as const, icon: "🎵", label: "Audio", filename, ctype }
  }
  // model_3d — must check extension because Android file.type is "" for .glb and ctype may be octet-stream
  if (type === "model_3d" || lowerCtype.includes("model") || lowerCtype === "model/gltf-binary" || lowerCtype.includes("gltf") || /\.(glb|gltf|fbx|obj)$/i.test(lowerName)) {
    return { kind: "model" as const, icon: "📦", label: "3D Model", filename, ctype }
  }
  // texture fallback
  if (type === "texture" || /\.(png|jpg|jpeg|webp)$/i.test(lowerName)) {
    return { kind: "image" as const, icon: "🖼️", label: "Texture", filename, ctype }
  }
  return { kind: "other" as const, icon: "📄", label: "File", filename, ctype }
}

export default function AssetsPage() {
  const params = useParams()
  const projectId = Number(params.id)
  const { data: assets, isLoading } = useAssets(projectId)
  const upload = useUploadAsset(projectId)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [isDragOver, setIsDragOver] = useState(false)
  const [uploadError, setUploadError] = useState<string | null>(null)
  const [uploadSuccess, setUploadSuccess] = useState<string | null>(null)

  const handleFiles = useCallback(
    async (files: FileList | File[]) => {
      const fileArray = Array.from(files)
      if (fileArray.length === 0) return
      // clear previous status
      setUploadError(null)
      setUploadSuccess(null)
      // No duplicate size check here vs hook: delegate to useUploadAsset which uses config.maxUploadMB.
      // We still provide friendly batch validation using config for early feedback without hardcoding 50MB.
      const tooLarge = fileArray.filter((f) => f.size > config.maxUploadMB * 1024 * 1024)
      if (tooLarge.length > 0) {
        setUploadError(`Some files exceed ${config.maxUploadMB}MB: ${tooLarge.map((f) => f.name).join(", ")}`)
        // still attempt to upload the valid ones rather than blocking all
      }
      const validFiles = fileArray.filter((f) => f.size <= config.maxUploadMB * 1024 * 1024)
      if (validFiles.length === 0) {
        if (fileInputRef.current) fileInputRef.current.value = ""
        return
      }
      let successCount = 0
      for (const file of validFiles) {
        try {
          await upload.mutateAsync(file)
          successCount++
        } catch (err: unknown) {
          const msg = err instanceof Error ? err.message : typeof err === "string" ? err : "Upload failed"
          setUploadError((prev) => (prev ? `${prev}; ${file.name}: ${msg}` : `${file.name}: ${msg}`))
        }
      }
      if (successCount > 0) setUploadSuccess(`Uploaded ${successCount} file(s)`)
      if (fileInputRef.current) fileInputRef.current.value = ""
    },
    [upload]
  )

  const handleInputChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files
    if (files) await handleFiles(files)
  }

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault()
    e.stopPropagation()
    setIsDragOver(true)
  }
  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault()
    e.stopPropagation()
    setIsDragOver(false)
  }
  const handleDrop = async (e: React.DragEvent) => {
    e.preventDefault()
    e.stopPropagation()
    setIsDragOver(false)
    const files = e.dataTransfer.files
    if (files && files.length > 0) await handleFiles(files)
  }

  const handleKeyActivate = (e: React.KeyboardEvent, filename: string) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault()
      // focusable card: could open preview in future; for now announce
      // keep keyboard accessible
    }
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-lg font-semibold">Assets</h3>
        <div>
          <input
            ref={fileInputRef}
            type="file"
            accept=".glb,.gltf,.fbx,.obj,.png,.jpg,.jpeg,.webp,.hdr,.exr,.mp3,.wav,.ogg,.m4a"
            className="hidden"
            onChange={handleInputChange}
            multiple
            aria-label="Upload assets"
          />
          <Button size="sm" onClick={() => fileInputRef.current?.click()} disabled={upload.isPending}>
            {upload.isPending ? "Uploading..." : "Upload Asset"}
          </Button>
        </div>
      </div>

      {/* drag-drop zone + aria-live */}
      <div
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        role="region"
        aria-label="Upload drop zone"
        className={`mb-4 rounded-lg border-2 border-dashed p-6 text-center transition-colors ${isDragOver ? "border-primary bg-primary/5" : "border-muted-foreground/25 hover:border-muted-foreground/50"} ${upload.isPending ? "opacity-60 pointer-events-none" : ""}`}
      >
        <p className="text-sm text-muted-foreground">
          Drag & drop files here, or click Upload Asset. Supports multiple files. Max {config.maxUploadMB}MB per file.
        </p>
        <p className="text-xs text-muted-foreground mt-1">Accepted: .glb .gltf .fbx .obj .png .jpg .webp .mp3 .wav .ogg</p>
      </div>

      <div aria-live="polite" aria-atomic="true" className="sr-only" role="status">
        {uploadError ? `Upload error: ${uploadError}` : ""}
        {uploadSuccess ? uploadSuccess : ""}
        {upload.isPending ? "Uploading..." : ""}
      </div>
      {uploadError && (
        <div role="alert" className="mb-3 rounded-md bg-destructive/15 p-3 text-sm text-destructive">
          {uploadError}
        </div>
      )}
      {uploadSuccess && (
        <div role="status" className="mb-3 rounded-md bg-green-50 p-3 text-sm text-green-700 border border-green-200">
          {uploadSuccess}
        </div>
      )}

      {isLoading ? (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          {[1, 2, 3, 4].map((i) => (
            <Card key={i}>
              <CardContent className="p-4">
                <Skeleton className="h-20 w-full rounded mb-2" />
                <Skeleton className="h-4 w-3/4 rounded" />
                <Skeleton className="h-3 w-1/2 rounded mt-2" />
              </CardContent>
            </Card>
          ))}
        </div>
      ) : assets && assets.length > 0 ? (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          {assets.map((asset: { id: string | number; metadata_json?: Record<string, unknown>; content_type?: string; size?: number; filename?: string; storage_key?: string; status?: string; type?: string }) => {
            const meta = (asset.metadata_json || {}) as Record<string, unknown>
            const size = (asset.size as number) || (meta.size as number) || (meta.original_size as number) || null
            const visual = getAssetVisual(asset as unknown as { type?: string; content_type?: string; metadata_json?: Record<string, unknown>; filename?: string; storage_key?: string })
            const filename = visual.filename
            const isImage = visual.kind === "image"

            // Try to resolve image URL: storage_key may be minio key; if image, construct preview URL via minioUrl if available
            // Fallback to emoji if no URL; alt handled for image.
            const imageUrl = (() => {
              if (!isImage) return null
              // prefer explicit url fields if backend provides them
              const urlFromMeta = (meta.url as string) || (meta.preview_url as string) || (meta.storage_url as string)
              if (urlFromMeta) return urlFromMeta
              // storage_key like "project/123/asset.glb" — join with minioUrl if present
              if (asset.storage_key && config.minioUrl) {
                // MinIO bucket assumed from key first segment? Use direct key path.
                const base = config.minioUrl.replace(/\/$/, "")
                // Heuristic: bucket may be part of key; just append key
                return `${base}/${String(asset.storage_key).replace(/^\//, "")}`
              }
              return null
            })()

            return (
              <Card
                key={asset.id}
                tabIndex={0}
                role="group"
                aria-label={`${visual.label}: ${filename}`}
                onKeyDown={(e) => handleKeyActivate(e, filename)}
                className="hover:shadow-md transition-shadow focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
              >
                <CardContent className="p-4">
                  <div className="h-20 bg-muted rounded flex items-center justify-center text-2xl mb-2 overflow-hidden">
                    {isImage && imageUrl ? (
                      // eslint-disable-next-line @next/next/no-img-element
                      <img
                        src={imageUrl}
                        alt={filename}
                        className="h-full w-full object-cover"
                        loading="lazy"
                        onError={(e) => {
                          // fallback to icon on load failure
                          ;(e.currentTarget as HTMLImageElement).style.display = "none"
                          const fallback = e.currentTarget.nextElementSibling as HTMLElement | null
                          if (fallback) fallback.style.display = "flex"
                        }}
                      />
                    ) : null}
                    {/* fallback / default visual */}
                    <span
                      aria-hidden="true"
                      className={isImage && imageUrl ? "hidden items-center justify-center w-full h-full" : "flex items-center justify-center w-full h-full"}
                    >
                      {visual.icon}
                    </span>
                  </div>
                  <p className="text-sm font-medium truncate" title={filename}>
                    {filename}
                  </p>
                  <p className="text-xs text-muted-foreground">
                    {size ? `${(Number(size) / 1024).toFixed(1)} KB` : String(asset.status ?? visual.label)}
                    {visual.kind !== "other" ? ` · ${visual.label}` : ""}
                  </p>
                </CardContent>
              </Card>
            )
          })}
        </div>
      ) : (
        <p className="text-muted-foreground">No assets uploaded yet.</p>
      )}
    </div>
  )
}
