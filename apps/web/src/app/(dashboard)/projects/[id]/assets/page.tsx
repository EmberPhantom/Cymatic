"use client"

import { useParams } from "next/navigation"
import { useRef, useState, useCallback, useMemo } from "react"
import { useAssets } from "@/hooks/use-assets"
import { useUploadAsset } from "@/hooks/use-upload-asset"
import { config } from "@/lib/config"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Skeleton } from "@/components/ui/skeleton"
import {
  Upload,
  Box,
  Image as ImageIcon,
  Music,
  FileText,
  Check,
  HardDrive,
  FolderOpen,
  Plus
} from "lucide-react"

type AssetCategory = "all" | "models" | "textures" | "audio" | "docs"

function getAssetVisual(asset: {
  type?: string
  content_type?: string
  metadata_json?: Record<string, unknown>
  filename?: string
  storage_key?: string
}) {
  const meta = (asset.metadata_json || {}) as Record<string, unknown>
  const ctype =
    (asset.content_type as string) ||
    (meta.content_type as string) ||
    (meta.original_content_type as string) ||
    ""
  const lowerCtype = ctype.toLowerCase()
  const filename =
    (asset.filename as string) ||
    (meta.original_filename as string) ||
    (meta.filename as string) ||
    (asset.storage_key?.split("/").pop() as string) ||
    "asset"
  const lowerName = filename.toLowerCase()
  const type = (asset.type as string) || ""

  // 3D Model
  if (
    type === "model_3d" ||
    lowerCtype.includes("model") ||
    lowerCtype === "model/gltf-binary" ||
    lowerCtype.includes("gltf") ||
    /\.(glb|gltf|fbx|obj)$/i.test(lowerName)
  ) {
    return { kind: "model" as const, label: "3D Model", filename, ctype, category: "models" as const }
  }
  // Audio
  if (
    lowerCtype.startsWith("audio/") ||
    type === "audio" ||
    /\.(mp3|wav|ogg|m4a|flac)$/i.test(lowerName)
  ) {
    return { kind: "audio" as const, label: "Audio", filename, ctype, category: "audio" as const }
  }
  // Texture
  if (type === "texture") {
    return { kind: "texture" as const, label: "Texture", filename, ctype, category: "textures" as const }
  }
  // Image
  if (
    lowerCtype.startsWith("image/") ||
    /\.(png|jpg|jpeg|webp|hdr|exr|gif|bmp)$/i.test(lowerName)
  ) {
    return { kind: "image" as const, label: "Image", filename, ctype, category: "textures" as const }
  }

  return { kind: "other" as const, label: "Document", filename, ctype, category: "docs" as const }
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
  const [category, setCategory] = useState<AssetCategory>("all")

  const handleFiles = useCallback(
    async (files: FileList | File[]) => {
      const fileArray = Array.from(files)
      if (fileArray.length === 0) return
      setUploadError(null)
      setUploadSuccess(null)

      const tooLarge = fileArray.filter((f) => f.size > config.maxUploadMB * 1024 * 1024)
      if (tooLarge.length > 0) {
        setUploadError(`Files exceeding ${config.maxUploadMB}MB limit: ${tooLarge.map((f) => f.name).join(", ")}`)
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
      if (successCount > 0) setUploadSuccess(`Uploaded ${successCount} asset file(s) to MinIO`)
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

  // Filter assets by selected category
  const filteredAssets = useMemo(() => {
    if (!assets) return []
    if (category === "all") return assets
    return assets.filter((asset: any) => {
      const visual = getAssetVisual(asset)
      return visual.category === category
    })
  }, [assets, category])

  return (
    <div className="space-y-6">
      {/* Top Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-3 border-b border-border">
        <div>
          <div className="flex items-center gap-2 text-[10px] font-mono uppercase tracking-widest text-stonegray mb-0.5">
            <span className="text-terracotta font-bold">SPATIAL ASSET LIBRARY</span>
            <span>&bull;</span>
            <span>MINIO REPOSITORY</span>
          </div>
          <h1 className="text-xl sm:text-2xl font-bold tracking-tight text-foreground">
            Asset Repository
          </h1>
        </div>

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
          <Button
            variant="terracotta"
            size="sm"
            onClick={() => fileInputRef.current?.click()}
            disabled={upload.isPending}
            className="gap-1.5 font-medium shadow-sm"
          >
            <Plus className="h-4 w-4" />
            <span>{upload.isPending ? "Uploading…" : "+ Upload Asset"}</span>
          </Button>
        </div>
      </div>

      {/* Drag & Drop Upload Zone */}
      <div
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        role="region"
        aria-label="Upload drop zone"
        className={`rounded-2xl border-2 border-dashed p-8 text-center transition-all ${
          isDragOver
            ? "border-terracotta bg-terracotta-50/40 dark:bg-terracotta-950/20 shadow-sm"
            : "border-warmgray bg-muted/20 hover:border-foreground/40 hover:bg-muted/30"
        } ${upload.isPending ? "opacity-60 pointer-events-none" : ""}`}
      >
        <div className="h-10 w-10 rounded-xl bg-card border border-warmgray text-terracotta mx-auto flex items-center justify-center mb-2 shadow-sm">
          <Upload className="h-5 w-5" />
        </div>
        <p className="text-xs font-semibold text-foreground">
          Drag &amp; drop 3D models, textures, or audio narration files here
        </p>
        <p className="text-[11px] text-stonegray mt-1">
          Supports .glb, .gltf, .fbx, .obj, .png, .jpg, .webp, .hdr, .mp3, .wav (Max {config.maxUploadMB}MB per file)
        </p>
      </div>

      {uploadError && (
        <div role="alert" className="rounded-xl bg-destructive/10 border border-destructive/20 p-3 text-xs text-destructive">
          {uploadError}
        </div>
      )}
      {uploadSuccess && (
        <div role="status" className="rounded-xl bg-sage-50 dark:bg-sage-950/30 border border-sage-200 dark:border-sage-800 p-3 text-xs text-sage flex items-center gap-2">
          <Check className="h-4 w-4" />
          <span>{uploadSuccess}</span>
        </div>
      )}

      {/* Category Tabs */}
      <div className="flex items-center gap-1.5 border-b border-border pb-2 overflow-x-auto">
        <button
          type="button"
          onClick={() => setCategory("all")}
          className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
            category === "all" ? "bg-charcoal text-white dark:bg-ivory dark:text-charcoal font-semibold shadow-sm" : "text-stonegray hover:text-foreground hover:bg-muted/40"
          }`}
        >
          All Assets ({assets?.length || 0})
        </button>
        <button
          type="button"
          onClick={() => setCategory("models")}
          className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
            category === "models" ? "bg-charcoal text-white dark:bg-ivory dark:text-charcoal font-semibold shadow-sm" : "text-stonegray hover:text-foreground hover:bg-muted/40"
          }`}
        >
          3D Models (.glb, .obj)
        </button>
        <button
          type="button"
          onClick={() => setCategory("textures")}
          className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
            category === "textures" ? "bg-charcoal text-white dark:bg-ivory dark:text-charcoal font-semibold shadow-sm" : "text-stonegray hover:text-foreground hover:bg-muted/40"
          }`}
        >
          Textures &amp; Images
        </button>
        <button
          type="button"
          onClick={() => setCategory("audio")}
          className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
            category === "audio" ? "bg-charcoal text-white dark:bg-ivory dark:text-charcoal font-semibold shadow-sm" : "text-stonegray hover:text-foreground hover:bg-muted/40"
          }`}
        >
          Audio &amp; Narration
        </button>
      </div>

      {/* Assets Grid */}
      {isLoading ? (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          {[1, 2, 3, 4].map((i) => (
            <Card key={i} className="border-warmgray">
              <CardContent className="p-4">
                <Skeleton className="h-24 w-full rounded-lg mb-3" />
                <Skeleton className="h-4 w-3/4 rounded" />
                <Skeleton className="h-3 w-1/2 rounded mt-2" />
              </CardContent>
            </Card>
          ))}
        </div>
      ) : filteredAssets && filteredAssets.length > 0 ? (
        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-4">
          {filteredAssets.map((asset: any) => {
            const meta = (asset.metadata_json || {}) as Record<string, unknown>
            const size = (asset.size as number) || (meta.size as number) || (meta.original_size as number) || null
            const visual = getAssetVisual(asset)
            const filename = visual.filename
            const isImage = visual.kind === "image" || visual.kind === "texture"
            const isModel = visual.kind === "model"
            const isAudio = visual.kind === "audio"

            const badgeVariant = isModel ? "sage" : isImage ? "terracotta" : isAudio ? "gold" : "outline"

            const imageUrl = (() => {
              if (!isImage) return null
              const urlFromMeta = (meta.url as string) || (meta.preview_url as string) || (meta.storage_url as string)
              if (urlFromMeta) return urlFromMeta
              if (asset.storage_key && config.minioUrl) {
                const base = config.minioUrl.replace(/\/$/, "")
                return `${base}/${String(asset.storage_key).replace(/^\//, "")}`
              }
              return null
            })()

            return (
              <Card
                key={asset.id}
                tabIndex={0}
                className="border-warmgray bg-card hover:border-foreground/40 hover:shadow-sm transition-all overflow-hidden flex flex-col justify-between"
              >
                <CardContent className="p-3.5 space-y-3">
                  {/* Thumbnail / Graphic representation */}
                  <div className="h-28 bg-charcoal text-white rounded-xl flex items-center justify-center overflow-hidden relative border border-warmgray/40">
                    {isImage && imageUrl ? (
                      // eslint-disable-next-line @next/next/no-img-element
                      <img
                        src={imageUrl}
                        alt={filename}
                        className="h-full w-full object-cover"
                        loading="lazy"
                        onError={(e) => {
                          ;(e.currentTarget as HTMLImageElement).style.display = "none"
                        }}
                      />
                    ) : isModel ? (
                      <div className="flex flex-col items-center justify-center text-sage">
                        <Box className="h-8 w-8" />
                        <span className="text-[9px] font-mono text-stonegray-300 mt-1">LOD0 3D MESH</span>
                      </div>
                    ) : isAudio ? (
                      <div className="flex flex-col items-center justify-center text-gold">
                        <Music className="h-8 w-8" />
                        <span className="text-[9px] font-mono text-stonegray-300 mt-1">VOICE TRACK</span>
                      </div>
                    ) : (
                      <div className="flex flex-col items-center justify-center text-stonegray">
                        <FileText className="h-8 w-8" />
                        <span className="text-[9px] font-mono text-stonegray-300 mt-1">DOCUMENT</span>
                      </div>
                    )}

                    <div className="absolute top-2 right-2">
                      <Badge variant={badgeVariant} className="text-[9px] font-mono uppercase px-1.5 py-0">
                        {visual.label}
                      </Badge>
                    </div>
                  </div>

                  {/* Asset Metadata */}
                  <div className="space-y-1">
                    <p className="text-xs font-bold truncate text-foreground" title={filename}>
                      {filename}
                    </p>
                    <div className="flex items-center justify-between text-[10px] font-mono text-stonegray">
                      <span>{size ? `${(Number(size) / 1024).toFixed(1)} KB` : "Stored"}</span>
                      <span className="text-sage font-medium">Used in Scene</span>
                    </div>
                  </div>
                </CardContent>
              </Card>
            )
          })}
        </div>
      ) : (
        <div className="rounded-xl border border-dashed border-warmgray p-10 text-center max-w-md mx-auto my-6">
          <FolderOpen className="h-8 w-8 text-stonegray mx-auto mb-2 opacity-50" />
          <h3 className="text-sm font-bold text-foreground">No Assets in Category</h3>
          <p className="text-xs text-stonegray mt-1">
            Upload 3D models or textures to populate the spatial repository for this project.
          </p>
        </div>
      )}
    </div>
  )
}
