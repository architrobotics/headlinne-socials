"""A small Reddit API client (read plus a guarded single-comment submit).

Auth is the OAuth2 "script app" password grant. Create an app at
https://www.reddit.com/prefs/apps (type: script) and set these env vars:

    REDDIT_CLIENT_ID       the string under the app name
    REDDIT_CLIENT_SECRET   the app secret
    REDDIT_USERNAME        the Reddit account the tool acts as
    REDDIT_PASSWORD        that account's password
    REDDIT_USER_AGENT      a descriptive UA, e.g. "web:headlinne-assist:v1 (by /u/you)"

Note: a single bearer string is NOT a Reddit credential. If someone hands you
one, it is almost certainly for a different service (e.g. a Gemini token). Reddit
needs the client id + secret + account above.

The client only reads (search / listings) for discovery. Posting a comment is a
separate, explicitly-guarded call used by the reviewed `reddit post` command,
never in a loop.
"""

from __future__ import annotations

import time

import requests

from ..config import REDDIT_USER_AGENT, SECRETS
from ..logging_setup import get_logger

log = get_logger("reddit.client")

_TOKEN_URL = "https://www.reddit.com/api/v1/access_token"
_API = "https://oauth.reddit.com"
_TIMEOUT = 20


class RedditError(RuntimeError):
    pass


class RedditClient:
    def __init__(self):
        self._token: str | None = None
        self._token_expiry = 0.0
        self._session = requests.Session()
        self._session.headers["User-Agent"] = REDDIT_USER_AGENT

    # ---- auth ----
    def _ensure_token(self) -> str:
        if self._token and time.time() < self._token_expiry - 30:
            return self._token
        cid, secret = SECRETS.reddit_client_id, SECRETS.reddit_client_secret
        user, pw = SECRETS.reddit_username, SECRETS.reddit_password
        if not all((cid, secret, user, pw)):
            raise RedditError(
                "Reddit credentials are not set. Need REDDIT_CLIENT_ID, "
                "REDDIT_CLIENT_SECRET, REDDIT_USERNAME and REDDIT_PASSWORD "
                "(a script app from reddit.com/prefs/apps).")
        resp = requests.post(
            _TOKEN_URL,
            auth=(cid, secret),
            data={"grant_type": "password", "username": user, "password": pw},
            headers={"User-Agent": REDDIT_USER_AGENT},
            timeout=_TIMEOUT,
        )
        if resp.status_code != 200:
            raise RedditError(f"auth failed: HTTP {resp.status_code} {resp.text[:200]}")
        body = resp.json()
        self._token = body.get("access_token")
        if not self._token:
            raise RedditError(f"no access_token in response: {body}")
        self._token_expiry = time.time() + int(body.get("expires_in", 3600))
        self._session.headers["Authorization"] = f"bearer {self._token}"
        return self._token

    # ---- low-level ----
    def _get(self, path: str, params: dict | None = None) -> dict:
        self._ensure_token()
        resp = self._session.get(f"{_API}{path}", params=params or {}, timeout=_TIMEOUT)
        _respect_ratelimit(resp)
        if resp.status_code != 200:
            raise RedditError(f"GET {path} -> HTTP {resp.status_code}: {resp.text[:200]}")
        return resp.json()

    def _post(self, path: str, data: dict) -> dict:
        self._ensure_token()
        resp = self._session.post(f"{_API}{path}", data=data, timeout=_TIMEOUT)
        _respect_ratelimit(resp)
        if resp.status_code != 200:
            raise RedditError(f"POST {path} -> HTTP {resp.status_code}: {resp.text[:200]}")
        return resp.json()

    # ---- read: discovery ----
    def search_subreddit(self, subreddit: str, query: str, *, limit: int = 15,
                         sort: str = "new", t: str = "week") -> list[dict]:
        """Search one subreddit for a query. Returns raw child 'data' dicts."""
        data = self._get(f"/r/{subreddit}/search", {
            "q": query, "restrict_sr": 1, "limit": limit, "sort": sort, "t": t,
            "raw_json": 1,
        })
        return [c.get("data", {}) for c in data.get("data", {}).get("children", [])]

    def listing(self, subreddit: str, *, sort: str = "hot", limit: int = 25) -> list[dict]:
        data = self._get(f"/r/{subreddit}/{sort}", {"limit": limit, "raw_json": 1})
        return [c.get("data", {}) for c in data.get("data", {}).get("children", [])]

    # ---- write: guarded ----
    def submit_comment(self, parent_fullname: str, text: str) -> dict:
        """Post one comment as a reply to `parent_fullname` (t3_<id> for a post).

        This is the only write path. It is called by the reviewed `reddit post`
        command for a single approved draft, never automatically in bulk.
        """
        if not text.strip():
            raise RedditError("refusing to submit an empty comment")
        body = self._post("/api/comment", {
            "api_type": "json", "thing_id": parent_fullname, "text": text,
        })
        errors = body.get("json", {}).get("errors") or []
        if errors:
            raise RedditError(f"Reddit rejected the comment: {errors}")
        log.info("posted comment to %s", parent_fullname)
        return body


def _respect_ratelimit(resp: requests.Response) -> None:
    """Sleep briefly if Reddit says we are near the per-minute limit."""
    try:
        remaining = float(resp.headers.get("x-ratelimit-remaining", "60"))
        reset = float(resp.headers.get("x-ratelimit-reset", "0"))
    except ValueError:
        return
    if remaining <= 2 and reset > 0:
        log.info("near Reddit rate limit, pausing %.0fs", min(reset, 30))
        time.sleep(min(reset, 30))
