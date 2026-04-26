"""Expanded preflight failure-mode coverage.

Complements test_smoke.py with the variants the basic suite doesn't
cover: missing path key, multi-shot list specs, run_or_exit semantics.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from cvs_lib import preflight


def _beat(slug, dur, spec):
    return (slug, dur, "minor", slug.upper(), spec)


def test_missing_path_key_reports_error(tmp_path, capsys):
    """A spec dict with no 'path' key must surface a clean ERROR."""
    beats = [
        _beat("a", 7.0, {}),
        _beat("b", 23.0, {}),
    ]
    code = preflight.run(beats, 30.0, rotation_cache_dir=tmp_path / "rot")
    out = capsys.readouterr().out
    assert code == 1
    assert "spec_missing_path" in out


def test_multi_shot_list_spec_checks_each_path(tmp_path, capsys):
    """Romulus-style list-of-shots: every shot's path is validated."""
    src = tmp_path / "exists.mp4"
    src.write_bytes(b"x")
    missing = tmp_path / "missing.mp4"
    beats = [
        _beat("multi", 30.0, [
            {"path": src, "in_t": 0.0, "out_t": 4.0},
            {"path": missing, "in_t": 4.0, "out_t": 30.0},
        ]),
    ]
    code = preflight.run(beats, 30.0, rotation_cache_dir=tmp_path / "rot")
    out = capsys.readouterr().out
    assert code == 1
    assert "missing.mp4" in out


def test_run_or_exit_calls_sys_exit(tmp_path, monkeypatch):
    """run_or_exit must propagate non-zero codes via sys.exit."""
    monkeypatch.chdir(tmp_path)
    beats = [_beat("a", 5.0, {})]  # both errors: missing path + sum mismatch
    with pytest.raises(SystemExit) as ei:
        preflight.run_or_exit(beats, 30.0,
                              rotation_cache_dir=tmp_path / "rot")
    assert ei.value.code == 1


def test_negative_in_t_reports_error(tmp_path, capsys):
    """Negative in_t/out_t is an error."""
    src = tmp_path / "x.mp4"
    src.write_bytes(b"")
    beats = [_beat("a", 30.0, {"path": src, "in_t": -1.0, "out_t": 5.0})]
    code = preflight.run(beats, 30.0, rotation_cache_dir=tmp_path / "rot")
    out = capsys.readouterr().out
    assert code == 1
    assert "negative_time" in out
