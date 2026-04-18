import { redirect } from "next/navigation";
import { createClient } from "@/lib/supabase/server";

export default async function ReposLayout({ children }: { children: React.ReactNode }) {
  const supabase = createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) {
    redirect("/login?next=/repos");
  }
  return <>{children}</>;
}
