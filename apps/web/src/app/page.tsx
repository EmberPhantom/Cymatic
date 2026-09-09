"use client"

import React, { useState } from "react"
import Link from "next/link"
import { useRouter } from "next/navigation"
import { useAuthStore } from "@/stores/auth-store"
import { Button } from "@/components/ui/button"
import { ThemeToggle } from "@/components/ui/theme-toggle"
import { SceneViewportPreview } from "@/components/scene/SceneViewportPreview"
import {
  ArrowRight,
  Code2,
  Copy,
  Check,
  Cpu,
  Layers,
  Radio,
  Sliders,
  Sparkles,
  Terminal,
  Activity,
  Maximize2,
  ShieldCheck,
  Glasses
} from "lucide-react"

export default function Home() {
  const router = useRouter()
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated)
  const authReady = useAuthStore((s) => s.authReady)
  const logout = useAuthStore((s) => s.logout)

  // Interactive Simulator State
  const [activeDomain, setActiveDomain] = useState<"heritage" | "real_estate">("heritage")
  const [activePipelineTab, setActivePipelineTab] = useState<"prompt" | "spec" | "scene" | "stream">("prompt")
  const [copiedSpec, setCopiedSpec] = useState(false)
  const [inspectorNode, setInspectorNode] = useState({
    name: "Sanctum Platform",
    zone: "Central Sanctum",
    triangles: 14200,
    material: "Carved Sandstone (PBR)",
    coords: "[0.0, 0.4, 0.0]"
  })

  // Sample prompt selection
  const [selectedPrompt, setSelectedPrompt] = useState(
    "A 14th-century Vijayanagara temple courtyard with carved granite mandapa pillars, central sanctum, and baked global illumination."
  )

  const promptPresets = [
    {
      domain: "heritage" as const,
      label: "Hampi Courtyard",
      prompt: "A 14th-century Vijayanagara temple courtyard with carved granite mandapa pillars, central sanctum, and baked global illumination."
    },
    {
      domain: "heritage" as const,
      label: "Stepwell Corridor",
      prompt: "A subterranean multi-tiered stepwell with geometric pavilion pavilions, weathered basalt stonework, and dramatic zenith light shafts."
    },
    {
      domain: "real_estate" as const,
      label: "Modern Penthouse",
      prompt: "A minimalist glass-cantilever penthouse with warm teak ceilings, open dining pavilion, and panoramic terrace floorplan."
    },
    {
      domain: "real_estate" as const,
      label: "Courtyard Villa",
      prompt: "A coastal architectural villa with exposed polished concrete walls, central atrium reflecting pool, and linear cross-ventilation."
    }
  ]

  const specData = {
    schema_version: "1.0.0",
    simulation_id: activeDomain === "heritage" ? "sim_hampi_mandapa_v1" : "sim_modern_penthouse_v1",
    domain: activeDomain,
    performance_budget: {
      max_triangles: 80000,
      target_fps: 60,
      max_texture_memory_mb: 256,
      max_draw_calls: 120
    },
    environment: {
      lighting_workflow: "baked_gi",
      ambient_color: activeDomain === "heritage" ? "#B89452" : "#6F7D68",
      skybox_tone: "architectural_neutral"
    },
    camera_rig: {
      initial_position: [0.0, 1.65, 3.5],
      ipd_mm: 64,
      stereo_rendering: true
    },
    entities_count: activeDomain === "heritage" ? 18 : 14
  }

  const handleCopySpec = () => {
    navigator.clipboard.writeText(JSON.stringify(specData, null, 2))
    setCopiedSpec(true)
    setTimeout(() => setCopiedSpec(false), 2000)
  }

  return (
    <div className="min-h-screen flex flex-col bg-background text-foreground selection:bg-terracotta/20 selection:text-terracotta-700">
      {/* Top Header */}
      <header className="sticky top-0 z-50 w-full border-b border-border bg-background/95 backdrop-blur-md">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-14 flex items-center justify-between">
          <div className="flex items-center gap-6">
            <Link href="/" className="flex items-center gap-2.5 group">
              <div className="h-6 w-6 rounded-md bg-charcoal dark:bg-ivory text-white dark:text-charcoal flex items-center justify-center font-bold text-xs shadow-xs transition-transform group-hover:scale-105">
                CY
              </div>
              <div className="flex items-center gap-2">
                <span className="font-bold text-sm tracking-tight text-foreground">
                  CYMATIC
                </span>
                <span className="hidden sm:inline-block px-1.5 py-0.5 rounded text-[9px] font-mono border border-border text-stonegray">
                  v1.0 STUDIO
                </span>
              </div>
            </Link>

            <nav className="hidden md:flex items-center gap-5 text-xs font-medium text-stonegray">
              <a href="#simulator" className="hover:text-foreground transition-colors">Simulator</a>
              <a href="#pipeline" className="hover:text-foreground transition-colors">Pipeline</a>
              <a href="#architecture" className="hover:text-foreground transition-colors">Architecture</a>
              <a href="#telemetry" className="hover:text-foreground transition-colors">Telemetry</a>
            </nav>
          </div>

          <div className="flex items-center gap-3">
            <ThemeToggle />

            {authReady && isAuthenticated ? (
              <div className="flex items-center gap-2">
                <Link href="/dashboard">
                  <Button variant="terracotta" size="sm" className="font-medium gap-1.5 h-8 text-xs">
                    <span>Open Studio</span>
                    <ArrowRight className="h-3 w-3" />
                  </Button>
                </Link>
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-8 text-xs text-stonegray hover:text-foreground"
                  onClick={() => {
                    logout()
                    router.replace("/login")
                  }}
                >
                  Sign Out
                </Button>
              </div>
            ) : (
              <div className="flex items-center gap-2">
                <Link href="/login">
                  <Button variant="ghost" size="sm" className="h-8 text-xs font-normal text-stonegray hover:text-foreground">
                    Sign In
                  </Button>
                </Link>
                <Link href="/register">
                  <Button variant="terracotta" size="sm" className="h-8 text-xs font-medium">
                    Start Building
                  </Button>
                </Link>
              </div>
            )}
          </div>
        </div>
      </header>

      {/* Main Interactive Studio Hero */}
      <main className="flex-1" id="simulator">
        <section className="pt-8 pb-12 px-4 sm:px-6 lg:px-8 max-w-7xl mx-auto">
          {/* Top Hero Section */}
          <div className="flex flex-col lg:flex-row lg:items-end justify-between gap-6 pb-6 border-b border-border">
            <div className="max-w-3xl space-y-2.5">
              <div className="inline-flex items-center gap-2 px-2.5 py-0.5 rounded-full text-[10px] font-mono tracking-wider uppercase border border-warmgray bg-muted/40 text-stonegray">
                <span className="h-1.5 w-1.5 rounded-full bg-terracotta" />
                <span>CYMATIC SPATIAL SIMULATION ENGINE</span>
              </div>

              <h1 className="text-3xl sm:text-5xl lg:text-5xl font-bold tracking-tight text-foreground leading-[1.1]">
                Specification-First 3D Walkthroughs
              </h1>

              <p className="text-xs sm:text-sm text-stonegray leading-relaxed max-w-2xl">
                Convert architectural prompts into validated simulation specifications, optimized 3D geometry, and low-latency mobile VR streams.
              </p>

              <div className="pt-2 flex flex-wrap items-center gap-3">
                <Link href={isAuthenticated ? "/dashboard" : "/register"}>
                  <Button variant="terracotta" size="lg" className="h-9 px-5 text-xs font-semibold gap-2 shadow-xs">
                    <span>Start Building →</span>
                  </Button>
                </Link>
                <a href="#pipeline">
                  <Button variant="outline" size="lg" className="h-9 px-4 text-xs font-medium border-border text-foreground hover:bg-muted/50">
                    <span>View Architecture</span>
                  </Button>
                </a>
              </div>
            </div>

            {/* Interactive Domain Switcher Pill */}
            <div className="flex items-center bg-muted/40 p-1 rounded-xl border border-border shrink-0 self-start lg:self-end">
              <button
                type="button"
                onClick={() => {
                  setActiveDomain("heritage")
                  setInspectorNode({
                    name: "Sanctum Platform",
                    zone: "Central Sanctum",
                    triangles: 14200,
                    material: "Carved Sandstone (PBR)",
                    coords: "[0.0, 0.4, 0.0]"
                  })
                }}
                className={`px-3 py-1.5 text-xs font-medium rounded-lg transition-all ${
                  activeDomain === "heritage"
                    ? "bg-card text-foreground shadow-xs border border-border/80 font-semibold"
                    : "text-stonegray hover:text-foreground"
                }`}
              >
                Heritage Architecture
              </button>
              <button
                type="button"
                onClick={() => {
                  setActiveDomain("real_estate")
                  setInspectorNode({
                    name: "Main Pavilion",
                    zone: "Living & Dining Room",
                    triangles: 18500,
                    material: "Polished Concrete & Teak",
                    coords: "[0.0, 0.0, 1.2]"
                  })
                }}
                className={`px-3 py-1.5 text-xs font-medium rounded-lg transition-all ${
                  activeDomain === "real_estate"
                    ? "bg-card text-foreground shadow-xs border border-border/80 font-semibold"
                    : "text-stonegray hover:text-foreground"
                }`}
              >
                Real Estate Walkthrough
              </button>
            </div>
          </div>

          {/* Interactive 3D Spatial Simulator Grid */}
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-5 pt-6">
            {/* Left 8 Cols: Interactive 3D Viewport */}
            <div className="lg:col-span-8 flex flex-col gap-3">
              <SceneViewportPreview
                title={activeDomain === "heritage" ? "Vijayanagara Temple Courtyard" : "Minimalist Penthouse Villa"}
                domain={activeDomain}
                height="h-96 sm:h-[420px]"
                onSelectNode={(name, meta) => setInspectorNode({ name, ...meta })}
              />

              {/* Viewport Action Bar */}
              <div className="flex flex-wrap items-center justify-between gap-3 text-xs text-stonegray bg-card p-3 rounded-xl border border-border">
                <div className="flex items-center gap-2 font-mono text-[11px]">
                  <span className="text-foreground font-semibold">VIEWPORT CONTROLS:</span>
                  <span>Select 3D, TOP, or FRONT to rotate camera. Toggle Sun for environment lighting.</span>
                </div>

                <Link href={isAuthenticated ? "/dashboard" : "/register"}>
                  <Button variant="terracotta" size="sm" className="h-7 text-xs font-medium gap-1">
                    <span>Start Building →</span>
                  </Button>
                </Link>
              </div>
            </div>

            {/* Right 4 Cols: Live Node & Telemetry Inspector */}
            <div className="lg:col-span-4 flex flex-col gap-4">
              {/* Active Node Inspector Card */}
              <div className="p-4 rounded-xl border border-border bg-card shadow-2xs space-y-3">
                <div className="flex items-center justify-between border-b border-border pb-2.5">
                  <div className="flex items-center gap-2">
                    <Layers className="h-4 w-4 text-terracotta" />
                    <span className="text-xs font-bold tracking-tight text-foreground uppercase">
                      Node Inspector
                    </span>
                  </div>
                  <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-muted text-stonegray border border-border">
                    ACTIVE MESH
                  </span>
                </div>

                <div className="space-y-2 text-xs">
                  <div className="flex items-center justify-between">
                    <span className="text-stonegray">Selected Object:</span>
                    <span className="font-semibold text-foreground">{inspectorNode.name}</span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-stonegray">Spatial Zone:</span>
                    <span className="font-mono text-stonegray-800 dark:text-stonegray-200">{inspectorNode.zone}</span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-stonegray">Triangle Cost:</span>
                    <span className="font-mono text-terracotta font-semibold">
                      {inspectorNode.triangles.toLocaleString()} TRI
                    </span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-stonegray">PBR Material:</span>
                    <span className="font-mono text-foreground">{inspectorNode.material}</span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-stonegray">Local Coordinates:</span>
                    <span className="font-mono text-xs text-stonegray">{inspectorNode.coords}</span>
                  </div>
                </div>
              </div>

              {/* Hardware Performance Constraints Card */}
              <div className="p-4 rounded-xl border border-border bg-card shadow-2xs space-y-3">
                <div className="flex items-center justify-between border-b border-border pb-2.5">
                  <div className="flex items-center gap-2">
                    <Cpu className="h-4 w-4 text-sage" />
                    <span className="text-xs font-bold tracking-tight text-foreground uppercase">
                      Hardware Budget
                    </span>
                  </div>
                  <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-sage-50 text-sage border border-sage-200 dark:bg-sage-950/40">
                    PASSING
                  </span>
                </div>

                <div className="space-y-2.5 text-xs">
                  <div>
                    <div className="flex justify-between text-[11px] mb-1">
                      <span className="text-stonegray">Polygon Allocation</span>
                      <span className="font-mono font-medium">
                        {activeDomain === "heritage" ? "74,800 / 80,000" : "68,200 / 80,000"}
                      </span>
                    </div>
                    <div className="w-full h-1.5 bg-muted rounded-full overflow-hidden">
                      <div
                        className="h-full bg-terracotta rounded-full transition-all duration-300"
                        style={{ width: activeDomain === "heritage" ? "93.5%" : "85.2%" }}
                      />
                    </div>
                  </div>

                  <div>
                    <div className="flex justify-between text-[11px] mb-1">
                      <span className="text-stonegray">Texture VRAM Budget</span>
                      <span className="font-mono font-medium">174 MB / 256 MB</span>
                    </div>
                    <div className="w-full h-1.5 bg-muted rounded-full overflow-hidden">
                      <div className="h-full bg-gold rounded-full w-[68%]" />
                    </div>
                  </div>

                  <div>
                    <div className="flex justify-between text-[11px] mb-1">
                      <span className="text-stonegray">Stereo Framerate Target</span>
                      <span className="font-mono font-medium text-sage">60.0 FPS</span>
                    </div>
                    <div className="w-full h-1.5 bg-muted rounded-full overflow-hidden">
                      <div className="h-full bg-sage rounded-full w-[100%]" />
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* INTERACTIVE 4-STAGE PIPELINE EXPLORER */}
        <section id="pipeline" className="py-12 px-4 sm:px-6 lg:px-8 max-w-7xl mx-auto border-t border-border">
          <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 mb-6">
            <div>
              <span className="text-[11px] font-mono uppercase tracking-widest text-gold font-semibold">
                PIPELINE ARCHITECTURE
              </span>
              <h2 className="text-xl sm:text-2xl font-bold tracking-tight text-foreground mt-1">
                From Specification to Low-Latency VR
              </h2>
            </div>

            {/* Interactive Pipeline Stage Tabs */}
            <div className="flex items-center bg-card p-1 rounded-xl border border-border shadow-2xs overflow-x-auto">
              <button
                type="button"
                onClick={() => setActivePipelineTab("prompt")}
                className={`flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg whitespace-nowrap transition-all ${
                  activePipelineTab === "prompt"
                    ? "bg-terracotta text-white font-semibold"
                    : "text-stonegray hover:text-foreground"
                }`}
              >
                <Sparkles className="h-3.5 w-3.5" />
                <span>1. Prompt Input</span>
              </button>

              <button
                type="button"
                onClick={() => setActivePipelineTab("spec")}
                className={`flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg whitespace-nowrap transition-all ${
                  activePipelineTab === "spec"
                    ? "bg-terracotta text-white font-semibold"
                    : "text-stonegray hover:text-foreground"
                }`}
              >
                <Code2 className="h-3.5 w-3.5" />
                <span>2. Spec Schema</span>
              </button>

              <button
                type="button"
                onClick={() => setActivePipelineTab("scene")}
                className={`flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg whitespace-nowrap transition-all ${
                  activePipelineTab === "scene"
                    ? "bg-terracotta text-white font-semibold"
                    : "text-stonegray hover:text-foreground"
                }`}
              >
                <Layers className="h-3.5 w-3.5" />
                <span>3. Scene Graph</span>
              </button>

              <button
                type="button"
                onClick={() => setActivePipelineTab("stream")}
                className={`flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg whitespace-nowrap transition-all ${
                  activePipelineTab === "stream"
                    ? "bg-terracotta text-white font-semibold"
                    : "text-stonegray hover:text-foreground"
                }`}
              >
                <Radio className="h-3.5 w-3.5" />
                <span>4. WebRTC Stream</span>
              </button>
            </div>
          </div>

          {/* Interactive Tab Body */}
          <div className="rounded-xl border border-border bg-card p-6 shadow-2xs min-h-[280px]">
            {activePipelineTab === "prompt" && (
              <div className="space-y-4">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <span className="text-xs font-bold text-foreground uppercase tracking-wide">
                    Interactive Prompt Selection
                  </span>
                  <span className="text-[11px] text-stonegray">Click a preset chip to test generation parameters:</span>
                </div>

                <div className="flex flex-wrap gap-2">
                  {promptPresets.map((preset) => (
                    <button
                      key={preset.label}
                      type="button"
                      onClick={() => {
                        setSelectedPrompt(preset.prompt)
                        setActiveDomain(preset.domain)
                      }}
                      className={`px-3 py-1.5 rounded-lg text-xs font-medium border transition-colors ${
                        selectedPrompt === preset.prompt
                          ? "border-terracotta bg-terracotta/10 text-terracotta font-semibold"
                          : "border-border text-stonegray hover:text-foreground hover:bg-muted/40"
                      }`}
                    >
                      {preset.label}
                    </button>
                  ))}
                </div>

                <div className="p-3.5 rounded-lg bg-muted/40 border border-border font-mono text-xs text-foreground leading-relaxed">
                  {selectedPrompt}
                </div>

                <div className="flex items-center justify-between text-xs text-stonegray pt-2 border-t border-border">
                  <div className="flex items-center gap-4">
                    <span>LLM Router: <strong>LiteLLM Fallback</strong></span>
                    <span>Spec Schema: <strong>v1.0.0 Validated</strong></span>
                  </div>
                  <Link href={isAuthenticated ? "/dashboard" : "/register"}>
                    <Button variant="outline-terracotta" size="sm" className="h-7 text-xs">
                      Simulate in Studio →
                    </Button>
                  </Link>
                </div>
              </div>
            )}

            {activePipelineTab === "spec" && (
              <div className="space-y-4">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-bold text-foreground uppercase">
                      Deterministic Simulation Specification (JSON)
                    </span>
                    <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-sage-50 text-sage border border-sage-200">
                      SCHEMA // VALID
                    </span>
                  </div>

                  <Button
                    variant="outline"
                    size="sm"
                    className="h-7 text-xs gap-1.5 text-stonegray hover:text-foreground"
                    onClick={handleCopySpec}
                  >
                    {copiedSpec ? (
                      <>
                        <Check className="h-3 w-3 text-sage" />
                        <span>Copied!</span>
                      </>
                    ) : (
                      <>
                        <Copy className="h-3 w-3" />
                        <span>Copy JSON</span>
                      </>
                    )}
                  </Button>
                </div>

                <pre className="p-4 rounded-lg bg-charcoal text-ivory font-mono text-xs overflow-x-auto max-h-56 leading-relaxed border border-white/10">
                  {JSON.stringify(specData, null, 2)}
                </pre>
              </div>
            )}

            {activePipelineTab === "scene" && (
              <div className="space-y-4">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-bold text-foreground uppercase">
                    Spatial Node Hierarchy
                  </span>
                  <span className="text-[11px] font-mono text-stonegray">
                    NODES: {specData.entities_count} // DRAW CALLS: 48
                  </span>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-xs font-mono">
                  <div className="p-3 rounded-lg bg-muted/40 border border-border space-y-1.5">
                    <div className="font-bold text-foreground flex items-center gap-1.5">
                      <Layers className="h-3.5 w-3.5 text-terracotta" />
                      <span>SceneRoot (Origin [0, 0, 0])</span>
                    </div>
                    <div className="pl-4 text-stonegray space-y-1">
                      <div>├─ Foundation_Slab (MeshCollider, Static)</div>
                      <div>├─ Courtyard_Platform (BakedLightmap_01)</div>
                      <div>├─ Stone_Pillars_Array [1..8] (LOD0: 24k tri)</div>
                      <div>└─ Sanctum_Superstructure (PBR Material)</div>
                    </div>
                  </div>

                  <div className="p-3 rounded-lg bg-muted/40 border border-border space-y-1.5">
                    <div className="font-bold text-foreground flex items-center gap-1.5">
                      <Sliders className="h-3.5 w-3.5 text-gold" />
                      <span>Lighting &amp; VR Camera Rig</span>
                    </div>
                    <div className="pl-4 text-stonegray space-y-1">
                      <div>├─ Sun_DirectionalLight (Baked Shadowmap 2048)</div>
                      <div>├─ AmbientProbe_Volume (HDR Irradiance)</div>
                      <div>├─ StereoCamera_Rig (IPD: 64mm, FOV: 90°)</div>
                      <div>└─ IMU_Orientation_Tracker (Zero-drift filter)</div>
                    </div>
                  </div>
                </div>
              </div>
            )}

            {activePipelineTab === "stream" && (
              <div className="space-y-4">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <Activity className="h-4 w-4 text-sage" />
                    <span className="text-xs font-bold text-foreground uppercase">
                      Real-Time WebRTC Video Pipeline
                    </span>
                  </div>
                  <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-sage-50 text-sage border border-sage-200">
                    ICE // CONNECTED
                  </span>
                </div>

                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs">
                  <div className="p-3 rounded-lg bg-muted/30 border border-border">
                    <span className="text-stonegray text-[11px]">Stereo Resolution</span>
                    <div className="text-base font-bold font-mono text-foreground mt-0.5">1920 × 1080</div>
                  </div>
                  <div className="p-3 rounded-lg bg-muted/30 border border-border">
                    <span className="text-stonegray text-[11px]">LAN Latency</span>
                    <div className="text-base font-bold font-mono text-terracotta mt-0.5">42 ms RTT</div>
                  </div>
                  <div className="p-3 rounded-lg bg-muted/30 border border-border">
                    <span className="text-stonegray text-[11px]">H.264 Bitrate</span>
                    <div className="text-base font-bold font-mono text-foreground mt-0.5">14.8 Mbps</div>
                  </div>
                  <div className="p-3 rounded-lg bg-muted/30 border border-border">
                    <span className="text-stonegray text-[11px]">Packet Loss</span>
                    <div className="text-base font-bold font-mono text-sage mt-0.5">0.00 %</div>
                  </div>
                </div>
              </div>
            )}
          </div>
        </section>

        {/* ENGINE ARCHITECTURAL PILLARS */}
        <section id="architecture" className="py-12 px-4 sm:px-6 lg:px-8 max-w-7xl mx-auto border-t border-border">
          <div className="max-w-2xl mb-8 space-y-1.5">
            <span className="text-[11px] font-mono uppercase tracking-widest text-gold font-semibold">
              CORE ENGINE ARCHITECTURE
            </span>
            <h2 className="text-xl sm:text-2xl font-bold tracking-tight text-foreground">
              Designed for Mobile VR Headsets &amp; Spatial Precision
            </h2>
            <p className="text-xs text-stonegray leading-relaxed">
              Every simulation is constrained by strict hardware budgets, verified schemas, and deterministic agent orchestration.
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
            <div className="p-4 rounded-xl border border-border bg-card shadow-2xs space-y-2.5 flex flex-col justify-between">
              <div className="space-y-2">
                <div className="h-8 w-8 rounded-lg bg-terracotta/10 text-terracotta flex items-center justify-center border border-terracotta/20">
                  <Sparkles className="h-4 w-4" />
                </div>
                <h3 className="text-xs font-bold text-foreground tracking-tight">Multi-Agent Spatial Reasoning</h3>
                <p className="text-[11px] text-stonegray leading-relaxed">
                  Specialized AI agents synthesize architectural intent, extract spatial relations, and structure verified scene graphs.
                </p>
              </div>
              <div className="pt-2 border-t border-border/60 text-[10px] font-mono text-terracotta font-medium">
                SPEC-FIRST PIPELINE
              </div>
            </div>

            <div className="p-4 rounded-xl border border-border bg-card shadow-2xs space-y-2.5 flex flex-col justify-between">
              <div className="space-y-2">
                <div className="h-8 w-8 rounded-lg bg-sage/10 text-sage flex items-center justify-center border border-sage/20">
                  <Cpu className="h-4 w-4" />
                </div>
                <h3 className="text-xs font-bold text-foreground tracking-tight">Thermal-Safe Mobile Constraints</h3>
                <p className="text-[11px] text-stonegray leading-relaxed">
                  Enforces 80,000 polygon limit and baked global illumination to prevent thermal throttling on Android phone VR.
                </p>
              </div>
              <div className="pt-2 border-t border-border/60 text-[10px] font-mono text-sage font-medium">
                &le;80K TRI // 60 FPS
              </div>
            </div>

            <div className="p-4 rounded-xl border border-border bg-card shadow-2xs space-y-2.5 flex flex-col justify-between">
              <div className="space-y-2">
                <div className="h-8 w-8 rounded-lg bg-gold/10 text-gold flex items-center justify-center border border-gold/20">
                  <Glasses className="h-4 w-4" />
                </div>
                <h3 className="text-xs font-bold text-foreground tracking-tight">True Stereoscopic Streaming</h3>
                <p className="text-[11px] text-stonegray leading-relaxed">
                  Low-latency WebRTC video pipeline delivering dual-eye perspective rendering with zero-drift IMU head tracking.
                </p>
              </div>
              <div className="pt-2 border-t border-border/60 text-[10px] font-mono text-gold font-medium">
                WEBRTC &lt;45MS LAN
              </div>
            </div>

            <div className="p-4 rounded-xl border border-border bg-card shadow-2xs space-y-2.5 flex flex-col justify-between">
              <div className="space-y-2">
                <div className="h-8 w-8 rounded-lg bg-darkmineral/10 text-foreground dark:bg-ivory/10 flex items-center justify-center border border-border">
                  <ShieldCheck className="h-4 w-4 text-terracotta" />
                </div>
                <h3 className="text-xs font-bold text-foreground tracking-tight">Deterministic Schema Validation</h3>
                <p className="text-[11px] text-stonegray leading-relaxed">
                  All AI proposals pass strict schema verification before mutating Unity scene state or runtime memory.
                </p>
              </div>
              <div className="pt-2 border-t border-border/60 text-[10px] font-mono text-stonegray font-medium">
                TRUSTED SERVICE GATE
              </div>
            </div>
          </div>
        </section>

        {/* 4-METRIC STRIP */}
        <section id="telemetry" className="py-8 px-4 sm:px-6 lg:px-8 max-w-7xl mx-auto border-t border-border">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div className="p-4 rounded-xl border border-border bg-card shadow-2xs">
              <div className="flex items-baseline justify-between">
                <span className="text-2xl sm:text-3xl font-bold tracking-tight text-foreground font-mono">60 FPS</span>
                <span className="text-[10px] font-mono text-sage font-semibold">STEREO</span>
              </div>
              <div className="text-xs font-semibold text-foreground mt-1">Mobile VR Target</div>
              <div className="text-[11px] text-stonegray mt-0.5">Thermal-safe mobile refresh rate</div>
            </div>

            <div className="p-4 rounded-xl border border-border bg-card shadow-2xs">
              <div className="flex items-baseline justify-between">
                <span className="text-2xl sm:text-3xl font-bold tracking-tight text-foreground font-mono">&lt;50ms</span>
                <span className="text-[10px] font-mono text-terracotta font-semibold">LATENCY</span>
              </div>
              <div className="text-xs font-semibold text-foreground mt-1">LAN WebRTC Latency</div>
              <div className="text-[11px] text-stonegray mt-0.5">Direct motion-to-photon pipeline</div>
            </div>

            <div className="p-4 rounded-xl border border-border bg-card shadow-2xs">
              <div className="flex items-baseline justify-between">
                <span className="text-2xl sm:text-3xl font-bold tracking-tight text-foreground font-mono">80K</span>
                <span className="text-[10px] font-mono text-gold font-semibold">BUDGET</span>
              </div>
              <div className="text-xs font-semibold text-foreground mt-1">Polygon Budget</div>
              <div className="text-[11px] text-stonegray mt-0.5">Enforced geometric limit</div>
            </div>

            <div className="p-4 rounded-xl border border-border bg-card shadow-2xs">
              <div className="flex items-baseline justify-between">
                <span className="text-2xl sm:text-3xl font-bold tracking-tight text-foreground font-mono">7</span>
                <span className="text-[10px] font-mono text-stonegray font-semibold">PIPELINE</span>
              </div>
              <div className="text-xs font-semibold text-foreground mt-1">Orchestrated Agents</div>
              <div className="text-[11px] text-stonegray mt-0.5">Prompt, spec, scene, and bake</div>
            </div>
          </div>
        </section>
      </main>

      {/* Clean, Technical Footer */}
      <footer className="border-t border-border py-6 px-4 sm:px-6 lg:px-8 bg-card text-xs text-stonegray">
        <div className="max-w-7xl mx-auto flex flex-col sm:flex-row items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <span className="font-bold text-foreground">CYMATIC</span>
            <span>— Spatial Computing &amp; Architectural Simulation Platform</span>
          </div>
          <div className="flex items-center gap-4 text-[11px] font-mono">
            <span className="flex items-center gap-1.5 text-sage">
              <span className="h-1.5 w-1.5 rounded-full bg-sage" />
              <span>SYSTEM OPERATIONAL</span>
            </span>
            <span>API v1.0.0</span>
          </div>
        </div>
      </footer>
    </div>
  )
}
