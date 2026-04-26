"""Smoke tests for cvs_lib.beat_builder CLI.

Argparse is exercised directly. The full render path is mocked because
moviepy's write_videofile is slow and exercised end-to-end elsewhere.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from cvs_lib import beat_builder


def test_argparse_rejects_missing_required():
    """argparse exits 2 when required args are missing."""
    with pytest.raises(SystemExit):
        beat_builder.main(["--source", "x.mp4"])


def test_argparse_parses_full_invocation(tmp_path):
    """A complete CLI invocation routes through to ChromeRenderer +
    build_beat_clip without crashing. We mock the heavy pieces so the
    test stays fast."""
    palette = tmp_path / "brand"
    palette.mkdir()
    # Minimal palette + dummy logo.
    (palette / "palette.json").write_text(
        '{"colors": {"white": {"rgb": [255,255,255]}, '
        '"deep_magenta": {"rgb": [200,40,120]}, '
        '"sky_blue": {"rgb": [80,180,230]}, '
        '"soft_pink": {"rgb": [255,180,200]}, '
        '"near_black": {"rgb": [10,10,15]}}, '
        '"fonts": {"headline": {"path": "C:/Windows/Fonts/arial.ttf"}, '
        '"body": {"path": "C:/Windows/Fonts/arial.ttf"}}}',
        encoding="utf-8",
    )
    (palette / "logo_wide_alpha.png").write_bytes(b"x")  # placeholder

    out_mp4 = tmp_path / "out.mp4"

    fake_clip = MagicMock()
    fake_clip.duration = 7.0
    fake_clip.size = (1080, 1920)
    fake_clip.write_videofile = MagicMock()

    with patch("cvs_lib.beat_builder.build_beat_clip", return_value=fake_clip), \
         patch("cvs_lib.beat_builder.ChromeRenderer") as mock_chrome_cls:
        mock_chrome = MagicMock()
        mock_chrome.render_beat.return_value = b""  # not actually used
        mock_chrome_cls.return_value = mock_chrome
        rc = beat_builder.main([
            "--source", "anything.mp4",
            "--in-t", "13", "--out-t", "20",
            "--chip", "RELEASED",
            "--out", str(out_mp4),
            "--brand-dir", str(palette),
            "--rotation-cache-dir", str(tmp_path / "rot"),
        ])
    assert rc == 0
    fake_clip.write_videofile.assert_called_once()


def test_missing_palette_returns_one(tmp_path, capsys):
    """If the brand dir has no palette.json, the CLI exits 1 with a
    helpful stderr message."""
    rc = beat_builder.main([
        "--source", "x.mp4", "--in-t", "0", "--out-t", "1",
        "--brand-dir", str(tmp_path / "missing"),
        "--out", str(tmp_path / "out.mp4"),
    ])
    assert rc == 1
    err = capsys.readouterr().err
    assert "missing palette" in err
