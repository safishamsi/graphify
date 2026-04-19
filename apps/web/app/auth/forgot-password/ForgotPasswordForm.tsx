"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { ArrowRight, Mail, MailCheck } from "lucide-react";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { AuthCard } from "@/components/auth/AuthCard";
import { AuthInput } from "@/components/auth/AuthInput";
import { AuthButton } from "@/components/auth/AuthButton";
import { AuthAlert } from "@/components/auth/AuthAlert";
import { RateLimitBanner } from "@/components/auth/RateLimitBanner";
import { requestPasswordReset } from "@/lib/auth/actions";
import { useAuthSubmit } from "@/lib/auth/useAuthSubmit";
import { useResendCooldown } from "@/lib/auth/hooks";
import { validateEmail } from "@/lib/auth/validation";

export function ForgotPasswordForm() {
  const params = useSearchParams();
  const expired = params.get("error") === "expired";

  const [email, setEmail] = useState("");
  const [touched, setTouched] = useState(false);
  const [sent, setSent] = useState(false);
  const submit = useAuthSubmit();
  const cooldown = useResendCooldown(45);
  const emailRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!sent) emailRef.current?.focus();
  }, [sent]);

  useEffect(() => {
    if (submit.fieldErrors.email) emailRef.current?.focus();
  }, [submit.fieldErrors]);

  const emailErr =
    submit.fieldErrors.email ?? (touched ? validateEmail(email) : null);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setTouched(true);
    if (validateEmail(email)) {
      emailRef.current?.focus();
      return;
    }
    const res = await submit.run(() => requestPasswordReset(email));
    if (res.ok) {
      setSent(true);
      cooldown.trigger();
    }
  }

  async function onResend() {
    if (!cooldown.canResend) return;
    const res = await submit.run(() => requestPasswordReset(email));
    if (res.ok) cooldown.trigger();
  }

  if (sent) {
    return (
      <AuthCard
        eyebrow="Reset requested"
        title="Check your inbox"
        description={
          <>
            If an account exists for{" "}
            <span className="text-text-primary">{email}</span>, we sent a link
            to reset your password.
          </>
        }
        footer={
          <Link
            href="/auth/sign-in"
            className="rounded text-text-secondary hover:text-text-primary focus-visible:shadow-ring-mint focus-visible:outline-none"
          >
            ← Back to sign in
          </Link>
        }
      >
        <div className="grid place-items-center py-2">
          <div className="relative">
            <span className="absolute inset-0 motion-safe:animate-pulse-glow rounded-full bg-brand-mint/20 blur-xl" />
            <div className="relative grid h-16 w-16 place-items-center rounded-full bg-bg-elevated ring-1 ring-brand-mint/40">
              <MailCheck className="h-7 w-7 text-brand-mint" aria-hidden />
            </div>
          </div>
        </div>
        <p className="mt-4 text-center text-xs text-text-muted">
          Link expires in one hour. Not in your inbox?{" "}
          <button
            type="button"
            disabled={!cooldown.canResend || submit.submitting || submit.isRateLimited}
            onClick={() => void onResend()}
            className="rounded text-brand-mint hover:text-brand-mintHover disabled:opacity-60 focus-visible:shadow-ring-mint focus-visible:outline-none"
          >
            {submit.submitting
              ? "sending…"
              : cooldown.canResend
                ? "resend"
                : `resend in ${cooldown.secondsLeft}s`}
          </button>
        </p>
        {submit.isRateLimited ? (
          <div className="mt-3">
            <RateLimitBanner secondsLeft={submit.cooldownSeconds} />
          </div>
        ) : null}
      </AuthCard>
    );
  }

  return (
    <AuthCard
      eyebrow="Forgot password"
      title="Reset your password"
      description="We'll email you a secure link to choose a new one."
      footer={
        <Link
          href="/auth/sign-in"
          className="rounded text-text-secondary hover:text-text-primary focus-visible:shadow-ring-mint focus-visible:outline-none"
        >
          ← Back to sign in
        </Link>
      }
    >
      {expired ? (
        <div className="mb-4">
          <AuthAlert tone="warning" title="Link expired">
            That reset link is no longer valid. Request a fresh one below.
          </AuthAlert>
        </div>
      ) : null}

      <form onSubmit={(e) => void onSubmit(e)} noValidate className="space-y-4">
        <AuthInput
          ref={emailRef}
          label="Email"
          type="email"
          name="email"
          inputMode="email"
          autoComplete="email"
          placeholder="you@company.dev"
          value={email}
          leadingIcon={<Mail className="h-3.5 w-3.5" aria-hidden />}
          onBlur={() => setTouched(true)}
          onChange={(e) => {
            setEmail(e.target.value);
            if (submit.fieldErrors.email) submit.clearFieldError("email");
          }}
          error={emailErr}
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
          loadingLabel="Sending link…"
          disabled={submit.isRateLimited}
        >
          Email me a reset link
          <ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-0.5" aria-hidden />
        </AuthButton>
      </form>
    </AuthCard>
  );
}
