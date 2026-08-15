"""Every setting must actually be read by something.

Twice in one branch a setting was declared in config.py and never consumed:
CAROUSEL_WEIGHTS-style dead config reads as a working feature in review and in
the commit message, while the old behaviour carries on unchanged in production.
These tests make that failure loud.

The .env.example check exists for the same reason from the other direction: a
setting nobody can discover is barely better than one nobody reads.
"""

from __future__ import annotations

import pathlib
import re

REPO = pathlib.Path(__file__).resolve().parents[1]
CONFIG = REPO / "headlinne" / "config.py"

# Settings that are genuinely config-only: consumed by operators or by the
# workflows rather than by application code.
_EXTERNAL_ONLY = {
    "GITHUB_REF_NAME", "GITHUB_REPOSITORY", "FFMPEG_BINARY",
}


def _declared_settings() -> set[str]:
    src = CONFIG.read_text(encoding="utf-8")
    names = set(re.findall(r"_env_(?:str|flag|number)\(\s*\"([A-Z_0-9]+)\"", src))
    names |= set(re.findall(r"os\.getenv\(\"([A-Z_0-9]+)\"", src))
    return names - _EXTERNAL_ONLY


def _symbol_for(name: str, config_src: str) -> str:
    """The name application code would actually import for this setting.

    Two shapes exist: a module-level constant fed by _env_*(), and a SECRETS
    dataclass field fed by os.getenv(). Searching for the raw environment
    variable name finds neither, which is how three correctly-wired settings
    first tripped this test.
    """
    m = re.search(r"^([A-Z_0-9]+)\s*(?::[^=]+)?=\s*(?:tuple\()?\s*"
                  r"(?:\w+\s+for\s+\w+\s+in\s+)?_env_\w+\(\s*\"%s\"" % name,
                  config_src, re.M)
    if m:
        return m.group(1)
    m = re.search(r"^\s*([a-z_0-9]+)\s*:[^=]+=\s*field\([^)]*os\.getenv\(\"%s\""
                  % name, config_src, re.M)
    if m:
        return m.group(1)
    return name


def _python_sources() -> str:
    parts = []
    for path in (REPO / "headlinne").rglob("*.py"):
        if "__pycache__" in path.parts or path.name == "config.py":
            continue
        parts.append(path.read_text(encoding="utf-8"))
    return "\n".join(parts)


def test_every_setting_reaches_application_code():
    """A constant nobody imports is a feature that silently does not exist."""
    src = _python_sources()
    config_src = CONFIG.read_text(encoding="utf-8")
    unused = []
    for name in sorted(_declared_settings()):
        if _symbol_for(name, config_src) in src:
            continue
        unused.append(f"{name} -> {_symbol_for(name, config_src)}")
    assert not unused, "declared but never consumed: " + ", ".join(unused)


def test_env_example_documents_the_settings_operators_need():
    example = (REPO / ".env.example").read_text(encoding="utf-8")
    for name in ("GEMINI_API_KEY", "GEMINI_FALLBACK_MODELS", "CAROUSEL_WEEKDAYS",
                 "IG_SECOND_CAROUSEL", "BUFFER_SCHEDULING_MODE",
                 "REEL_TTS_MIN_INTERVAL", "PUBLIC_IMAGE_BASE_URL"):
        assert name in example, f"{name} is undocumented in .env.example"


def test_env_example_carries_no_real_values():
    """It is committed. A populated secret here would be a leak."""
    example = (REPO / ".env.example").read_text(encoding="utf-8")
    for line in example.splitlines():
        if not line.strip() or line.lstrip().startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        if any(t in key for t in ("TOKEN", "KEY", "SECRET", "PASSWORD", "ID")):
            assert value.strip() == "", f"{key.strip()} has a value committed"
