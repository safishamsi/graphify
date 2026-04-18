"""Acceptance test #2 \u2014 the shipped supabase migrations are parsed and
``organization_members`` is classified as RLS full (enabled + policies).

We scan the *real* ``supabase/migrations/*.sql`` files that landed in
PR 0a, not a throwaway fixture. This test doubles as protection against
accidental regressions in those migrations (e.g. dropping RLS policies
or forgetting to enable RLS).
"""
from __future__ import annotations

from pathlib import Path

import pytest

from depos.analysis.schemas import RLSCoverage
from depos.enrichment.rls_resolver import build_table_model, classify

MIGRATION_GLOB = "supabase/migrations/*.sql"


@pytest.fixture(scope="module")
def migrations() -> list[Path]:
    files = sorted(Path().glob(MIGRATION_GLOB))
    if not files:
        pytest.skip("no supabase/migrations/*.sql found")
    return files


def test_organization_members_is_rls_full(migrations: list[Path]) -> None:
    tables = build_table_model(migrations)
    org_members = tables.get("organization_members")
    assert org_members is not None, "organization_members table was not parsed"
    assert org_members.enabled, "RLS should be ENABLE'd on organization_members"
    assert org_members.policy_count >= 1, (
        f"expected at least one CREATE POLICY on organization_members, saw {org_members.policy_count}"
    )
    assert classify(org_members) == RLSCoverage.full


def test_profiles_is_rls_full(migrations: list[Path]) -> None:
    tables = build_table_model(migrations)
    profiles = tables.get("profiles")
    assert profiles is not None, "profiles table was not parsed"
    assert classify(profiles) == RLSCoverage.full
