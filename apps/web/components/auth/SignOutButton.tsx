"use client";

import { LogOut } from "lucide-react";
import { useTransition } from "react";
import { useRouter } from "next/navigation";
import { signOut } from "@/lib/auth/actions";
import { cn } from "@/lib/cn";

type SignOutButtonProps = {
  className?: string;
  /** Where to land after sign-out. Defaults to landing page. */
  next?: string;
  children?: React.ReactNode;
};

export function SignOutButton({
  className,
  next = "/",
  children,
}: SignOutButtonProps) {
  const router = useRouter();
  const [pending, start] = useTransition();

  return (
    <button
      type="button"
      disabled={pending}
      onClick={() =>
        start(async () => {
          await signOut();
          router.push(next);
          router.refresh();
        })
      }
      className={cn(
        "inline-flex items-center gap-1.5 rounded-md px-2.5 py-1.5 text-xs font-medium text-text-secondary transition-colors hover:bg-bg-hover hover:text-text-primary disabled:opacity-60",
        className,
      )}
    >
      <LogOut className="h-3.5 w-3.5" />
      <span>{children ?? (pending ? "Signing out…" : "Sign out")}</span>
    </button>
  );
}
