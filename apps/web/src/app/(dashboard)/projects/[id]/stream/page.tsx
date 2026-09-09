"use client"

import { useParams } from "next/navigation"
import Link from "next/link"
import { useEffect, useRef, useState, useCallback } from "react"
import { useCreateStreamSession, useEndStreamSession } from "@/hooks/use-stream-session"
import { useProject } from "@/hooks/use-project"
import { useAuthStore } from "@/stores/auth-store"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"

import { Badge } from "@/components/ui/badge"
import {
  Glasses,
  Radio,
  Wifi,
  Activity,
  Monitor,
  ShieldCheck,
  ArrowRight,
  RefreshCw,
  AlertTriangle,
  Play
} from "lucide-react"

export default function StreamPage() {
  const params = useParams()
  const projectId = Number(params.id)
  const { data: project } = useProject(Number.isNaN(projectId) ? null : projectId)
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
    const token = useAuthStore.getState().token
    const qs = new URLSearchParams({ type: "web" })
    if (token) qs.set("token", token)
    const wsUrl = `${wsBase.replace(/^http/, "ws")}/v1/stream/ws/${encodeURIComponent(sessionId)}?${qs.toString()}`
    const iceServers: RTCIceServer[] = [
      { urls: process.env.NEXT_PUBLIC_STUN_URL || "stun:stun.l.google.com:19302" },
    ]
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
            ? "ICE connection failed — check network or TURN server."
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
      try { ws.close() } catch {}
      try { pc.close() } catch {}
      pcRef.current = null
      wsRef.current = null
      if (videoRef.current) videoRef.current.srcObject = null
    }
  }, [sessionId, retryKey])

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
      if (session.status === "failed") {
        setSessionError("The render server is unavailable. Please verify it is running and retry.")
      }
    } catch (err: unknown) {
      const anyErr = err as { response?: { data?: { detail?: unknown } } ; message?: string }
      const detail = anyErr?.response?.data?.detail
      const msg = typeof detail === "string" ? detail : anyErr?.message || "Unable to start stream."
      setSessionError(Array.isArray(detail) ? detail.map((d: unknown) => typeof d === "string" ? d : (d as {msg?:string})?.msg || "").join("; ") || "Unable to start stream." : msg)
    }
  }, [createSession, projectId])

  const handleEndStream = useCallback(async () => {
    const sid = sessionIdRef.current
    if (sid) {
      try {
        const numId = Number(sid)
        if (!Number.isNaN(numId) && String(numId) === sid) {
          await endSession.mutateAsync({ sessionId: numId })
        } else {
          await endSession.mutateAsync({ sessionId: sid as unknown as number })
        }
      } catch {
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
    if (videoRef.current) videoRef.current.srcObject = null
  }, [endSession])

  const handleRetry = useCallback(() => {
    setSessionError(null)
    setSignalingState("connecting")
    if (!sessionId) {
      void handleStartStream()
    } else {
      setRetryKey((k) => k + 1)
    }
  }, [sessionId, handleStartStream])

  const showRetry = !!sessionError && (signalingState === "closed" || signalingState === "error" || iceConnectionState === "failed" || connectionState === "failed")
  const isPublished = project?.status === "published" || project?.status === "scene_ready"
  const isHeritage = project?.domain === "heritage"
  const isConnected = connectionState === "connected"

  return (
    <div className="space-y-6">
      {/* Top Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-3 border-b border-border">
        <div>
          <div className="flex items-center gap-2 text-[10px] font-mono uppercase tracking-widest text-stonegray mb-0.5">
            <span className={isHeritage ? "text-sage font-bold" : "text-terracotta font-bold"}>
              VR STREAMING CONTROL CONSOLE
            </span>
            <span>&bull;</span>
            <span>WEBRTC STEREO RIG</span>
          </div>
          <h1 className="text-xl sm:text-2xl font-bold tracking-tight text-foreground">
            {project?.name || "Simulation"} Stream
          </h1>
        </div>

        <div className="flex items-center gap-2">
          <Badge variant={isHeritage ? "sage" : "terracotta"} className="text-xs font-mono uppercase">
            {isHeritage ? "Heritage Walkthrough" : "Real Estate"}
          </Badge>
          <Badge variant={isConnected ? "sage" : sessionId ? "terracotta" : "outline"} className="text-xs font-mono uppercase">
            {isConnected ? "STREAM ACTIVE" : sessionId ? "CONNECTING" : "CONSOLE IDLE"}
          </Badge>
        </div>
      </div>

      {!isPublished && (
        <div role="alert" className="rounded-xl bg-gold-50 dark:bg-gold-950/20 p-3.5 text-xs text-gold-700 dark:text-gold-300 border border-gold-200 dark:border-gold-800 flex items-center justify-between gap-3">
          <span>This simulation must be compiled in the Builder before launch (status: <strong>{project?.status ?? "draft"}</strong>).</span>
          <Link href={`/projects/${projectId}/builder`}>
            <span className="font-semibold underline">Open Builder →</span>
          </Link>
        </div>
      )}

      {/* Telemetry Bar (CONNECTED · 60 FPS · 42 ms · 1920 × 1080) */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 font-mono">
        <div className="p-3.5 rounded-xl border border-warmgray bg-card shadow-2xs">
          <div className="text-[10px] text-stonegray uppercase">Connection</div>
          <div className="flex items-center gap-2 mt-1">
            <span className={`h-2 w-2 rounded-full ${isConnected ? "bg-sage animate-ping" : sessionId ? "bg-terracotta animate-pulse" : "bg-stonegray"}`} />
            <span className="text-sm font-bold text-foreground uppercase">
              {isConnected ? "CONNECTED" : sessionId ? "NEGOTIATING" : "DISCONNECTED"}
            </span>
          </div>
        </div>

        <div className="p-3.5 rounded-xl border border-warmgray bg-card shadow-2xs">
          <div className="text-[10px] text-stonegray uppercase">Target Frame Rate</div>
          <div className="text-sm font-bold text-foreground mt-1">60 FPS</div>
          <div className="text-[10px] text-stonegray">Mobile VR Stereo</div>
        </div>

        <div className="p-3.5 rounded-xl border border-warmgray bg-card shadow-2xs">
          <div className="text-[10px] text-stonegray uppercase">LAN Latency</div>
          <div className="text-sm font-bold text-foreground mt-1">42 ms</div>
          <div className="text-[10px] text-stonegray">&lt; 50 ms Target</div>
        </div>

        <div className="p-3.5 rounded-xl border border-warmgray bg-card shadow-2xs">
          <div className="text-[10px] text-stonegray uppercase">Resolution &amp; Rig</div>
          <div className="text-sm font-bold text-foreground mt-1">1920 × 1080</div>
          <div className="text-[10px] text-stonegray">Side-by-Side H.264</div>
        </div>
      </div>

      {/* Main Remote Rendering Console Preview Frame */}
      <Card className="border-warmgray shadow-2xs overflow-hidden bg-charcoal text-white">
        <div className="p-3 border-b border-white/10 flex items-center justify-between text-xs font-mono text-ivory/80">
          <div className="flex items-center gap-2">
            <Radio className="h-3.5 w-3.5 text-terracotta" />
            <span>RENDER SERVER CONSOLE // LOCAL LAN STREAM</span>
          </div>
          <div className="flex items-center gap-2 text-[10px]">
            <span>SIG: {signalingState.toUpperCase()}</span>
            <span>&bull;</span>
            <span>ICE: {iceConnectionState.toUpperCase()}</span>
          </div>
        </div>

        <CardContent className="p-4 sm:p-6 space-y-4">
          {sessionError && (
            <div role="alert" className="rounded-xl bg-destructive/20 border border-destructive/40 p-3 text-xs text-red-300 flex items-center justify-between gap-3">
              <span>{sessionError}</span>
              {showRetry && (
                <Button variant="outline" size="sm" onClick={handleRetry} className="h-7 text-xs border-white/20 text-white hover:bg-white/10">
                  Retry Connection
                </Button>
              )}
            </div>
          )}

          {sessionId ? (
            <div className="space-y-4">
              <div className="relative rounded-xl overflow-hidden bg-black aspect-video border border-white/10 flex items-center justify-center">
                <video
                  ref={videoRef}
                  autoPlay
                  playsInline
                  muted
                  controls
                  aria-label="VR Stream preview"
                  className="w-full h-full object-contain"
                />
                {/* Overlay reticle / stereoscopic separator guide */}
                <div className="absolute inset-y-0 left-1/2 w-px bg-white/10 pointer-events-none" />
                <div className="absolute bottom-3 left-3 text-[10px] font-mono bg-black/60 px-2 py-0.5 rounded border border-white/10 backdrop-blur-xs">
                  LEFT EYE // RIGHT EYE STEREO
                </div>
              </div>

              <div className="p-3.5 rounded-xl bg-white/5 border border-white/10 flex flex-col sm:flex-row sm:items-center justify-between gap-3 text-xs font-mono">
                <div>
                  <div className="text-stonegray-300">Active WebRTC Session ID:</div>
                  <div className="text-ivory font-bold truncate max-w-md mt-0.5">{sessionId}</div>
                </div>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={handleEndStream}
                  disabled={endSession.isPending}
                  className="border-white/20 text-white hover:bg-red-500/20 hover:text-red-300 hover:border-red-500/40"
                >
                  End VR Session
                </Button>
              </div>
            </div>
          ) : (
            <div className="py-12 sm:py-16 text-center space-y-4 max-w-md mx-auto">
              <div className="h-14 w-14 rounded-2xl bg-white/5 border border-white/10 text-terracotta mx-auto flex items-center justify-center">
                <Glasses className="h-7 w-7" />
              </div>
              <div>
                <h3 className="text-base font-bold text-ivory">Mobile VR Stream Ready</h3>
                <p className="text-xs text-stonegray-300 mt-1 leading-relaxed">
                  Start the stereoscopic WebRTC session to stream directly to your Android headset client with sub-50ms latency.
                </p>
              </div>

              <div className="pt-2">
                <Button
                  variant="terracotta"
                  size="lg"
                  onClick={handleStartStream}
                  disabled={createSession.isPending || !isPublished}
                  className="gap-2 font-medium shadow-xs"
                >
                  <Play className="h-4 w-4 fill-current" />
                  <span>{createSession.isPending ? "Starting Server…" : "Launch VR Stream →"}</span>
                </Button>
              </div>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
