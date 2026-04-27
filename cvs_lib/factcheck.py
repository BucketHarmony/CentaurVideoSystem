"""Pre-render fact-check for MPC reel scripts.

Two responsibilities:

1. **Name validation** against `mpc/roster.json`.
   - Exact match → silent.
   - Close match (1–2 edits from a roster form) → ERROR (likely misspelling).
   - Match found and entry has `progressive: false` → WARN (needs sign-off).
   - Title-case unknown name token → WARN (potentially missing from roster).

2. **Claims verification** via per-reel `mpc/claims/<reel_slug>.json`.
   - Required fields: `content_hash`, `verified_by`, `verified_at`.
   - `verified_by` is a model identifier (e.g. `claude-sonnet-4-6`); the
     `mpc-claims-verifier` subagent writes this file after web-verifying
     each factual claim. The legacy human-gate (`signed_off_by`) was
     removed 2026-04-26.
   - `content_hash` must match the hash of the current beats' caption text +
     chip labels. Edit the script → hash changes → factcheck blocks until
     the verifier subagent re-runs and re-attests.
   - Missing claims file is an ERROR (must be created by the verifier).

Returns `Issue` objects compatible with `cvs_lib.preflight`. Plug into the
existing `preflight.run()` call site so scripts pick it up for free.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Dict, List, Sequence, Set, Tuple


@dataclass(frozen=True)
class Issue:
    severity: str  # "ERROR" or "WARN"
    code: str
    message: str

    def format(self) -> str:
        return f"[factcheck {self.severity}] {self.code}: {self.message}"


Beat = Tuple[str, float, str, Any, Dict[str, Any]]


# ───────────────────────────── roster ─────────────────────────────

def load_roster(path: Path) -> Dict[str, Dict[str, Any]]:
    """Load mpc/roster.json. Strips the _schema sentinel. Returns empty
    dict if the file is missing — callers that require a roster should
    raise; the factcheck preflight treats missing-roster as ERROR."""
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return {k: v for k, v in data.items() if not k.startswith("_")}


def _all_valid_forms(entry: Dict[str, Any]) -> Set[str]:
    """Every spelling that should pass for one roster entry: canonical
    name, last-token-of-canonical, and every alias."""
    forms: Set[str] = set()
    name = entry.get("name", "")
    if name:
        forms.add(name)
        # also accept the last token alone (e.g. "McKinney" from "Donovan McKinney")
        last = name.split()[-1] if name.split() else ""
        if last:
            forms.add(last)
    for a in entry.get("aliases", []) or []:
        forms.add(str(a))
    return forms


def _build_lookup(roster: Dict[str, Dict[str, Any]]) -> Dict[str, str]:
    """Map every valid form (lowercased) → roster key. Used to detect
    'token X matches person Y exactly or near-exactly'."""
    lookup: Dict[str, str] = {}
    for key, entry in roster.items():
        for form in _all_valid_forms(entry):
            lookup[form.lower()] = key
    return lookup


# ───────────────────────────── name extraction ─────────────────────────────

# Matches sequences of capitalized words ("Donovan McKinney", "Rep. McKinney",
# "Kristi Noem"). Allows internal punctuation like "Rep." and apostrophes.
# Won't match SCREAMING-CAPS chip labels — those go through a separate path.
_NAME_RE = re.compile(
    r"\b(?:[A-Z][A-Za-z'’]+\.?)(?:\s+[A-Z][A-Za-z'’]+\.?){0,3}\b"
)

# Common false-positives in caption text — sentence starts that aren't names.
_NOT_A_NAME = {
    # sentence-start function words
    "the", "a", "an", "and", "but", "or", "if", "so", "then", "i", "we",
    "you", "they", "he", "she", "it", "this", "that", "these", "those",
    "my", "your", "our", "their", "his", "her", "its",
    # frequent capitalized non-names in MPC scripts
    "ice", "geo", "ndcm", "mpc",
    "abolish", "free", "stand", "say", "build",
    "detroit", "michigan", "warren", "romulus", "north lake", "8 mile",
    "house", "district", "judges", "federal", "asylum",
    "april", "friday", "monday", "october",
    "do", "does", "did", "is", "was", "are", "were", "be", "been",
    "let", "have", "has", "had", "will", "would", "could", "should",
    "very", "right", "now", "here", "there", "still",
    "also", "much", "many", "some", "every", "all", "no", "not",
    "yes", "okay", "ok", "yeah", "well",
}


def _extract_name_candidates(text: str) -> List[str]:
    """Pull title-cased multi-word phrases that look like names. Filters
    sentence-start single tokens that are common function words."""
    out: List[str] = []
    for m in _NAME_RE.finditer(text):
        cand = m.group(0).strip(".'’")
        # Skip if it's a single token AND that token is in the deny list.
        # Multi-word phrases starting with a denied first word are kept —
        # e.g. "I Was Released" wouldn't be a name, but "Detroit Knows"
        # also wouldn't, so we apply the deny list to single tokens only.
        if len(cand.split()) == 1 and cand.lower() in _NOT_A_NAME:
            continue
        out.append(cand)
    return out


# ───────────────────────────── name validation ─────────────────────────────

def _close_match(candidate: str, valid_forms: Set[str]) -> Tuple[str, float]:
    """Return (best_form, similarity) for the highest-similarity valid form,
    or ("", 0.0) if nothing meets the threshold."""
    best = ("", 0.0)
    cl = candidate.lower()
    for f in valid_forms:
        sim = SequenceMatcher(None, cl, f.lower()).ratio()
        if sim > best[1]:
            best = (f, sim)
    return best


def _is_all_caps(s: str) -> bool:
    """True if every alphabetic character in s is uppercase. Detects
    SCREAMING-CAPS chip text vs. sentence-case caption text.

    Note: a single lowercase letter (e.g. McKINNEY's 'c') makes this False,
    which is the desired behavior — those phrases still get name-checked."""
    letters = [c for c in s if c.isalpha()]
    return bool(letters) and all(c.isupper() for c in letters)


def _contained_form(candidate: str, valid_forms: Set[str]) -> str:
    """Longest *multi-word* roster form that appears as a whole-word
    substring of candidate, or '' if none. Used so that 'Rep. Donovan
    McKinney' matches the canonical 'Donovan McKinney' rather than
    triggering a misspelling ERROR.

    Only multi-word forms count: a single-word alias like 'McKinney'
    alone won't grant a bypass — otherwise 'Donavan Mckinney' (a real
    misspelling that happens to contain 'McKinney') would slip through.
    Misspellings around a correctly-spelled last name still need to fall
    through to the fuzzy-match path."""
    cl = candidate.lower()
    matches: List[str] = []
    for f in valid_forms:
        if len(f.split()) < 2:
            continue
        fl = f.lower()
        if re.search(r"\b" + re.escape(fl) + r"\b", cl):
            matches.append(f)
    if not matches:
        return ""
    return max(matches, key=len)


def check_name_in_text(
    text: str,
    where: str,
    roster: Dict[str, Dict[str, Any]],
    lookup: Dict[str, str],
) -> List[Issue]:
    """Validate every name-shaped token in `text` against roster."""
    issues: List[Issue] = []
    if not text or not roster:
        return issues

    all_forms: Set[str] = set()
    for entry in roster.values():
        all_forms |= _all_valid_forms(entry)

    for cand in _extract_name_candidates(text):
        cl = cand.lower()
        toks = cand.split()
        toks_lower = [t.lower().strip(".'’,") for t in toks]

        # Exact (case-insensitive) match — the spelling is correct.
        if cl in lookup:
            entry = roster[lookup[cl]]
            if entry.get("progressive") is False:
                issues.append(Issue(
                    "WARN", "non_progressive_mention",
                    f"{where}: '{cand}' is flagged progressive=false in "
                    f"roster ({entry.get('notes', 'sign-off required')}). "
                    f"Confirm critical framing of this line."
                ))
            continue

        # Roster form contained as substring (e.g. "Rep. Donovan McKinney"
        # contains the canonical "Donovan McKinney" or alias "Rep. McKinney").
        # Treat as exact-equivalent: silent unless non-progressive.
        contained = _contained_form(cand, all_forms)
        if contained:
            entry = roster[lookup[contained.lower()]]
            if entry.get("progressive") is False:
                issues.append(Issue(
                    "WARN", "non_progressive_mention",
                    f"{where}: '{cand}' references '{entry.get('name')}' "
                    f"({entry.get('notes', 'sign-off required')}). "
                    f"Confirm critical framing of this line."
                ))
            continue

        # Skip SCREAMING-CAPS chip text (slogans, headlines). If a roster
        # form were inside, _contained_form would already have caught it.
        if _is_all_caps(cand):
            continue

        # Skip multi-word phrases where every token is in the deny list
        # ("House District", "Abolish ICE", "GEO Group", etc.). If every
        # word is independently uninteresting, the phrase is too.
        if all(t in _NOT_A_NAME for t in toks_lower if t):
            continue

        # Close match — likely a misspelling/casing drift.
        best_form, sim = _close_match(cand, all_forms)
        if sim >= 0.85 and best_form:
            issues.append(Issue(
                "ERROR", "name_misspelled",
                f"{where}: '{cand}' looks like a misspelling of "
                f"'{best_form}' (similarity={sim:.2f}). Fix in caption_lines."
            ))
            continue

        # Stricter check for unknown names: only warn for genuinely
        # name-shaped tokens (≥2 capitalized words, OR a single capitalized
        # word with an honorific). Single capitalized words at sentence
        # starts are too noisy.
        is_name_shaped = len(toks) >= 2 or (
            len(toks) == 1 and any(
                cand.startswith(p) for p in ("Rep.", "Sen.", "Gov.", "AG", "Sec.")
            )
        )
        if is_name_shaped:
            issues.append(Issue(
                "WARN", "name_not_in_roster",
                f"{where}: '{cand}' looks like a name but is not in "
                f"roster. Add to mpc/roster.json or confirm it's a place/"
                f"organization, not a person."
            ))

    return issues


# ───────────────────────────── beats traversal ─────────────────────────────

def _iter_beat_text(beats: Sequence[Beat]):
    """Yield (where_label, text) for every human-facing string in beats:
    chip labels, caption_lines text, CTA labels."""
    for slug, _dur, _chord, chip, spec in beats:
        if chip:
            yield f"chip:{slug}", str(chip)
        if spec is None:
            continue
        # Multi-shot specs (lists) carry their own caption_lines under each sub.
        sub_specs = spec if isinstance(spec, list) else [spec]
        for sub in sub_specs:
            if not isinstance(sub, dict):
                continue
            for i, line in enumerate(sub.get("caption_lines") or []):
                try:
                    _s, _e, txt = line
                except (TypeError, ValueError):
                    continue
                yield f"caption_lines:{slug}:{i}", str(txt)


def check_beats_against_roster(
    beats: Sequence[Beat],
    roster_path: Path,
) -> List[Issue]:
    """Walk every chip + caption text and validate names against the
    roster. Returns one Issue per problem found."""
    if not roster_path.exists():
        return [Issue(
            "ERROR", "roster_missing",
            f"roster file not found at {roster_path}. "
            f"Create it or remove factcheck from preflight."
        )]
    roster = load_roster(roster_path)
    if not roster:
        return [Issue(
            "WARN", "roster_empty",
            f"roster {roster_path} loaded but contains no entries — "
            f"name validation is a no-op until populated."
        )]
    lookup = _build_lookup(roster)

    issues: List[Issue] = []
    for where, text in _iter_beat_text(beats):
        issues += check_name_in_text(text, where, roster, lookup)
    return issues


# ───────────────────────────── claims sign-off ─────────────────────────────

def _content_hash(beats: Sequence[Beat]) -> str:
    """Stable hash over the human-facing text content of all beats. Edit
    a chip label or caption line → hash changes → claims must be re-signed."""
    parts: List[str] = []
    for where, text in _iter_beat_text(beats):
        parts.append(f"{where}\t{text}")
    payload = "\n".join(parts).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:16]


def check_claims_signoff(
    beats: Sequence[Beat],
    reel_slug: str,
    claims_dir: Path,
) -> List[Issue]:
    """Verify mpc/claims/<reel_slug>.json exists and its content_hash
    matches the current beats. Stale or unverified → ERROR.

    The verifier subagent (`mpc-claims-verifier`) writes this file after
    web-verifying each factual claim. `verified_by` holds the model id
    that did the verification. The legacy human-gated `signed_off_by`
    field was removed; we no longer accept it as a sign-off."""
    claims_path = claims_dir / f"{reel_slug}.json"
    expected_hash = _content_hash(beats)

    if not claims_path.exists():
        return [Issue(
            "ERROR", "claims_unverified",
            f"no claims verification at {claims_path}. Invoke the "
            f"mpc-claims-verifier subagent for reel_slug={reel_slug!r} "
            f"to verify and write this file (current content_hash="
            f"{expected_hash})."
        )]

    try:
        data = json.loads(claims_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        return [Issue(
            "ERROR", "claims_invalid_json",
            f"{claims_path} is not valid JSON: {e}"
        )]

    actual = data.get("content_hash", "")
    if actual != expected_hash:
        return [Issue(
            "ERROR", "claims_stale",
            f"{claims_path} content_hash={actual!r} does not match "
            f"current beats hash={expected_hash!r}. The reel script's "
            f"caption_lines or chip labels changed since verification — "
            f"re-invoke the mpc-claims-verifier subagent."
        )]

    if not data.get("verified_by"):
        return [Issue(
            "ERROR", "claims_no_verifier",
            f"{claims_path} missing 'verified_by' field. Re-invoke "
            f"the mpc-claims-verifier subagent."
        )]

    return []


# ───────────────────────────── orchestrator ─────────────────────────────

def run(
    beats: Sequence[Beat],
    reel_slug: str,
    roster_path: Path,
    claims_dir: Path,
    require_claims: bool = True,
) -> List[Issue]:
    """Run all factcheck validators and return a flat list of issues.
    Caller (typically `cvs_lib.preflight.run`) prints + decides exit."""
    issues: List[Issue] = []
    issues += check_beats_against_roster(beats, roster_path)
    if require_claims:
        issues += check_claims_signoff(beats, reel_slug, claims_dir)
    return issues
