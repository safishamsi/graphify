"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { deposJson, humanizeDeposApiError } from "@/lib/depos/api";
import { requireSessionAccessToken } from "@/lib/depos/server";

function slugify(raw: string): string {
  return raw
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9-]/g, "-")
    .replace(/-+/g, "-")
    .replace(/^-|-$/g, "");
}

export async function createOrgAction(_prev: { error?: string } | undefined, formData: FormData) {
  const rawSlug = String(formData.get("slug") ?? "");
  const slug = slugify(rawSlug);
  const name = String(formData.get("name") ?? "").trim();
  if (!slug || slug.length < 2) {
    return { error: "Choose a slug (letters, numbers, hyphens; min 2 chars)." };
  }
  try {
    const token = await requireSessionAccessToken();
    await deposJson<{ id: string; slug: string }>("/v1/orgs", token, {
      method: "POST",
      json: { slug, name: name || slug },
    });
  } catch (e) {
    return { error: humanizeDeposApiError(e, 400) };
  }
  revalidatePath("/orgs");
  redirect(`/orgs/${slug}`);
}
