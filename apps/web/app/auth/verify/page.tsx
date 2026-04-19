import { Suspense } from "react";
import { VerifyForm } from "./VerifyForm";
import { AuthSkeleton } from "@/components/auth/AuthSkeleton";

export const metadata = { title: "Verify · depOS" };

export default function VerifyPage() {
  return (
    <Suspense fallback={<AuthSkeleton fields={1} />}>
      <VerifyForm />
    </Suspense>
  );
}
