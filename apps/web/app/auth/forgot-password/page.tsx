import { Suspense } from "react";
import { ForgotPasswordForm } from "./ForgotPasswordForm";
import { AuthSkeleton } from "@/components/auth/AuthSkeleton";

export const metadata = { title: "Forgot password · depOS" };

export default function ForgotPasswordPage() {
  return (
    <Suspense fallback={<AuthSkeleton fields={1} />}>
      <ForgotPasswordForm />
    </Suspense>
  );
}
