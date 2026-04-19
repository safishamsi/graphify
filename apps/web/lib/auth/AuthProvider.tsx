"use client";

import {
  createContext,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { useRouter } from "next/navigation";
import type { Session, User } from "@supabase/supabase-js";
import { createClient } from "@/lib/supabase/client";

type Status = "loading" | "authenticated" | "unauthenticated";

type AuthContextValue = {
  status: Status;
  session: Session | null;
  user: User | null;
};

const AuthContext = createContext<AuthContextValue>({
  status: "loading",
  session: null,
  user: null,
});

/**
 * Listens to Supabase `onAuthStateChange` and exposes a typed snapshot to
 * any client component via `useAuth()`. Refreshes the RSC tree on
 * sign-in / sign-out so server-rendered pages re-fetch with the new cookies.
 */
export function AuthProvider({
  children,
  initialSession = null,
}: {
  children: React.ReactNode;
  initialSession?: Session | null;
}) {
  const supabase = useMemo(() => createClient(), []);
  const router = useRouter();
  const [session, setSession] = useState<Session | null>(initialSession);
  const [status, setStatus] = useState<Status>(
    initialSession ? "authenticated" : "loading",
  );
  const lastEvent = useRef<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    supabase.auth.getSession().then(({ data }) => {
      if (cancelled) return;
      setSession(data.session ?? null);
      setStatus(data.session ? "authenticated" : "unauthenticated");
    });

    const {
      data: { subscription },
    } = supabase.auth.onAuthStateChange((event, nextSession) => {
      setSession(nextSession);
      setStatus(nextSession ? "authenticated" : "unauthenticated");

      // Only refresh the RSC tree when the auth boundary actually crosses,
      // not on every TOKEN_REFRESHED tick.
      const crossed =
        (event === "SIGNED_IN" && lastEvent.current !== "SIGNED_IN") ||
        event === "SIGNED_OUT" ||
        event === "USER_UPDATED" ||
        event === "PASSWORD_RECOVERY";
      lastEvent.current = event;
      if (crossed) router.refresh();
    });

    return () => {
      cancelled = true;
      subscription.unsubscribe();
    };
  }, [supabase, router]);

  const value = useMemo<AuthContextValue>(
    () => ({ status, session, user: session?.user ?? null }),
    [status, session],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  return useContext(AuthContext);
}
