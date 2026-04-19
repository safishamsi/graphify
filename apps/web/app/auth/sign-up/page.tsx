import { Suspense } from "react";
import { SignUpForm } from "./SignUpForm";
import { AuthSkeleton } from "@/components/auth/AuthSkeleton";

export const metadata = { title: "Create account · depOS" };

export default function SignUpPage() {
  return (
    <Suspense fallback={<AuthSkeleton fields={3} withStrength />}>
      <SignUpForm />
    </Suspense>
  );
}
