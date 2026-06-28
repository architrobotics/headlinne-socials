"""Minimal zero-dependency test runner.

Lets you run the suite without installing pytest:

    python -m tests

It discovers every test_*.py module in this package, runs each top-level
function named test_*, and prints a summary. Exit code is non-zero if any test
fails, so it works in CI too. (pytest also works if you prefer it.)
"""

from __future__ import annotations

import importlib
import pkgutil
import sys
import traceback
from types import FunctionType

import tests as tests_pkg


def _discover():
    """Yield (module_name, func_name, func) for every test_* function."""
    for mod_info in pkgutil.iter_modules(tests_pkg.__path__):
        name = mod_info.name
        if not name.startswith("test_"):
            continue
        module = importlib.import_module(f"tests.{name}")
        for attr in sorted(vars(module)):
            obj = getattr(module, attr)
            if isinstance(obj, FunctionType) and attr.startswith("test_"):
                yield name, attr, obj


def main() -> int:
    passed = 0
    failures: list[tuple[str, str, str]] = []

    for mod_name, func_name, func in _discover():
        label = f"{mod_name}.{func_name}"
        try:
            func()
        except Exception:  # noqa: BLE001 - we want to report everything
            tb = traceback.format_exc()
            failures.append((mod_name, func_name, tb))
            print(f"FAIL  {label}")
        else:
            passed += 1
            print(f"ok    {label}")

    total = passed + len(failures)
    print("\n" + "-" * 60)
    print(f"{passed}/{total} passed")

    if failures:
        print("\n===== FAILURES =====")
        for mod_name, func_name, tb in failures:
            print(f"\n--- {mod_name}.{func_name} ---")
            print(tb)
        return 1
    print("All tests passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
