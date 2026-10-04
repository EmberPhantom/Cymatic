"use client"

import React, { useId, useState } from "react"
import { cn } from "@/lib/utils"
import {
  Grid,
  RotateCcw,
  Box,
  Sun,
  Info
} from "lucide-react"

/** Real measured stats. When absent the HUD is labelled illustrative and
 * shows no numbers — the schematic never reports fake FPS/triangle counts. */
export interface ViewportStats {
  fps?: number | null
  triangles?: number | null
  triangleBudget?: number | null
}

export interface SceneViewportPreviewProps {
  title?: string
  domain?: "heritage" | "real_estate" | string
  isInteractive?: boolean
  className?: string
  height?: string
  /** Real scene stats when the caller has them (builder has none at mount). */
  stats?: ViewportStats | null
  onSelectNode?: (nodeName: string, metadata: { zone: string; triangles: number; material: string; coords: string }) => void
}

export function SceneViewportPreview({
  title = "Temple Courtyard Sanctum",
  domain = "heritage",
  isInteractive = true,
  className,
  height = "h-80 md:h-96",
  stats = null,
  onSelectNode,
}: SceneViewportPreviewProps) {
  const [showGrid, setShowGrid] = useState(true)
  const [viewMode, setViewMode] = useState<"shaded" | "wireframe" | "bounds">("shaded")
  const [cameraMode, setCameraMode] = useState<"perspective" | "top" | "front">("perspective")
  const [lightingMode, setLightingMode] = useState<"daylight" | "golden" | "night">("daylight")
  const [selectedNode, setSelectedNode] = useState<string | null>(null)
  const svgTitleId = useId()

  const isHeritage = domain === "heritage"

  // Compute camera rotation values
  const getCameraStyle = () => {
    switch (cameraMode) {
      case "top":
        return { transform: "perspective(800px) rotateX(70deg) rotateZ(-15deg) scale(0.9)" }
      case "front":
        return { transform: "perspective(800px) rotateX(5deg) rotateY(0deg) scale(1.05)" }
      case "perspective":
      default:
        return { transform: "perspective(650px) rotateX(20deg) rotateY(25deg)" }
    }
  }

  // Background ambiance based on lighting mode
  const getCanvasBackground = () => {
    switch (lightingMode) {
      case "golden":
        return "radial-gradient(ellipse at center, #261E17 0%, #171512 60%, #0F0E0D 100%)"
      case "night":
        return "radial-gradient(ellipse at center, #151D26 0%, #10151C 65%, #0B0E12 100%)"
      case "daylight":
      default:
        return "radial-gradient(ellipse at center, #212524 0%, #182321 65%, #0F1413 100%)"
    }
  }

  const handleNodeClick = (
    name: string,
    meta: { zone: string; triangles: number; material: string; coords: string }
  ) => {
    setSelectedNode(name)
    if (onSelectNode) {
      onSelectNode(name, meta)
    }
  }

  // Clickable SVG nodes: pointer + keyboard (Enter/Space) activation.
  const nodeProps = (
    name: string,
    meta: { zone: string; triangles: number; material: string; coords: string }
  ) => ({
    onClick: () => handleNodeClick(name, meta),
    role: "button" as const,
    tabIndex: 0,
    "aria-label": `Select ${name}`,
    onKeyDown: (e: React.KeyboardEvent) => {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault()
        handleNodeClick(name, meta)
      }
    },
  })

  return (
    <div
      className={cn(
        "relative w-full rounded-xl border border-warmgray overflow-hidden bg-charcoal text-white flex flex-col select-none shadow-sm group",
        height,
        className
      )}
    >
      {/* Top Viewport Toolbar / Technical HUD Metrics */}
      <div className="absolute top-0 inset-x-0 z-20 flex items-center justify-between px-3 py-2 bg-charcoal/90 backdrop-blur-sm border-b border-white/10 text-xs">
        <div className="flex items-center gap-2">
          <span className="flex h-2 w-2 relative">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-sage opacity-75" />
            <span className="relative inline-flex rounded-full h-2 w-2 bg-sage" />
          </span>
          <span className="font-mono text-[11px] tracking-wide text-ivory font-bold uppercase">
            {isHeritage ? "HERITAGE SITE" : "REAL ESTATE SITE"}
          </span>
          <span
            className={cn(
              "hidden sm:inline-block px-1.5 py-0.5 rounded text-[9px] font-mono border uppercase tracking-wider font-semibold",
              isHeritage
                ? "border-gold/50 text-gold bg-gold/10"
                : "border-terracotta/50 text-terracotta-300 bg-terracotta/10"
            )}
          >
            {isHeritage ? "HERITAGE // V1 SPEC" : "REAL ESTATE // V1 SPEC"}
          </span>
        </div>

        {/* Technical HUD: real stats when wired, otherwise an explicit
            illustrative label — never fake-precise numbers. */}
        <div className="flex items-center gap-1.5 font-mono text-[10px]">
          {stats?.fps != null || stats?.triangles != null ? (
            <>
              {stats.fps != null && (
                <span className="px-1.5 py-0.5 rounded bg-white/10 text-ivory border border-white/10 tracking-tight">
                  {stats.fps} FPS
                </span>
              )}
              {stats.triangles != null && (
                <span className="px-1.5 py-0.5 rounded bg-terracotta/20 text-terracotta-300 border border-terracotta/40 tracking-tight">
                  {(stats.triangles / 1000).toFixed(1)}K{stats.triangleBudget != null ? ` / ${(stats.triangleBudget / 1000).toFixed(0)}K` : ""}
                </span>
              )}
            </>
          ) : (
            <span className="px-1.5 py-0.5 rounded bg-white/10 text-ivory border border-white/10 tracking-tight uppercase">
              Preview (illustrative)
            </span>
          )}
        </div>
      </div>

      {/* 3D Architectural Scene Canvas */}
      <div
        className="flex-1 relative flex items-center justify-center overflow-hidden transition-colors duration-500"
        style={{ background: getCanvasBackground() }}
      >
        {/* Coordinate grid ground plane */}
        {showGrid && (
          <div
            className="absolute inset-0 pointer-events-none opacity-25"
            style={{
              backgroundImage:
                "linear-gradient(to right, rgba(221, 217, 208, 0.4) 1px, transparent 1px), linear-gradient(to bottom, rgba(221, 217, 208, 0.4) 1px, transparent 1px)",
              backgroundSize: "24px 24px",
              transform: "perspective(400px) rotateX(60deg) translateY(30px)",
              transformOrigin: "bottom center",
            }}
          />
        )}

        {/* Renderable SVG Canvas (decorative schematic, not measured output) */}
        <svg
          viewBox="0 0 400 240"
          className="w-full h-full max-w-lg object-contain transition-transform duration-500"
          style={getCameraStyle()}
          role="img"
          aria-label={`Illustrative ${isHeritage ? "heritage" : "real estate"} scene schematic for ${title}`}
        >
          <title id={`${svgTitleId}`}>{title} — illustrative schematic</title>
          <defs>
            <linearGradient id="wallGradHeritage" x1="0%" y1="0%" x2="100%" y2="100%">
              <stop offset="0%" stopColor="#C69A4B" stopOpacity={lightingMode === "golden" ? "0.6" : "0.35"} />
              <stop offset="100%" stopColor="#B85C38" stopOpacity="0.15" />
            </linearGradient>
            <linearGradient id="wallGradRealEstate" x1="0%" y1="0%" x2="100%" y2="100%">
              <stop offset="0%" stopColor="#667B62" stopOpacity="0.45" />
              <stop offset="100%" stopColor="#182321" stopOpacity="0.2" />
            </linearGradient>
            <linearGradient id="columnGrad" x1="0%" y1="0%" x2="0%" y2="100%">
              <stop offset="0%" stopColor="#DDD9D0" stopOpacity="0.8" />
              <stop offset="100%" stopColor="#5F625F" stopOpacity="0.4" />
            </linearGradient>
          </defs>

          {/* Bounds Bounding Box */}
          {viewMode === "bounds" && (
            <polygon
              points="40,210 200,238 360,210 200,140"
              fill="rgba(184, 92, 56, 0.05)"
              stroke="#B85C38"
              strokeWidth="1.5"
              strokeDasharray="4 4"
            />
          )}

          {isHeritage ? (
            /* HERITAGE TEMPLE SCHEMATIC */
            <g>
              <polygon
                points="50,195 200,232 350,195 200,152"
                fill={viewMode === "wireframe" ? "none" : "rgba(198, 154, 75, 0.08)"}
                stroke="#C69A4B"
                strokeWidth="1.2"
                strokeDasharray="3 3"
              />

              <polygon
                points="120,182 200,206 280,182 200,158"
                fill={viewMode === "wireframe" ? "none" : "url(#wallGradHeritage)"}
                stroke={selectedNode === "Sanctum Platform" ? "#FFFFFF" : "#B85C38"}
                strokeWidth={selectedNode === "Sanctum Platform" ? "2.5" : "1.5"}
                className="cursor-pointer hover:opacity-90"
                {...nodeProps("Sanctum Platform", {
                  zone: "Central Sanctum",
                  triangles: 14200,
                  material: "Carved Sandstone (PBR)",
                  coords: "[0.0, 0.4, 0.0]",
                })}
              />

              <line x1="120" y1="182" x2="120" y2="115" stroke="url(#columnGrad)" strokeWidth="3.5" strokeLinecap="round" />
              <line x1="200" y1="206" x2="200" y2="138" stroke="url(#columnGrad)" strokeWidth="3.5" strokeLinecap="round" />
              <line x1="280" y1="182" x2="280" y2="115" stroke="url(#columnGrad)" strokeWidth="3.5" strokeLinecap="round" />
              <line x1="200" y1="158" x2="200" y2="90" stroke="url(#columnGrad)" strokeWidth="2.8" strokeLinecap="round" strokeDasharray="2 2" />

              <polygon
                points="120,115 200,138 280,115 200,90"
                fill={viewMode === "wireframe" ? "none" : "rgba(221, 217, 208, 0.25)"}
                stroke="#DDD9D0"
                strokeWidth="1.5"
              />
              <polygon
                points="145,95 200,112 255,95 200,76"
                fill={viewMode === "wireframe" ? "none" : "rgba(198, 154, 75, 0.3)"}
                stroke="#C69A4B"
                strokeWidth="1.2"
                className="cursor-pointer hover:opacity-90"
                {...nodeProps("Tiered Shikhara", {
                  zone: "Roof Superstructure",
                  triangles: 28400,
                  material: "Granite Masonry",
                  coords: "[0.0, 4.2, 0.0]",
                })}
              />
              <line x1="200" y1="76" x2="200" y2="38" stroke="#C69A4B" strokeWidth="2.5" />
              <circle cx="200" cy="38" r="4" fill="#C69A4B" />

              <g
                className="cursor-pointer group"
                {...nodeProps("Entry Mandapa", {
                  zone: "East Gateway",
                  triangles: 8200,
                  material: "Basalt Flagstone",
                  coords: "[-2.5, 0.0, 4.0]",
                })}
              >
                <circle cx="155" cy="195" r="4.5" fill="#B85C38" className="animate-pulse" />
                <circle cx="155" cy="195" r="9" fill="none" stroke="#B85C38" strokeWidth="0.8" opacity="0.6" />
                <text x="168" y="198" fill="#F5F3EE" fontSize="8" fontFamily="monospace" fontWeight="bold">
                  Mandapa Entry
                </text>
              </g>

              <g
                className="cursor-pointer group"
                {...nodeProps("Inner Sanctum", {
                  zone: "Garbhagriha",
                  triangles: 24000,
                  material: "Aged Sandstone",
                  coords: "[0.0, 0.5, 0.0]",
                })}
              >
                <circle cx="245" cy="195" r="4.5" fill="#667B62" className="animate-pulse" />
                <circle cx="245" cy="195" r="9" fill="none" stroke="#667B62" strokeWidth="0.8" opacity="0.6" />
                <text x="258" y="198" fill="#F5F3EE" fontSize="8" fontFamily="monospace" fontWeight="bold">
                  Sanctum POI
                </text>
              </g>
            </g>
          ) : (
            /* REAL ESTATE MODERN VILLA SCHEMATIC */
            <g>
              <polygon
                points="45,190 200,235 355,190 200,145"
                fill={viewMode === "wireframe" ? "none" : "rgba(102, 123, 98, 0.1)"}
                stroke="#667B62"
                strokeWidth="1.2"
                strokeDasharray="3 3"
              />

              <polygon
                points="80,180 200,215 320,180 200,145"
                fill={viewMode === "wireframe" ? "none" : "url(#wallGradRealEstate)"}
                stroke={selectedNode === "Main Pavilion" ? "#FFFFFF" : "#667B62"}
                strokeWidth={selectedNode === "Main Pavilion" ? "2.5" : "1.5"}
                className="cursor-pointer hover:opacity-90"
                {...nodeProps("Main Pavilion", {
                  zone: "Living & Dining Room",
                  triangles: 18500,
                  material: "Polished Concrete & Teak",
                  coords: "[0.0, 0.0, 1.2]",
                })}
              />

              <line x1="80" y1="180" x2="80" y2="120" stroke="#DDD9D0" strokeWidth="3" strokeLinecap="round" />
              <line x1="200" y1="215" x2="200" y2="155" stroke="#DDD9D0" strokeWidth="3" strokeLinecap="round" />
              <line x1="320" y1="180" x2="320" y2="120" stroke="#DDD9D0" strokeWidth="3" strokeLinecap="round" />

              <polygon
                points="70,120 200,158 330,120 200,85"
                fill={viewMode === "wireframe" ? "none" : "rgba(221, 217, 208, 0.2)"}
                stroke="#B85C38"
                strokeWidth="1.5"
                className="cursor-pointer hover:opacity-90"
                {...nodeProps("Cantilever Deck", {
                  zone: "Upper Terrace",
                  triangles: 12400,
                  material: "Tempered Glass & Steel",
                  coords: "[0.0, 3.2, 0.0]",
                })}
              />

              <polygon
                points="90,95 200,125 310,95 200,68"
                fill={viewMode === "wireframe" ? "none" : "rgba(184, 92, 56, 0.25)"}
                stroke="#B85C38"
                strokeWidth="1.2"
              />

              <g
                className="cursor-pointer group"
                {...nodeProps("Balcony Viewpoint", {
                  zone: "Master Balcony",
                  material: "Frameless Glass Railing",
                  triangles: 9100,
                  coords: "[1.8, 3.2, -0.5]",
                })}
              >
                <circle cx="150" cy="140" r="4.5" fill="#C69A4B" className="animate-pulse" />
                <circle cx="150" cy="140" r="9" fill="none" stroke="#C69A4B" strokeWidth="0.8" opacity="0.6" />
                <text x="162" y="143" fill="#F5F3EE" fontSize="8" fontFamily="monospace" fontWeight="bold">
                  Balcony POI
                </text>
              </g>

              <g
                className="cursor-pointer group"
                {...nodeProps("Foyer Entry", {
                  zone: "Entrance Lounge",
                  triangles: 7600,
                  material: "Marble Flooring",
                  coords: "[-2.0, 0.0, 3.5]",
                })}
              >
                <circle cx="230" cy="205" r="4.5" fill="#667B62" className="animate-pulse" />
                <circle cx="230" cy="205" r="9" fill="none" stroke="#667B62" strokeWidth="0.8" opacity="0.6" />
                <text x="242" y="208" fill="#F5F3EE" fontSize="8" fontFamily="monospace" fontWeight="bold">
                  Foyer Entry
                </text>
              </g>
            </g>
          )}

          {/* Coordinate Axes Gizmo */}
          <g transform="translate(42, 65)">
            <line x1="0" y1="0" x2="26" y2="0" stroke="#B85C38" strokeWidth="2" />
            <text x="30" y="3" fill="#B85C38" fontSize="9" fontWeight="bold">X</text>
            <line x1="0" y1="0" x2="0" y2="-26" stroke="#667B62" strokeWidth="2" />
            <text x="-4" y="-30" fill="#667B62" fontSize="9" fontWeight="bold">Y</text>
            <line x1="0" y1="0" x2="-16" y2="12" stroke="#C69A4B" strokeWidth="2" />
            <text x="-26" y="20" fill="#C69A4B" fontSize="9" fontWeight="bold">Z</text>
            <circle cx="0" cy="0" r="2.5" fill="#FFFFFF" />
          </g>
        </svg>

        {/* Selected Node Tooltip Overlay */}
        {selectedNode && (
          <div className="absolute top-12 left-3 z-20 flex items-center gap-2 px-2.5 py-1 rounded-md bg-charcoal/90 border border-white/20 backdrop-blur-md shadow-md">
            <Info className="h-3 w-3 text-terracotta shrink-0" />
            <span className="text-[10px] font-mono text-ivory font-medium">
              NODE: <strong className="text-white">{selectedNode}</strong>
            </span>
            <button
              type="button"
              onClick={() => setSelectedNode(null)}
              aria-label="Dismiss node details"
              className="text-stonegray hover:text-white text-xs ml-1 min-w-[24px] min-h-[24px]"
            >
              ×
            </button>
          </div>
        )}

        {/* Viewport Floating Interactive Controls (Compact, Polished, With Tooltips) */}
        {isInteractive && (
          <div className="absolute bottom-3 right-3 z-20 flex items-center gap-1.5 bg-charcoal/90 backdrop-blur-sm p-1 rounded-lg border border-white/15 shadow-md">
            {/* Camera Angle Selector: 3D, TOP, FRONT */}
            <div className="flex items-center bg-white/5 rounded p-0.5 border border-white/10 mr-1">
              <button
                type="button"
                onClick={() => setCameraMode("perspective")}
                className={cn(
                  "px-2 py-0.5 text-[10px] font-mono rounded transition-colors",
                  cameraMode === "perspective" ? "bg-terracotta text-white font-bold" : "text-white/60 hover:text-white"
                )}
                title="3D Perspective Camera"
                aria-label="3D perspective camera"
                aria-pressed={cameraMode === "perspective"}
              >
                3D
              </button>
              <button
                type="button"
                onClick={() => setCameraMode("top")}
                className={cn(
                  "px-2 py-0.5 text-[10px] font-mono rounded transition-colors",
                  cameraMode === "top" ? "bg-terracotta text-white font-bold" : "text-white/60 hover:text-white"
                )}
                title="TOP Floorplan View"
                aria-label="Top floorplan view"
                aria-pressed={cameraMode === "top"}
              >
                TOP
              </button>
              <button
                type="button"
                onClick={() => setCameraMode("front")}
                className={cn(
                  "px-2 py-0.5 text-[10px] font-mono rounded transition-colors",
                  cameraMode === "front" ? "bg-terracotta text-white font-bold" : "text-white/60 hover:text-white"
                )}
                title="FRONT Elevation View"
                aria-label="Front elevation view"
                aria-pressed={cameraMode === "front"}
              >
                FRONT
              </button>
            </div>

            {/* Lighting Toggle */}
            <button
              type="button"
              onClick={() =>
                setLightingMode((prev) =>
                  prev === "daylight" ? "golden" : prev === "golden" ? "night" : "daylight"
                )
              }
              className={cn(
                "px-2 py-1 rounded text-[10px] font-mono flex items-center gap-1 transition-colors",
                lightingMode === "golden"
                  ? "text-gold bg-white/10"
                  : lightingMode === "night"
                  ? "text-blue-300 bg-white/10"
                  : "text-white/70 hover:text-white hover:bg-white/10"
              )}
              title={`Lighting: ${lightingMode.toUpperCase()} (Click to toggle environment)`}
              aria-label={`Lighting: ${lightingMode}. Activate to cycle environment.`}
            >
              <Sun className="h-3 w-3" />
              <span className="hidden sm:inline">Lighting</span>
            </button>

            {/* Grid Toggle */}
            <button
              type="button"
              onClick={() => setShowGrid(!showGrid)}
              className={cn(
                "px-2 py-1 rounded text-[10px] font-mono flex items-center gap-1 transition-colors",
                showGrid ? "text-terracotta bg-white/10" : "text-white/60 hover:text-white hover:bg-white/10"
              )}
              title="Toggle Architectural Ground Grid"
              aria-label={showGrid ? "Hide architectural ground grid" : "Show architectural ground grid"}
              aria-pressed={showGrid}
            >
              <Grid className="h-3 w-3" />
              <span className="hidden sm:inline">Grid</span>
            </button>

            {/* View Mode Toggle: Wireframe / Shaded */}
            <button
              type="button"
              onClick={() =>
                setViewMode((prev) =>
                  prev === "shaded" ? "wireframe" : prev === "wireframe" ? "bounds" : "shaded"
                )
              }
              className={cn(
                "px-2 py-1 rounded text-[10px] font-mono flex items-center gap-1 transition-colors",
                viewMode !== "shaded" ? "text-terracotta bg-white/10" : "text-white/70 hover:text-white hover:bg-white/10"
              )}
              title={`View Mode: ${viewMode.toUpperCase()} (Click to cycle wireframe/shaded)`}
              aria-label={`View mode: ${viewMode}. Activate to cycle wireframe modes.`}
            >
              <Box className="h-3 w-3" />
              <span className="hidden sm:inline">Wireframe</span>
            </button>

            {/* Reset Camera */}
            <button
              type="button"
              onClick={() => {
                setCameraMode("perspective")
                setLightingMode("daylight")
                setViewMode("shaded")
                setSelectedNode(null)
              }}
              className="p-1.5 rounded text-white/60 hover:text-white hover:bg-white/10 transition-colors min-w-[28px] min-h-[28px]"
              title="Reset Camera View to Default"
              aria-label="Reset camera view to default"
            >
              <RotateCcw className="h-3 w-3" aria-hidden="true" />
            </button>
          </div>
        )}

        {/* Status Pill Lower Left */}
        <div className="absolute bottom-3 left-3 z-20 flex items-center gap-1.5 text-[10px] font-mono text-stonegray-300">
          <span className="px-2 py-0.5 rounded bg-charcoal/80 border border-white/10 backdrop-blur-sm">
            {lightingMode.toUpperCase()} LIGHTING
          </span>
          <span className="hidden sm:inline-block px-2 py-0.5 rounded bg-charcoal/80 border border-white/10 backdrop-blur-sm">
            {viewMode.toUpperCase()}
          </span>
        </div>
      </div>
    </div>
  )
}
