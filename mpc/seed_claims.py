"""Status report for mpc/claims/<reel_slug>.json files.

Prints current content_hash for every MPC reel, compares it against the
hash recorded in its claims file (if any), and reports state:

  OK         — claims file exists, hash matches.
  STALE      — claims file exists but hash drifted (re-verify required).
  NEW        — no claims file yet (verifier never run).

The legacy `--sign-as <name>` flag was removed 2026-04-26. Claims files
are now written by the `mpc-claims-verifier` subagent — run via Claude
Code, not this script.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
CLAIMS = ROOT / "mpc" / "claims"

sys.path.insert(0, str(ROOT))

REELS = [
    ("mpc_ep_north_lake.py", "north_lake"),
    ("mpc_ep_we_dont_back_down.py", "we_dont_back_down"),
    ("mpc_ep_romulus.py", "romulus"),
    ("mpc_ep_abolish_ice_congress.py", "abolish_ice_congress"),
    ("mpc_ep_follow_the_money.py", "follow_the_money"),
    ("mpc_ep_people_power.py", "people_power"),
    ("mpc_ep_ten_weeks.py", "ten_weeks"),
    ("mpc_ep_detroit_knows.py", "detroit_knows"),
]


def _load_reel_beats(script_path):
    """Import a reel script's module body without running main(), and
    return its BEATS list. Romulus uses _preview_beats() instead.

    Exposed for the mpc-claims-verifier subagent to compute hashes via:
        from mpc.seed_claims import _load_reel_beats
    """
    src = Path(script_path).read_text(encoding="utf-8")
    spec = importlib.util.spec_from_loader(
        f"reel_{Path(script_path).stem}", loader=None
    )
    mod = importlib.util.module_from_spec(spec)
    mod.__file__ = str(script_path)
    code = compile(src, str(script_path), "exec")
    try:
        exec(code, mod.__dict__)
    except SystemExit:
        pass
    beats = getattr(mod, "BEATS", None)
    if beats is None:
        bp = getattr(mod, "_preview_beats", None)
        if bp is not None:
            beats = bp()
    return beats


def main():
    from cvs_lib import factcheck
    CLAIMS.mkdir(parents=True, exist_ok=True)

    print(f"{'reel':<24} {'state':<8} {'hash':<18} {'verified_by'}")
    print("-" * 80)

    for filename, slug in REELS:
        script = SCRIPTS / filename
        if not script.exists():
            print(f"{slug:<24} {'MISSING':<8}")
            continue

        try:
            beats = _load_reel_beats(script)
        except Exception as e:
            print(f"{slug:<24} {'IMPORT_FAIL':<8} {type(e).__name__}: {e}")
            continue

        if beats is None:
            print(f"{slug:<24} {'NO_BEATS':<8}")
            continue

        h = factcheck._content_hash(beats)
        claims_file = CLAIMS / f"{slug}.json"

        existing = {}
        if claims_file.exists():
            try:
                existing = json.loads(claims_file.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                existing = {}

        prev_hash = existing.get("content_hash", "")
        verifier = existing.get("verified_by", "")
        if not claims_file.exists():
            state = "NEW"
        elif prev_hash != h:
            state = "STALE"
        else:
            state = "OK"

        print(f"{slug:<24} {state:<8} {h:<18} {verifier or '(unverified)'}")


if __name__ == "__main__":
    main()
