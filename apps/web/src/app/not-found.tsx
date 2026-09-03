import Link from "next/link"
import { Button } from "@/components/ui/button"

export default function NotFound() {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center p-8 text-center">
      <h2 className="text-2xl font-bold">Not Found</h2>
      <p className="text-sm text-muted-foreground mt-2">The page you are looking for does not exist.</p>
      <Link href="/" className="mt-6">
        <Button>Go Home</Button>
      </Link>
    </div>
  )
}
