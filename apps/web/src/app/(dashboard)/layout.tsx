"use client"

import Link from "next/link"
import { usePathname, useRouter } from "next/navigation"
import { useEffect, useRef, useState, useCallback, useMemo } from "react"
import { useQueryClient } from "@tanstack/react-query"
import { useAuthStore } from "@/stores/auth-store"
import { useProjects } from "@/hooks/use-projects"
import { Button } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"
import { HistoryNav } from "@/components/navigation/HistoryNav"
import { ThemeToggle } from "@/components/ui/theme-toggle"
import { cn } from "@/lib/utils"
import { api } from "@/lib/api"
import { isActivePath, getBreadcrumbs, projectIdFromPath, routes } from "@/lib/routes"
import {
  LayoutGrid,
  Compass,
  Sparkles,
  FileCode2,
  Package,
  Glasses,
  LogOut,
  ChevronDown,
  Search,
  Menu,
  X,
  Check
} from "lucide-react"

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname()
  const router = useRouter()
  const queryClient = useQueryClient()
  const { user, setAuth, logout, authReady } = useAuthStore()
  const [authError, setAuthError] = useState<string | null>(null)
  const [mobileOpen, setMobileOpen] = useState(false)
  const [signingOut, setSigningOut] = useState(false)
  const [switcherOpen, setSwitcherOpen] = useState(false)
  const sidebarRef = useRef<HTMLElement>(null)
  const toggleRef = useRef<HTMLButtonElement>(null)
  const switcherRef = useRef<HTMLDivElement>(null)

  const { data: projects } = useProjects()

  const handleLogout = useCallback(async () => {
    if (signingOut) return
    setSigningOut(true)
    try { await api.post("/v1/auth/logout") } catch { /* best effort */ }
    finally {
      logout()
      queryClient.clear()
      setSigningOut(false)
      router.replace(routes.login)
    }
  }, [logout, queryClient, router, signingOut])

  // Validate session once on mount
  useEffect(() => {
    let active = true
    const controller = new AbortController()
    api.get("/v1/auth/me", { signal: controller.signal } as unknown as Record<string, unknown>)
      .then(({ data }) => { if (active) { setAuth(data, useAuthStore.getState().token); setAuthError(null) } })
      .catch((error: unknown) => {
        const err = error as { name?: string; response?: { status?: number } }
        if (!active || err?.name === "CanceledError" || (err as { code?: string })?.code === "ERR_CANCELED") return
        if (err.response?.status === 401) {
          logout()
          queryClient.clear()
          router.replace(`${routes.login}?next=${encodeURIComponent(pathname)}`)
        }
        else setAuthError("Unable to load your session. Please retry.")
      })
    return () => { active = false; controller.abort() }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // Close switcher dropdown on outside click
  useEffect(() => {
    const handleOutsideClick = (e: MouseEvent) => {
      if (switcherRef.current && !switcherRef.current.contains(e.target as Node)) {
        setSwitcherOpen(false)
      }
    }
    document.addEventListener("mousedown", handleOutsideClick)
    return () => document.removeEventListener("mousedown", handleOutsideClick)
  }, [])

  // Focus trap for mobile drawer
  useEffect(() => {
    if (!mobileOpen) return
    const sidebar = sidebarRef.current
    if (!sidebar) return
    const focusable = sidebar.querySelectorAll<HTMLElement>(
      'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'
    )
    const first = focusable[0]
    const last = focusable[focusable.length - 1]
    requestAnimationFrame(() => first?.focus())
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault()
        setMobileOpen(false)
        toggleRef.current?.focus()
      }
      if (e.key === "Tab" && focusable.length > 0) {
        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault()
          ;(last as HTMLElement)?.focus()
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault()
          ;(first as HTMLElement)?.focus()
        }
      }
    }
    document.addEventListener("keydown", handleKeyDown)
    const prevOverflow = document.body.style.overflow
    document.body.style.overflow = "hidden"
    return () => {
      document.removeEventListener("keydown", handleKeyDown)
      document.body.style.overflow = prevOverflow
    }
  }, [mobileOpen])

  const projectId = projectIdFromPath(pathname)

  const activeProject = useMemo(() => {
    if (!projectId || !projects) return null
    return projects.find((p) => p.id === projectId) || null
  }, [projectId, projects])

  // Breadcrumbs placed in the page body, not in navbar
  const breadcrumbItems = getBreadcrumbs(pathname, activeProject?.name)

  const projectNavItems: Array<{ href: string; label: string; icon: typeof Compass; exact?: boolean }> = projectId
    ? [
        { href: routes.project(projectId), label: "Overview", icon: Compass, exact: true },
        { href: routes.builder(projectId), label: "Builder", icon: Sparkles },
        { href: routes.specs(projectId), label: "Specifications", icon: FileCode2 },
        { href: routes.assets(projectId), label: "Assets", icon: Package },
        { href: routes.stream(projectId), label: "VR Stream", icon: Glasses },
      ]
    : []

  return (
    <div className="flex h-screen h-[100dvh] overflow-hidden bg-background text-foreground">
      {/* Mobile toggle button */}
      <button
        ref={toggleRef}
        aria-label="Toggle navigation"
        aria-expanded={mobileOpen}
        aria-controls="sidebar-nav"
        className="md:hidden fixed top-3 left-4 z-40 rounded-md bg-background border border-border p-1.5 shadow-sm"
        onClick={() => setMobileOpen((v) => !v)}
      >
        {mobileOpen ? <X className="h-4 w-4" /> : <Menu className="h-4 w-4" />}
      </button>

      {/* Minimal Sidebar */}
      <aside
        id="sidebar-nav"
        ref={sidebarRef}
        aria-hidden={!mobileOpen && typeof window !== "undefined" && window.innerWidth < 768 ? true : undefined}
        className={cn(
          "w-60 shrink-0 border-r border-border bg-card flex flex-col fixed md:sticky md:top-0 md:h-screen md:h-[100dvh] md:overflow-hidden inset-y-0 left-0 z-30 transform transition-transform duration-200 md:translate-x-0",
          mobileOpen ? "translate-x-0 shadow-lg" : "-translate-x-full md:translate-x-0"
        )}
        role="navigation"
        aria-label="Main"
      >
        {/* Brand header — h-14 matches the top bar height so borders align */}
        <div className="h-14 px-4 shrink-0 border-b border-border flex items-center justify-between">
          <Link href="/" className="flex items-center gap-2.5 group">
            <div className="h-7 w-7 rounded-md bg-charcoal dark:bg-ivory text-white dark:text-charcoal flex items-center justify-center font-bold text-xs shadow-sm transition-transform group-hover:scale-105">
              CY
            </div>
            <div className="flex flex-col">
              <span className="font-bold text-sm tracking-tight text-foreground leading-none">
                CYMATIC
              </span>
              <span className="text-[9px] font-mono text-stonegray tracking-widest mt-0.5">
                SPATIAL ENGINE
              </span>
            </div>
          </Link>
        </div>

        {/* Workspace section */}
        <div className="p-3 pb-1">
          <div className="text-[10px] font-mono uppercase tracking-wider text-stonegray px-2 mb-1.5 font-medium">
            WORKSPACE
          </div>
          <Link
            href={routes.dashboard}
            aria-current={!projectId && isActivePath(pathname, routes.dashboard) ? "page" : undefined}
            onClick={() => setMobileOpen(false)}
            className={cn(
              "flex items-center gap-2.5 px-3 py-2 rounded-lg text-xs font-medium transition-all duration-150",
              !projectId && isActivePath(pathname, routes.dashboard)
                ? "bg-darkmineral text-white dark:bg-charcoal dark:text-white font-semibold shadow-sm"
                : "text-stonegray hover:text-foreground hover:bg-muted/50"
            )}
          >
            <LayoutGrid
              className={cn(
                "h-4 w-4 shrink-0 transition-colors",
                !projectId && isActivePath(pathname, routes.dashboard)
                  ? "text-terracotta"
                  : "text-stonegray"
              )}
            />
            <span>All Projects</span>
          </Link>
        </div>

        {/* Project Switcher Dropdown (Shown when inside a project) */}
        {projectId && (
          <div className="px-3 py-2 border-t border-border/70 relative" ref={switcherRef}>
            <div className="text-[10px] font-mono uppercase tracking-wider text-stonegray px-2 mb-1.5 flex items-center justify-between font-medium">
              <span>PROJECT</span>
              {activeProject?.domain === "heritage" ? (
                <span className="text-[9px] text-sage font-bold font-mono">HERITAGE</span>
              ) : (
                <span className="text-[9px] text-terracotta font-bold font-mono">REAL ESTATE</span>
              )}
            </div>
            <button
              type="button"
              onClick={() => setSwitcherOpen((v) => !v)}
              className="w-full flex items-center justify-between p-2 rounded-lg bg-muted/40 border border-border text-xs hover:bg-muted/70 transition-colors text-left"
            >
              <span className="truncate font-medium text-foreground">
                {activeProject?.name || `Project #${projectId}`}
              </span>
              <ChevronDown className={cn("h-3.5 w-3.5 text-stonegray shrink-0 transition-transform duration-200", switcherOpen && "rotate-180")} />
            </button>

            {/* Switcher Dropdown Menu */}
            {switcherOpen && (
              <div className="absolute top-full left-3 right-3 mt-1 py-1 rounded-lg bg-card border border-border shadow-md z-50 max-h-52 overflow-y-auto">
                {projects && projects.length > 0 ? (
                  projects.map((p) => (
                    <Link
                      key={p.id}
                      href={routes.project(p.id)}
                      onClick={() => setSwitcherOpen(false)}
                      className={cn(
                        "flex items-center justify-between px-3 py-1.5 text-xs hover:bg-muted transition-colors",
                        p.id === projectId && "bg-muted font-medium text-foreground"
                      )}
                    >
                      <span className="truncate">{p.name}</span>
                      {p.id === projectId && <Check className="h-3 w-3 text-terracotta shrink-0" />}
                    </Link>
                  ))
                ) : (
                  <div className="px-3 py-2 text-xs text-stonegray">No simulations found</div>
                )}
                <div className="border-t border-border mt-1 pt-1">
                  <Link
                    href={routes.dashboard}
                    onClick={() => setSwitcherOpen(false)}
                    className="block px-3 py-1 text-xs text-stonegray hover:text-foreground"
                  >
                    All projects
                  </Link>
                </div>
              </div>
            )}
          </div>
        )}

        {/* Sidebar Navigation */}
        <nav className="flex-1 min-h-0 p-3 space-y-4 overflow-y-auto overscroll-contain">
          {/* Project-specific navigation items */}
          {projectId && (
            <div className="space-y-1 pt-1">
              <div className="px-2 text-[10px] font-mono uppercase tracking-wider text-stonegray mb-1.5 font-medium">
                EXPLORE
              </div>
              {projectNavItems.map((item) => {
                const active = isActivePath(pathname, item.href, { exact: item.exact })
                const IconComponent = item.icon
                return (
                  <Link
                    key={item.href}
                    href={item.href}
                    aria-current={active ? "page" : undefined}
                    onClick={() => setMobileOpen(false)}
                    className={cn(
                      "flex items-center gap-2.5 px-3 py-2 rounded-lg text-xs font-medium transition-all duration-150",
                      active
                        ? "bg-darkmineral text-white dark:bg-charcoal dark:text-white font-semibold shadow-sm"
                        : "text-stonegray hover:text-foreground hover:bg-muted/50"
                    )}
                  >
                    <IconComponent
                      className={cn(
                        "h-4 w-4 shrink-0 transition-colors",
                        active ? "text-terracotta" : "text-stonegray"
                      )}
                    />
                    <span>{item.label}</span>
                  </Link>
                )
              })}
            </div>
          )}
        </nav>

        {/* User Card & Settings/Sign Out in Sidebar Footer */}
        <div className="p-3 border-t border-border bg-muted/20">
          <div className="flex items-center justify-between gap-2">
            <div className="flex items-center gap-2 min-w-0 flex-1">
              <div className="h-7 w-7 rounded-full bg-stonegray/20 text-foreground flex items-center justify-center font-medium text-xs shrink-0">
                {user?.name ? user.name.slice(0, 1).toUpperCase() : "U"}
              </div>
              <div className="min-w-0 flex-1">
                <div className="text-xs font-semibold truncate text-foreground">{user?.name || "Architect"}</div>
                <div className="text-[10px] text-stonegray truncate">{user?.email}</div>
              </div>
            </div>
            <div className="flex items-center gap-0.5">
              <Link href={routes.dashboard}>
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-7 w-7 p-0 text-stonegray hover:text-foreground"
                  title="Workspace Settings"
                  aria-label="Settings"
                >
                  <Compass className="h-3.5 w-3.5" />
                </Button>
              </Link>
              <Button
                variant="ghost"
                size="sm"
                className="h-7 w-7 p-0 text-stonegray hover:text-destructive"
                onClick={handleLogout}
                disabled={signingOut}
                title="Sign Out"
                aria-label="Sign out"
              >
                <LogOut className="h-3.5 w-3.5" />
              </Button>
            </div>
          </div>
        </div>
      </aside>

      {/* Mobile Backdrop */}
      {mobileOpen && (
        <div
          className="fixed inset-0 bg-black/40 z-20 md:hidden"
          onClick={() => setMobileOpen(false)}
          aria-hidden="true"
        />
      )}

      {/* Main workspace content area */}
      <main className="flex-1 min-h-0 min-w-0 overflow-y-auto overflow-x-hidden flex flex-col overscroll-contain">
        {/* Clean Top Bar (NO BREADCRUMBS in navbar) */}
        <header className="sticky top-0 z-10 h-14 shrink-0 flex items-center justify-between gap-3 border-b border-border bg-background/95 px-4 backdrop-blur-sm sm:px-6">
          <div className="flex min-w-0 items-center gap-2">
            <span className="w-8 md:hidden" aria-hidden="true" />
            {/* HistoryNav: Only arrows, zero text */}
            <HistoryNav />
          </div>

          <div className="flex items-center gap-2">
            {/* Minimal Search Trigger */}
            <Link href={routes.dashboard}>
              <button
                type="button"
                className="hidden sm:flex items-center gap-2 px-2 py-1 rounded-md border border-border text-xs text-muted-foreground hover:text-foreground hover:bg-muted/40 transition-colors"
                title="Search simulations"
              >
                <Search className="h-3 w-3" />
                <span>Search</span>
                <kbd className="px-1 py-0.2 rounded bg-muted border text-[10px] font-mono">/</kbd>
              </button>
            </Link>

            <ThemeToggle />

            <span className="hidden max-w-40 truncate text-xs text-muted-foreground md:block">
              {user?.email || ""}
            </span>

            <Button
              variant="ghost"
              size="sm"
              className="h-8 w-8 p-0 text-muted-foreground hover:text-foreground"
              onClick={handleLogout}
              disabled={signingOut}
              title="Sign Out"
              aria-label="Sign out"
            >
              <LogOut className="h-4 w-4" />
            </Button>
          </div>
        </header>

        {/* Content Viewport with In-Page Breadcrumbs */}
        <div className="flex-1 p-4 sm:p-6 lg:p-8 max-w-7xl w-full mx-auto">
          {/* Directive 5: Page Path Location in the page itself */}
          {breadcrumbItems.length > 1 && (
            <nav aria-label="Breadcrumb" className="mb-4 text-xs text-muted-foreground">
              <ol className="flex items-center gap-1.5 flex-wrap">
                {breadcrumbItems.map((crumb, idx) => {
                  const isLast = idx === breadcrumbItems.length - 1
                  return (
                    <li key={`${crumb.href ?? "current"}-${crumb.label}-${idx}`} className="flex items-center gap-1.5">
                      {idx > 0 && <span className="text-muted-foreground/50" aria-hidden="true">/</span>}
                      {isLast || !crumb.href ? (
                        <span aria-current="page" className="font-medium text-foreground">
                          {crumb.label}
                        </span>
                      ) : (
                        <Link href={crumb.href} className="hover:text-foreground transition-colors">
                          {crumb.label}
                        </Link>
                      )}
                    </li>
                  )
                })}
              </ol>
            </nav>
          )}

          {!authReady ? (
            <div className="space-y-3 pt-2" role="status" aria-live="polite" aria-label="Loading workspace">
              <Skeleton className="h-8 w-1/3 rounded" />
              <Skeleton className="h-4 w-1/2 rounded" />
              <div className="grid grid-cols-1 md:grid-cols-3 gap-3 pt-3">
                <Skeleton className="h-28 rounded" />
                <Skeleton className="h-28 rounded" />
                <Skeleton className="h-28 rounded" />
              </div>
              <span className="sr-only">Loading workspace…</span>
            </div>
          ) : authError ? (
            <div className="flex min-h-64 items-center justify-center">
              <div className="space-y-3 text-center max-w-sm p-6 rounded-lg border border-border bg-card">
                <p role="alert" className="text-sm font-medium text-destructive">{authError}</p>
                <Button onClick={() => window.location.reload()} size="sm" variant="outline">
                  Retry
                </Button>
              </div>
            </div>
          ) : (
            children
          )}
        </div>
      </main>
    </div>
  )
}
