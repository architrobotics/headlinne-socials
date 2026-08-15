"""How configuration reads the environment.

These exist because of a specific production failure. A workflow line like
``REEL_VOICEOVER: ${{ vars.REEL_VOICEOVER }}`` does not leave the variable unset
when the repository variable has never been created: GitHub substitutes an empty
string. `os.getenv(name, default)` then returns `""` rather than the default,
because the variable *is* set as far as Python is concerned.

The result was reels shipping silent on every run, with nothing in the logs
saying why, because from the code's point of view the operator had asked for
silence. So: an empty value means "not configured", and the default wins.
"""

from __future__ import annotations

import importlib
import os

import headlinne.config as config
from headlinne.config import _env_flag, _env_number, _env_str

# Every setting the workflows pass through as `${{ vars.X }}`, which is exactly
# the set that can arrive empty.
WORKFLOW_VARIABLES = (
    "BUFFER_SCHEDULING_MODE", "PUBLIC_IMAGE_BASE_URL", "REELS_ENABLED",
    "STORY_CARD_ENABLED", "IG_SECOND_CAROUSEL", "REEL_VOICEOVER",
    "REEL_TTS_MODEL", "REEL_VOICE_NEWS", "REEL_VOICE_EDUCATION",
)


class _Env:
    """Set env vars for the duration of a block, then restore them."""

    def __init__(self, **values):
        self.values = values
        self.saved: dict[str, str | None] = {}

    def __enter__(self):
        for key, value in self.values.items():
            self.saved[key] = os.environ.get(key)
            os.environ[key] = value
        return self

    def __exit__(self, *exc):
        for key, old in self.saved.items():
            if old is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = old
        return False


# --------------------------------------------------------------------------- #
# The helpers
# --------------------------------------------------------------------------- #
def test_empty_means_unset_not_false():
    with _Env(HEADLINNE_TEST_FLAG=""):
        assert _env_flag("HEADLINNE_TEST_FLAG", True) is True
        assert _env_flag("HEADLINNE_TEST_FLAG", False) is False


def test_whitespace_only_also_means_unset():
    with _Env(HEADLINNE_TEST_FLAG="   "):
        assert _env_flag("HEADLINNE_TEST_FLAG", True) is True
    with _Env(HEADLINNE_TEST_STR="  "):
        assert _env_str("HEADLINNE_TEST_STR", "fallback") == "fallback"


def test_an_explicit_opt_out_is_still_honoured():
    # The whole point is that turning something off must still be possible.
    for value in ("false", "FALSE", "no", "0", "off", "nonsense"):
        with _Env(HEADLINNE_TEST_FLAG=value):
            assert _env_flag("HEADLINNE_TEST_FLAG", True) is False


def test_truthy_words_are_accepted_in_any_case():
    for value in ("true", "TRUE", "True", "1", "yes", "on"):
        with _Env(HEADLINNE_TEST_FLAG=value):
            assert _env_flag("HEADLINNE_TEST_FLAG", False) is True


def test_a_string_setting_falls_back_when_empty():
    with _Env(HEADLINNE_TEST_STR=""):
        assert _env_str("HEADLINNE_TEST_STR", "gemini-tts") == "gemini-tts"
    with _Env(HEADLINNE_TEST_STR="override"):
        assert _env_str("HEADLINNE_TEST_STR", "gemini-tts") == "override"


def test_a_number_falls_back_when_empty_or_unparseable():
    with _Env(HEADLINNE_TEST_NUM=""):
        assert _env_number("HEADLINNE_TEST_NUM", 20, int) == 20
    with _Env(HEADLINNE_TEST_NUM="not a number"):
        assert _env_number("HEADLINNE_TEST_NUM", 20, int) == 20
    with _Env(HEADLINNE_TEST_NUM="31"):
        assert _env_number("HEADLINNE_TEST_NUM", 20, int) == 31
    with _Env(HEADLINNE_TEST_NUM="0.9"):
        assert abs(_env_number("HEADLINNE_TEST_NUM", 0.65, float) - 0.9) < 1e-9


# --------------------------------------------------------------------------- #
# The whole module, under runner conditions
# --------------------------------------------------------------------------- #
def test_defaults_survive_a_runner_with_no_variables_set():
    """Reload config exactly as a GitHub runner would see it, with every
    workflow-passed variable present but empty."""
    with _Env(**{name: "" for name in WORKFLOW_VARIABLES}):
        fresh = importlib.reload(config)
        try:
            assert fresh.REELS_ENABLED is True
            assert fresh.STORY_CARD_ENABLED is True
            # Now off by default. Carousels moved to a weekly cadence: five
            # slides of argument is a considered weekly artefact, not a daily
            # one, and four feed posts a day dilutes every one of them.
            assert fresh.IG_SECOND_CAROUSEL is False
            assert fresh.CAROUSEL_WEEKDAYS
            assert fresh.REEL_VOICEOVER is True
            # An empty model name is worse than a wrong one: every speech call
            # fails and the reel goes out silent with no obvious cause.
            assert fresh.REEL_TTS_MODEL
            assert fresh.REEL_VOICE_NEWS and fresh.REEL_VOICE_EDUCATION
            # This one is pre-existing and just as damaging: an empty value is
            # not "scheduled", so the pipeline would switch publishing modes.
            assert fresh.BUFFER_SCHEDULING_MODE == "scheduled"
        finally:
            importlib.reload(config)


def test_opting_out_through_a_variable_still_works_on_a_runner():
    with _Env(REELS_ENABLED="false", REEL_VOICEOVER="false",
              IG_SECOND_CAROUSEL="false"):
        fresh = importlib.reload(config)
        try:
            assert fresh.REELS_ENABLED is False
            assert fresh.REEL_VOICEOVER is False
            assert fresh.IG_SECOND_CAROUSEL is False
        finally:
            importlib.reload(config)


def test_no_setting_reads_the_environment_directly_any_more():
    """Every env read goes through a helper, so none of them can regress.

    Secrets are the exception: for those an empty value genuinely does mean
    absent, and the code already treats it that way.
    """
    import pathlib
    import re

    source = pathlib.Path(config.__file__).read_text(encoding="utf-8")
    # Strip the helper definitions themselves before looking for raw reads.
    body = source.split("# Paths", 1)[1]
    raw = re.findall(r'os\.getenv\("([A-Z_]+)"', body)
    secrets = {
        "GEMINI_API_KEY", "BUFFER_ACCESS_TOKEN", "BUFFER_CHANNEL_ID_X",
        "BUFFER_CHANNEL_ID_LINKEDIN", "BUFFER_CHANNEL_ID_INSTAGRAM",
        "META_ACCESS_TOKEN", "IG_USER_ID", "REDDIT_CLIENT_ID",
        "REDDIT_CLIENT_SECRET", "REDDIT_USERNAME", "REDDIT_PASSWORD",
        "GITHUB_REPOSITORY", "PUBLIC_IMAGE_BASE_URL",
    }
    leaked = sorted(set(raw) - secrets)
    assert not leaked, f"these read the environment directly: {leaked}"
