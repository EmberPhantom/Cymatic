import { NextResponse } from "next/server"

const apiOrigin = () => process.env.API_INTERNAL_URL || process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"

export async function POST(request: Request) {
  const body = await request.text()
  let upstream: Response
  try {
    upstream = await fetch(`${apiOrigin()}/v1/auth/login`, {
      method: "POST",
      headers: { "content-type": "application/x-www-form-urlencoded" },
      body,
      cache: "no-store",
    })
  } catch {
    return NextResponse.json({ detail: "Authentication service unavailable" }, { status: 502 })
  }

  const response = new NextResponse(await upstream.text(), {
    status: upstream.status,
    headers: { "content-type": upstream.headers.get("content-type") || "application/json" },
  })

  const headersWithCookies = upstream.headers as Headers & { getSetCookie?: () => string[] }
  const cookies = typeof headersWithCookies.getSetCookie === "function"
    ? headersWithCookies.getSetCookie()
    : (upstream.headers.get("set-cookie") ? [upstream.headers.get("set-cookie") as string] : [])
  for (const cookie of cookies) response.headers.append("set-cookie", cookie)

  return response
}
