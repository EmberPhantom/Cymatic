import { NextResponse } from "next/server"
import type { NextRequest } from "next/server"

export function middleware(request: NextRequest) {
  const raw = request.cookies.get("cymatic_access_token")?.value ?? ""
  // Edge runtime cannot verify HS256 without secret; at least enforce JWT shape
  // so garbage/empty cookies don't pass as authenticated (full verify in API).
  const token = raw.split(".").length === 3 ? raw : undefined
  const isAuthPage = request.nextUrl.pathname.startsWith("/login") ||
                     request.nextUrl.pathname.startsWith("/register")
  const isDashboard = request.nextUrl.pathname.startsWith("/dashboard") ||
                      request.nextUrl.pathname.startsWith("/projects")

  // Allow auth pages without token
  if (isAuthPage) {
    if (token) {
      const rawNext = request.nextUrl.searchParams.get("next")
      let next = "/dashboard"
      try {
        const decoded = rawNext ? decodeURIComponent(rawNext) : null
        if (decoded && decoded.startsWith("/") && !decoded.startsWith("//") && !decoded.includes("\\") && decoded.length < 500) next = decoded
      } catch {}
      return NextResponse.redirect(new URL(next, request.url))
    }
    const res = NextResponse.next()
    res.headers.set("X-Frame-Options", "DENY")
    res.headers.set("X-Content-Type-Options", "nosniff")
    res.headers.set("Referrer-Policy", "strict-origin-when-cross-origin")
    // NOTE: Permissions-Policy is owned by next.config.js headers() (single
    // source of truth) — do NOT set it here.
    return res
  }

  // Protect dashboard
  if (isDashboard && !token) {
    const loginUrl = new URL("/login", request.url)
    loginUrl.searchParams.set("next", request.nextUrl.pathname + request.nextUrl.search)
    return NextResponse.redirect(loginUrl)
  }

  const res = NextResponse.next()
  res.headers.set("X-Frame-Options", "DENY")
  res.headers.set("X-Content-Type-Options", "nosniff")
  res.headers.set("Referrer-Policy", "strict-origin-when-cross-origin")
  // NOTE: Permissions-Policy is owned by next.config.js headers() (single
  // source of truth) — do NOT set it here.
  return res
}

export const config = {
  matcher: ["/dashboard/:path*", "/projects/:path*", "/login", "/register"],
}
