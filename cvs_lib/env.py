"""Tiny .env-style loader.

Extracted from scripts/mpc_ep_north_lake.py:413-423 (and 7 identical
copies across the MPC reel suite).
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Union

PathLike = Union[str, Path]


def load_env(path: PathLike = "E:/AI/CVS/.env") -> Dict[str, str]:
    """Parse a `.env`-style file into a dict.

    Lines: `KEY=value`. Blank lines and `#` comments ignored. Surrounding
    quotes (single or double) stripped from values. Missing file returns
    an empty dict (not an error).
    """
    p = Path(path)
    if not p.exists():
        return {}
    out: Dict[str, str] = {}
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        out[k.strip()] = v.strip().strip('"').strip("'")
    return out
