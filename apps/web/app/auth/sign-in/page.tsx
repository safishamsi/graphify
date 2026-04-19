import { Suspense } from "react";
import { SignInForm } from "./SignInForm";
import { AuthSkeleton } from "@/components/auth/AuthSkeleton";

export const metadata = { title: "Sign in · depOS" };

export default function SignInPage() {
  return (
    <Suspense fallback={<AuthSkeleton fields={2} withTabs />}>
      <SignInForm />
    </Suspense>
  );
}
