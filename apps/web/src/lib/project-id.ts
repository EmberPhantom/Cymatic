// Single source of truth for parsing the `[id]` route param into a project id.
//
// Mirrors the guard in `use-project.ts`: only positive safe integers are valid.
// Returns `null` for anything else (missing, NaN, non-integer, <= 0) so pages
// can render a local error state and never fire project-scoped hooks with a
// NaN/garbage id.
export function parseProjectId(value: unknown): number | null {
  const raw = Array.isArray(value) ? value[0] : value
  if (typeof raw !== "string" && typeof raw !== "number") return null
  const id = typeof raw === "number" ? raw : Number(raw.trim())
  if (!Number.isSafeInteger(id) || id <= 0) return null
  return id
}
