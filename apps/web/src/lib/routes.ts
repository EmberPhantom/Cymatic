export const routes = {
  home: "/",
  login: "/login",
  register: "/register",
  dashboard: "/dashboard",
  project: (id: number | string) => `/projects/${id}`,
  builder: (id: number | string) => `/projects/${id}/builder`,
  specs: (id: number | string) => `/projects/${id}/specs`,
  assets: (id: number | string) => `/projects/${id}/assets`,
  stream: (id: number | string) => `/projects/${id}/stream`,
} as const

/**
 * Segment-aware active check. Avoids the classic bug where
 * `pathname.startsWith("/")` marks Home active on every page.
 *
 * Pass `{ exact: true }` for leaf routes (e.g. project Overview,
 * whose href is a prefix of every child route) so descendants
 * don't keep the parent highlighted.
 */
export function isActivePath(pathname: string, href: string, opts?: { exact?: boolean }): boolean {
  if (href === "/") return pathname === "/"
  if (opts?.exact) return pathname === href
  return pathname === href || pathname.startsWith(`${href}/`)
}

/** Extract a numeric project id from a pathname like /projects/5/builder. */
export function projectIdFromPath(pathname: string): number | null {
  const match = pathname.match(/^\/projects\/(\d+)(?:\/|$)/)
  return match ? Number(match[1]) : null
}

export interface Crumb {
  href: string | null // null = current page, render as plain text
  label: string
}

const SEGMENT_LABELS: Record<string, string> = {
  dashboard: "Dashboard",
  projects: "Projects",
  builder: "Builder",
  specs: "Specifications",
  assets: "Assets",
  stream: "Stream",
}

/**
 * Build breadcrumbs for dashboard-shell routes. Numeric project ids are
 * rendered as `Project {id}` (or the resolved project name when provided)
 * and link to the project overview. The bare `/projects` segment links to
 * `/dashboard` since no `/projects` index page exists.
 */
export function getBreadcrumbs(pathname: string, projectName?: string | null): Crumb[] {
  const segments = pathname.split("/").filter(Boolean)
  if (segments.length === 0) return []

  const crumbs: Crumb[] = []
  let projectSeen = false

  segments.forEach((seg, idx) => {
    const isLast = idx === segments.length - 1
    const isId = /^\d+$/.test(seg) && segments[idx - 1] === "projects"

    if (isId) {
      projectSeen = true
      const id = seg
      crumbs.push({
        href: isLast ? null : routes.project(id),
        label: projectName || `Project ${id}`,
      })
      return
    }

    if (seg === "projects" && !projectSeen) {
      // No /projects index route — point at the dashboard list instead.
      crumbs.push({ href: isLast ? null : routes.dashboard, label: "Projects" })
      return
    }

    const label = SEGMENT_LABELS[seg] ?? decodeURIComponent(seg).replace(/[-_]/g, " ")
    const href = "/" + segments.slice(0, idx + 1).join("/")
    crumbs.push({ href: isLast ? null : href, label })
  })

  return crumbs
}
