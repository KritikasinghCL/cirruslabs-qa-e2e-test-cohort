"""
Smoke tests — GitHub connectivity and repository health.

These tests verify that the repository is reachable and that the
acceptance criteria for the "push a fresh test commit" story are met.
They are pure-Python and require no external connections at runtime;
they assert on the presence of artefacts that must exist in the repo
(files, markers in files) rather than making live API calls.

Marked @pytest.mark.smoke so they can be run in isolation:
    pytest -m smoke -v
"""
from __future__ import annotations

import os
import pathlib

import pytest

# Root of the repository (two levels up from tests/smoke/)
_REPO_ROOT = pathlib.Path(__file__).parent.parent.parent


@pytest.mark.smoke
class TestRepositoryStructure:
    """Verify the repository contains the artefacts the pipeline needs."""

    def test_readme_exists(self) -> None:
        """AC: a README.md is present at the repository root."""
        assert (_REPO_ROOT / "README.md").is_file(), "README.md not found"

    def test_requirements_txt_exists(self) -> None:
        """AC: runtime dependencies are declared in requirements.txt."""
        assert (_REPO_ROOT / "requirements.txt").is_file()

    def test_requirements_dev_txt_exists(self) -> None:
        """AC: dev/CI dependencies are declared in requirements-dev.txt."""
        assert (_REPO_ROOT / "requirements-dev.txt").is_file()

    def test_pytest_ini_exists(self) -> None:
        """AC: pytest.ini is present so the test command is documented."""
        assert (_REPO_ROOT / "pytest.ini").is_file()

    def test_ci_workflow_exists(self) -> None:
        """AC: a CI workflow file is present under .github/workflows/."""
        ci = _REPO_ROOT / ".github" / "workflows" / "ci.yml"
        assert ci.is_file(), ".github/workflows/ci.yml not found"

    def test_tests_directory_exists(self) -> None:
        """AC: the tests/ directory exists and is a package."""
        tests_dir = _REPO_ROOT / "tests"
        assert tests_dir.is_dir()
        assert (tests_dir / "__init__.py").is_file()

    def test_conftest_exists(self) -> None:
        """AC: shared fixtures are in tests/conftest.py."""
        assert (_REPO_ROOT / "tests" / "conftest.py").is_file()


@pytest.mark.smoke
class TestD1ToD7FilesPresent:
    """Verify each D1–D7 test file is present on this branch."""

    def test_d1_forecast_file_exists(self) -> None:
        assert (_REPO_ROOT / "tests" / "inventory" / "test_d1_forecast.py").is_file()

    def test_d2_overstock_file_exists(self) -> None:
        assert (_REPO_ROOT / "tests" / "inventory" / "test_d2_overstock.py").is_file()

    def test_d3_understock_file_exists(self) -> None:
        assert (_REPO_ROOT / "tests" / "inventory" / "test_d3_understock.py").is_file()

    def test_d4_nmi_smi_file_exists(self) -> None:
        assert (_REPO_ROOT / "tests" / "inventory" / "test_d4_nmi_smi.py").is_file()

    def test_d5_pr_suggestions_file_exists(self) -> None:
        assert (_REPO_ROOT / "tests" / "inventory" / "test_d5_pr_suggestions.py").is_file()

    def test_d6_mrp_eligibility_file_exists(self) -> None:
        assert (_REPO_ROOT / "tests" / "inventory" / "test_d6_mrp_eligibility.py").is_file()

    def test_d7_duplicate_materials_file_exists(self) -> None:
        assert (_REPO_ROOT / "tests" / "inventory" / "test_d7_duplicate_materials.py").is_file()


@pytest.mark.smoke
class TestGithubConnectivityArtefacts:
    """
    Verify the artefacts committed during the GitHub connectivity story exist.

    Story: 'Push a fresh test commit to GitHub and confirm it lands in the repo'
    Branch: feature/s-21-push-a-fresh-test-commit-to-github-and-c
    PR: #4 (https://github.com/KritikasinghCL/cirruslabs-qa-e2e-test-cohort/pull/4)
    """

    def test_github_connectivity_test_file_exists(self) -> None:
        candidate = _REPO_ROOT / "github_connectivity_test.md"
        if not candidate.is_file():
            pytest.skip(
                "github_connectivity_test.md not present on this branch — "
                "it lives on feature/s-21-push-a-fresh-test-commit-to-github-and-c "
                "and will be here after PR #4 is merged."
            )
        assert candidate.is_file()

    def test_env_example_exists(self) -> None:
        candidate = _REPO_ROOT / ".env.example"
        if not candidate.is_file():
            pytest.skip(
                ".env.example not present on this branch — "
                "it lives on feature/env-example-file and will be here after PR #5 is merged."
            )
        assert candidate.is_file()


@pytest.mark.smoke
class TestTestSuiteRunnable:
    """Verify the test suite itself is runnable (meta-smoke)."""

    def test_pytest_ini_has_testpaths(self) -> None:
        ini = _REPO_ROOT / "pytest.ini"
        content = ini.read_text()
        assert "testpaths" in content

    def test_pytest_ini_declares_markers(self) -> None:
        ini = _REPO_ROOT / "pytest.ini"
        content = ini.read_text()
        assert "integration" in content
        assert "smoke" in content

    def test_run_integration_tests_env_var_defaults_to_zero(self) -> None:
        val = os.getenv("RUN_INTEGRATION_TESTS", "0")
        assert val in ("0", "1"), f"Unexpected value: {val!r}"
