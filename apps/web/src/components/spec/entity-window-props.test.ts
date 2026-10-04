import { describe, expect, it } from "vitest"
import { WINDOW_PROP_CANONICAL, normalizeWindowProps } from "./EntityEditor"

describe("normalizeWindowProps", () => {
  it("maps legacy has_windows to canonical has_window on read", () => {
    const out = normalizeWindowProps({ size: [1, 2, 3], has_windows: true })
    expect(out[WINDOW_PROP_CANONICAL]).toBe(true)
    expect("has_windows" in out).toBe(false)
    expect(out.size).toEqual([1, 2, 3])
  })

  it("keeps the canonical value when both keys are present", () => {
    const out = normalizeWindowProps({ has_window: false, has_windows: true })
    expect(out[WINDOW_PROP_CANONICAL]).toBe(false)
    expect("has_windows" in out).toBe(false)
  })

  it("leaves canonical-only input untouched", () => {
    const out = normalizeWindowProps({ has_window: true })
    expect(out).toEqual({ has_window: true })
  })

  it("leaves unrelated props untouched", () => {
    const out = normalizeWindowProps({ furnished: true })
    expect(out).toEqual({ furnished: true })
  })
})
