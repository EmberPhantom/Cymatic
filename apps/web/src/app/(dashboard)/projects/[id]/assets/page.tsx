"use client"

import { useParams } from "next/navigation"
import { useRef } from "react"
import { useAssets } from "@/hooks/use-assets"
import { useUploadAsset } from "@/hooks/use-upload-asset"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"

export default function AssetsPage() {
  const params = useParams()
  const projectId = Number(params.id)
  const { data: assets, isLoading } = useAssets(projectId)
  const upload = useUploadAsset(projectId)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (file) {
      await upload.mutateAsync(file)
      if (fileInputRef.current) fileInputRef.current.value = ""
    }
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-lg font-semibold">Assets</h3>
        <div>
          <input ref={fileInputRef} type="file" className="hidden" onChange={handleUpload} />
          <Button size="sm" onClick={() => fileInputRef.current?.click()} disabled={upload.isPending}>
            {upload.isPending ? "Uploading..." : "Upload Asset"}
          </Button>
        </div>
      </div>
      {isLoading ? (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          {[1, 2, 3, 4].map((i) => (
            <Card key={i} className="animate-pulse"><CardContent className="p-4"><div className="h-20 bg-gray-200 rounded" /></CardContent></Card>
          ))}
        </div>
      ) : assets && assets.length > 0 ? (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          {assets.map((asset) => (
            <Card key={asset.id} className="hover:shadow-md transition-shadow">
              <CardContent className="p-4">
                <div className="h-20 bg-muted rounded flex items-center justify-center text-2xl mb-2">
                  {asset.content_type?.startsWith("image/") ? "🖼️" : asset.content_type?.includes("audio") ? "🎵" : "📄"}
                </div>
                <p className="text-sm font-medium truncate">{asset.filename}</p>
                <p className="text-xs text-muted-foreground">{(asset.size / 1024).toFixed(1)} KB</p>
              </CardContent>
            </Card>
          ))}
        </div>
      ) : (
        <p className="text-muted-foreground">No assets uploaded yet.</p>
      )}
    </div>
  )
}
