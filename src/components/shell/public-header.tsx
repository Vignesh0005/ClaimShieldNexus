import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Logo } from "./logo";

export function PublicHeader({ minimal }: { minimal?: boolean }) {
  return (
    <header className="glass-header sticky top-0 z-30 border-b">
      <div className="mx-auto flex h-14 max-w-6xl items-center justify-between gap-4 px-4 sm:px-6">
        <Link href="/" className="rounded-sm">
          <Logo />
        </Link>
        {minimal ? null : (
          <nav aria-label="Site" className="flex items-center gap-1 sm:gap-2">
            <Button asChild variant="ghost" size="sm" className="hidden sm:inline-flex">
              <a href="/#how-it-works">How it works</a>
            </Button>
            <Button asChild variant="ghost" size="sm" className="hidden sm:inline-flex">
              <a href="/#why">Features</a>
            </Button>
            <Button asChild variant="ghost" size="sm">
              <Link href="/login">Log in</Link>
            </Button>
            <Button asChild size="sm">
              <Link href="/demo">Request a demo</Link>
            </Button>
          </nav>
        )}
      </div>
    </header>
  );
}
