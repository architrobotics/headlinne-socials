"""Where the hashtag long tail goes.

Posting it as the first comment is a paid Buffer feature, and the free plan does
not ignore the field: it rejects the whole post. That cost a real Instagram slot
once, so there are two defences here.

Up front, the tags are folded into the caption unless first comments are
explicitly enabled. And at the API boundary, a paid-plan rejection is retried
once without the field rather than allowed to lose the post. The tags still work
from the end of a caption, and the opening line, which is what Instagram indexes
for search, is unaffected either way.
"""

from __future__ import annotations

from headlinne.publish.buffer import (_append_tags, _has_first_comment,
                                      _is_paid_feature_error,
                                      _without_first_comment,
                                      apply_first_comment_policy)


def _meta(first_comment: str = "#a #b") -> dict:
    return {"instagram": {"type": "post", "shouldShareToFeed": True,
                          "firstComment": first_comment}}


# --------------------------------------------------------------------------- #
# The up-front policy
# --------------------------------------------------------------------------- #
def test_tags_go_in_the_caption_when_first_comments_are_off():
    caption, first = apply_first_comment_policy("Opening.\n\n#Tech", "#AI #Chips")
    assert first == ""
    assert caption.endswith("#AI #Chips")
    # The opening line, the part that matters for search, is untouched.
    assert caption.startswith("Opening.")


def test_nothing_is_appended_when_there_is_no_tail():
    caption, first = apply_first_comment_policy("Just a caption.", "")
    assert (caption, first) == ("Just a caption.", "")


def test_tags_already_present_are_not_duplicated():
    caption, first = apply_first_comment_policy("Body.\n\n#AI #Chips", "#AI #Chips")
    assert caption.count("#AI #Chips") == 1
    assert first == ""


def test_the_caption_limit_is_respected():
    from headlinne.config import INSTAGRAM_CAPTION_LIMIT

    caption, _ = apply_first_comment_policy("x" * (INSTAGRAM_CAPTION_LIMIT - 5),
                                            "#one #two #three")
    assert len(caption) <= INSTAGRAM_CAPTION_LIMIT


def test_a_paid_plan_keeps_the_first_comment_separate(monkeypatch=None):
    import headlinne.publish.buffer as buf

    original = buf.BUFFER_FIRST_COMMENT
    buf.BUFFER_FIRST_COMMENT = True
    try:
        caption, first = apply_first_comment_policy("Opening.", "#AI #Chips")
        assert caption == "Opening."
        assert first == "#AI #Chips"
    finally:
        buf.BUFFER_FIRST_COMMENT = original


# --------------------------------------------------------------------------- #
# The API-boundary fallback
# --------------------------------------------------------------------------- #
def test_the_paid_plan_rejection_is_recognised():
    assert _is_paid_feature_error(
        "Invalid post: First comment requires a paid plan. "
        "Please upgrade to use this feature.")
    assert _is_paid_feature_error("Please upgrade your plan")
    # An unrelated failure must not trigger a silent retry that changes the post.
    assert not _is_paid_feature_error("Channel not found")
    assert not _is_paid_feature_error("")


def test_the_field_is_detected_and_stripped_cleanly():
    assert _has_first_comment({"metadata": _meta()})
    assert not _has_first_comment({"metadata": _meta("   ")})
    assert not _has_first_comment({})

    stripped = _without_first_comment(_meta())
    assert "firstComment" not in stripped["instagram"]
    # Everything else Buffer requires survives the strip.
    assert stripped["instagram"]["type"] == "post"
    assert stripped["instagram"]["shouldShareToFeed"] is True


def test_the_rejected_tags_move_into_the_caption_on_retry():
    # The retry must not quietly drop the hashtags along with the field.
    assert _append_tags("Body.", {"metadata": _meta("#a #b")}) == "Body.\n\n#a #b"
    assert _append_tags("Body.\n\n#a #b", {"metadata": _meta("#a #b")}) == "Body.\n\n#a #b"
    assert _append_tags("Body.", {"metadata": _meta("")}) == "Body."


def test_a_rejection_retries_once_without_the_field_and_succeeds():
    from headlinne.publish.buffer import BufferClient

    calls: list[dict] = []

    class _Client(BufferClient):
        def _graphql(self, query, variables):
            calls.append(variables["input"])
            if _has_first_comment(variables["input"]):
                return {"data": {"createPost": {
                    "message": "Invalid post: First comment requires a paid "
                               "plan. Please upgrade to use this feature."}}}
            return {"data": {"createPost": {"post": {"id": "1", "status": "ok"}}}}

    post = _Client(token="x").create_post(
        channel_id="c", text="Body.", image_urls=["https://e/1.png"],
        metadata=_meta("#a #b"))

    assert post["id"] == "1"
    assert len(calls) == 2                      # rejected, then retried
    assert not _has_first_comment(calls[1])     # field gone
    assert calls[1]["text"].endswith("#a #b")   # tags kept
    assert calls[1]["assets"] == calls[0]["assets"]  # the post is otherwise identical


def test_an_unrelated_error_is_not_retried():
    from headlinne.publish.buffer import BufferClient, BufferError

    calls: list[dict] = []

    class _Client(BufferClient):
        def _graphql(self, query, variables):
            calls.append(variables["input"])
            return {"data": {"createPost": {"message": "Channel not found"}}}

    try:
        _Client(token="x").create_post(channel_id="c", text="Body.",
                                       metadata=_meta())
    except BufferError as exc:
        assert "Channel not found" in str(exc)
    else:
        raise AssertionError("expected a BufferError")
    assert len(calls) == 1
