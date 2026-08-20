"use client"

import Link from "next/link"
import { usePathname } from "next/navigation"
import { useAuthStore } from "@/stores/auth-store"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"

const navItems = [
  { href: "/dashboard", label: "Projects" },
]

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname()
  const { user, logout } = useAuthStore()

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
          <Button variant="ghost" size="sm" className="mt-2 w-full justify-start" onClick={logout}>
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
