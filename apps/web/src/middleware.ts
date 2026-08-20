import { NextResponse } from "next/server"
import type { NextRequest } from "next/server"

export function middleware(request: NextRequest) {
  const token = request.cookies.get("cymatic_token")?.value
  const isAuthPage = request.nextUrl.pathname.startsWith("/login") || 
                     request.nextUrl.pathname.startsWith("/register")
  const isDashboard = request.nextUrl.pathname.startsWith("/dashboard")

  // Allow auth pages without token
  if (isAuthPage) {
    if (token) {
      return NextResponse.redirect(new URL("/dashboard", request.url))
    }
    return NextResponse.next()
  }

  // Protect dashboard
  if (isDashboard && !token) {
    return NextResponse.redirect(new URL("/login", request.url))
  }

  return NextResponse.next()
}

export const config = {
  matcher: ["/dashboard/:path*", "/login", "/register"],
}
