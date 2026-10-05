import { describe, expect, it } from "vitest"
import { render, screen, within } from "@testing-library/react"
import { BuilderSteps } from "./BuilderSteps"
import { GenerationProgress } from "./GenerationProgress"
import { BUILDER_STEPS } from "@/lib/builder-state"

describe("BuilderSteps", () => {
  it("renders an ordered list with aria-current on the current step", () => {
    render(<BuilderSteps steps={BUILDER_STEPS} currentIndex={2} />)
    const list = screen.getByRole("list", { name: "Build progress" })
    const items = within(list).getAllByRole("listitem")
    expect(items).toHaveLength(BUILDER_STEPS.length)
    expect(items[2]).toHaveAttribute("aria-current", "step")
    expect(items[0]).not.toHaveAttribute("aria-current")
    expect(items[0]).toHaveAccessibleName(/completed/i)
    expect(items[2]).toHaveAccessibleName(/current step/i)
  })
})

describe("GenerationProgress", () => {
  it("renders nothing when progress is unknown", () => {
    const { container } = render(<GenerationProgress progress={null} />)
    expect(container).toBeEmptyDOMElement()
  })

  it("exposes a progressbar with value semantics", () => {
    render(<GenerationProgress progress={42} />)
    const bar = screen.getByRole("progressbar", { name: "Generation progress" })
    expect(bar).toHaveAttribute("aria-valuenow", "42")
    expect(bar).toHaveAttribute("aria-valuemin", "0")
    expect(bar).toHaveAttribute("aria-valuemax", "100")
  })
})
