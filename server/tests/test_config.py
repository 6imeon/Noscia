from noscia.config import mask


def test_mask_empty():
    assert mask(None) == ""
    assert mask("") == ""


def test_mask_short_is_all_dots():
    assert set(mask("abc123")) == {"•"}


def test_mask_long_shows_ends_only():
    masked = mask("sk-or-v1-1234567890abcdef")
    assert masked.startswith("sk-o")
    assert masked.endswith("cdef")
    assert "…" in masked
    # the middle is never revealed
    assert "567890" not in masked
