"""Tests for graphify/prs.py."""
from __future__ import annotations

import subprocess
from datetime import datetime, timedelta, timezone
from unittest.mock import patch, MagicMock

import networkx as nx
import pytest

from graphify.prs import (
    PRInfo,
    _classify,
    _parse_ci,
    _path_match,
    build_community_labels,
    compute_pr_impact,
    fetch_worktrees,
    format_prs_text,
    _detect_default_branch,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def make_pr(
    number: int = 1,
    title: str = "Test PR",
    branch: str = "feature",
    base_branch: str = "v8",
    author: str = "alice",
    is_draft: bool = False,
    review_decision: str = "",
    ci_status: str = "SUCCESS",
    updated_at: datetime | None = None,
    expected_base: str = "v8",
) -> PRInfo:
    """Build a minimal PRInfo with sensible defaults."""
    if updated_at is None:
        updated_at = datetime.now(timezone.utc) - timedelta(days=1)
    return PRInfo(
        number=number,
        title=title,
        branch=branch,
        base_branch=base_branch,
        author=author,
        is_draft=is_draft,
        review_decision=review_decision,
        ci_status=ci_status,
        updated_at=updated_at,
        expected_base=expected_base,
    )


# ── _classify ─────────────────────────────────────────────────────────────────

class TestClassify:
    def test_ready(self):
        pr = make_pr(ci_status="SUCCESS", review_decision="", is_draft=False)
        assert _classify(pr, base="v8") == "READY"

    def test_ci_fail(self):
        pr = make_pr(ci_status="FAILURE")
        assert _classify(pr, base="v8") == "CI-FAIL"

    def test_changes_req(self):
        pr = make_pr(ci_status="SUCCESS", review_decision="CHANGES_REQUESTED")
        assert _classify(pr, base="v8") == "CHANGES-REQ"

    def test_draft(self):
        pr = make_pr(ci_status="SUCCESS", is_draft=True)
        assert _classify(pr, base="v8") == "DRAFT"

    def test_stale(self):
        old = datetime.now(timezone.utc) - timedelta(days=20)
        pr = make_pr(ci_status="SUCCESS", updated_at=old, is_draft=False)
        assert _classify(pr, base="v8") == "STALE"

    def test_draft_not_marked_stale(self):
        # Drafts show as DRAFT even when old — stale-detection only applies to non-drafts
        old = datetime.now(timezone.utc) - timedelta(days=20)
        pr = make_pr(ci_status="SUCCESS", updated_at=old, is_draft=True)
        assert _classify(pr, base="v8") == "DRAFT"

    def test_pending(self):
        pr = make_pr(ci_status="PENDING", is_draft=False, review_decision="")
        assert _classify(pr, base="v8") == "PENDING"

    def test_wrong_base(self):
        # WRONG-BASE takes precedence over everything else
        pr = make_pr(base_branch="master", ci_status="FAILURE")
        assert _classify(pr, base="v8") == "WRONG-BASE"


# ── _parse_ci ─────────────────────────────────────────────────────────────────

class TestParseCi:
    def test_empty_rollup_returns_none(self):
        assert _parse_ci([]) == "NONE"

    def test_failure_conclusion(self):
        rollup = [{"conclusion": "FAILURE", "status": "COMPLETED"}]
        assert _parse_ci(rollup) == "FAILURE"

    def test_cancelled_is_failure(self):
        rollup = [{"conclusion": "CANCELLED", "status": "COMPLETED"}]
        assert _parse_ci(rollup) == "FAILURE"

    def test_timed_out_is_failure(self):
        rollup = [{"conclusion": "TIMED_OUT", "status": "COMPLETED"}]
        assert _parse_ci(rollup) == "FAILURE"

    def test_in_progress_is_pending(self):
        rollup = [{"conclusion": None, "status": "IN_PROGRESS"}]
        assert _parse_ci(rollup) == "PENDING"

    def test_success(self):
        rollup = [{"conclusion": "SUCCESS", "status": "COMPLETED"}]
        assert _parse_ci(rollup) == "SUCCESS"

    def test_mixed_success_and_failure_is_failure(self):
        rollup = [
            {"conclusion": "SUCCESS", "status": "COMPLETED"},
            {"conclusion": "FAILURE", "status": "COMPLETED"},
        ]
        assert _parse_ci(rollup) == "FAILURE"


# ── _path_match ───────────────────────────────────────────────────────────────

class TestPathMatch:
    def test_exact_match(self):
        assert _path_match("src/auth/api.py", "src/auth/api.py") is True

    def test_graph_path_longer_with_boundary(self):
        # graph_src is longer, ends with "/" + pr_file
        assert _path_match("src/auth/api.py", "api.py") is True

    def test_no_false_positive_on_partial_filename(self):
        # "config.py" should NOT match "g.py" — must be at path boundary
        assert _path_match("config.py", "g.py") is False
        assert _path_match("g.py", "config.py") is False

    def test_both_directions_work(self):
        # pr_file longer than graph_src
        assert _path_match("api.py", "src/auth/api.py") is True
        # graph_src longer than pr_file
        assert _path_match("src/auth/api.py", "api.py") is True


# ── compute_pr_impact ─────────────────────────────────────────────────────────

class TestComputePrImpact:
    def _make_graph(self) -> nx.Graph:
        """3 nodes across 2 communities, 2 distinct source files."""
        G = nx.Graph()
        G.add_node("n1", source_file="src/auth/api.py", community=0)
        G.add_node("n2", source_file="src/auth/api.py", community=0)
        G.add_node("n3", source_file="src/utils/helpers.py", community=1)
        return G

    def test_matching_files_returns_correct_communities_and_count(self):
        G = self._make_graph()
        comms, nodes = compute_pr_impact(["src/auth/api.py"], G)
        assert comms == [0]
        assert nodes == 2

    def test_matching_both_files(self):
        G = self._make_graph()
        comms, nodes = compute_pr_impact(
            ["src/auth/api.py", "src/utils/helpers.py"], G
        )
        assert comms == [0, 1]
        assert nodes == 3

    def test_empty_files_returns_empty(self):
        G = self._make_graph()
        comms, nodes = compute_pr_impact([], G)
        assert comms == []
        assert nodes == 0

    def test_no_matching_files_returns_empty(self):
        G = self._make_graph()
        comms, nodes = compute_pr_impact(["docs/README.md"], G)
        assert comms == []
        assert nodes == 0

    def test_no_double_counting_when_basename_matches_multiple_paths(self):
        # "api.py" should NOT match both src/auth/api.py AND src/admin/api.py
        G = nx.Graph()
        G.add_node("a1", source_file="src/auth/api.py", community=0)
        G.add_node("a2", source_file="src/admin/api.py", community=1)
        comms, nodes = compute_pr_impact(["src/auth/api.py"], G)
        # Only src/auth/api.py matches by exact path — not src/admin/api.py
        assert nodes == 1
        assert comms == [0]

    def test_no_double_counting_same_graph_file_matched_by_two_pr_files(self):
        # If PR diff lists both "api.py" and "src/auth/api.py", the graph node
        # for src/auth/api.py should only be counted once
        G = nx.Graph()
        G.add_node("n1", source_file="src/auth/api.py", community=0)
        G.add_node("n2", source_file="src/auth/api.py", community=0)
        comms, nodes = compute_pr_impact(["src/auth/api.py", "api.py"], G)
        assert nodes == 2  # 2 nodes in that file, counted once
        assert comms == [0]


# ── fetch_worktrees ───────────────────────────────────────────────────────────

class TestFetchWorktrees:
    def test_normal_case_maps_branch_to_path(self):
        porcelain = (
            "worktree /home/user/proj\n"
            "HEAD abc123\n"
            "branch refs/heads/main\n"
            "\n"
            "worktree /home/user/proj-feature\n"
            "HEAD def456\n"
            "branch refs/heads/feature-x\n"
            "\n"
        )
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = porcelain
        with patch("graphify.prs.subprocess.run", return_value=mock_result):
            mapping = fetch_worktrees()
        assert mapping == {
            "main": "/home/user/proj",
            "feature-x": "/home/user/proj-feature",
        }

    def test_detached_head_does_not_leak_into_next_record(self):
        """A detached HEAD (no branch line) must not associate its path with the
        next record's branch — the blank line separator resets state."""
        porcelain = (
            "worktree /home/user/detached\n"
            "HEAD abc123\n"
            "detached\n"
            "\n"
            "worktree /home/user/proj-feature\n"
            "HEAD def456\n"
            "branch refs/heads/feature-x\n"
            "\n"
        )
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = porcelain
        with patch("graphify.prs.subprocess.run", return_value=mock_result):
            mapping = fetch_worktrees()
        # Only feature-x should be mapped, and it should point to its own worktree
        assert mapping == {"feature-x": "/home/user/proj-feature"}
        assert "/home/user/detached" not in mapping.values()

    def test_empty_output_returns_empty_dict(self):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = ""
        with patch("graphify.prs.subprocess.run", return_value=mock_result):
            mapping = fetch_worktrees()
        assert mapping == {}

    def test_nonzero_returncode_returns_empty_dict(self):
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        with patch("graphify.prs.subprocess.run", return_value=mock_result):
            mapping = fetch_worktrees()
        assert mapping == {}

    def test_subprocess_failure_returns_empty_dict(self):
        with patch(
            "graphify.prs.subprocess.run",
            side_effect=FileNotFoundError("git not found"),
        ):
            mapping = fetch_worktrees()
        assert mapping == {}


# ── format_prs_text ───────────────────────────────────────────────────────────

class TestFormatPrsText:
    def test_contains_pr_metadata_and_count_header(self):
        prs = [
            make_pr(
                number=101,
                title="Add awesome feature",
                base_branch="v8",
                expected_base="v8",
                ci_status="SUCCESS",
            ),
            make_pr(
                number=102,
                title="Fix flaky test",
                base_branch="v8",
                expected_base="v8",
                ci_status="FAILURE",
            ),
            make_pr(
                number=103,
                title="Wrong base PR",
                base_branch="master",
                expected_base="v8",
            ),
        ]
        out = format_prs_text(prs, base="v8")

        # Count header: 2 actionable, 1 on wrong base
        assert "Open PRs targeting v8: 2" in out
        assert "(1 on wrong base, not shown)" in out

        # PR numbers and titles included
        assert "#101" in out
        assert "Add awesome feature" in out
        assert "#102" in out
        assert "Fix flaky test" in out

        # Statuses included
        assert "[READY]" in out
        assert "[CI-FAIL]" in out

        # Wrong-base PR should be filtered out of body
        assert "#103" not in out

    def test_empty_pr_list(self):
        out = format_prs_text([], base="v8")
        assert "Open PRs targeting v8: 0" in out
        assert "(0 on wrong base, not shown)" in out


# ── _detect_default_branch ────────────────────────────────────────────────────

class TestDetectDefaultBranch:
    def test_gh_returns_main(self):
        with patch(
            "graphify.prs._gh",
            return_value={"defaultBranchRef": {"name": "main"}},
        ):
            assert _detect_default_branch() == "main"

    def test_falls_back_to_git_symbolic_ref(self):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "refs/remotes/origin/develop\n"
        with patch("graphify.prs._gh", return_value=None), patch(
            "graphify.prs.subprocess.run", return_value=mock_result
        ):
            assert _detect_default_branch() == "develop"

    def test_both_fail_returns_main(self):
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        with patch("graphify.prs._gh", return_value=None), patch(
            "graphify.prs.subprocess.run", return_value=mock_result
        ):
            assert _detect_default_branch() == "main"

    def test_gh_returns_empty_dict_falls_back(self):
        """gh returns data but with no defaultBranchRef — should still fall back."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "refs/remotes/origin/trunk\n"
        with patch("graphify.prs._gh", return_value={}), patch(
            "graphify.prs.subprocess.run", return_value=mock_result
        ):
            assert _detect_default_branch() == "trunk"

    def test_git_timeout_returns_main(self):
        with patch("graphify.prs._gh", return_value=None), patch(
            "graphify.prs.subprocess.run",
            side_effect=subprocess.TimeoutExpired("git", 5),
        ):
            assert _detect_default_branch() == "main"


# ── build_community_labels ─────────────────────────────────────────────────────

class TestBuildCommunityLabels:
    def test_basic_grouping(self):
        data = {
            "nodes": [
                {"id": "a", "label": "Alpha", "community": 0},
                {"id": "b", "label": "Beta",  "community": 0},
                {"id": "c", "label": "Gamma", "community": 1},
            ]
        }
        labels = build_community_labels(data)
        assert set(labels[0]) == {"Alpha", "Beta"}
        assert labels[1] == ["Gamma"]

    def test_top_n_capped(self):
        nodes = [{"id": str(i), "label": f"Node{i}", "community": 0} for i in range(10)]
        labels = build_community_labels({"nodes": nodes}, top_n=4)
        assert len(labels[0]) == 4

    def test_no_community_field_skipped(self):
        data = {"nodes": [{"id": "x", "label": "X"}]}
        assert build_community_labels(data) == {}

    def test_empty_nodes(self):
        assert build_community_labels({}) == {}
        assert build_community_labels({"nodes": []}) == {}
