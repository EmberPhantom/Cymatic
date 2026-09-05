import { describe, it, expect } from "vitest"
import { render, screen } from "@testing-library/react"
import { ProgressStepper } from "./ProgressStepper"

describe("ProgressStepper", () => {
  it("renders all stages", () => {
    render(<ProgressStepper currentStage="architect" completedStages={["intake", "clarification"]} />)
    expect(screen.getByText("Intake")).toBeInTheDocument()
    expect(screen.getByText("Architect")).toBeInTheDocument()
    expect(screen.getByText(/Overall Progress/)).toBeInTheDocument()
  })
  it("shows completed check", () => {
    render(<ProgressStepper currentStage="validation" completedStages={["intake"]} />)
    expect(document.querySelector(".bg-primary")).toBeTruthy()
  })
})
