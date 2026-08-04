"""Fuzz tests for slugify() — random unicode/CJK/edge inputs must not crash.

Goal: ensure the slugify fallback path (hash) handles anything Python's str
can represent without raising. We don't assert exact output, only that:
- The result is filesystem-safe (no path separators, no leading dash).
- The result is non-empty.
- Two identical inputs produce identical outputs.
"""

from __future__ import annotations

import random
import string
import sys
import unittest
from pathlib import Path

# Make the script importable as a module
SCRIPT = Path(__file__).resolve().parent.parent / ".trellis-lite/scripts/trellis.py"
sys.path.insert(0, str(SCRIPT.parent))
# Load as a module to call slugify directly
import importlib.util  # noqa: E402

_spec = importlib.util.spec_from_file_location("trellis_script", SCRIPT)
_trellis = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_trellis)
slugify = _trellis.slugify


# A pool of adversarial unicode characters — covers common edge cases
# found in real titles, especially in multilingual teams.
_UNICODE_POOL = (
    "用户登录"        # Chinese
    "ユーザー認証"   # Japanese
    "Войти"          # Cyrillic
    "🔐login"        # Emoji
    "café"           # Latin-1 supplement
    "αβγδ"           # Greek
    "नमस्ते"          # Devanagari
    "  leading"      # leading whitespace
    "trailing  "     # trailing whitespace
    "  both  "       # both
    "UPPER lower"
    "with---many----dashes"
    "with___underscores"
    "with/slashes\\and\\backslashes"
    "with.dot.s"
    "...punctuation!?"
    "123 numbers"
    "——unicode——dashes——"
    "Mixed 用户 and ascii"
    "a"               # single char
    ""                # empty (special case)
    "      "          # all whitespace
    "!@#$%^&*()"      # symbols only
    "🚀🎉"            # emoji-only
)


class TestSlugify(unittest.TestCase):
    def test_known_examples(self) -> None:
        """Smoke checks against documented behavior."""
        self.assertEqual(slugify("Hello World"), "hello-world")
        self.assertEqual(slugify("Hello---World"), "hello-world")
        self.assertEqual(slugify("  hello  "), "hello")
        # Non-ASCII falls back to hash prefix
        result = slugify("用户登录")
        self.assertTrue(result.startswith("t-"))
        self.assertGreater(len(result), 2)

    def test_result_always_filesystem_safe(self) -> None:
        """Output must contain only [a-z0-9-] and not start/end with dash."""
        for raw in _UNICODE_POOL:
            result = slugify(raw)
            # Empty input still produces a hash-based fallback
            self.assertTrue(result, f"empty result for {raw!r}")
            # Only lowercase alnum and dash
            for ch in result:
                self.assertTrue(
                    ch.isascii() and (ch.isalnum() or ch == "-"),
                    f"unsafe char {ch!r} in slug {result!r} from {raw!r}",
                )
            # No leading/trailing dash
            self.assertFalse(result.startswith("-"), f"leading dash for {raw!r}")
            self.assertFalse(result.endswith("-"), f"trailing dash for {raw!r}")
            # No consecutive dashes (visual noise)
            self.assertNotIn("--", result, f"double dash for {raw!r}")

    def test_determinism(self) -> None:
        """Same input → same output (hashing must be stable)."""
        for raw in _UNICODE_POOL:
            a = slugify(raw)
            b = slugify(raw)
            self.assertEqual(a, b, f"non-deterministic for {raw!r}")

    def test_empty_input_handled(self) -> None:
        """Empty and whitespace-only inputs must return a fallback, not crash."""
        for raw in ("", " ", "  ", "\t", "\n", " \t\n "):
            result = slugify(raw)
            self.assertTrue(result, f"empty result for {raw!r}")
            # Pure whitespace → falls back to hash
            self.assertTrue(result.startswith("t-"))

    def test_random_fuzz(self) -> None:
        """1000 random unicode strings must not crash and must produce valid slugs."""
        rng = random.Random(42)  # deterministic
        chars = string.ascii_letters + string.digits + "".join(_UNICODE_POOL)
        for _ in range(1000):
            length = rng.randint(1, 30)
            raw = "".join(rng.choice(chars) for _ in range(length))
            try:
                result = slugify(raw)
            except Exception as e:
                self.fail(f"slugify crashed on {raw!r}: {e}")
            self.assertTrue(result, f"empty result for {raw!r}")
            # Idempotence
            self.assertEqual(slugify(result), result,
                             f"not idempotent: {raw!r} → {result!r}")

    def test_no_path_traversal(self) -> None:
        """Slugify must never produce a string usable for path traversal."""
        for raw in ("..", "../etc", "..\\windows", "/etc/passwd",
                    "../../../root", "....//etc"):
            result = slugify(raw)
            self.assertNotIn("..", result)
            self.assertNotIn("/", result)
            self.assertNotIn("\\", result)


if __name__ == "__main__":
    unittest.main()