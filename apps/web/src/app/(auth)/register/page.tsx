"use client"

import { useState, useMemo } from "react"
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
import { Eye, EyeOff, Loader2, ArrowRight, UserPlus, User, Mail, Lock, Check, Building2, Landmark } from "lucide-react"

const registerSchema = z.object({
  name: z.string().min(2, "Full name must be at least 2 characters"),
  email: z.string().email("Please enter a valid email address"),
  password: z.string().min(6, "Password must be at least 6 characters"),
})

type RegisterFormData = z.infer<typeof registerSchema>

export default function RegisterPage() {
  const router = useRouter()
  const setAuth = useAuthStore((s) => s.setAuth)
  const [error, setError] = useState("")
  const [loading, setLoading] = useState(false)
  const [showPassword, setShowPassword] = useState(false)
  const [selectedInterest, setSelectedInterest] = useState<"real_estate" | "heritage" | "both">("both")

  const { register, handleSubmit, watch, formState: { errors } } = useForm<RegisterFormData>({
    resolver: zodResolver(registerSchema),
  })

  const passwordValue = watch("password") || ""

  // Calculate password strength
  const passwordStrength = useMemo(() => {
    if (!passwordValue) return { score: 0, label: "", color: "bg-muted" }
    let score = 0
    if (passwordValue.length >= 6) score += 1
    if (passwordValue.length >= 10) score += 1
    if (/[A-Z]/.test(passwordValue)) score += 1
    if (/[0-9]/.test(passwordValue)) score += 1
    if (/[^A-Za-z0-9]/.test(passwordValue)) score += 1

    if (score <= 1) return { score: 20, label: "Weak", color: "bg-destructive" }
    if (score <= 2) return { score: 45, label: "Fair", color: "bg-gold" }
    if (score <= 3) return { score: 75, label: "Good", color: "bg-sage" }
    return { score: 100, label: "Strong", color: "bg-emerald-600" }
  }, [passwordValue])

  const onSubmit = async (data: RegisterFormData) => {
    setLoading(true)
    setError("")
    try {
      await api.post("/v1/auth/register", {
        name: data.name,
        email: data.email,
        password: data.password,
      })
      // Auto-login after registration
      const { data: session } = await api.post("/api/auth/login", new URLSearchParams({
        username: data.email,
        password: data.password,
      }), { headers: { "Content-Type": "application/x-www-form-urlencoded" } })
      const { data: user } = await api.get("/v1/auth/me")
      setAuth(user, session.access_token)
      router.refresh()
      router.replace("/dashboard")
    } catch (err: any) {
      setError(err.response?.data?.detail || "Registration failed. Please check your details and try again.")
    } finally {
      setLoading(false)
    }
  }

  return (
    <Card className="border border-border bg-card shadow-lg">
      <CardHeader className="space-y-1.5 text-center pb-5">
        <div className="mx-auto h-10 w-10 rounded-xl bg-terracotta/10 text-terracotta flex items-center justify-center mb-1 border border-terracotta/20">
          <UserPlus className="h-4 w-4" />
        </div>
        <CardTitle className="text-2xl font-bold tracking-tight text-foreground">Create Account</CardTitle>
        <CardDescription className="text-xs text-stonegray">
          Start building AI simulations streamed to mobile VR
        </CardDescription>
      </CardHeader>

      <CardContent>
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
            <Label htmlFor="name" className="text-xs font-semibold uppercase tracking-wider text-foreground">
              Full Name
            </Label>
            <div className="relative">
              <Input
                id="name"
                placeholder="Alex Morgan"
                autoComplete="name"
                className="pl-9 h-10 border-border focus-visible:ring-terracotta text-xs"
                {...register("name")}
              />
              <User className="absolute left-3 top-3 h-4 w-4 text-stonegray pointer-events-none" />
            </div>
            {errors.name && <p className="text-xs text-destructive font-medium">{errors.name.message}</p>}
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="email" className="text-xs font-semibold uppercase tracking-wider text-foreground">
              Email Address
            </Label>
            <div className="relative">
              <Input
                id="email"
                type="email"
                placeholder="alex@example.com"
                autoComplete="email"
                className="pl-9 h-10 border-border focus-visible:ring-terracotta text-xs"
                {...register("email")}
              />
              <Mail className="absolute left-3 top-3 h-4 w-4 text-stonegray pointer-events-none" />
            </div>
            {errors.email && <p className="text-xs text-destructive font-medium">{errors.email.message}</p>}
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="password" className="text-xs font-semibold uppercase tracking-wider text-foreground">
              Password
            </Label>
            <div className="relative">
              <Input
                id="password"
                type={showPassword ? "text" : "password"}
                placeholder="At least 6 characters"
                autoComplete="new-password"
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

            {/* Password strength meter */}
            {passwordValue && (
              <div className="space-y-1 pt-1">
                <div className="flex items-center justify-between text-[11px] text-stonegray">
                  <span>Strength: {passwordStrength.label}</span>
                  <span className="font-mono">{passwordStrength.score}%</span>
                </div>
                <div className="h-1.5 w-full bg-muted rounded-full overflow-hidden">
                  <div
                    className={`h-full ${passwordStrength.color} transition-all duration-300 rounded-full`}
                    style={{ width: `${passwordStrength.score}%` }}
                  />
                </div>
              </div>
            )}
          </div>

          {/* Primary Domain Interest Pills */}
          <div className="space-y-1.5 pt-1">
            <span className="text-xs font-semibold uppercase tracking-wider text-stonegray">
              Primary Simulation Focus
            </span>
            <div className="grid grid-cols-3 gap-2">
              <button
                type="button"
                onClick={() => setSelectedInterest("real_estate")}
                className={`px-2.5 py-2 rounded-lg border text-xs font-medium flex flex-col items-center gap-1 transition-all ${
                  selectedInterest === "real_estate"
                    ? "border-terracotta bg-terracotta/10 text-terracotta font-semibold shadow-xs"
                    : "border-border text-stonegray hover:text-foreground hover:bg-muted/40"
                }`}
              >
                <Building2 className="h-3.5 w-3.5" />
                <span>Real Estate</span>
              </button>

              <button
                type="button"
                onClick={() => setSelectedInterest("heritage")}
                className={`px-2.5 py-2 rounded-lg border text-xs font-medium flex flex-col items-center gap-1 transition-all ${
                  selectedInterest === "heritage"
                    ? "border-sage bg-sage/10 text-sage font-semibold shadow-xs"
                    : "border-border text-stonegray hover:text-foreground hover:bg-muted/40"
                }`}
              >
                <Landmark className="h-3.5 w-3.5" />
                <span>Heritage</span>
              </button>

              <button
                type="button"
                onClick={() => setSelectedInterest("both")}
                className={`px-2.5 py-2 rounded-lg border text-xs font-medium flex flex-col items-center gap-1 transition-all ${
                  selectedInterest === "both"
                    ? "border-charcoal bg-charcoal/10 text-foreground dark:border-ivory dark:bg-ivory/10 font-semibold shadow-xs"
                    : "border-border text-stonegray hover:text-foreground hover:bg-muted/40"
                }`}
              >
                <Check className="h-3.5 w-3.5" />
                <span>All Domains</span>
              </button>
            </div>
          </div>

          <Button type="submit" variant="terracotta" className="w-full h-10 font-semibold gap-2 shadow-xs mt-2" disabled={loading}>
            {loading ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" />
                <span>Creating your account…</span>
              </>
            ) : (
              <>
                <span>Create Free Account</span>
                <ArrowRight className="h-4 w-4" />
              </>
            )}
          </Button>

          <p className="text-center text-xs text-stonegray pt-1">
            Already have an account?{" "}
            <Link href="/login" className="text-terracotta font-semibold hover:underline">
              Sign in
            </Link>
          </p>
        </form>
      </CardContent>
    </Card>
  )
}
