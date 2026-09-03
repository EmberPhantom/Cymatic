"use client"

import React from "react"

interface Props {
  children: React.ReactNode
  fallback?: React.ReactNode
}

interface State {
  hasError: boolean
  error?: Error
}

export class ErrorBoundary extends React.Component<Props, State> {
  constructor(props: Props) {
    super(props)
    this.state = { hasError: false }
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error }
  }

  componentDidCatch(error: Error, errorInfo: React.ErrorInfo) {
    console.error("ErrorBoundary caught:", error, errorInfo)
  }

  render() {
    if (this.state.hasError) {
      return (
        this.props.fallback || (
          <div className="flex min-h-[200px] items-center justify-center p-6">
            <div className="text-center">
              <h2 className="text-lg font-semibold">Something went wrong</h2>
              <p className="text-sm text-muted-foreground mt-2">{this.state.error?.message || "Unexpected error"}</p>
              <button className="mt-4 rounded-md bg-primary px-4 py-2 text-sm text-primary-foreground" onClick={() => this.setState({ hasError: false, error: undefined })}>
                Try again
              </button>
            </div>
          </div>
        )
      )
    }

    return this.props.children
  }
}
