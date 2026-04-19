import { notFound, redirect } from "next/navigation";
import { createClient } from "@/lib/supabase/server";
import { AppShell } from "@/components/shell/AppShell";
import { DeposApiError } from "@/lib/depos/api";
import { fetchApiHealth, fetchMe } from "@/lib/depos/server";

type Props = { children: React.ReactNode; params: { slug: string } };

export default async function OrgSlugLayout({ children, params }: Props) {
  const supabase = createClient();
  const {
    data: { session },
  } = await supabase.auth.getSession();
  if (!session?.access_token) {
    redirect(`/auth/sign-in?next=/orgs/${encodeURIComponent(params.slug)}`);
  }

  let me;
  try {
    me = await fetchMe(session.access_token);
  } catch (e) {
    if (e instanceof DeposApiError && e.status === 401) {
      redirect(`/auth/sign-in?next=/orgs/${encodeURIComponent(params.slug)}`);
    }
    notFound();
  }

  const member = me.memberships?.find((m) => m.org_slug === params.slug);
  if (!member) {
    notFound();
  }

  const apiConfigured = Boolean(process.env.NEXT_PUBLIC_DEPOS_API_URL);
  const apiHealth = await fetchApiHealth();

  return (
    <AppShell
      orgSlug={params.slug}
      userEmail={me.email}
      memberships={me.memberships ?? []}
      apiConfigured={apiConfigured}
      apiHealth={apiHealth}
    >
      {children}
    </AppShell>
  );
}
