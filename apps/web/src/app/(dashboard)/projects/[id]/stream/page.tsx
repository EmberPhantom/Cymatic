"use client"

import { useParams } from "next/navigation"
import { useEffect, useRef, useState } from "react"
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
  const videoRef = useRef<HTMLVideoElement>(null)
  const wsRef = useRef<WebSocket | null>(null)
  const pcRef = useRef<RTCPeerConnection | null>(null)

  useEffect(() => {
    if (!sessionId) return
    const token = (() => { try { const raw = localStorage.getItem("auth-storage"); if (raw) { const p = JSON.parse(raw); return p?.state?.token || p?.token || "" } } catch {} return "" })()
    const wsBase = process.env.NEXT_PUBLIC_WS_URL || "ws://localhost:8000"
    const ws = new WebSocket(`${wsBase.replace(/^http/, "ws")}/v1/stream/ws/${sessionId}?token=${encodeURIComponent(token)}&type=web`)
    wsRef.current = ws
    ws.onopen = () => setSessionError(null)
    ws.onclose = () => setSessionError("Signaling closed")
    ws.onerror = () => setSessionError("Signaling error")
    ws.onmessage = async (ev) => {
      try {
        const msg = JSON.parse(ev.data)
        if (msg.type === "offer" && pcRef.current) {
          await pcRef.current.setRemoteDescription(new RTCSessionDescription(msg.payload))
          const answer = await pcRef.current.createAnswer()
          await pcRef.current.setLocalDescription(answer)
          ws.send(JSON.stringify({ type: "answer", payload: answer }))
        } else if (msg.type === "candidate" && pcRef.current) {
          await pcRef.current.addIceCandidate(new RTCIceCandidate(msg.payload))
        }
      } catch {}
    }
    const pc = new RTCPeerConnection({ iceServers: [{ urls: process.env.NEXT_PUBLIC_STUN_URL || "stun:stun.l.google.com:19302" }] })
    pcRef.current = pc
    pc.ontrack = (e) => { if (videoRef.current) videoRef.current.srcObject = e.streams[0] }
    pc.onicecandidate = (e) => { if (e.candidate) ws.send(JSON.stringify({ type: "candidate", payload: e.candidate })) }
    return () => { try { ws.close() } catch {}; try { pc.close() } catch {}; pcRef.current = null; wsRef.current = null }
  }, [sessionId])

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
              <video ref={videoRef} autoPlay playsInline muted className="w-full rounded bg-black aspect-video" />
              <div className="rounded-md bg-muted p-4 text-center">
                <p className="text-sm text-muted-foreground">Session Active</p>
                <p className="font-mono text-sm mt-1">{sessionId}</p>
              </div>
              <p className="text-sm text-muted-foreground text-center">
                Connect your Android VR client to start streaming. Video will appear above when the render server connects.
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
