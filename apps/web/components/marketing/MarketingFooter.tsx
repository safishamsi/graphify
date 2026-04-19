import Link from "next/link";
import { GitBranch } from "lucide-react";

export function MarketingFooter() {
  return (
    <footer className="relative border-t border-white/[0.06] bg-ink-900/60">
      <div className="mx-auto flex max-w-6xl flex-col gap-6 px-6 py-10 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-2.5">
          <span className="grid h-6 w-6 place-items-center rounded-full bg-ink-700 ring-1 ring-brand-mint/40">
            <GitBranch className="h-3 w-3 text-brand-mint" />
          </span>
          <p className="text-sm text-fog-200">
            depOS{" "}
            <span className="text-fog-500">
              · Dependency Map OS · graph-native intelligence
            </span>
          </p>
        </div>
        <nav className="flex items-center gap-5 font-mono text-[11px] uppercase tracking-[0.18em] text-fog-500">
          <Link href="/auth/sign-in" className="hover:text-fog-200">
            Console
          </Link>
          <Link href="/auth/sign-up" className="hover:text-fog-200">
            Sign up
          </Link>
          <a href="#docs" className="hover:text-fog-200">
            Docs
          </a>
        </nav>
      </div>
    </footer>
  );
}
