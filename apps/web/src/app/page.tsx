import Link from "next/link"
import { Button } from "@/components/ui/button"

export default function Home() {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center p-8">
      <div className="max-w-2xl text-center">
        <h1 className="text-4xl font-bold tracking-tight mb-4">
          CYMATIC
        </h1>
        <p className="text-xl text-muted-foreground mb-8">
          AI-powered simulation builder for real estate and heritage walkthroughs
        </p>
        <div className="flex gap-4 justify-center">
          <Link href="/login">
            <Button size="lg">Get Started</Button>
          </Link>
          <Link href="/dashboard">
            <Button variant="outline" size="lg">Dashboard</Button>
          </Link>
        </div>
      </div>
    </main>
  )
}
