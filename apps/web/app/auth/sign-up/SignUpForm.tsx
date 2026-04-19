"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { ArrowRight, Mail, MailCheck, User } from "lucide-react";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { AuthCard } from "@/components/auth/AuthCard";
import { AuthInput } from "@/components/auth/AuthInput";
import { PasswordInput } from "@/components/auth/PasswordInput";
import { AuthButton } from "@/components/auth/AuthButton";
import { AuthAlert } from "@/components/auth/AuthAlert";
import { RateLimitBanner } from "@/components/auth/RateLimitBanner";
import { resendConfirmation, signUpWithPassword } from "@/lib/auth/actions";
import { useAuthSubmit } from "@/lib/auth/useAuthSubmit";
import { useResendCooldown } from "@/lib/auth/hooks";
import { validateEmail, validatePassword } from "@/lib/auth/validation";
import { nextQueryString, safeNext } from "@/lib/auth/redirects";

export function SignUpForm() {
  const router = useRouter();
  const params = useSearchParams();
  const next = safeNext(params.get("next"));

  const [displayName, setDisplayName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [touched, setTouched] = useState<{ email?: boolean; password?: boolean }>({});
  const [pendingEmail, setPendingEmail] = useState<string | null>(null);
  const [resentTone, setResentTone] = useState<"success" | "error" | null>(null);
  const [resentMessage, setResentMessage] = useState<string | null>(null);

  const submit = useAuthSubmit();
  const resend = useAuthSubmit();
  const cooldown = useResendCooldown(30);

  const emailRef = useRef<HTMLInputElement>(null);
  const passwordRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!pendingEmail) emailRef.current?.focus();
  }, [pendingEmail]);

  useEffect(() => {
    if (submit.fieldErrors.email) emailRef.current?.focus();
    else if (submit.fieldErrors.password) passwordRef.current?.focus();
  }, [submit.fieldErrors]);

  const emailErr =
    submit.fieldErrors.email ?? (touched.email ? validateEmail(email) : null);
  const passwordErr =
    submit.fieldErrors.password ??
    (touched.password ? validatePassword(password) : null);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setTouched({ email: true, password: true });

    const e1 = validateEmail(email);
    if (e1) {
      emailRef.current?.focus();
      return;
    }
    const e2 = validatePassword(password);
    if (e2) {
      passwordRef.current?.focus();
      return;
    }

    const res = await submit.run(() =>
      signUpWithPassword({
        email,
        password,
        displayName: displayName.trim() || undefined,
      }),
    );
    if (!res.ok) return;

    if (res.data.requiresConfirmation) {
      setPendingEmail(email);
      cooldown.trigger(60);
      return;
    }
    router.push(next);
    router.refresh();
  }

  async function onResend() {
    if (!pendingEmail || !cooldown.canResend) return;
    setResentTone(null);
    setResentMessage(null);
    const res = await resend.run(() => resendConfirmation(pendingEmail));
    if (res.ok) {
      cooldown.trigger(60);
      setResentTone("success");
      setResentMessage("Confirmation email sent again.");
    } else {
      setResentTone("error");
      setResentMessage(res.error.message);
    }
  }

  if (pendingEmail) {
    return (
      <AuthCard
        eyebrow="One last step"
        title="Confirm your email"
        description={
          <>
            We sent a confirmation link to{" "}
            <span className="text-text-primary">{pendingEmail}</span>. Click it
            to activate your account, then return here to sign in.
          </>
        }
        footer={
          <p className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
            <Link
              href="/auth/sign-in"
              className="rounded text-text-secondary hover:text-text-primary focus-visible:shadow-ring-mint focus-visible:outline-none"
            >
              Back to sign in
            </Link>
            <button
              type="button"
              onClick={() => {
                setPendingEmail(null);
                setResentMessage(null);
                setResentTone(null);
                submit.reset();
              }}
              className="rounded text-text-muted hover:text-text-secondary focus-visible:shadow-ring-mint focus-visible:outline-none"
            >
              Use different email
            </button>
          </p>
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

        {resentMessage ? (
          <div className="mt-4">
            <AuthAlert tone={resentTone === "success" ? "success" : "error"}>
              {resentMessage}
            </AuthAlert>
          </div>
        ) : null}

        {resend.isRateLimited ? (
          <div className="mt-3">
            <RateLimitBanner secondsLeft={resend.cooldownSeconds} />
          </div>
        ) : null}

        <p className="mt-4 text-center text-xs text-text-muted">
          Didn&apos;t get it? Check spam, or{" "}
          <button
            type="button"
            disabled={!cooldown.canResend || resend.submitting || resend.isRateLimited}
            onClick={() => void onResend()}
            className="rounded text-brand-mint hover:text-brand-mintHover disabled:opacity-60 focus-visible:shadow-ring-mint focus-visible:outline-none"
          >
            {resend.submitting
              ? "sending…"
              : cooldown.canResend
                ? "resend the link"
                : `resend in ${cooldown.secondsLeft}s`}
          </button>
          .
        </p>
      </AuthCard>
    );
  }

  return (
    <AuthCard
      eyebrow="Get started"
      title="Create your account"
      description="Spin up your org and start mapping dependencies in minutes."
      footer={
        <p>
          Already have an account?{" "}
          <Link
            href={`/auth/sign-in${nextQueryString(next)}`}
            className="rounded text-brand-mint hover:text-brand-mintHover focus-visible:shadow-ring-mint focus-visible:outline-none"
          >
            Sign in
          </Link>
        </p>
      }
    >
      <form onSubmit={(e) => void onSubmit(e)} noValidate className="space-y-4">
        <AuthInput
          label="Display name"
          hint="Optional"
          name="display_name"
          autoComplete="name"
          placeholder="Ada Lovelace"
          value={displayName}
          leadingIcon={<User className="h-3.5 w-3.5" aria-hidden />}
          onChange={(e) => setDisplayName(e.target.value)}
        />
        <AuthInput
          ref={emailRef}
          label="Work email"
          type="email"
          name="email"
          inputMode="email"
          autoComplete="email"
          placeholder="you@company.dev"
          value={email}
          leadingIcon={<Mail className="h-3.5 w-3.5" aria-hidden />}
          onBlur={() => setTouched((t) => ({ ...t, email: true }))}
          onChange={(e) => {
            setEmail(e.target.value);
            if (submit.fieldErrors.email) submit.clearFieldError("email");
          }}
          error={emailErr}
          required
        />
        <PasswordInput
          ref={passwordRef}
          autoComplete="new-password"
          placeholder="At least 8 characters"
          value={password}
          showStrength
          onBlur={() => setTouched((t) => ({ ...t, password: true }))}
          onChange={(e) => {
            setPassword(e.target.value);
            if (submit.fieldErrors.password) submit.clearFieldError("password");
          }}
          error={passwordErr}
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
          loadingLabel="Creating account…"
          disabled={submit.isRateLimited}
        >
          Create account
          <ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-0.5" aria-hidden />
        </AuthButton>

        <p className="text-center text-[11px] text-text-muted">
          By continuing you agree to the{" "}
          <Link href="/" className="rounded underline-offset-4 hover:underline focus-visible:shadow-ring-mint focus-visible:outline-none">
            terms
          </Link>{" "}
          and{" "}
          <Link href="/" className="rounded underline-offset-4 hover:underline focus-visible:shadow-ring-mint focus-visible:outline-none">
            privacy notice
          </Link>
          .
        </p>
      </form>
    </AuthCard>
  );
}
