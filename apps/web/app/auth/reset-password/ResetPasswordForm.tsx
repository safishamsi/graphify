"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowRight, ShieldCheck } from "lucide-react";
import { useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import { AuthCard } from "@/components/auth/AuthCard";
import { AuthSkeleton } from "@/components/auth/AuthSkeleton";
import { PasswordInput } from "@/components/auth/PasswordInput";
import { AuthButton } from "@/components/auth/AuthButton";
import { AuthAlert } from "@/components/auth/AuthAlert";
import { RateLimitBanner } from "@/components/auth/RateLimitBanner";
import { updatePassword } from "@/lib/auth/actions";
import { useAuthSubmit } from "@/lib/auth/useAuthSubmit";
import { useRequireRecoverySession } from "@/lib/auth/hooks";
import { validatePassword } from "@/lib/auth/validation";

export function ResetPasswordForm() {
  const router = useRouter();
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [touched, setTouched] = useState<{ pw?: boolean; cf?: boolean }>({});
  const [done, setDone] = useState(false);

  const submit = useAuthSubmit();
  const gate = useRequireRecoverySession({ bypass: done });
  const passwordRef = useRef<HTMLInputElement>(null);
  const confirmRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (gate.status === "ready" && !done) passwordRef.current?.focus();
  }, [gate.status, done]);

  useEffect(() => {
    if (submit.fieldErrors.password) passwordRef.current?.focus();
  }, [submit.fieldErrors]);

  const pwErr =
    submit.fieldErrors.password ?? (touched.pw ? validatePassword(password) : null);
  const cfErr = useMemo(() => {
    if (!touched.cf) return null;
    if (!confirm) return "Confirm your new password.";
    if (confirm !== password) return "Passwords don't match.";
    return null;
  }, [confirm, password, touched.cf]);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setTouched({ pw: true, cf: true });
    if (validatePassword(password)) {
      passwordRef.current?.focus();
      return;
    }
    if (confirm !== password) {
      confirmRef.current?.focus();
      return;
    }
    const res = await submit.run(() => updatePassword(password));
    if (!res.ok) return;
    setDone(true);
    setTimeout(() => router.replace("/orgs"), 1500);
  }

  if (gate.status === "loading") return <AuthSkeleton fields={2} withStrength />;
  if (gate.status === "redirecting") {
    return (
      <AuthCard
        eyebrow="Redirecting"
        title="Recovery link expired"
        description="Sending you back to request a fresh reset link."
      >
        <div className="grid place-items-center py-3" />
      </AuthCard>
    );
  }

  if (done) {
    return (
      <AuthCard
        eyebrow="All set"
        title="Password updated"
        description="You're signed in. Redirecting to your console…"
      >
        <div className="grid place-items-center py-3">
          <div className="relative">
            <span className="absolute inset-0 motion-safe:animate-pulse-glow rounded-full bg-brand-mint/25 blur-xl" />
            <div className="relative grid h-16 w-16 place-items-center rounded-full bg-bg-elevated ring-1 ring-brand-mint/40">
              <ShieldCheck className="h-7 w-7 text-brand-mint" aria-hidden />
            </div>
          </div>
        </div>
      </AuthCard>
    );
  }

  return (
    <AuthCard
      eyebrow="Reset password"
      title="Choose a new password"
      description="Make it long, memorable, and unique to depOS."
      footer={
        <Link
          href="/auth/sign-in"
          className="rounded text-text-secondary hover:text-text-primary focus-visible:shadow-ring-mint focus-visible:outline-none"
        >
          ← Back to sign in
        </Link>
      }
    >
      <form onSubmit={(e) => void onSubmit(e)} noValidate className="space-y-4">
        <PasswordInput
          ref={passwordRef}
          label="New password"
          autoComplete="new-password"
          placeholder="At least 8 characters"
          value={password}
          showStrength
          onBlur={() => setTouched((t) => ({ ...t, pw: true }))}
          onChange={(e) => {
            setPassword(e.target.value);
            if (submit.fieldErrors.password) submit.clearFieldError("password");
          }}
          error={pwErr}
          required
        />
        <PasswordInput
          ref={confirmRef}
          label="Confirm new password"
          autoComplete="new-password"
          placeholder="Type it again"
          value={confirm}
          onBlur={() => setTouched((t) => ({ ...t, cf: true }))}
          onChange={(e) => setConfirm(e.target.value)}
          error={cfErr}
          required
        />

        {submit.formError ? (
          <AuthAlert tone={submit.formError.kind === "network" ? "warning" : "error"}>
            {submit.formError.message}
          </AuthAlert>
        ) : null}
        {submit.isRateLimited ? (
          <RateLimitBanner secondsLeft={submit.cooldownSeconds} />
        ) : null}

        <AuthButton
          type="submit"
          loading={submit.submitting}
          loadingLabel="Updating…"
          disabled={submit.isRateLimited}
        >
          Update password
          <ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-0.5" aria-hidden />
        </AuthButton>
      </form>
    </AuthCard>
  );
}
