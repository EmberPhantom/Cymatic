"use client"

import { useParams } from "next/navigation"
import { useState } from "react"
import { useCreateStreamSession, useEndStreamSession } from "@/hooks/use-stream-session"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"

export default function StreamPage() {
  const params = useParams()
  const projectId = Number(params.id)
  const createSession = useCreateStreamSession()
  const endSession = useEndStreamSession()
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [sessionError, setSessionError] = useState<string | null>(null)

  const handleStartStream = async () => {
    try {
      setSessionError(null)
      const session = await createSession.mutateAsync({ projectId })
      setSessionId(session.id)
      if (session.status === "failed") setSessionError("The render server is unavailable. Start it and try again.")
    } catch (err: any) {
      setSessionError(err?.response?.data?.detail || "Unable to start the stream.")
    }
  }

  const handleEndStream = async () => {
    if (sessionId) await endSession.mutateAsync({ sessionId: Number(sessionId) })
    setSessionId(null)
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
          {sessionError && <div className="rounded-md bg-destructive/15 p-3 text-sm text-destructive">{sessionError}</div>}
          {sessionId ? (
            <div className="space-y-4">
              <div className="rounded-md bg-muted p-4 text-center">
                <p className="text-sm text-muted-foreground">Session Active</p>
                <p className="font-mono text-sm mt-1">{sessionId}</p>
              </div>
              <p className="text-sm text-muted-foreground text-center">
                Connect your Android VR client to start streaming.
              </p>
              <Button variant="outline" className="w-full" onClick={handleEndStream} disabled={endSession.isPending}>
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
