"use client"

import Link from "next/link"
import { usePathname } from "next/navigation"
import { useRouter } from "next/navigation"
import { useEffect, useRef, useState, useCallback } from "react"
import { useAuthStore } from "@/stores/auth-store"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"
import { api } from "@/lib/api"

const navItems = [
  { href: "/dashboard", label: "Projects" },
  { href: "/", label: "Home" },
]

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname()
  const router = useRouter()
  const { user, setAuth, logout, authReady } = useAuthStore()
  const [authError, setAuthError] = useState<string | null>(null)
  const [mobileOpen, setMobileOpen] = useState(false)
  const sidebarRef = useRef<HTMLElement>(null)
  const toggleRef = useRef<HTMLButtonElement>(null)

  const handleLogout = useCallback(async () => {
    try { await api.post("/v1/auth/logout") } finally { logout(); router.replace("/login") }
  }, [logout, router])

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
          router.replace(`/login?next=${encodeURIComponent(pathname)}`)
        }
        else setAuthError("Unable to load your session. Please retry.")
      })
    return () => { active = false; controller.abort() }
  }, [pathname, router, setAuth, logout])

  // Focus trap for mobile drawer
  useEffect(() => {
    if (!mobileOpen) {
      // return focus to toggle when closing
      return
    }
    const sidebar = sidebarRef.current
    if (!sidebar) return
    const focusable = sidebar.querySelectorAll<HTMLElement>(
      'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'
    )
    const first = focusable[0]
    const last = focusable[focusable.length - 1]
    // Focus first element when opening
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
    // prevent background scroll
    const prevOverflow = document.body.style.overflow
    document.body.style.overflow = "hidden"
    return () => {
      document.removeEventListener("keydown", handleKeyDown)
      document.body.style.overflow = prevOverflow
    }
  }, [mobileOpen])

  if (!authReady) {
    return <div className="flex min-h-screen items-center justify-center text-sm text-muted-foreground" role="status" aria-live="polite">Loading your workspace…</div>
  }

  if (authError) {
    return <div className="flex min-h-screen items-center justify-center"><div className="space-y-3 text-center"><p role="alert" className="text-sm text-destructive">{authError}</p><Button onClick={() => window.location.reload()}>Retry</Button></div></div>
  }

  const segments = pathname.split("/").filter(Boolean)
  const breadcrumbItems = segments.map((seg, idx) => {
    const href = "/" + segments.slice(0, idx + 1).join("/")
    const label = decodeURIComponent(seg)
    return { href, label }
  })

  return (
    <div className="flex min-h-screen">
      {/* Mobile toggle */}
      <button
        ref={toggleRef}
        aria-label="Toggle navigation"
        aria-expanded={mobileOpen}
        aria-controls="sidebar-nav"
        className="md:hidden fixed top-4 left-4 z-40 rounded-md bg-background border p-2"
        onClick={() => setMobileOpen((v) => !v)}
      >
        ☰
      </button>
      {/* Sidebar */}
      <aside
        id="sidebar-nav"
        ref={sidebarRef}
        aria-hidden={!mobileOpen && typeof window !== "undefined" && window.innerWidth < 768 ? true : undefined}
        className={cn("w-64 border-r bg-gray-50/50 flex flex-col fixed md:static inset-y-0 left-0 z-30 transform transition-transform md:translate-x-0", mobileOpen ? "translate-x-0" : "-translate-x-full md:translate-x-0")}
        role="navigation"
        aria-label="Main"
      >
        <div className="p-6 border-b">
          <h1 className="text-xl font-bold">CYMATIC</h1>
          <p className="text-xs text-muted-foreground mt-1">Simulation Builder</p>
        </div>
        <nav className="flex-1 p-4 space-y-1">
          {navItems.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              aria-current={pathname.startsWith(item.href) ? "page" : undefined}
              onClick={() => setMobileOpen(false)}
              className={cn(
                "block px-3 py-2 rounded-md text-sm transition-colors",
                pathname.startsWith(item.href)
                  ? "bg-primary text-primary-foreground"
                  : "text-muted-foreground hover:bg-gray-100"
              )}
            >
              {item.label}
            </Link>
          ))}
        </nav>
        <div className="p-4 border-t">
          <div className="text-sm font-medium truncate">{user?.name || "User"}</div>
          <div className="text-xs text-muted-foreground truncate">{user?.email}</div>
          <Button variant="ghost" size="sm" className="mt-2 w-full justify-start" onClick={handleLogout}>
            Sign Out
          </Button>
        </div>
      </aside>
      {mobileOpen && (
        <div
          className="fixed inset-0 bg-black/20 z-20 md:hidden"
          onClick={() => setMobileOpen(false)}
          aria-hidden="true"
        />
      )}

      {/* Main content */}
      <main className="flex-1 overflow-auto md:ml-0">
        <div className="p-6">
          {breadcrumbItems.length > 1 && (
            <nav aria-label="Breadcrumb" className="text-xs text-muted-foreground mb-4">
              <ol className="flex items-center gap-1 flex-wrap">
                {breadcrumbItems.map((crumb, idx) => {
                  const isLast = idx === breadcrumbItems.length - 1
                  return (
                    <li key={crumb.href} className="flex items-center gap-1">
                      {idx > 0 && <span aria-hidden="true">/</span>}
                      {isLast ? (
                        <span aria-current="page" className="font-medium text-foreground">{crumb.label}</span>
                      ) : (
                        <Link href={crumb.href} className="hover:underline hover:text-foreground">
                          {crumb.label}
                        </Link>
                      )}
                    </li>
                  )
                })}
              </ol>
            </nav>
          )}
          {children}
        </div>
      </main>
    </div>
  )
}
