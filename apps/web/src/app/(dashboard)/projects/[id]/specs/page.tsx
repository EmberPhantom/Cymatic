"use client"

import { useParams } from "next/navigation"
import { useSpecs } from "@/hooks/use-specs"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"

export default function SpecsPage() {
  const params = useParams()
  const projectId = Number(params.id)
  const { data: specs, isLoading } = useSpecs(projectId)

  return (
    <div>
      <h3 className="text-lg font-semibold mb-4">Specifications</h3>
      {isLoading ? (
        <div className="space-y-3">
          {[1, 2].map((i) => (
            <Card key={i} className="animate-pulse">
              <CardContent className="p-6"><div className="h-4 bg-gray-200 rounded w-1/3" /></CardContent>
            </Card>
          ))}
        </div>
      ) : specs && specs.length > 0 ? (
        <div className="space-y-3">
          {specs.map((spec) => (
            <Card key={spec.id}>
              <CardHeader className="pb-2">
                <CardTitle className="text-base flex items-center justify-between">
                  <span>Spec v{spec.version}</span>
                  <span className={`text-xs px-2 py-1 rounded-full ${
                    spec.status === "active" ? "bg-green-100 text-green-700" : "bg-gray-100 text-gray-600"
                  }`}>
                    {spec.status}
                  </span>
                </CardTitle>
              </CardHeader>
              <CardContent>
                <p className="text-sm text-muted-foreground">
                  Created: {new Date(spec.created_at).toLocaleString()}
                </p>
                <details className="mt-2">
                  <summary className="text-sm text-primary cursor-pointer hover:underline">View JSON</summary>
                  <pre className="mt-2 text-xs bg-muted p-3 rounded overflow-auto max-h-48">
                    {JSON.stringify(spec.payload_json, null, 2)}
                  </pre>
                </details>
              </CardContent>
            </Card>
          ))}
        </div>
      ) : (
        <p className="text-muted-foreground">No specs yet. Use the builder to generate one.</p>
      )}
    </div>
  )
}
