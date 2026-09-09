"use client"

import Link from "next/link"
import { ArrowLeft, Check } from "lucide-react"
import { ThemeToggle } from "@/components/ui/theme-toggle"

export default function AuthLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen w-full flex flex-col lg:flex-row bg-background text-foreground">
      {/* Left Presentation Panel (Visible on desktop) */}
      <div className="hidden lg:flex lg:w-1/2 relative bg-muted/30 p-12 flex-col justify-between border-r border-border">
        {/* Top Logo */}
        <div>
          <Link href="/" className="inline-flex items-center gap-2.5 group">
            <div className="h-7 w-7 rounded-md bg-charcoal dark:bg-ivory text-white dark:text-charcoal flex items-center justify-center font-bold text-xs shadow-xs transition-transform group-hover:scale-105">
              CY
            </div>
            <div className="flex flex-col">
              <span className="font-bold text-sm tracking-tight text-foreground leading-none">CYMATIC</span>
              <span className="text-[9px] font-mono text-stonegray tracking-widest mt-0.5">SPATIAL ENGINE</span>
            </div>
          </Link>
        </div>

        {/* Center Architectural Studio Summary */}
        <div className="my-auto py-8 max-w-md space-y-5">
          <div className="inline-flex items-center gap-2 px-2.5 py-0.5 rounded-full text-[10px] font-mono tracking-wider uppercase border border-border bg-background/60 text-stonegray">
            <span className="h-1.5 w-1.5 rounded-full bg-terracotta" />
            <span>AI 3D STUDIO PLATFORM</span>
          </div>

          <h2 className="text-2xl lg:text-3xl font-bold tracking-tight text-foreground leading-snug">
            Autonomous simulation generation for mobile VR headsets.
          </h2>

          <p className="text-stonegray text-xs leading-relaxed">
            Specification-driven pipeline translating spatial intent into verified 3D environments streamed with low latency over local LAN.
          </p>

          {/* Mini Spec & Telemetry Card */}
          <div className="p-3.5 rounded-xl border border-border bg-card shadow-2xs space-y-2.5">
            <div className="flex items-center justify-between border-b border-border pb-2">
              <span className="text-[10px] font-mono font-bold text-foreground uppercase tracking-wider">
                SIMULATION SPEC // V1.0
              </span>
              <span className="text-[9px] font-mono px-1.5 py-0.5 rounded bg-sage-50 text-sage border border-sage-200 dark:bg-sage-950/40">
                VALIDATED
              </span>
            </div>

            <pre className="p-2.5 rounded-lg bg-charcoal text-ivory font-mono text-[11px] leading-relaxed border border-white/10 overflow-x-auto">
{`{
  "domain": "heritage_walkthrough",
  "render_target": "mobile_android_vr",
  "budget": { "triangles": 80000, "fps": 60 },
  "lighting": "baked_global_illum"
}`}
            </pre>

            <div className="flex items-center justify-between text-[10px] font-mono text-stonegray pt-1">
              <span className="text-sage font-medium">60 FPS STEREO</span>
              <span>&bull;</span>
              <span className="text-terracotta font-medium">&lt;45ms RTT</span>
              <span>&bull;</span>
              <span>BAKED GI</span>
            </div>
          </div>

          <div className="space-y-2 pt-1 text-xs text-stonegray">
            <div className="flex items-center gap-2.5">
              <Check className="h-3.5 w-3.5 text-sage shrink-0" />
              <span>Multi-agent spatial composition &amp; automated spec validation</span>
            </div>
            <div className="flex items-center gap-2.5">
              <Check className="h-3.5 w-3.5 text-sage shrink-0" />
              <span>Baked lighting pipeline targeting mobile Android headroom</span>
            </div>
            <div className="flex items-center gap-2.5">
              <Check className="h-3.5 w-3.5 text-sage shrink-0" />
              <span>Direct WebRTC stereoscopic streaming to phone VR clients</span>
            </div>
          </div>
        </div>

        {/* Bottom Metadata */}
        <div className="text-xs text-stonegray pt-4 border-t border-border flex items-center justify-between font-mono text-[11px]">
          <span>CYMATIC STUDIO PLATFORM</span>
          <span className="text-sage flex items-center gap-1.5">
            <span className="h-1.5 w-1.5 rounded-full bg-sage" />
            <span>OPERATIONAL</span>
          </span>
        </div>
      </div>

      {/* Right Form Panel */}
      <div className="w-full lg:w-1/2 flex flex-col min-h-screen justify-between p-6 sm:p-10 relative">
        {/* Top bar with Arrow-only back button and Theme toggle */}
        <div className="flex items-center justify-between w-full max-w-md mx-auto">
          <Link
            href="/"
            className="h-8 w-8 rounded-md border border-border/80 flex items-center justify-center text-muted-foreground hover:text-foreground hover:bg-muted/70 transition-colors"
            aria-label="Back to home"
            title="Back to home"
          >
            <ArrowLeft className="h-4 w-4" />
          </Link>

          <ThemeToggle />
        </div>

        {/* Center Auth Form Content */}
        <div className="w-full max-w-md mx-auto my-auto py-8">
          {children}
        </div>

        {/* Minimal Footer Info */}
        <div className="text-center text-xs text-muted-foreground w-full max-w-md mx-auto">
          <span>Tenant Scoped &bull; Secure Authentication</span>
        </div>
      </div>
    </div>
  )
}
