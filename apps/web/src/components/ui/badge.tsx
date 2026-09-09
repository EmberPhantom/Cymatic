import * as React from "react"
import { cn } from "@/lib/utils"

export interface BadgeProps extends React.HTMLAttributes<HTMLDivElement> {
  variant?:
    | "default"
    | "secondary"
    | "destructive"
    | "outline"
    | "heritage"
    | "terracotta"
    | "gold"
    | "sage"
    | "charcoal"
}

const variantClasses: Record<NonNullable<BadgeProps["variant"]>, string> = {
  default: "border-transparent bg-primary text-primary-foreground",
  secondary: "border-border bg-secondary/80 text-foreground",
  destructive: "border-transparent bg-destructive/15 text-destructive",
  outline: "border-border text-foreground",
  heritage: "border-sage-200 bg-sage-50 text-sage-700 dark:bg-sage-700/20 dark:border-sage-700/40 dark:text-sage-300",
  sage: "border-sage-200 bg-sage-50 text-sage-700 dark:bg-sage-700/20 dark:border-sage-700/40 dark:text-sage-300",
  terracotta: "border-terracotta-200 bg-terracotta-50 text-terracotta-700 dark:bg-terracotta-700/20 dark:border-terracotta-700/40 dark:text-terracotta-300",
  gold: "border-gold-200 bg-gold-50 text-gold-700 dark:bg-gold-700/20 dark:border-gold-700/40 dark:text-gold-300",
  charcoal: "border-transparent bg-charcoal text-white",
}

function Badge({ className, variant = "default", ...props }: BadgeProps) {
  return (
    <div
      className={cn(
        "inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-semibold transition-colors focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2",
        variantClasses[variant],
        className
      )}
      {...props}
    />
  )
}

export { Badge }
