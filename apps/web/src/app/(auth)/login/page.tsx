"use client"

import { useState } from "react"
import { useRouter } from "next/navigation"
import Link from "next/link"
import { useForm } from "react-hook-form"
import { zodResolver } from "@hookform/resolvers/zod"
import { z } from "zod"
import { api } from "@/lib/api"
import { getErrorMessage } from "@/lib/errors"
import { useAuthStore } from "@/stores/auth-store"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Eye, EyeOff, Loader2, Sparkles, ArrowRight, Lock, Mail } from "lucide-react"

const loginSchema = z.object({
  email: z.string().email("Please enter a valid email address"),
  password: z.string().min(6, "Password must be at least 6 characters"),
})

type LoginFormData = z.infer<typeof loginSchema>

export default function LoginPage() {
  const router = useRouter()
  const setAuth = useAuthStore((s) => s.setAuth)
  const [error, setError] = useState("")
  const [loading, setLoading] = useState(false)
  const [showPassword, setShowPassword] = useState(false)
  const [rememberMe, setRememberMe] = useState(true)

  const { register, handleSubmit, setValue, formState: { errors } } = useForm<LoginFormData>({
    resolver: zodResolver(loginSchema),
    defaultValues: {
      email: "",
      password: "",
    },
  })

  const onSubmit = async (data: LoginFormData) => {
    setLoading(true)
    setError("")
    try {
      const { data: session } = await api.post("/api/auth/login", new URLSearchParams({
        username: data.email,
        password: data.password,
      }), { headers: { "Content-Type": "application/x-www-form-urlencoded" } })
      const { data: user } = await api.get("/v1/auth/me")
      const next = new URLSearchParams(window.location.search).get("next")
      setAuth(user, session.access_token)
      // Refresh router cache so middleware/layout observe the freshly committed auth cookie
      router.refresh()
      router.replace(next && next.startsWith("/") && !next.startsWith("//") ? next : "/dashboard")
    } catch (err: any) {
      setError(getErrorMessage(err, "Invalid email or password. Please try again."))
    } finally {
      setLoading(false)
    }
  }

  const fillDemoAccount = () => {
    setValue("email", "admin@cymatic.local")
    setValue("password", "admin123456")
    setError("")
  }

  return (
    <Card className="border border-border bg-card shadow-lg">
      <CardHeader className="space-y-1.5 text-center pb-5">
        <div className="mx-auto h-10 w-10 rounded-xl bg-terracotta/10 text-terracotta flex items-center justify-center mb-1 border border-terracotta/20">
          <Lock className="h-4 w-4" />
        </div>
        <CardTitle className="text-2xl font-bold tracking-tight text-foreground">Welcome Back</CardTitle>
        <CardDescription className="text-xs text-stonegray">
          Sign in to your CYMATIC simulation workspace
        </CardDescription>
      </CardHeader>

      <CardContent>
        {/* Quick Demo Fill Pill for Fast Evaluation */}
        <div className="mb-5 p-2.5 rounded-xl border border-terracotta/20 bg-terracotta/5 flex items-center justify-between text-xs">
          <div className="flex items-center gap-1.5 text-stonegray">
            <Sparkles className="h-3.5 w-3.5 text-terracotta" />
            <span>Need evaluation credentials?</span>
          </div>
          <button
            type="button"
            onClick={fillDemoAccount}
            className="text-terracotta hover:underline font-semibold text-xs inline-flex items-center gap-1"
          >
            <span>Fill Demo</span>
            <ArrowRight className="h-3 w-3" />
          </button>
        </div>

        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
          {error && (
            <div
              role="alert"
              className="rounded-lg bg-destructive/15 border border-destructive/30 p-3 text-xs text-destructive leading-relaxed"
            >
              {error}
            </div>
          )}

          <div className="space-y-1.5">
            <Label htmlFor="email" className="text-xs font-semibold uppercase tracking-wider text-foreground">
              Email Address
            </Label>
            <div className="relative">
              <Input
                id="email"
                type="email"
                placeholder="name@company.com"
                autoComplete="email"
                className="pl-9 h-10 border-border focus-visible:ring-terracotta text-xs"
                {...register("email")}
              />
              <Mail className="absolute left-3 top-3 h-4 w-4 text-stonegray pointer-events-none" />
            </div>
            {errors.email && <p className="text-xs text-destructive font-medium">{errors.email.message}</p>}
          </div>

          <div className="space-y-1.5">
            <div className="flex items-center justify-between">
              <Label htmlFor="password" className="text-xs font-semibold uppercase tracking-wider text-foreground">
                Password
              </Label>
              <span className="text-xs text-stonegray hover:text-foreground cursor-pointer">
                Forgot password?
              </span>
            </div>
            <div className="relative">
              <Input
                id="password"
                type={showPassword ? "text" : "password"}
                placeholder="••••••••"
                autoComplete="current-password"
                className="pl-9 pr-10 h-10 border-border focus-visible:ring-terracotta text-xs"
                {...register("password")}
              />
              <Lock className="absolute left-3 top-3 h-4 w-4 text-stonegray pointer-events-none" />
              <button
                type="button"
                onClick={() => setShowPassword((v) => !v)}
                aria-label={showPassword ? "Hide password" : "Show password"}
                className="absolute right-3 top-3 text-stonegray hover:text-foreground focus:outline-none transition-colors"
              >
                {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
              </button>
            </div>
            {errors.password && <p className="text-xs text-destructive font-medium">{errors.password.message}</p>}
          </div>

          <div className="flex items-center gap-2 pt-1">
            <input
              id="remember"
              type="checkbox"
              checked={rememberMe}
              onChange={(e) => setRememberMe(e.target.checked)}
              className="rounded border-border text-terracotta focus:ring-terracotta h-4 w-4 accent-terracotta"
            />
            <Label htmlFor="remember" className="text-xs text-stonegray font-normal cursor-pointer">
              Remember me on this device
            </Label>
          </div>

          <Button type="submit" variant="terracotta" className="w-full h-10 font-semibold gap-2 shadow-sm" disabled={loading}>
            {loading ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" />
                <span>Signing in…</span>
              </>
            ) : (
              <>
                <span>Sign In to CYMATIC</span>
                <ArrowRight className="h-4 w-4" />
              </>
            )}
          </Button>

          <p className="text-center text-xs text-stonegray pt-2">
            Don&apos;t have an account yet?{" "}
            <Link href="/register" className="text-terracotta font-semibold hover:underline">
              Create an account
            </Link>
          </p>
        </form>
      </CardContent>
    </Card>
  )
}
