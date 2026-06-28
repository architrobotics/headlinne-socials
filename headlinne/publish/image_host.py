"""Turn locally-rendered slide PNGs into publicly reachable URLs.

Buffer does not accept image uploads. For Instagram carousels it fetches each
image from a public URL. The simplest zero-cost option is to commit the rendered
PNGs to a public GitHub repo and serve them through raw.githubusercontent.com.

If your repo is private, set PUBLIC_IMAGE_BASE_URL to a host you control (S3,
Cloudflare R2, a small static server, etc.) that serves the same committed paths,
and the CustomHost will build URLs against it.
"""

from __future__ import annotations

from pathlib import Path

from ..config import ROOT, SECRETS
from ..logging_setup import get_logger

log = get_logger("publish.image_host")


class ImageHost:
    """Maps a local file under the repo to a public URL."""

    def url_for(self, local_path: Path) -> str:  # pragma: no cover - interface
        raise NotImplementedError

    @staticmethod
    def _rel(local_path: Path) -> str:
        path = Path(local_path).resolve()
        try:
            return path.relative_to(ROOT.resolve()).as_posix()
        except ValueError:
            # Not under the repo root, fall back to the file name only.
            return path.name


class GitHubRawHost(ImageHost):
    """Serves committed files via raw.githubusercontent.com."""

    def __init__(self, repository: str, ref: str = "main"):
        if not repository:
            raise ValueError("GITHUB_REPOSITORY is required for GitHubRawHost.")
        self.base = f"https://raw.githubusercontent.com/{repository}/{ref}"

    def url_for(self, local_path: Path) -> str:
        return f"{self.base}/{self._rel(local_path)}"


class CustomHost(ImageHost):
    """Serves committed files from a base URL you control."""

    def __init__(self, base_url: str):
        self.base = base_url.rstrip("/")

    def url_for(self, local_path: Path) -> str:
        return f"{self.base}/{self._rel(local_path)}"


def get_image_host() -> ImageHost:
    """Pick the right host from configuration.

    Preference order:
      1. PUBLIC_IMAGE_BASE_URL  -> CustomHost (works for private repos)
      2. GITHUB_REPOSITORY      -> GitHubRawHost (public repo, default in CI)
    """
    base = (SECRETS.public_image_base_url or "").strip()
    if base:
        if base.startswith("http://") or base.startswith("https://"):
            log.info("Using custom image host: %s", base)
            return CustomHost(base)
        # A non-URL value (e.g. a leftover placeholder like "empty") would build
        # broken image URLs, so ignore it and fall back instead of failing late.
        log.warning("Ignoring PUBLIC_IMAGE_BASE_URL=%r (not an http(s) URL). "
                    "Unset it to use the public GitHub repo, or set a real URL.",
                    base)
    if SECRETS.github_repository:
        log.info("Using GitHub raw host for %s@%s",
                 SECRETS.github_repository, SECRETS.github_ref_name)
        return GitHubRawHost(SECRETS.github_repository, SECRETS.github_ref_name)
    raise RuntimeError(
        "No public image host configured. Set PUBLIC_IMAGE_BASE_URL to an "
        "http(s) URL, or run in GitHub Actions where GITHUB_REPOSITORY is "
        "available (public repo)."
    )
