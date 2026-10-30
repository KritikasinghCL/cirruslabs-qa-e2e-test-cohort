"""
Automated QA tests for veg_biryani_recipe.txt.

Acceptance criteria verified:
  AC1  File exists at the repo root
  AC2  File is non-empty
  AC3  File is plain text (UTF-8 decodable, no binary content)
  AC4  File contains an INGREDIENTS section
  AC5  File contains a METHOD / STEPS section
  AC6  File includes prep time information
  AC7  File includes cook time information
  AC8  File includes serving / serves information
  AC9  Ingredients section lists actual ingredient entries (bullet lines)
  AC10 Method section contains numbered/labelled steps
"""

import pathlib
import re

import pytest

# ---------------------------------------------------------------------------
# Locate the recipe file relative to this test file (repo root)
# ---------------------------------------------------------------------------
REPO_ROOT = pathlib.Path(__file__).parent.parent
RECIPE_PATH = REPO_ROOT / "veg_biryani_recipe.txt"


@pytest.fixture(scope="module")
def recipe_text():
    """Return the full text of the recipe file."""
    return RECIPE_PATH.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# AC1 — File exists
# ---------------------------------------------------------------------------
class TestFileExists:
    def test_recipe_file_exists(self):
        """AC1: veg_biryani_recipe.txt must exist at the repo root."""
        assert RECIPE_PATH.exists(), (
            f"Expected {RECIPE_PATH} to exist but it was not found."
        )

    def test_recipe_file_is_a_regular_file(self):
        """AC1b: Path must be a regular file, not a directory or symlink."""
        assert RECIPE_PATH.is_file(), (
            f"{RECIPE_PATH} exists but is not a regular file."
        )


# ---------------------------------------------------------------------------
# AC2 — Non-empty
# ---------------------------------------------------------------------------
class TestNonEmpty:
    def test_file_is_non_empty(self, recipe_text):
        """AC2: File must contain at least one non-whitespace character."""
        assert recipe_text.strip(), "veg_biryani_recipe.txt is empty."

    def test_file_has_meaningful_length(self, recipe_text):
        """AC2b: File should be at least 200 characters (a real recipe)."""
        assert len(recipe_text) >= 200, (
            f"File is suspiciously short ({len(recipe_text)} chars); "
            "expected a complete recipe."
        )


# ---------------------------------------------------------------------------
# AC3 — Plain text (UTF-8, no binary/null bytes)
# ---------------------------------------------------------------------------
class TestPlainText:
    def test_file_is_utf8_decodable(self):
        """AC3: File must be decodable as UTF-8."""
        try:
            RECIPE_PATH.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            pytest.fail(f"File is not valid UTF-8: {exc}")

    def test_file_has_no_null_bytes(self):
        """AC3b: Plain-text files must not contain null bytes."""
        raw = RECIPE_PATH.read_bytes()
        assert b"\x00" not in raw, (
            "File contains null bytes — it may be binary, not plain text."
        )

    def test_file_extension_is_txt(self):
        """AC3c: File name must end with .txt."""
        assert RECIPE_PATH.suffix.lower() == ".txt", (
            f"Expected .txt extension, got '{RECIPE_PATH.suffix}'."
        )


# ---------------------------------------------------------------------------
# AC4 — Contains INGREDIENTS section
# ---------------------------------------------------------------------------
class TestIngredientsSection:
    def test_ingredients_heading_present(self, recipe_text):
        """AC4: File must contain an 'INGREDIENTS' heading (case-insensitive)."""
        assert re.search(r"ingredients", recipe_text, re.IGNORECASE), (
            "No 'INGREDIENTS' section found in the recipe."
        )

    def test_ingredients_section_has_entries(self, recipe_text):
        """AC9: Ingredients section must list actual ingredient items."""
        pattern = re.compile(
            r"ingredients.*?(?=method|steps|preparation|$)",
            re.IGNORECASE | re.DOTALL,
        )
        match = pattern.search(recipe_text)
        assert match, "Could not locate the INGREDIENTS section body."
        section = match.group(0)
        ingredient_lines = [
            line for line in section.splitlines()
            if re.search(
                r"[•\-\*]|\d+\s*(cup|tbsp|tsp|g|kg|ml|litre|pinch|medium|large|small)",
                line, re.IGNORECASE
            )
        ]
        assert len(ingredient_lines) >= 5, (
            f"Expected at least 5 ingredient entries, found {len(ingredient_lines)}."
        )


# ---------------------------------------------------------------------------
# AC5 — Contains METHOD / STEPS section
# ---------------------------------------------------------------------------
class TestMethodSection:
    def test_method_heading_present(self, recipe_text):
        """AC5: File must contain a 'METHOD' or 'STEPS' heading (case-insensitive)."""
        assert re.search(
            r"\b(method|steps?|instructions?|directions?)\b",
            recipe_text, re.IGNORECASE
        ), "No 'METHOD' or 'STEPS' section found in the recipe."

    def test_method_section_has_steps(self, recipe_text):
        """AC10: Method section must contain numbered or labelled steps."""
        pattern = re.compile(
            r"(?:method|steps?|instructions?|directions?).*",
            re.IGNORECASE | re.DOTALL,
        )
        match = pattern.search(recipe_text)
        assert match, "Could not locate the METHOD section body."
        section = match.group(0)
        step_lines = [
            line for line in section.splitlines()
            if re.search(r"(step\s*\d+|\d+[\.\)])", line, re.IGNORECASE)
        ]
        assert len(step_lines) >= 3, (
            f"Expected at least 3 method steps, found {len(step_lines)}."
        )


# ---------------------------------------------------------------------------
# AC6 — Prep time
# ---------------------------------------------------------------------------
class TestPrepTime:
    def test_prep_time_present(self, recipe_text):
        """AC6: File must mention prep time."""
        assert re.search(r"prep\s*(time)?", recipe_text, re.IGNORECASE), (
            "No prep time information found in the recipe."
        )


# ---------------------------------------------------------------------------
# AC7 — Cook time
# ---------------------------------------------------------------------------
class TestCookTime:
    def test_cook_time_present(self, recipe_text):
        """AC7: File must mention cook time."""
        assert re.search(r"cook\s*(time)?", recipe_text, re.IGNORECASE), (
            "No cook time information found in the recipe."
        )


# ---------------------------------------------------------------------------
# AC8 — Serving size
# ---------------------------------------------------------------------------
class TestServingSize:
    def test_serving_size_present(self, recipe_text):
        """AC8: File must mention serving size."""
        assert re.search(r"\b(serves?|servings?|yield)\b", recipe_text, re.IGNORECASE), (
            "No serving size information found in the recipe."
        )
