import { Suspense } from "react";
import { ResetPasswordForm } from "./ResetPasswordForm";
import { AuthSkeleton } from "@/components/auth/AuthSkeleton";

export const metadata = { title: "Reset password · depOS" };

export default function ResetPasswordPage() {
  return (
    <Suspense fallback={<AuthSkeleton fields={2} withStrength />}>
      <ResetPasswordForm />
    </Suspense>
  );
}
