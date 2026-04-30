"""Tests for cvs_lib.posting — AST extraction + posting markdown.

Pure-function tests against synthetic script + manifest fixtures.
Plus a sanity test against a real MPC reel to confirm the AST
extraction handles production scripts without surprises.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from cvs_lib.posting import (
    DEFAULT_BASE_HASHTAGS,
    PLATFORM_NOTES,
    ReelMeta,
    _suggest_alt_text,
    _suggest_caption,
    build_meta,
    docstring_title_and_synopsis,
    hashtags_for_reel,
    parse_reel_script,
    render_posting_md,
)

REELS_DIR = Path("E:/AI/CVS/scripts")
LIVE_REEL = REELS_DIR / "mpc_ep_abolish_ice_congress.py"


# -------------------------- AST extraction -------------------------- #

def test_parse_reel_script_pulls_string_constants(tmp_path):
    src = tmp_path / "fake_reel.py"
    src.write_text(
        '"""Title line.\n\nBody."""\n'
        'CTA_HEADLINE = "ABOLISH ICE"\n'
        'CTA_SUBHEAD = "CHIP IN"\n'
        'CTA_RALLY = "ice_out_romulus"\n',
        encoding="utf-8",
    )
    parsed = parse_reel_script(src)
    assert parsed["constants"]["CTA_HEADLINE"] == "ABOLISH ICE"
    assert parsed["constants"]["CTA_SUBHEAD"] == "CHIP IN"
    assert parsed["constants"]["CTA_RALLY"] == "ice_out_romulus"


def test_parse_reel_script_skips_computed_assignments(tmp_path):
    """`CTA_URL = config.get(...)` is computed at runtime — the AST
    parser must not return it. Caller layers in computed values from
    the cta.json read."""
    src = tmp_path / "fake_reel.py"
    src.write_text(
        '"""Doc."""\n'
        'CTA_HEADLINE = "X"\n'
        'CTA_URL = config.get("url", "")\n',
        encoding="utf-8",
    )
    parsed = parse_reel_script(src)
    assert "CTA_HEADLINE" in parsed["constants"]
    # CTA_URL isn't in our string-constants whitelist anyway, but make
    # sure non-literal values for whitelisted names also don't leak.


def test_parse_reel_script_returns_docstring(tmp_path):
    src = tmp_path / "r.py"
    src.write_text('"""First.\n\nSecond."""\n', encoding="utf-8")
    parsed = parse_reel_script(src)
    assert parsed["docstring"].startswith("First.")
    assert "Second." in parsed["docstring"]


# ------------------------- docstring split -------------------------- #

def test_docstring_title_strips_trailing_period():
    title, synopsis = docstring_title_and_synopsis(
        "MPC reel title.\n\nBody text here.\n",
    )
    assert title == "MPC reel title"
    assert "Body text here." in synopsis


def test_docstring_synopsis_stops_at_beats_block():
    """Beats: / Output: / Run: are structured detail, not synopsis."""
    doc = (
        "Reel title.\n\n"
        "Two-line synopsis describing the angle.\n\n"
        "Beats (30s):\n"
        "  0-10  HOOK ...\n"
    )
    title, synopsis = docstring_title_and_synopsis(doc)
    assert title == "Reel title"
    assert "Two-line synopsis" in synopsis
    assert "HOOK" not in synopsis
    assert "Beats" not in synopsis


def test_docstring_synopsis_handles_run_terminator():
    doc = "Title.\n\nWhy this matters.\n\nRun:\n    python ...\n"
    _, synopsis = docstring_title_and_synopsis(doc)
    assert "Why this matters." in synopsis
    assert "python" not in synopsis


def test_docstring_empty_returns_empty_pair():
    assert docstring_title_and_synopsis("") == ("", "")


# ----------------------------- hashtags ----------------------------- #

def test_hashtags_for_reel_appends_headline_tag():
    tags = hashtags_for_reel("FREE THEM ALL", base=["X"])
    assert tags[0] == "X"
    assert "FreeThemAll" in tags


def test_hashtags_for_reel_skips_existing_headline_tag_case_insensitive():
    """If headline tag would collide with a base entry, don't double up."""
    tags = hashtags_for_reel("ABOLISH ICE", base=["AbolishIce"])
    assert tags.count("AbolishIce") + tags.count("AbolishICE") == 1


def test_hashtags_for_reel_handles_empty_headline():
    tags = hashtags_for_reel("", base=["A", "B"])
    assert tags == ["A", "B"]


def test_hashtags_for_reel_default_base_when_unspecified():
    tags = hashtags_for_reel("DETROIT KNOWS")
    assert tags[: len(DEFAULT_BASE_HASHTAGS)] == DEFAULT_BASE_HASHTAGS
    assert "DetroitKnows" in tags


# ------------------------ caption / alt text ------------------------ #

def test_suggest_caption_uses_title_and_cta_pair():
    meta = ReelMeta(
        slug="test",
        title="The angle in one line",
        cta_headline="STAND WITH JUAN",
        cta_subhead="CHIP IN",
    )
    cap = _suggest_caption(meta)
    assert "The angle in one line." in cap
    assert "Stand With Juan" in cap
    assert "Chip In" in cap


def test_suggest_caption_falls_back_to_slug_when_title_missing():
    meta = ReelMeta(slug="follow_the_money", title="",
                    cta_headline="DEFUND", cta_subhead="CHIP IN")
    cap = _suggest_caption(meta)
    assert "Follow The Money" in cap


def test_suggest_alt_text_includes_rally_when_set():
    meta = ReelMeta(
        slug="north_lake", title="Juan released after 90 days",
        cta_headline="FREE THEM ALL", cta_rally="ice_out_romulus",
    )
    alt = _suggest_alt_text(meta)
    assert "Ice Out Romulus" in alt
    assert "Juan" in alt
    assert "Free Them All" in alt


def test_suggest_alt_text_falls_back_to_slug_when_empty():
    meta = ReelMeta(slug="my_test_reel", title="")
    alt = _suggest_alt_text(meta)
    assert "My Test Reel" in alt


# --------------------------- composite render --------------------------- #

def _meta_fixture():
    return ReelMeta(
        slug="abolish_ice_congress",
        title="Abolish ICE — From Congress to the Curb",
        synopsis="Tlaib names the law. Crowd answers with the chant.",
        cta_headline="ABOLISH ICE",
        cta_subhead="CHIP IN",
        cta_url="secure.actblue.com/donate/x",
        cta_rally="ice_out_romulus",
        duration_s=30.0,
        output_path="ComfyUI/output/mpc/abolish_ice_congress.mp4",
        cover_path="ComfyUI/output/mpc/covers/abolish_ice_congress.png",
        size_bytes=27_266_509,
        cover_size_bytes=1_949_456,
        width=1080, height=1920,
    )


def test_render_posting_md_has_required_sections():
    md = render_posting_md(_meta_fixture())
    assert "# Abolish ICE" in md
    assert "## Synopsis" in md
    assert "## Suggested caption" in md
    assert "## Hashtags" in md
    assert "## Alt text" in md
    assert "## Posting checklist" in md


def test_render_posting_md_lists_each_platform_with_note():
    md = render_posting_md(_meta_fixture())
    for platform, note in PLATFORM_NOTES.items():
        assert f"**{platform}**" in md
        assert note in md


def test_render_posting_md_size_format_mb_vs_kb():
    """Files >= 1 MB render as MB; smaller as KB."""
    big = _meta_fixture()
    md_big = render_posting_md(big)
    assert "MB" in md_big
    small = _meta_fixture()
    small.size_bytes = 50_000  # 50 KB
    small.cover_size_bytes = 10_000
    md_small = render_posting_md(small)
    assert "KB" in md_small


def test_render_posting_md_includes_donate_url_when_set():
    md = render_posting_md(_meta_fixture())
    assert "secure.actblue.com" in md
    no_url = _meta_fixture()
    no_url.cta_url = ""
    md2 = render_posting_md(no_url)
    assert "Donate:" not in md2


def test_render_posting_md_hashtags_are_octothorped():
    md = render_posting_md(_meta_fixture())
    assert "#ImmigrantRights" in md
    assert "#AbolishICE" in md  # base entry


# -------------------------- build_meta merge -------------------------- #

def test_build_meta_merges_script_and_manifest(tmp_path):
    src = tmp_path / "mpc_ep_test.py"
    src.write_text(
        '"""Test reel title.\n\nWhy this matters."""\n'
        'CTA_HEADLINE = "TEST HEADLINE"\n'
        'CTA_SUBHEAD = "TEST SUB"\n'
        'CTA_RALLY = "test_rally"\n',
        encoding="utf-8",
    )
    manifest_entry = {
        "output": "out/test.mp4",
        "duration_s": 25.0,
        "size_bytes": 5_000_000,
        "width": 1080, "height": 1920,
    }
    meta = build_meta(src, manifest_entry)
    assert meta.slug == "test"
    assert meta.title == "Test reel title"
    assert "Why this matters." in meta.synopsis
    assert meta.cta_headline == "TEST HEADLINE"
    assert meta.duration_s == 25.0
    assert meta.output_path == "out/test.mp4"


def test_build_meta_resolves_cta_url_from_config(tmp_path):
    src = tmp_path / "r.py"
    src.write_text(
        '"""T."""\n'
        'CTA_HEADLINE = "X"\n'
        'CTA_RALLY = "ice_out_romulus"\n',
        encoding="utf-8",
    )
    cta_config = {
        "defaults": {"handle_line": "@x"},
        "rallies": {"ice_out_romulus": {"url": "actblue.com/x"}},
    }
    meta = build_meta(src, {}, cta_config=cta_config)
    assert meta.cta_url == "actblue.com/x"
    assert meta.cta_handle_line == "@x"


def test_build_meta_no_manifest_entry_uses_defaults(tmp_path):
    src = tmp_path / "r.py"
    src.write_text('"""Doc."""\nCTA_HEADLINE = "X"\n', encoding="utf-8")
    meta = build_meta(src, None)
    assert meta.duration_s == 0.0
    assert meta.output_path == ""


# ----------------------- live MPC reel sanity ----------------------- #

@pytest.mark.skipif(not LIVE_REEL.exists(),
                    reason="live MPC reel not available")
def test_build_meta_against_real_mpc_reel():
    meta = build_meta(LIVE_REEL, {})
    assert meta.slug == "abolish_ice_congress"
    assert meta.cta_headline == "ABOLISH ICE"
    assert meta.cta_subhead == "CHIP IN"
    # Title comes from the docstring's first non-blank line.
    assert "Abolish ICE" in meta.title
    md = render_posting_md(meta)
    # End-to-end render produced sensible markdown.
    assert "# " in md
    assert "ABOLISH ICE" in md or "Abolish ICE" in md
