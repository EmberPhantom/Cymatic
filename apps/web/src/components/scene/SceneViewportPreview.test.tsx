import { describe, expect, it } from "vitest"
import { render, screen } from "@testing-library/react"
import { SceneViewportPreview } from "./SceneViewportPreview"

describe("SceneViewportPreview (illustrative HUD + a11y)", () => {
  it("labels the schematic illustrative and shows no fake-precise numbers", () => {
    render(<SceneViewportPreview title="Test Villa" domain="real_estate" />)
    expect(screen.getByText("Preview (illustrative)")).toBeInTheDocument()
    expect(screen.queryByText("60 FPS")).not.toBeInTheDocument()
    expect(screen.queryByText("BAKED GI")).not.toBeInTheDocument()
  })

  it("renders real stats when wired through props", () => {
    render(<SceneViewportPreview stats={{ fps: 59, triangles: 74800, triangleBudget: 80000 }} />)
    expect(screen.getByText("59 FPS")).toBeInTheDocument()
    expect(screen.getByText("74.8K / 80K")).toBeInTheDocument()
    expect(screen.queryByText("Preview (illustrative)")).not.toBeInTheDocument()
  })

  it("exposes the schematic svg as an image with a label", () => {
    render(<SceneViewportPreview title="Test Villa" domain="real_estate" />)
    const svg = screen.getByRole("img", { name: /illustrative real estate scene schematic/i })
    expect(svg).toBeInTheDocument()
  })

  it("gives viewport toggles accessible names and pressed state", () => {
    render(<SceneViewportPreview />)
    expect(screen.getByRole("button", { name: "3D perspective camera" })).toHaveAttribute("aria-pressed", "true")
    expect(screen.getByRole("button", { name: "Top floorplan view" })).toHaveAttribute("aria-pressed", "false")
    expect(
      screen.getByRole("button", { name: /architectural ground grid/i })
    ).toHaveAttribute("aria-pressed", "true")
    expect(screen.getByRole("button", { name: /lighting:/i })).toBeInTheDocument()
    expect(screen.getByRole("button", { name: /view mode:/i })).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Reset camera view to default" })).toBeInTheDocument()
  })
})
