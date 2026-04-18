"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const NAV: { segment: string; label: string }[] = [
  { segment: "", label: "Overview" },
  { segment: "repos", label: "Repositories" },
  { segment: "snapshots", label: "Snapshots" },
  { segment: "analyze", label: "Analyze" },
  { segment: "postci", label: "Post-CI" },
  { segment: "ci", label: "CI signals" },
  { segment: "federation", label: "Federation" },
  { segment: "drift", label: "Drift" },
  { segment: "intelligence", label: "Intelligence" },
];

export function OrgNav({ orgSlug }: { orgSlug: string }) {
  const pathname = usePathname();
  const base = `/orgs/${orgSlug}`;

  return (
    <nav aria-label="Organization">
      <ul className="nav-list">
        {NAV.map(({ segment, label }) => {
          const href = segment ? `${base}/${segment}` : base;
          const active =
            segment === "" ? pathname === base : pathname === href || pathname.startsWith(`${href}/`);
          return (
            <li key={href}>
              <Link href={href} className="nav-link" data-active={active ? "true" : "false"} prefetch={false}>
                {label}
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
