"use client"

import { useState } from "react"
import { useRouter } from "next/navigation"
import Link from "next/link"
import { useForm } from "react-hook-form"
import { zodResolver } from "@hookform/resolvers/zod"
import { z } from "zod"
import { api } from "@/lib/api"
import { useAuthStore } from "@/stores/auth-store"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"

const loginSchema = z.object({
  email: z.string().email("Invalid email address"),
  password: z.string().min(6, "Password must be at least 6 characters"),
})

type LoginFormData = z.infer<typeof loginSchema>

export default function LoginPage() {
  const router = useRouter()
  const setAuth = useAuthStore((s) => s.setAuth)
  const [error, setError] = useState("")
  const [loading, setLoading] = useState(false)

  const { register, handleSubmit, formState: { errors } } = useForm<LoginFormData>({
    resolver: zodResolver(loginSchema),
  })

  const onSubmit = async (data: LoginFormData) => {
    setLoading(true)
    setError("")
    try {
      const response = await api.post("/v1/auth/login", {
        username: data.email,
        password: data.password,
      })
      const { access_token, user } = response.data
      setAuth(user, access_token)
      router.push("/dashboard")
    } catch (err: any) {
      setError(err.response?.data?.detail || "Login failed")
    } finally {
      setLoading(false)
    }
  }

  return (
    <Card>
      <CardHeader className="text-center">
        <CardTitle className="text-2xl">Welcome Back</CardTitle>
        <CardDescription>Sign in to your CYMATIC account</CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
          {error && (
            <div className="rounded-md bg-destructive/15 p-3 text-sm text-destructive">
              {error}
            </div>
          )}
          <div className="space-y-2">
            <Label htmlFor="email">Email</Label>
            <Input id="email" type="email" placeholder="you@example.com" {...register("email")} />
            {errors.email && <p className="text-sm text-destructive">{errors.email.message}</p>}
          </div>
          <div className="space-y-2">
            <Label htmlFor="password">Password</Label>
            <Input id="password" type="password" placeholder="••••••" {...register("password")} />
            {errors.password && <p className="text-sm text-destructive">{errors.password.message}</p>}
          </div>
          <Button type="submit" className="w-full" disabled={loading}>
            {loading ? "Signing in..." : "Sign In"}
          </Button>
          <p className="text-center text-sm text-muted-foreground">
            Don&apos;t have an account?{" "}
            <Link href="/register" className="text-primary hover:underline">Sign up</Link>
          </p>
        </form>
      </CardContent>
    </Card>
  )
}
