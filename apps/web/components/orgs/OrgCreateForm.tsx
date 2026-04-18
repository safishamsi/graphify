"use client";

import { useFormState, useFormStatus } from "react-dom";
import { createOrgAction } from "@/app/orgs/actions";
import { Button } from "@/components/ui/button";

function Submit() {
  const { pending } = useFormStatus();
  return (
    <Button type="submit" variant="primary" disabled={pending}>
      {pending ? "Creating…" : "Create and open"}
    </Button>
  );
}

const initial: { error?: string } = {};

export function OrgCreateForm() {
  const [state, formAction] = useFormState(createOrgAction, initial);

  return (
    <form action={formAction}>
      {state?.error ? <p className="text-danger">{state.error}</p> : null}
      <div className="field">
        <label htmlFor="slug">Slug</label>
        <input id="slug" name="slug" className="input" required placeholder="acme" autoComplete="off" />
      </div>
      <div className="field">
        <label htmlFor="name">Display name (optional)</label>
        <input id="name" name="name" className="input" placeholder="Acme Corp" />
      </div>
      <Submit />
    </form>
  );
}
