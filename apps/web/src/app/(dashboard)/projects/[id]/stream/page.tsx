"use client"

import { useParams } from "next/navigation"
import { useEffect, useRef, useState, useCallback } from "react"
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
  const [iceConnectionState, setIceConnectionState] = useState<string>("new")
  const [connectionState, setConnectionState] = useState<string>("new")
  const [signalingState, setSignalingState] = useState<string>("idle")
  const [retryKey, setRetryKey] = useState(0)
  const videoRef = useRef<HTMLVideoElement>(null)
  const wsRef = useRef<WebSocket | null>(null)
  const pcRef = useRef<RTCPeerConnection | null>(null)
  const sessionIdRef = useRef<string | null>(null)

  // keep ref in sync for beforeunload / unmount cleanup (stale closure safe)
  useEffect(() => {
    sessionIdRef.current = sessionId
  }, [sessionId])

  useEffect(() => {
    if (!sessionId) {
      setSignalingState("idle")
      setIceConnectionState("new")
      setConnectionState("new")
      return
    }
    const wsBase = process.env.NEXT_PUBLIC_WS_URL || "ws://localhost:8000"
    // Use cookie auth (withCredentials) instead of token in URL to avoid leak via logs/history
    const wsUrl = `${wsBase.replace(/^http/, "ws")}/v1/stream/ws/${encodeURIComponent(sessionId)}?type=web`
    const iceServers: RTCIceServer[] = [
      { urls: process.env.NEXT_PUBLIC_STUN_URL || "stun:stun.l.google.com:19302" },
    ]
    // Add TURN if configured (P:\Cymatic\apps\web\src\lib\config.ts:5)
    const turnUrl = process.env.NEXT_PUBLIC_TURN_URL
    const turnUser = process.env.NEXT_PUBLIC_TURN_USERNAME
    const turnPass = process.env.NEXT_PUBLIC_TURN_PASSWORD
    if (turnUrl && turnUser && turnPass) {
      iceServers.push({ urls: turnUrl, username: turnUser, credential: turnPass })
    }
    const pc = new RTCPeerConnection({ iceServers })
    pcRef.current = pc
    setIceConnectionState(pc.iceConnectionState)
    setConnectionState(pc.connectionState)
    setSignalingState("connecting")

    pc.oniceconnectionstatechange = () => {
      setIceConnectionState(pc.iceConnectionState)
      if (pc.iceConnectionState === "failed" || pc.iceConnectionState === "disconnected") {
        setSessionError(
          pc.iceConnectionState === "failed"
            ? "ICE connection failed — retry or check TURN/STUN config."
            : "ICE disconnected — network may be unstable."
        )
      }
      if (pc.iceConnectionState === "connected" || pc.iceConnectionState === "completed") {
        setSessionError(null)
      }
    }
    pc.onconnectionstatechange = () => {
      setConnectionState(pc.connectionState)
      if (pc.connectionState === "failed") {
        setSessionError("Peer connection failed. Click Retry to reconnect.")
      }
    }
    pc.ontrack = (e) => {
      if (videoRef.current) {
        // Unified plan may deliver track without stream
        const stream = e.streams && e.streams[0] ? e.streams[0] : new MediaStream([e.track])
        videoRef.current.srcObject = stream
      }
    }
    pc.onicecandidate = (e) => {
      if (e.candidate && wsRef.current?.readyState === WebSocket.OPEN) {
        wsRef.current.send(JSON.stringify({ type: "candidate", payload: e.candidate }))
      }
    }
    const ws = new WebSocket(wsUrl)
    wsRef.current = ws
    ws.onopen = () => {
      setSessionError(null)
      setSignalingState("open")
    }
    ws.onclose = () => {
      setSignalingState("closed")
      // only set error if still has session (not intentional end)
      if (sessionIdRef.current) setSessionError((prev) => prev || "Signaling closed")
    }
    ws.onerror = () => {
      setSignalingState("error")
      setSessionError("Signaling error")
    }
    ws.onmessage = async (ev) => {
      try {
        const msg = JSON.parse(ev.data)
        if (msg.type === "offer" && pcRef.current) {
          await pcRef.current.setRemoteDescription(new RTCSessionDescription(msg.payload))
          const answer = await pcRef.current.createAnswer()
          await pcRef.current.setLocalDescription(answer)
          if (ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ type: "answer", payload: answer }))
        } else if (msg.type === "candidate" && pcRef.current) {
          try {
            await pcRef.current.addIceCandidate(new RTCIceCandidate(msg.payload))
          } catch (err) {
            console.warn("addIceCandidate failed", err)
          }
        } else if (msg.type === "error") {
          setSessionError(msg.payload?.detail || msg.payload || "Stream error")
        }
      } catch (err) {
        console.warn("signaling message error", err)
      }
    }
    return () => {
      try {
        ws.close()
      } catch {}
      try {
        pc.close()
      } catch {}
      pcRef.current = null
      wsRef.current = null
      // clear video srcObject to release media
      if (videoRef.current) {
        videoRef.current.srcObject = null
      }
    }
  }, [sessionId, retryKey])

  // beforeunload + pagehide + unmount cleanup via sendBeacon (same-origin proxied to API)
  useEffect(() => {
    const handleBeforeUnload = () => {
      const sid = sessionIdRef.current
      if (sid) {
        try {
          const blob = new Blob([], { type: "application/json" })
          navigator.sendBeacon(`/v1/stream/sessions/${encodeURIComponent(sid)}/end`, blob)
        } catch {}
      }
    }
    window.addEventListener("beforeunload", handleBeforeUnload)
    window.addEventListener("pagehide", handleBeforeUnload)
    return () => {
      window.removeEventListener("beforeunload", handleBeforeUnload)
      window.removeEventListener("pagehide", handleBeforeUnload)
      // SPA navigation unmount: best-effort beacon as well
      handleBeforeUnload()
    }
  }, [])

  const handleStartStream = useCallback(async () => {
    try {
      setSessionError(null)
      setSignalingState("connecting")
      setIceConnectionState("new")
      setConnectionState("new")
      const session = await createSession.mutateAsync({ projectId })
      setSessionId(session.id)
      // session.status: handle failed explicitly — render server unavailable
      if (session.status === "failed") {
        setSessionError("The render server is unavailable. Start it and try again.")
        // keep sessionId so user can retry End Session, but allow retry flow
      }
      if (session.status && !["active", "created", "starting", "pending"].includes(session.status) && session.status !== "failed") {
        // unknown status still surface
        if (session.status !== "failed") setSessionError(null)
      }
    } catch (err: unknown) {
      const anyErr = err as { response?: { data?: { detail?: unknown } } ; message?: string }
      const detail = anyErr?.response?.data?.detail
      const msg = typeof detail === "string" ? detail : anyErr?.message || "Unable to start the stream."
      setSessionError(Array.isArray(detail) ? detail.map((d: unknown) => typeof d === "string" ? d : (d as {msg?:string})?.msg || "").join("; ") || "Unable to start the stream." : msg)
    }
  }, [createSession, projectId])

  const handleEndStream = useCallback(async () => {
    const sid = sessionIdRef.current
    if (sid) {
      try {
        // endSession expects number but API id may be string (uuid); coerce safely
        const numId = Number(sid)
        if (!Number.isNaN(numId) && String(numId) === sid) {
          await endSession.mutateAsync({ sessionId: numId })
        } else {
          // fallback: try string path via direct api for uuid sessions
          await endSession.mutateAsync({ sessionId: sid as unknown as number })
        }
      } catch {
        // fallback beacon on failure
        try {
          const blob = new Blob([], { type: "application/json" })
          navigator.sendBeacon(`/v1/stream/sessions/${encodeURIComponent(sid)}/end`, blob)
        } catch {}
      }
    }
    setSessionId(null)
    setSessionError(null)
    setSignalingState("idle")
    setIceConnectionState("new")
    setConnectionState("new")
    // clear video
    if (videoRef.current) videoRef.current.srcObject = null
  }, [endSession])

  const handleRetry = useCallback(() => {
    setSessionError(null)
    setSignalingState("connecting")
    // if no session, restart creation; else force ws/pc recreate
    if (!sessionId) {
      void handleStartStream()
    } else {
      setRetryKey((k) => k + 1)
    }
  }, [sessionId, handleStartStream])

  const showRetry = !!sessionError && (signalingState === "closed" || signalingState === "error" || iceConnectionState === "failed" || connectionState === "failed")

  return (
    <div>
      <h3 className="text-lg font-semibold mb-4">Stream</h3>
      <Card>
        <CardHeader>
          <CardTitle>VR Stream</CardTitle>
          <CardDescription>Launch a VR stream to your Android headset</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {/* aria-live for status/errors */}
          <div aria-live="polite" aria-atomic="true" className="sr-only" role="status">
            {sessionError ? `Error: ${sessionError}` : ""}
            {signalingState !== "idle" ? ` Signaling ${signalingState}.` : ""}
            {iceConnectionState !== "new" ? ` ICE ${iceConnectionState}.` : ""}
            {connectionState !== "new" ? ` Connection ${connectionState}.` : ""}
          </div>
          {sessionError && (
            <div role="alert" aria-live="assertive" className="rounded-md bg-destructive/15 p-3 text-sm text-destructive flex items-center justify-between gap-3">
              <span>{sessionError}</span>
              {showRetry && (
                <Button variant="outline" size="sm" onClick={handleRetry} aria-label="Retry stream connection">
                  Retry
                </Button>
              )}
            </div>
          )}
          {/* connection state UI */}
          {sessionId && (
            <div className="flex flex-wrap gap-2 text-xs" aria-live="polite">
              <span
                className={`inline-flex items-center rounded-full border px-2.5 py-0.5 font-medium ${
                  signalingState === "open" ? "bg-green-100 text-green-700 border-green-200" : signalingState === "error" || signalingState === "closed" ? "bg-red-100 text-red-700 border-red-200" : "bg-gray-100 text-gray-600"
                }`}
                title="Signaling WebSocket state"
              >
                Signaling: {signalingState}
              </span>
              <span
                className={`inline-flex items-center rounded-full border px-2.5 py-0.5 font-medium ${
                  iceConnectionState === "connected" || iceConnectionState === "completed"
                    ? "bg-green-100 text-green-700 border-green-200"
                    : iceConnectionState === "failed" || iceConnectionState === "disconnected"
                      ? "bg-red-100 text-red-700 border-red-200"
                      : iceConnectionState === "checking"
                        ? "bg-amber-100 text-amber-700 border-amber-200"
                        : "bg-gray-100 text-gray-600"
                }`}
                title="ICE connection state"
              >
                ICE: {iceConnectionState}
              </span>
              <span
                className={`inline-flex items-center rounded-full border px-2.5 py-0.5 font-medium ${
                  connectionState === "connected" ? "bg-green-100 text-green-700 border-green-200" : connectionState === "failed" ? "bg-red-100 text-red-700 border-red-200" : "bg-gray-100 text-gray-600"
                }`}
                title="Peer connection state"
              >
                Peer: {connectionState}
              </span>
            </div>
          )}
          {sessionId ? (
            <div className="space-y-4">
              <video
                ref={videoRef}
                autoPlay
                playsInline
                muted
                controls
                aria-label="VR Stream preview"
                className="w-full rounded bg-black aspect-video"
              />
              <div className="rounded-md bg-muted p-4 text-center">
                <p className="text-sm text-muted-foreground">Session Active</p>
                <p className="font-mono text-sm mt-1 break-all">{sessionId}</p>
              </div>
              <p className="text-sm text-muted-foreground text-center">
                Connect your Android VR client to start streaming. Video will appear above when the render server connects.
              </p>
              <div className="flex gap-2">
                {showRetry && (
                  <Button variant="outline" className="flex-1" onClick={handleRetry}>
                    Retry Connection
                  </Button>
                )}
                <Button variant="outline" className="flex-1" onClick={handleEndStream} disabled={endSession.isPending}>
                  End Session
                </Button>
              </div>
            </div>
          ) : (
            <div className="text-center py-8">
              <Button onClick={handleStartStream} disabled={createSession.isPending} size="lg">
                {createSession.isPending ? "Starting..." : "Start VR Stream"}
              </Button>
              {showRetry && (
                <Button variant="outline" className="ml-2" onClick={handleRetry}>
                  Retry
                </Button>
              )}
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
