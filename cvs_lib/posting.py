"""Posting metadata helper: <reel>.posting.md sidecar per rendered reel.

Saves the manual step of typing platform captions, hashtags, and alt
text for every TikTok/Instagram/Bluesky/Facebook post. Reads the
existing `output/<pipeline>/manifest.json` (from `mpc_render_all.py`)
plus AST-parses each reel's source script to extract:
  - module docstring (synopsis + beat ladder)
  - CTA_HEADLINE / CTA_SUBHEAD / CTA_RALLY constants
  - reel slug from the filename

No module imports — AST only — so this stays cheap and side-effect-free
even if a reel's import-time code is heavy.

Pure renderers in this module; the driver lives in
`scripts/mpc_make_posting.py`.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional


# Brand-level hashtags applied to every MPC reel. Per-reel hashtags
# layered on top of these.
DEFAULT_BASE_HASHTAGS = [
    "MichiganProgressive",
    "ImmigrantRights",
    "AbolishICE",
    "IceOutRomulus",
]

# Per-platform character / hashtag-count guidance summarised in the
# checklist. Numbers are platform soft caps, not hard limits.
PLATFORM_NOTES = {
    "TikTok": "caption ~150 chars, 3-5 hashtags",
    "Instagram": "caption ~200 chars, up to 30 hashtags (but stick to ~10)",
    "Bluesky": "300 char hard limit, hashtags inline",
    "Facebook": "no hashtag culture; 1-2 sentences max",
}


@dataclass
class ReelMeta:
    """Pure data extracted from a reel script + manifest entry."""
    slug: str                     # filesystem stem, e.g. "abolish_ice_congress"
    title: str                    # docstring first line (or slug derived)
    synopsis: str = ""            # docstring body up to "Beats:" / "Run:"
    cta_headline: str = ""
    cta_subhead: str = ""
    cta_url: str = ""
    cta_handle_line: str = ""
    cta_rally: str = ""
    duration_s: float = 0.0
    output_path: str = ""
    cover_path: str = ""
    size_bytes: int = 0
    cover_size_bytes: int = 0
    width: int = 0
    height: int = 0


# --------------------------------------------------------------------------- #
# AST extraction
# --------------------------------------------------------------------------- #

# Constants we lift verbatim from the script as string assignments.
_STRING_CONSTANTS = {
    "CTA_HEADLINE",
    "CTA_SUBHEAD",
    "CTA_RALLY",
}


def _literal_str(node: ast.AST) -> Optional[str]:
    """Return the literal string value of an AST node, or None if it's
    not a simple string constant. Skips computed values like
    `_CTA_RALLY_CFG.get(...)` — those resolve at runtime, not parse time."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def parse_reel_script(script_path: Path) -> Dict:
    """Parse a reel script and return `{docstring, constants}`.

    `constants` maps each found name in `_STRING_CONSTANTS` to its
    literal string value. Names assigned to non-literal expressions
    (e.g. `CTA_URL = _CTA_RALLY_CFG.get("url", ...)`) are skipped — the
    caller layers in computed values from a separate config read.
    """
    src = script_path.read_text(encoding="utf-8")
    tree = ast.parse(src)
    docstring = ast.get_docstring(tree) or ""
    constants: Dict[str, str] = {}
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for tgt in node.targets:
                if (
                    isinstance(tgt, ast.Name)
                    and tgt.id in _STRING_CONSTANTS
                ):
                    val = _literal_str(node.value)
                    if val is not None:
                        constants[tgt.id] = val
    return {"docstring": docstring, "constants": constants}


# --------------------------------------------------------------------------- #
# Docstring parsing
# --------------------------------------------------------------------------- #

# Common heading lines in MPC docstrings that mark where the prose
# synopsis ends and structured detail begins. Splitting on the first
# match keeps the synopsis tight.
_SYNOPSIS_TERMINATORS = (
    "Beats (",       # "Beats (30s):"
    "Beats:",
    "NOTE on",
    "Output:",
    "Run:",
    "Notes:",
)


def docstring_title_and_synopsis(docstring: str) -> tuple:
    """Split a docstring into `(title, synopsis)`.

    Title is the first non-blank line stripped of trailing punctuation.
    Synopsis is everything between title and the first synopsis
    terminator (a `Beats:` / `Output:` / `Run:` block heading), with
    blank-line-only paragraph breaks preserved.
    """
    if not docstring:
        return ("", "")
    lines = docstring.strip().splitlines()
    title = ""
    body_start = 0
    for i, ln in enumerate(lines):
        if ln.strip():
            title = ln.strip().rstrip(".")
            body_start = i + 1
            break
    body_lines: List[str] = []
    for ln in lines[body_start:]:
        if any(ln.lstrip().startswith(t) for t in _SYNOPSIS_TERMINATORS):
            break
        body_lines.append(ln)
    synopsis = "\n".join(body_lines).strip()
    return (title, synopsis)


# --------------------------------------------------------------------------- #
# Hashtags
# --------------------------------------------------------------------------- #

def hashtags_for_reel(
    cta_headline: str,
    base: Optional[List[str]] = None,
) -> List[str]:
    """Brand base + a tag derived from CTA_HEADLINE (CamelCase, no
    spaces, no punctuation). De-duplicated, base order preserved with
    headline tag appended last."""
    out = list(base) if base is not None else list(DEFAULT_BASE_HASHTAGS)
    if cta_headline:
        # "ABOLISH ICE" -> "AbolishIce" -> "AbolishICE" already in base?
        # Title-case each word so "ABOLISH ICE" -> "AbolishIce" looks
        # natural; if the result collides with a base entry (case
        # insensitive), don't add.
        words = re.findall(r"[A-Za-z]+", cta_headline)
        if words:
            tag = "".join(w.title() for w in words)
            if tag.lower() not in (h.lower() for h in out):
                out.append(tag)
    return out


# --------------------------------------------------------------------------- #
# Composite render
# --------------------------------------------------------------------------- #

def _fmt_size(b: int) -> str:
    if not b:
        return "?"
    if b < 1024 * 1024:
        return f"{b / 1024:.0f} KB"
    return f"{b / (1024 * 1024):.1f} MB"


def render_posting_md(
    meta: ReelMeta,
    *,
    base_hashtags: Optional[List[str]] = None,
) -> str:
    """Compose the full posting markdown sidecar."""
    title = meta.title or meta.slug
    parts = [f"# {title}", ""]

    # File block
    file_lines = []
    if meta.output_path:
        size_part = f" ({meta.duration_s:.0f}s, {_fmt_size(meta.size_bytes)})" \
            if meta.duration_s else f" ({_fmt_size(meta.size_bytes)})"
        file_lines.append(f"- **File**: `{meta.output_path}`{size_part}")
    if meta.cover_path:
        file_lines.append(
            f"- **Cover**: `{meta.cover_path}` "
            f"({_fmt_size(meta.cover_size_bytes)})"
        )
    if meta.width and meta.height:
        file_lines.append(f"- **Dimensions**: {meta.width}x{meta.height}")
    if file_lines:
        parts.extend(file_lines)
        parts.append("")

    # Synopsis (from docstring body)
    if meta.synopsis:
        parts.append("## Synopsis")
        parts.append("")
        parts.append(meta.synopsis)
        parts.append("")

    # Suggested caption
    parts.append("## Suggested caption")
    parts.append("")
    caption = _suggest_caption(meta)
    parts.append(caption)
    parts.append("")
    if meta.cta_url:
        parts.append(f"Donate: {meta.cta_url}")
        parts.append("")

    # Hashtags
    parts.append("## Hashtags")
    parts.append("")
    tags = hashtags_for_reel(meta.cta_headline, base=base_hashtags)
    parts.append(" ".join(f"#{t}" for t in tags))
    parts.append("")

    # Alt text
    parts.append("## Alt text")
    parts.append("")
    parts.append(_suggest_alt_text(meta))
    parts.append("")

    # Posting checklist
    parts.append("## Posting checklist")
    parts.append("")
    for platform, note in PLATFORM_NOTES.items():
        parts.append(f"- [ ] **{platform}** — {note}")
    parts.append("")

    return "\n".join(parts)


def _suggest_caption(meta: ReelMeta) -> str:
    """Two-sentence caption: synopsis lead-in + CTA call. Editorial
    will rewrite, but the structure is correct out of the gate."""
    headline = meta.cta_headline or meta.title or meta.slug
    subhead = meta.cta_subhead or "Stand with us"
    # Lead from the title (which is the docstring first line — already
    # an editorial summary). Keep it short.
    lead = meta.title or meta.slug.replace("_", " ").title()
    if lead.endswith("."):
        lead = lead[:-1]
    return (
        f"{lead}.\n"
        f"\n"
        f"{headline.title()} — {subhead.title()}."
    )


def _suggest_alt_text(meta: ReelMeta) -> str:
    """Functional accessibility alt-text: who, where, what's on screen.
    Keep under ~250 chars (screen-reader sweet spot)."""
    rally = meta.cta_rally.replace("_", " ").title() if meta.cta_rally else ""
    parts = []
    if rally:
        parts.append(f"{rally} rally video.")
    if meta.title:
        title = meta.title.rstrip(".")
        parts.append(f"{title}.")
    headline = meta.cta_headline.title() if meta.cta_headline else ""
    if headline:
        parts.append(f"Headline: {headline}.")
    if not parts:
        parts.append(meta.slug.replace("_", " ").title())
    return " ".join(parts)


# --------------------------------------------------------------------------- #
# Composer
# --------------------------------------------------------------------------- #

def build_meta(
    script_path: Path,
    manifest_entry: Optional[Dict] = None,
    *,
    cta_config: Optional[Dict] = None,
) -> ReelMeta:
    """Compose a ReelMeta from a reel's script + its manifest entry.

    `cta_config` is the parsed `mpc/cta.json`. When the script's
    `CTA_RALLY` constant is set and the rally exists in the config,
    URL + handle_line are merged in (mirrors what the reel resolves
    at import time).
    """
    parsed = parse_reel_script(script_path)
    title, synopsis = docstring_title_and_synopsis(parsed["docstring"])
    consts = parsed["constants"]
    rally = consts.get("CTA_RALLY", "")
    cta_url = ""
    cta_handle_line = ""
    if cta_config and rally:
        rally_cfg = (cta_config.get("rallies") or {}).get(rally, {})
        defaults = cta_config.get("defaults", {})
        cta_url = rally_cfg.get("url", defaults.get("url", ""))
        cta_handle_line = rally_cfg.get(
            "handle_line", defaults.get("handle_line", ""),
        )
    m = manifest_entry or {}
    return ReelMeta(
        slug=script_path.stem.replace("mpc_ep_", ""),
        title=title,
        synopsis=synopsis,
        cta_headline=consts.get("CTA_HEADLINE", ""),
        cta_subhead=consts.get("CTA_SUBHEAD", ""),
        cta_url=cta_url,
        cta_handle_line=cta_handle_line,
        cta_rally=rally,
        duration_s=float(m.get("duration_s", 0.0)),
        output_path=m.get("output", ""),
        cover_path=m.get("cover", ""),
        size_bytes=int(m.get("size_bytes", 0)),
        cover_size_bytes=int(m.get("cover_size_bytes", 0)),
        width=int(m.get("width", 0)),
        height=int(m.get("height", 0)),
    )
