"use client";

import Link from "next/link";
import * as DropdownMenu from "@radix-ui/react-dropdown-menu";
import { ChevronDown } from "lucide-react";
import type { MeMembership } from "@/lib/depos/types";

export function OrgSwitcher({ orgSlug, memberships }: { orgSlug: string; memberships: MeMembership[] }) {
  const orgs = memberships.filter((m): m is MeMembership & { org_slug: string } => Boolean(m.org_slug));

  if (orgs.length <= 1) {
    return (
      <p className="font-mono" style={{ margin: 0, fontSize: "0.85rem", color: "var(--accent)" }}>
        {orgSlug}
      </p>
    );
  }

  return (
    <DropdownMenu.Root>
      <DropdownMenu.Trigger asChild>
        <button type="button" className="btn btn-ghost" style={{ width: "100%", justifyContent: "space-between" }}>
          <span className="font-mono" style={{ fontSize: "0.85rem" }}>
            {orgSlug}
          </span>
          <ChevronDown size={16} aria-hidden />
        </button>
      </DropdownMenu.Trigger>
      <DropdownMenu.Portal>
        <DropdownMenu.Content
          sideOffset={6}
          style={{
            background: "var(--bg-elevated)",
            border: "1px solid var(--border)",
            borderRadius: "var(--radius-sm)",
            padding: "0.25rem",
            minWidth: "var(--sidebar-width)",
            zIndex: 50,
            boxShadow: "0 12px 40px rgba(0,0,0,0.45)",
          }}
        >
          {orgs.map((m) => (
            <DropdownMenu.Item key={m.org_slug} asChild>
              <Link
                href={`/orgs/${m.org_slug}`}
                style={{
                  display: "block",
                  padding: "0.5rem 0.75rem",
                  borderRadius: "4px",
                  color: "var(--fg)",
                  fontSize: "0.875rem",
                  textDecoration: "none",
                  outline: "none",
                }}
              >
                {m.org_slug}
                <span style={{ marginLeft: "0.35rem", color: "var(--fg-muted)", fontSize: "0.75rem" }}>
                  ({m.role})
                </span>
              </Link>
            </DropdownMenu.Item>
          ))}
        </DropdownMenu.Content>
      </DropdownMenu.Portal>
    </DropdownMenu.Root>
  );
}
