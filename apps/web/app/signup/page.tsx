import { redirect } from "next/navigation";
import { safeNext } from "@/lib/auth/redirects";

type SearchParams = { [key: string]: string | string[] | undefined };

/** Legacy /signup route — redirect to the new /auth/sign-up path. */
export default function LegacySignupPage({
  searchParams,
}: {
  searchParams: SearchParams;
}) {
  const params = new URLSearchParams();
  const rawNext = typeof searchParams.next === "string" ? searchParams.next : null;
  const next = safeNext(rawNext);
  if (next !== "/orgs") params.set("next", next);
  const qs = params.toString();
  redirect(`/auth/sign-up${qs ? `?${qs}` : ""}`);
}
