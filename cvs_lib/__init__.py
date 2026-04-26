"""CVS Video Pipeline shared library.

Extracted from copy-pasted infrastructure across the MPC reel suite
(scripts/mpc_ep_*.py). See E:/AI/CVS/mpc/BACKLOG.md for the migration
roadmap and design decisions.

Public modules:
    env             — load_env() for .env-style files
    preflight       — pre-render validators
    index           — load mpc/index/clips/<stem>.json transcripts/scenes
    captions        — caption-event spec → MoviePy clips, with auto-fill
    audio           — chord synthesis, sidechain duck, VO duck envelope
    elevenlabs_tts  — TTS generation + caching
    moviepy_helpers — rotation cache, footage prep, audio extraction
    mpc_chrome      — MPC brand chrome (banner, chip, well, CTA)
    preview         — still-frame preview render
    beat_builder    — single-beat render CLI
"""

__version__ = "0.1.0"
