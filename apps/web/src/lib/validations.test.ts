import { describe, expect, it } from "vitest"
import {
  PayloadValidationError,
  asEntityRecord,
  clarifyResultSchema,
  countSpecEntities,
  intakeResultSchema,
  parseClarifyResultOrThrow,
  parseIntakeResultOrThrow,
  parseSpecPayloadOrThrow,
  specEntities,
  specPayloadSchema,
  specSection,
} from "./validations"

const validIntake = {
  detected_domain: "real_estate",
  objective: "3-bed apartment",
  missing_fields: ["budget"],
  suggested_questions: ["budget?"],
  extracted_entities: { bedrooms: 3 },
  confidence: 0.9,
  run_id: "run_1",
}

const validClarify = {
  updated_fields: { budget: "100k" },
  ready_for_generation: true,
  completion_percentage: 1,
  remaining_questions: [],
  run_id: "run_1",
}

describe("specPayloadSchema", () => {
  it("accepts a well-formed payload", () => {
    const parsed = specPayloadSchema.safeParse({ entities: [{ id: "a" }], performance_budget: { target_fps: 60 } })
    expect(parsed.success).toBe(true)
  })

  it("rejects non-object payloads with a typed error", () => {
    expect(() => parseSpecPayloadOrThrow("nope")).toThrow(PayloadValidationError)
    expect(() => parseSpecPayloadOrThrow(null)).toThrow(PayloadValidationError)
    expect(() => parseSpecPayloadOrThrow([1, 2])).toThrow(PayloadValidationError)
  })

  it("rejects a non-array entities field", () => {
    const parsed = specPayloadSchema.safeParse({ entities: "room_living" })
    expect(parsed.success).toBe(false)
  })
})

describe("spec accessors", () => {
  it("specEntities returns [] for malformed payloads", () => {
    expect(specEntities(null)).toEqual([])
    expect(specEntities("garbage")).toEqual([])
    expect(specEntities({ entities: "not-an-array" })).toEqual([])
    expect(specEntities({ entities: [{ id: "a" }, { id: "b" }] })).toHaveLength(2)
  })

  it("countSpecEntities counts safely", () => {
    expect(countSpecEntities(undefined)).toBe(0)
    expect(countSpecEntities({ entities: [1, 2, 3] })).toBe(3)
  })

  it("specSection returns {} for missing/malformed sections", () => {
    expect(specSection(null, "performance_budget")).toEqual({})
    expect(specSection({ performance_budget: { target_fps: 60 } }, "performance_budget")).toEqual({ target_fps: 60 })
    expect(specSection({ performance_budget: 42 }, "performance_budget")).toEqual({})
  })

  it("asEntityRecord narrows blobs to records", () => {
    expect(asEntityRecord({ a: 1 })).toEqual({ a: 1 })
    expect(asEntityRecord([1])).toEqual({})
    expect(asEntityRecord(null)).toEqual({})
    expect(asEntityRecord("x")).toEqual({})
  })
})

describe("intakeResultSchema", () => {
  it("accepts a well-formed intake result", () => {
    expect(intakeResultSchema.safeParse(validIntake).success).toBe(true)
    expect(parseIntakeResultOrThrow(validIntake).detected_domain).toBe("real_estate")
  })

  it("throws PayloadValidationError on malformed intake", () => {
    expect(() => parseIntakeResultOrThrow(null)).toThrow(PayloadValidationError)
    expect(() => parseIntakeResultOrThrow({})).toThrow(PayloadValidationError)
    expect(() =>
      parseIntakeResultOrThrow({ ...validIntake, missing_fields: "budget" })
    ).toThrow(PayloadValidationError)
    expect(() =>
      parseIntakeResultOrThrow({ ...validIntake, confidence: "high" })
    ).toThrow(PayloadValidationError)
  })
})

describe("clarifyResultSchema", () => {
  it("accepts a well-formed clarify result", () => {
    expect(clarifyResultSchema.safeParse(validClarify).success).toBe(true)
    expect(parseClarifyResultOrThrow(validClarify).ready_for_generation).toBe(true)
  })

  it("throws PayloadValidationError on malformed clarify", () => {
    expect(() => parseClarifyResultOrThrow(undefined)).toThrow(PayloadValidationError)
    expect(() =>
      parseClarifyResultOrThrow({ ...validClarify, ready_for_generation: "yes" })
    ).toThrow(PayloadValidationError)
    expect(() =>
      parseClarifyResultOrThrow({ ...validClarify, remaining_questions: [{ field: 1 }] })
    ).toThrow(PayloadValidationError)
  })
})
