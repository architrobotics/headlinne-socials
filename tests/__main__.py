"""Minimal zero-dependency test runner.

Lets you run the suite without installing pytest:

    python -m tests

It discovers every test_*.py module in this package, runs each top-level
function named test_*, and prints a summary. Exit code is non-zero if any test
fails, so it works in CI too. (pytest also works if you prefer it.)
"""

from __future__ import annotations

import importlib
import inspect
import pkgutil
import shutil
import sys
import tempfile
import traceback
from pathlib import Path
from types import FunctionType

import tests as tests_pkg

# The one pytest fixture this runner knows how to supply. Tests that write files
# need a scratch directory, and without this they raise TypeError here while
# passing under pytest - which is exactly the kind of split where the zero
# dependency runner quietly stops being the thing CI actually checks.
FIXTURES = {"tmp_path"}


def _fixtures_for(func) -> tuple[dict, list[Path]]:
    """Build the arguments a test asked for, and the temp dirs to clean up.

    Only parameters with no default are required. Some tests here declare a
    pytest fixture with a default (`monkeypatch=None`) precisely so they run
    under both runners, and treating those as unsupplied fixtures would break
    the tests that went out of their way to be portable.
    """
    params = inspect.signature(func).parameters
    required = [n for n, p in params.items() if p.default is inspect.Parameter.empty]
    unknown = [n for n in required if n not in FIXTURES]
    if unknown:
        raise TypeError(
            f"{func.__name__} requires {unknown}, which this runner cannot "
            f"supply. Known fixtures: {sorted(FIXTURES)}. Give the parameter a "
            f"default if the test can run without it.")
    kwargs, temps = {}, []
    for name in required:
        if name == "tmp_path":
            path = Path(tempfile.mkdtemp(prefix="headlinne-test-"))
            kwargs[name] = path
            temps.append(path)
    return kwargs, temps


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
        temps: list[Path] = []
        try:
            kwargs, temps = _fixtures_for(func)
            func(**kwargs)
        except Exception:  # noqa: BLE001 - we want to report everything
            tb = traceback.format_exc()
            failures.append((mod_name, func_name, tb))
            print(f"FAIL  {label}")
        else:
            passed += 1
            print(f"ok    {label}")
        finally:
            for path in temps:
                shutil.rmtree(path, ignore_errors=True)

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
