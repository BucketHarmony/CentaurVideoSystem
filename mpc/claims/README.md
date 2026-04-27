# MPC Claims Verification

Each `<reel_slug>.json` in this directory is a verification record
written by the `mpc-claims-verifier` subagent: every factual claim in
the reel's caption_lines + chip text was identified and web-verified
before this file landed.

**The legacy human sign-off (`signed_off_by: "<name>"`) was removed
2026-04-26.** Verification is now LLM-driven, not human-gated.

## File schema

```json
{
  "content_hash": "16-char sha256 prefix of beats text",
  "verified_by": "claude-sonnet-4-6",
  "verified_at": "2026-04-26",
  "claims_reviewed": [
    {
      "claim": "Donovan McKinney represents MI House District 14.",
      "verdict": "supported",
      "sources": ["https://house.mi.gov/..."],
      "notes": ""
    }
  ],
  "summary": "5 claims reviewed: 4 supported, 1 uncertain. Cleared for render."
}
```

Verdicts: `supported` | `unsupported` | `uncertain`.

## How factcheck uses it

`cvs_lib.factcheck.check_claims_signoff()` is invoked by
`cvs_lib.preflight.run()` whenever the reel script passes `reel_slug=...`.
It verifies:

1. The file exists. Missing → `claims_unverified` ERROR.
2. `content_hash` matches a fresh hash of the reel's beats. Drift means
   the captions/chips have been edited since the last verification →
   `claims_stale` ERROR.
3. `verified_by` is non-empty (must name the model that did verification).

A failed check exits the render with code 1.

## How to verify a reel

In Claude Code, ask:

> Verify the claims for `<reel_slug>` before we render.

The assistant will launch the `mpc-claims-verifier` subagent. The agent:

1. Loads the script's BEATS, extracts factual claims from chips +
   caption_lines.
2. Computes the current `content_hash`.
3. WebSearches authoritative sources (.gov, AP, MLive, Detroit Free
   Press, etc.) for each claim.
4. Records verdict + sources per claim.
5. Writes `mpc/claims/<reel_slug>.json` if everything verifies, or
   refuses (and tells you what failed) if 2+ claims come back
   unsupported.

For batch operation across all reels, ask:

> Verify all MPC reels.

Eight verifier agents run in parallel; report comes back when all
finish.

## Status report

```
python mpc/seed_claims.py
```

Prints current content_hash for each reel and whether its claims file
is OK / STALE / NEW (missing).

## When to re-verify

Every time you edit a `caption_lines` tuple or chip label:

```bash
python scripts/mpc_ep_<reel>.py            # render attempt → claims_stale ERROR
# Ask Claude in this session:
#   "Re-verify the claims for <reel>."
# Subagent re-runs, writes fresh claims file.
python scripts/mpc_ep_<reel>.py            # render now passes
```
