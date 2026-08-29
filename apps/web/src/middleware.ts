import { NextResponse } from "next/server"
import type { NextRequest } from "next/server"

export function middleware(request: NextRequest) {
  const token = request.cookies.get("cymatic_access_token")?.value
  const isAuthPage = request.nextUrl.pathname.startsWith("/login") || 
                     request.nextUrl.pathname.startsWith("/register")
  const isDashboard = request.nextUrl.pathname.startsWith("/dashboard") ||
                      request.nextUrl.pathname.startsWith("/projects")

  // Allow auth pages without token
  if (isAuthPage) {
    if (token) {
      const next = request.nextUrl.searchParams.get("next")
      return NextResponse.redirect(new URL(next && next.startsWith("/") && !next.startsWith("//") ? next : "/dashboard", request.url))
    }
    return NextResponse.next()
  }

  // Protect dashboard
  if (isDashboard && !token) {
    const loginUrl = new URL("/login", request.url)
    loginUrl.searchParams.set("next", request.nextUrl.pathname + request.nextUrl.search)
    return NextResponse.redirect(loginUrl)
  }

  return NextResponse.next()
}

export const config = {
  matcher: ["/dashboard/:path*", "/projects/:path*", "/login", "/register"],
}
