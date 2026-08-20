"use client"

import { useParams } from "next/navigation"
import { useState } from "react"
import { useCreateStreamSession } from "@/hooks/use-stream-session"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"

export default function StreamPage() {
  const params = useParams()
  const projectId = Number(params.id)
  const createSession = useCreateStreamSession()
  const [sessionId, setSessionId] = useState<string | null>(null)

  const handleStartStream = async () => {
    try {
      const session = await createSession.mutateAsync({ projectId })
      setSessionId(session.id)
    } catch (err) {
      console.error("Failed to create session:", err)
    }
  }

  return (
    <div>
      <h3 className="text-lg font-semibold mb-4">Stream</h3>
      <Card>
        <CardHeader>
          <CardTitle>VR Stream</CardTitle>
          <CardDescription>Launch a VR stream to your Android headset</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {sessionId ? (
            <div className="space-y-4">
              <div className="rounded-md bg-muted p-4 text-center">
                <p className="text-sm text-muted-foreground">Session Active</p>
                <p className="font-mono text-sm mt-1">{sessionId}</p>
              </div>
              <p className="text-sm text-muted-foreground text-center">
                Connect your Android VR client to start streaming.
              </p>
              <Button variant="outline" className="w-full" onClick={() => setSessionId(null)}>
                End Session
              </Button>
            </div>
          ) : (
            <div className="text-center py-8">
              <Button onClick={handleStartStream} disabled={createSession.isPending} size="lg">
                {createSession.isPending ? "Starting..." : "Start VR Stream"}
              </Button>
              <p className="text-sm text-muted-foreground mt-3">
                Make sure your render server is running and the Android client is connected.
              </p>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
