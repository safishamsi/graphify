import { redirect } from "next/navigation";
import { safeNext } from "@/lib/auth/redirects";

type SearchParams = { [key: string]: string | string[] | undefined };

/** Legacy /login route — redirect to the new /auth/sign-in path. */
export default function LegacyLoginPage({
  searchParams,
}: {
  searchParams: SearchParams;
}) {
  const params = new URLSearchParams();
  const rawNext = typeof searchParams.next === "string" ? searchParams.next : null;
  const next = safeNext(rawNext);
  if (next !== "/orgs") params.set("next", next);
  const error = searchParams.error;
  if (typeof error === "string") params.set("error", error);
  const qs = params.toString();
  redirect(`/auth/sign-in${qs ? `?${qs}` : ""}`);
}
