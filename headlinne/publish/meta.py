"""Publish Instagram carousels through the Meta Graph API.

Instagram carousel publishing is a three-step container flow:

  1. For each image, create a child item container
     POST /{ig-user-id}/media  with image_url and is_carousel_item=true
  2. Create the parent carousel container
     POST /{ig-user-id}/media  with media_type=CAROUSEL, children=<ids>, caption
  3. Publish the parent container
     POST /{ig-user-id}/media_publish  with creation_id=<parent id>

Meta fetches each image_url itself, so the images MUST be on a public host (see
publish.image_host). Containers are processed asynchronously, so we poll each
container's status_code until it reports FINISHED before moving on.
"""

from __future__ import annotations

import time

import requests

from ..config import (INSTAGRAM_CAPTION_LIMIT, META_GRAPH_URL,
                      META_GRAPH_VERSION, SECRETS)
from ..logging_setup import get_logger

log = get_logger("publish.meta")

_POLL_INTERVAL_SECONDS = 4
_POLL_MAX_ATTEMPTS = 30  # ~2 minutes per container
_REQUEST_TIMEOUT = 40


class MetaError(RuntimeError):
    pass


class MetaClient:
    def __init__(self, token: str | None = None, ig_user_id: str | None = None):
        self.token = token or SECRETS.meta_token
        self.ig_user_id = ig_user_id or SECRETS.ig_user_id
        self.base = f"{META_GRAPH_URL}/{META_GRAPH_VERSION}"

    def _check(self) -> None:
        if not self.token:
            raise MetaError("META_ACCESS_TOKEN is not set.")
        if not self.ig_user_id:
            raise MetaError("IG_USER_ID is not set.")

    def _post(self, path: str, params: dict) -> dict:
        self._check()
        params = {**params, "access_token": self.token}
        resp = requests.post(f"{self.base}/{path}", data=params, timeout=_REQUEST_TIMEOUT)
        return self._parse(resp)

    def _get(self, path: str, params: dict) -> dict:
        self._check()
        params = {**params, "access_token": self.token}
        resp = requests.get(f"{self.base}/{path}", params=params, timeout=_REQUEST_TIMEOUT)
        return self._parse(resp)

    @staticmethod
    def _parse(resp: requests.Response) -> dict:
        try:
            body = resp.json()
        except ValueError:
            resp.raise_for_status()
            raise MetaError("non-JSON response from Meta")
        if isinstance(body, dict) and body.get("error"):
            err = body["error"]
            raise MetaError(f"{err.get('type')}: {err.get('message')} (code {err.get('code')})")
        resp.raise_for_status()
        return body

    # ---- container flow ----
    def _create_child(self, image_url: str) -> str:
        body = self._post(f"{self.ig_user_id}/media", {
            "image_url": image_url,
            "is_carousel_item": "true",
        })
        cid = body.get("id")
        if not cid:
            raise MetaError(f"no container id for child image {image_url}")
        return cid

    def _create_parent(self, children: list[str], caption: str) -> str:
        body = self._post(f"{self.ig_user_id}/media", {
            "media_type": "CAROUSEL",
            "children": ",".join(children),
            "caption": caption,
        })
        cid = body.get("id")
        if not cid:
            raise MetaError("no container id for carousel parent")
        return cid

    def _wait_finished(self, container_id: str) -> None:
        """Poll a container until it is FINISHED (or fail on ERROR/timeout)."""
        for _ in range(_POLL_MAX_ATTEMPTS):
            body = self._get(container_id, {"fields": "status_code,status"})
            status = body.get("status_code")
            if status == "FINISHED":
                return
            if status == "ERROR":
                raise MetaError(f"container {container_id} failed: {body.get('status')}")
            time.sleep(_POLL_INTERVAL_SECONDS)
        raise MetaError(f"container {container_id} not ready after polling")

    def _publish(self, creation_id: str) -> str:
        body = self._post(f"{self.ig_user_id}/media_publish", {
            "creation_id": creation_id,
        })
        media_id = body.get("id")
        if not media_id:
            raise MetaError("publish returned no media id")
        return media_id

    def publish_carousel(self, image_urls: list[str], caption: str) -> str:
        """Publish a carousel from public image URLs. Returns the media id."""
        if not (2 <= len(image_urls) <= 10):
            raise MetaError(f"carousel needs 2 to 10 images, got {len(image_urls)}")
        caption = caption[:INSTAGRAM_CAPTION_LIMIT]

        log.info("Creating %d child containers", len(image_urls))
        children: list[str] = []
        for url in image_urls:
            cid = self._create_child(url)
            children.append(cid)
        for cid in children:
            self._wait_finished(cid)

        log.info("Creating carousel parent container")
        parent = self._create_parent(children, caption)
        self._wait_finished(parent)

        log.info("Publishing carousel")
        media_id = self._publish(parent)
        log.info("Instagram carousel published, media id=%s", media_id)
        return media_id


def build_caption(caption: str, hashtags: list[str]) -> str:
    """Combine the caption text and hashtags into one Instagram caption."""
    tags = " ".join("#" + str(h).lstrip("#").replace(" ", "") for h in hashtags if str(h).strip())
    full = caption.strip()
    if tags:
        full = f"{full}\n\n{tags}"
    return full[:INSTAGRAM_CAPTION_LIMIT]
