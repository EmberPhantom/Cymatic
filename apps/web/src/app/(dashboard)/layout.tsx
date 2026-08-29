"use client"

import Link from "next/link"
import { usePathname } from "next/navigation"
import { useRouter } from "next/navigation"
import { useEffect, useState } from "react"
import { useAuthStore } from "@/stores/auth-store"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"
import { api } from "@/lib/api"

const navItems = [
  { href: "/dashboard", label: "Projects" },
]

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname()
  const router = useRouter()
  const { user, setAuth, logout, authReady } = useAuthStore()
  const [authError, setAuthError] = useState<string | null>(null)

  useEffect(() => {
    let active = true
    api.get("/v1/auth/me")
      .then(({ data }) => { if (active) { setAuth(data); setAuthError(null) } })
      .catch((error) => {
        if (!active) return
        if (error.response?.status === 401) {
          logout()
          router.replace(`/login?next=${encodeURIComponent(pathname)}`)
        }
        else setAuthError("Unable to load your session. Please retry.")
      })
    return () => { active = false }
  }, [setAuth, logout, router, pathname])

  if (!authReady) {
    return <div className="flex min-h-screen items-center justify-center text-sm text-muted-foreground">Loading your workspace…</div>
  }

  if (authError) {
    return <div className="flex min-h-screen items-center justify-center"><div className="space-y-3 text-center"><p className="text-sm text-destructive">{authError}</p><Button onClick={() => window.location.reload()}>Retry</Button></div></div>
  }

  return (
    <div className="flex min-h-screen">
      {/* Sidebar */}
      <aside className="w-64 border-r bg-gray-50/50 flex flex-col">
        <div className="p-6 border-b">
          <h1 className="text-xl font-bold">CYMATIC</h1>
          <p className="text-xs text-muted-foreground mt-1">Simulation Builder</p>
        </div>
        <nav className="flex-1 p-4 space-y-1">
          {navItems.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                "block px-3 py-2 rounded-md text-sm transition-colors",
                pathname === item.href
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
          <Button variant="ghost" size="sm" className="mt-2 w-full justify-start" onClick={async () => {
            try { await api.post("/v1/auth/logout") } finally { logout() }
          }}>
            Sign Out
          </Button>
        </div>
      </aside>

      {/* Main content */}
      <main className="flex-1 overflow-auto">
        <div className="p-6">
          {children}
        </div>
      </main>
    </div>
  )
}
