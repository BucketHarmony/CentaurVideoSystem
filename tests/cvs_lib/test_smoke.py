"""Phase 1 smoke tests for cvs_lib.

Five tests covering: env loader edge cases, preflight hard fails,
preflight soft warnings, preflight strict-mode promotion, and
beat-tuple shape sanity.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from cvs_lib.env import load_env
from cvs_lib import preflight


# --------------------------------------------------------------------------- #
# env.load_env
# --------------------------------------------------------------------------- #

def test_load_env_missing_file_returns_empty(tmp_path):
    """A missing .env file yields an empty dict, not an error."""
    assert load_env(tmp_path / "does_not_exist.env") == {}


def test_load_env_strips_quotes_and_comments(tmp_path):
    """Comments, blanks, and surrounding quotes are handled correctly."""
    env_file = tmp_path / ".env"
    env_file.write_text(textwrap.dedent("""\
        # leading comment
        FOO=bar

        BAZ="quoted value"
        QUX='single quoted'
        # not_a_var
        no_equals_sign_line
        EMPTY=
        SPACES_AROUND  =  yes
    """), encoding="utf-8")
    out = load_env(env_file)
    assert out == {
        "FOO": "bar",
        "BAZ": "quoted value",
        "QUX": "single quoted",
        "EMPTY": "",
        "SPACES_AROUND": "yes",
    }


# --------------------------------------------------------------------------- #
# preflight
# --------------------------------------------------------------------------- #

def _beat(slug, dur, path, in_t=0.0, out_t=1.0, **extra):
    spec = {"path": Path(path), "in_t": in_t, "out_t": out_t, **extra}
    return (slug, dur, "minor", slug.upper(), spec)


def test_preflight_passes_on_clean_beats(tmp_path):
    """A coherent BEATS list passes preflight cleanly."""
    src = tmp_path / "fake.mp4"
    src.write_bytes(b"")
    beats = [
        _beat("a", 10.0, src, in_t=0.0, out_t=10.0),
        _beat("b", 20.0, src, in_t=10.0, out_t=30.0),
    ]
    code = preflight.run(beats, 30.0, rotation_cache_dir=tmp_path / "rot")
    assert code == 0


def test_preflight_catches_duration_mismatch(tmp_path, capsys):
    """Sum-of-beats != DURATION fails as ERROR with exit code 1."""
    src = tmp_path / "fake.mp4"
    src.write_bytes(b"")
    beats = [
        _beat("a", 7.0, src, in_t=0.0, out_t=7.0),
        _beat("b", 8.0, src, in_t=7.0, out_t=15.0),
    ]
    code = preflight.run(beats, 30.0, rotation_cache_dir=tmp_path / "rot")
    out = capsys.readouterr().out
    assert code == 1
    assert "duration_mismatch" in out
    assert "15.000" in out and "30.000" in out


def test_preflight_catches_missing_source(tmp_path, capsys):
    """Missing source file fails as ERROR with exit code 1."""
    src = tmp_path / "does_not_exist.mp4"  # never created
    beats = [_beat("a", 30.0, src, in_t=0.0, out_t=30.0)]
    code = preflight.run(beats, 30.0, rotation_cache_dir=tmp_path / "rot")
    out = capsys.readouterr().out
    assert code == 1
    assert "source_missing" in out


def test_preflight_strict_promotes_warnings(tmp_path, capsys):
    """A caption window outside the beat is a WARN; strict=True makes it fatal."""
    src = tmp_path / "fake.mp4"
    src.write_bytes(b"")
    # caption_lines window (0, 99) far exceeds beat dur=5
    bad_caption = (0.0, 99.0, "way too long")
    beats = [
        _beat("a", 5.0, src, in_t=0.0, out_t=5.0,
              caption_lines=[bad_caption]),
        _beat("b", 25.0, src, in_t=5.0, out_t=30.0),
    ]
    # non-strict: WARN printed but exit OK
    code_lenient = preflight.run(beats, 30.0,
                                 rotation_cache_dir=tmp_path / "rot",
                                 strict=False)
    out_lenient = capsys.readouterr().out
    assert code_lenient == 0
    assert "caption_window" in out_lenient
    assert "WARN" in out_lenient

    # strict: same input now fails
    code_strict = preflight.run(beats, 30.0,
                                rotation_cache_dir=tmp_path / "rot",
                                strict=True)
    assert code_strict == 1


def test_preflight_catches_in_out_ordering(tmp_path, capsys):
    """in_t >= out_t fails as ERROR."""
    src = tmp_path / "fake.mp4"
    src.write_bytes(b"")
    beats = [
        _beat("backwards", 30.0, src, in_t=20.0, out_t=10.0),
    ]
    code = preflight.run(beats, 30.0, rotation_cache_dir=tmp_path / "rot")
    out = capsys.readouterr().out
    assert code == 1
    assert "in_out_ordering" in out
