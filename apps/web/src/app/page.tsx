"use client"

import Link from "next/link"
import { useEffect } from "react"
import { useRouter } from "next/navigation"
import { useAuthStore } from "@/stores/auth-store"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"

export default function Home() {
  const router = useRouter()
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated)
  const authReady = useAuthStore((s) => s.authReady)

  useEffect(() => {
    if (authReady && isAuthenticated) router.replace("/dashboard")
  }, [authReady, isAuthenticated, router])

  return (
    <main className="flex min-h-screen flex-col items-center justify-center p-8">
      <div className="max-w-3xl text-center">
        <h1 className="text-4xl font-bold tracking-tight mb-4">CYMATIC</h1>
        <p className="text-xl text-muted-foreground mb-8">AI-powered simulation builder for real estate and heritage walkthroughs</p>
        <div className="flex gap-4 justify-center mb-12">
          <Link href="/login"><Button size="lg">Get Started</Button></Link>
          <Link href="/register"><Button variant="outline" size="lg">Create Account</Button></Link>
          <Link href="/dashboard"><Button variant="ghost" size="lg">Dashboard</Button></Link>
        </div>
        <div className="grid md:grid-cols-2 gap-4 text-left">
          <Card><CardHeader><CardTitle className="text-lg">Real Estate</CardTitle><CardDescription>Modern apartments, villas, commercial spaces with furnished walkthroughs, warm lighting, city views.</CardDescription></CardHeader><CardContent className="text-sm text-muted-foreground">Up to 20 rooms, 60 FPS / 80k triangles, baked lighting for low-end Android.</CardContent></Card>
          <Card><CardHeader><CardTitle className="text-lg">Heritage</CardTitle><CardDescription>Temples, palaces, courtyards with narration, multilingual copilot, historical POIs.</CardDescription></CardHeader><CardContent className="text-sm text-muted-foreground">Up to 50 POIs, radial/courtyard layouts, expert narrator voice.</CardContent></Card>
        </div>
        <p className="text-xs text-muted-foreground mt-8">LAN streaming • Single concurrent stream • Adaptive quality • <Link href="/login" className="underline">Sign in to start building</Link></p>
      </div>
    </main>
  )
}
