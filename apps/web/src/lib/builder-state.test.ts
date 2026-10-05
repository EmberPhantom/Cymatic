import { describe, expect, it } from "vitest"
import {
  builderReducer,
  initialBuilderState,
  intakeFromGenerationRun,
  isFullIntakeResult,
  resolveHydratedJob,
  sanitizeHydratedState,
  stepAfterDeadJob,
} from "./builder-state"

const fullIntake = {
  run_id: "run_123",
  detected_domain: "real_estate",
  objective: "3-bed apartment",
  missing_fields: [],
  suggested_questions: [],
  extracted_entities: {},
  confidence: 0.9,
}

describe("builderReducer", () => {
  it("HYDRATE merges partial state without touching other fields", () => {
    const next = builderReducer(initialBuilderState, {
      type: "HYDRATE",
      payload: { prompt: "villa", currentJobId: "job-1" },
    })
    expect(next.prompt).toBe("villa")
    expect(next.currentJobId).toBe("job-1")
    expect(next.step).toBe("prompt")
  })

  it("RESET_JOB clears only the job id (dead/GC'd job path)", () => {
    const started = builderReducer(initialBuilderState, { type: "SET_JOB", payload: "job-9" })
    const next = builderReducer(started, { type: "RESET_JOB" })
    expect(next.currentJobId).toBeNull()
  })
})

describe("isFullIntakeResult", () => {
  it("rejects run_id-only objects (the fake-shape bug)", () => {
    expect(isFullIntakeResult({ run_id: "run_123" })).toBe(false)
    expect(isFullIntakeResult(null)).toBe(false)
    expect(isFullIntakeResult(fullIntake)).toBe(true)
  })
})

describe("sanitizeHydratedState", () => {
  it("never synthesizes a fake intake from run_id-only storage", () => {
    const { hydrate, pendingRunIdFetch } = sanitizeHydratedState(
      { intakeResult: { run_id: "run_abc" }, step: "review" },
      null,
    )
    expect(hydrate.intakeResult).toBeUndefined()
    expect(hydrate.step).toBe("review")
    expect(pendingRunIdFetch).toBe("run_abc")
  })

  it("queues a refetch for URL run_id with no stored intake", () => {
    const { hydrate, pendingRunIdFetch } = sanitizeHydratedState(null, "run_url_1")
    expect(hydrate.intakeResult).toBeUndefined()
    expect(pendingRunIdFetch).toBe("run_url_1")
  })

  it("keeps full-shape stored intake with no refetch", () => {
    const { hydrate, pendingRunIdFetch } = sanitizeHydratedState({ intakeResult: fullIntake }, "run_123")
    expect(hydrate.intakeResult).toEqual(fullIntake)
    expect(pendingRunIdFetch).toBeNull()
  })

  it("drops invalid step/stage values", () => {
    const { hydrate } = sanitizeHydratedState({ step: "nope", generationStage: "bogus", currentJobId: 42 }, null)
    expect(hydrate.step).toBeUndefined()
    expect(hydrate.generationStage).toBeUndefined()
    expect(hydrate.currentJobId).toBeUndefined()
  })
})

describe("intakeFromGenerationRun", () => {
  it("rebuilds a full intake from the stored run", () => {
    const { run_id: _drop, ...stored } = fullIntake
    void _drop
    const rebuilt = intakeFromGenerationRun({ id: "run_123", intake: stored })
    expect(rebuilt).toEqual(fullIntake)
  })

  it("returns null when the run has no usable intake", () => {
    expect(intakeFromGenerationRun({ id: "run_123", intake: { run_id: "run_123" } })).toBeNull()
    expect(intakeFromGenerationRun({ id: "run_123", intake: null })).toBeNull()
    expect(intakeFromGenerationRun(null)).toBeNull()
  })
})

describe("resolveHydratedJob", () => {
  it("treats live/continuable statuses as live", () => {
    for (const s of ["pending", "queued", "running", "retry", "completed"]) {
      expect(resolveHydratedJob(s, false, false)).toBe("live")
    }
  })

  it("treats GC'd (404) and terminal failed/cancelled jobs as dead", () => {
    expect(resolveHydratedJob(undefined, true, true)).toBe("dead")
    expect(resolveHydratedJob("failed", false, false)).toBe("dead")
    expect(resolveHydratedJob("cancelled", false, false)).toBe("dead")
  })

  it("fails open on network blips (no 404)", () => {
    expect(resolveHydratedJob(undefined, true, false)).toBe("live")
  })
})

describe("stepAfterDeadJob", () => {
  it("resets to review when a plan/intake exists, prompt otherwise", () => {
    expect(stepAfterDeadJob(true)).toBe("review")
    expect(stepAfterDeadJob(false)).toBe("prompt")
  })
})
