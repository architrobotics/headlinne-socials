"""Publish X (Twitter), LinkedIn and Instagram through Buffer's GraphQL API.

Buffer exposes a single GraphQL endpoint at https://api.buffer.com. We use the
createPost mutation with a typed input. Buffer has exactly two scheduling modes:

  - customScheduled + dueAt  -> Buffer publishes the post at a specific UTC time.
  - addToQueue               -> Buffer drops it in the next free queue slot.

There is no "publish now" mode. To publish immediately (when a cron-job.org
trigger fires at the slot time, or in trigger mode), we therefore use
customScheduled with a dueAt a couple of minutes in the future, which Buffer
sends out right away. A small cushion avoids "time in the past" rejections from
clock differences.

Images (for Instagram carousels and any image post) are passed as an ordered
`assets` list, each entry being `{ image: { url } }`. Buffer does not accept file
uploads, so every image URL must be publicly reachable. Several image URLs on one
Instagram post become a carousel, in the order given. See publish.image_host for
how the rendered slides are turned into public URLs.

The API returns HTTP 200 with typed error objects for most problems, but a
malformed request (for example an unknown enum value) comes back as HTTP 400, so
we surface both. Note: the Buffer API cannot edit or delete a post once created,
so we only create when we intend to publish.
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timedelta, timezone

import requests

from ..config import BUFFER_API_URL, INSTAGRAM_CAPTION_LIMIT, SECRETS
from ..logging_setup import get_logger

log = get_logger("publish.buffer")

# Buffer has no immediate-publish mode, so "now" posts are scheduled this many
# minutes ahead with customScheduled. Small enough to feel immediate, large
# enough to clear clock skew and any minimum lead time.
_IMMEDIATE_LEAD_MINUTES = 2


def _immediate_due_at() -> str:
    """A dueAt a short moment from now, in Buffer's UTC format."""
    when = datetime.now(timezone.utc) + timedelta(minutes=_IMMEDIATE_LEAD_MINUTES)
    return when.strftime("%Y-%m-%dT%H:%M:%S.000Z")

_CREATE_POST = """
mutation CreatePost($input: CreatePostInput!) {
  createPost(input: $input) {
    ... on PostActionSuccess {
      post { id status dueAt assets { id mimeType } }
    }
    ... on MutationError {
      message
    }
  }
}
""".strip()

_MAX_RETRIES = 4


class BufferError(RuntimeError):
    pass


class BufferClient:
    def __init__(self, token: str | None = None, endpoint: str = BUFFER_API_URL):
        self.token = token or SECRETS.buffer_token
        self.endpoint = endpoint

    def _headers(self) -> dict:
        if not self.token:
            raise BufferError("BUFFER_ACCESS_TOKEN is not set.")
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.token}",
        }

    def _graphql(self, query: str, variables: dict) -> dict:
        payload = json.dumps({"query": query, "variables": variables})
        last_err: Exception | None = None
        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                resp = requests.post(self.endpoint, headers=self._headers(),
                                     data=payload, timeout=30)
                # The API uses HTTP 200 for success; 429 means slow down.
                if resp.status_code == 429:
                    raise BufferError("rate limited (429)")
                resp.raise_for_status()
                body = resp.json()
                if body.get("errors"):
                    msg = "; ".join(e.get("message", str(e)) for e in body["errors"])
                    raise BufferError(f"GraphQL errors: {msg}")
                return body
            except Exception as exc:  # noqa: BLE001
                last_err = exc
                wait = min(2 ** attempt, 20)
                log.warning("Buffer attempt %d/%d failed: %s (retry in %ss)",
                            attempt, _MAX_RETRIES, exc, wait)
                time.sleep(wait)
        raise BufferError(f"Buffer request failed after {_MAX_RETRIES} attempts: {last_err}")

    def create_post(self, *, channel_id: str, text: str,
                    image_urls: list[str] | None = None,
                    due_at_utc: str | None = None,
                    metadata: dict | None = None) -> dict:
        """Create a post on a channel.

        Pass image_urls to attach images (several become an Instagram carousel,
        in order). Schedules the post if due_at_utc is given, otherwise publishes
        immediately.
        """
        if not channel_id:
            raise BufferError("channel_id is empty (check BUFFER_CHANNEL_ID_*).")
        input_obj: dict = {
            "text": text,
            "channelId": channel_id,
            "schedulingType": "automatic",
        }
        if image_urls:
            input_obj["assets"] = [{"image": {"url": u}} for u in image_urls if u]
        if metadata:
            input_obj["metadata"] = metadata
        # Buffer has no "now" mode, so an immediate post is customScheduled a
        # couple of minutes ahead. A given due time is used as-is.
        input_obj["mode"] = "customScheduled"
        input_obj["dueAt"] = due_at_utc or _immediate_due_at()

        body = self._graphql(_CREATE_POST, {"input": input_obj})
        result = body.get("data", {}).get("createPost", {})
        post = result.get("post")
        if not post:
            raise BufferError(result.get("message", "unknown Buffer error"))
        log.info("Buffer post created id=%s status=%s due=%s assets=%d",
                 post.get("id"), post.get("status"), post.get("dueAt"),
                 len(post.get("assets") or []))
        return post

    # -- convenience wrappers bound to the configured channels --
    def post_twitter(self, text: str, due_at_utc: str | None = None) -> dict:
        return self.create_post(channel_id=SECRETS.buffer_channel_x, text=text,
                                due_at_utc=due_at_utc)

    def post_linkedin(self, text: str, due_at_utc: str | None = None) -> dict:
        return self.create_post(channel_id=SECRETS.buffer_channel_linkedin, text=text,
                                due_at_utc=due_at_utc)

    def post_instagram(self, image_urls: list[str], caption: str,
                       due_at_utc: str | None = None) -> dict:
        """Publish an Instagram feed post. Two or more images make a carousel, in
        the order given. Instagram allows 2 to 10 images in a carousel.

        Instagram requires a post type (post, story or reel); a feed carousel is
        type "post", set via the channel-specific metadata field.
        """
        if not image_urls:
            raise BufferError("Instagram post needs at least one image URL.")
        if len(image_urls) > 10:
            raise BufferError(f"Instagram carousel allows up to 10 images, got {len(image_urls)}.")
        return self.create_post(channel_id=SECRETS.buffer_channel_instagram,
                                text=caption, image_urls=image_urls,
                                due_at_utc=due_at_utc,
                                metadata={"instagram": {"type": "post"}})


def build_caption(caption: str, hashtags: list[str]) -> str:
    """Combine the caption text and hashtags into one Instagram caption."""
    tags = " ".join("#" + str(h).lstrip("#").replace(" ", "") for h in hashtags if str(h).strip())
    full = caption.strip()
    if tags:
        full = f"{full}\n\n{tags}"
    return full[:INSTAGRAM_CAPTION_LIMIT]