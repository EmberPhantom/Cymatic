"use client"

import * as React from "react"
import { cn } from "@/lib/utils"

interface DialogProps {
  open?: boolean
  onOpenChange?: (open: boolean) => void
  children: React.ReactNode
}

function Dialog({ open, onOpenChange, children }: DialogProps) {
  const trigger = React.Children.toArray(children).find((c: any) => c?.type?.displayName === "DialogTrigger" || (c as any)?.props?.__isTrigger)
  const content = React.Children.toArray(children).filter((c: any) => c?.type?.displayName !== "DialogTrigger")
  // Fallback: separate trigger and content by type
  const triggers: React.ReactNode[] = []
  const contents: React.ReactNode[] = []
  React.Children.forEach(children, (child: any) => {
    if (child?.type === DialogTrigger) triggers.push(child)
    else contents.push(child)
  })
  return (
    <>
      {triggers}
      {open && (
        <div className="fixed inset-0 z-50">
          <div className="fixed inset-0 bg-black/80" onClick={() => onOpenChange?.(false)} />
          <div className="fixed inset-0 flex items-center justify-center p-4">{contents}</div>
        </div>
      )}
    </>
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
  const Comp: any = asChild ? "span" : "button"
  return <Comp {...props}>{children}</Comp>
}
DialogTrigger.displayName = "DialogTrigger"

export { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogTrigger }
