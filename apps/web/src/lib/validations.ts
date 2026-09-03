import { z } from "zod"

export const loginSchema = z.object({
  email: z.string().email("Invalid email address"),
  password: z.string().min(6, "Password must be at least 6 characters"),
})

export const registerSchema = z.object({
  name: z.string().min(2, "Name must be at least 2 characters"),
  email: z.string().email("Invalid email address"),
  password: z.string().min(6, "Password must be at least 6 characters"),
})

export const projectSchema = z.object({
  name: z.string().min(2, "Name must be at least 2 characters").max(100),
  domain: z.enum(["real_estate", "heritage"]),
})

export const promptSchema = z.object({
  prompt: z.string().min(10, "Prompt must be at least 10 characters").max(5000, "Prompt too long"),
})

export type LoginFormData = z.infer<typeof loginSchema>
export type RegisterFormData = z.infer<typeof registerSchema>
export type ProjectFormData = z.infer<typeof projectSchema>
export type PromptFormData = z.infer<typeof promptSchema>
