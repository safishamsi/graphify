# depOS web — Layer 1 (frontend-design skill)

## Visual thesis

Industrial dark console: cool deep base, one sharp accent for actions and graph-health, monospace only for data and JSON — a sharp display serif for page titles only.

## Content plan

- **Marketing `/`:** Hero (depOS mark + promise + single primary CTA) → proof strip (what the console does) → workflow depth (snapshot → analyze → CI) → final CTA to sign in.
- **App `/orgs/*`:** Shell (org context + sidebar nav) → page workspace → optional secondary panel (e.g. raw JSON for analyze/federation).
- **Auth:** Title, short orientation line, form, inline errors — no marketing paragraphs.

## Interaction plan

1. Sidebar nav: hover tint + 2px accent rail on active item (~180ms ease-out).
2. Marketing hero: title and subtitle use subtle staggered opacity on load; `@media (prefers-reduced-motion: reduce)` disables stagger.
3. Analyze / federation result panels: expand/collapse for raw JSON with height transition (~200ms).

## Post-build litmus (check before merge)

- [ ] depOS recognizable on first screen; one visual anchor (mark + hero composition).
- [ ] Headings-only scan explains each `/orgs/...` page.
- [ ] Cards only on interactive zones (upload, wizard steps), not wrapping every section.
- [ ] Focus visible on buttons, links, inputs, switches.
- [ ] Copy is product/operator tone, not prompt-y.

## Visual verification

Run once in browser: `/`, `/orgs/{slug}`, `/orgs/{slug}/analyze` after a successful analyze — or note manual verification in PR if no browser automation.
