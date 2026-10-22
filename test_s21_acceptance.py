"""
S-21 Acceptance Criteria Tests
================================
Verifies that the GitHub connectivity test artefact meets every acceptance criterion:

AC1 - A new branch named feature/s-21-push-a-fresh-test-commit-to-github-and-c exists
AC2 - The branch contains a clearly-labelled test file (github_connectivity_test.md)
AC3 - The file content is non-empty and references the ticket S-21
AC4 - The commit SHA on the branch matches the expected value
AC5 - A PR is open against main (verified via PR metadata embedded in the file)
AC6 - The file correctly identifies the branch name it lives on
"""

import os
import pathlib
import re
import subprocess

import pytest

REPO_DIR = pathlib.Path(__file__).parent
EXPECTED_BRANCH = "feature/s-21-push-a-fresh-test-commit-to-github-and-c"
EXPECTED_COMMIT_SHA = "66217878b8ec834b45effdc2482a2cd61b3af5ee"
TEST_FILE = REPO_DIR / "github_connectivity_test.md"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def git(*args):
    result = subprocess.run(
        ["git", *args],
        cwd=REPO_DIR,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip(), result.returncode


# ---------------------------------------------------------------------------
# AC1 — branch exists and is currently checked out
# ---------------------------------------------------------------------------

def test_ac1_branch_exists():
    """The feature branch must exist in the local checkout."""
    branch, rc = git("rev-parse", "--abbrev-ref", "HEAD")
    assert rc == 0, "git rev-parse failed"
    assert branch == EXPECTED_BRANCH, (
        f"Expected branch '{EXPECTED_BRANCH}', got '{branch}'"
    )


# ---------------------------------------------------------------------------
# AC2 — test file is present and clearly labelled
# ---------------------------------------------------------------------------

def test_ac2_test_file_exists():
    """github_connectivity_test.md must exist in the repo root."""
    assert TEST_FILE.exists(), f"Test file not found: {TEST_FILE}"


def test_ac2_test_file_is_markdown():
    """The file must be a Markdown file (.md extension)."""
    assert TEST_FILE.suffix == ".md", "Test file must have .md extension"


# ---------------------------------------------------------------------------
# AC3 — file content is non-empty and references S-21
# ---------------------------------------------------------------------------

def test_ac3_file_content_nonempty():
    """The test file must not be empty."""
    content = TEST_FILE.read_text(encoding="utf-8")
    assert len(content.strip()) > 0, "Test file is empty"


def test_ac3_file_references_ticket():
    """The file must reference ticket S-21."""
    content = TEST_FILE.read_text(encoding="utf-8")
    assert "S-21" in content, "Test file does not reference ticket S-21"


def test_ac3_file_has_purpose_section():
    """The file must contain a Purpose section explaining the probe."""
    content = TEST_FILE.read_text(encoding="utf-8")
    assert "Purpose" in content, "Test file missing 'Purpose' section"


# ---------------------------------------------------------------------------
# AC4 — commit SHA matches the expected value
# ---------------------------------------------------------------------------

def test_ac4_commit_sha_matches():
    """HEAD commit SHA must match the expected value from the work trail."""
    sha, rc = git("rev-parse", "HEAD")
    assert rc == 0, "git rev-parse HEAD failed"
    assert sha == EXPECTED_COMMIT_SHA, (
        f"Commit SHA mismatch: expected {EXPECTED_COMMIT_SHA}, got {sha}"
    )


def test_ac4_commit_message_references_s21():
    """The commit message must reference S-21."""
    msg, rc = git("log", "-1", "--pretty=%s")
    assert rc == 0, "git log failed"
    assert "S-21" in msg, f"Commit message does not reference S-21: '{msg}'"


# ---------------------------------------------------------------------------
# AC5 — PR metadata embedded in file references main as base
# ---------------------------------------------------------------------------

def test_ac5_file_references_pr_against_main():
    """The file content must confirm the PR targets main."""
    content = TEST_FILE.read_text(encoding="utf-8")
    # The file mentions 'main' as the target branch
    assert "main" in content, "Test file does not mention 'main' as PR target"


# ---------------------------------------------------------------------------
# AC6 — file correctly identifies its own branch
# ---------------------------------------------------------------------------

def test_ac6_file_identifies_branch():
    """The file must contain the correct branch name."""
    content = TEST_FILE.read_text(encoding="utf-8")
    assert EXPECTED_BRANCH in content, (
        f"Test file does not contain the expected branch name '{EXPECTED_BRANCH}'"
    )


# ---------------------------------------------------------------------------
# AC7 — file was added (not modified) — confirms it is a fresh commit
# ---------------------------------------------------------------------------

def test_ac7_file_is_new_addition():
    """The file must have been introduced by the S-21 commit (not pre-existing).

    We verify this by checking that the commit which first added the file
    is the expected S-21 commit SHA.  The file may already be on main if the
    PR was merged — that is a success state, not a failure.
    """
    # Find the commit that first added the file
    out, rc = git("log", "--diff-filter=A", "--pretty=%H", "--", "github_connectivity_test.md")
    assert rc == 0, "git log failed"
    introducing_commits = [c for c in out.splitlines() if c.strip()]
    assert len(introducing_commits) >= 1, "No commit found that added github_connectivity_test.md"
    # The introducing commit must be the S-21 commit
    assert EXPECTED_COMMIT_SHA in introducing_commits, (
        f"github_connectivity_test.md was not introduced by the expected S-21 commit "
        f"({EXPECTED_COMMIT_SHA}). Found: {introducing_commits}"
    )
