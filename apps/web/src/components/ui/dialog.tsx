"use client"

import * as React from "react"
import { cn } from "@/lib/utils"

interface DialogProps {
  open?: boolean
  onOpenChange?: (open: boolean) => void
  children: React.ReactNode
}

function Dialog({ open, onOpenChange, children }: DialogProps) {
  if (!open) return null
  return (
    <div className="fixed inset-0 z-50">
      <div className="fixed inset-0 bg-black/80" onClick={() => onOpenChange?.(false)} />
      <div className="fixed inset-0 flex items-center justify-center p-4">
        {children}
      </div>
    </div>
  )
}

function DialogContent({ className, children, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn(
        "relative z-50 w-full max-w-lg rounded-lg border bg-background p-6 shadow-lg",
        className
      )}
      {...props}
    >
      {children}
    </div>
  )
}

function DialogHeader({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("flex flex-col space-y-1.5 text-center sm:text-left", className)} {...props} />
}

function DialogTitle({ className, ...props }: React.HTMLAttributes<HTMLHeadingElement>) {
  return <h2 className={cn("text-lg font-semibold leading-none tracking-tight", className)} {...props} />
}

function DialogDescription({ className, ...props }: React.HTMLAttributes<HTMLParagraphElement>) {
  return <p className={cn("text-sm text-muted-foreground", className)} {...props} />
}

function DialogTrigger({ asChild, children, ...props }: { asChild?: boolean } & React.ButtonHTMLAttributes<HTMLButtonElement>) {
  return <button {...props}>{children}</button>
}

export { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogTrigger }
