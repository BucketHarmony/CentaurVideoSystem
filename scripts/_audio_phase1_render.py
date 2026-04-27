"""Phase 1 SCRATCH — render A/B WAVs for audible sign-off.

For each cc_flora and cc_hookshot script, render two WAVs:
- A: existing inline pad output (extracted + executed in isolation)
- B: canonical primitive output, no per-episode editorial events
- AB: stitched A + 0.5s gap + B, single WAV the user listens to

Outputs land in `tests/cvs_lib/fixtures/audio_compare/`.

Phase 1 sign-off: user listens to AB.wav per episode; signs off when
the canonical primitive can produce the same base sound the existing
inline code produces. Per-episode editorial events (act tensions,
ep04 battery-death, ep05 freeze) are deliberately absent from B —
they go in via callers in Phase 4.

Run:
    python E:/AI/CVS/scripts/_audio_phase1_render.py
"""

from __future__ import annotations

import ast
import sys
import wave
from pathlib import Path
from typing import Callable

import numpy as np
import scipy.signal

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from cvs_lib._audio_canonical_draft import (
    ambient_pad, chime_layer, cottagecore_pad_canonical, sting, MOODS,
)

SCRIPTS_DIR = Path("E:/AI/CVS/scripts")
OUT_DIR = Path("E:/AI/CVS/tests/cvs_lib/fixtures/audio_compare")
OUT_DIR.mkdir(parents=True, exist_ok=True)
SR = 44100


# --------------------------------------------------------------------------- #
# Episode metadata: which script, which duration, which chime schedule.
# Phase 0 audit gives us all of these (lines 296–313 in
# _audio_drift_audit.md).
# --------------------------------------------------------------------------- #

CC_FLORA_EPISODES = [
    # (slug, script_name, duration, chime_schedule, mood, drone_gain_scale)
    # Schedules pulled from Phase 0 audit (lines 296-313 of
    # _audio_drift_audit.md). For some episodes the audit only lists
    # the start/end span; we fill in evenly-spaced stops.
    ("ep02", "cc_flora_ep02_bigger_room.py", 30.0, [
        (0.1, 880), (2.5, 1108.73), (5.0, 1318.51), (7.5, 880), (10.0, 1108.73),
        (12.5, 1318.51), (15.0, 880), (17.5, 1108.73), (20.0, 1318.51),
        (22.5, 880), (25.0, 1108.73), (27.5, 1318.51),
    ], "cottagecore_warm", 1.0),

    ("ep03", "cc_flora_ep03_moon.py", 30.0, [
        (0.1, 880), (2.5, 1108.73), (5.0, 1318.51), (7.5, 880),
        (10.0, 1108.73), (12.5, 1318.51), (15.0, 880), (17.5, 1108.73),
        (20.0, 1318.51), (22.5, 880), (25.0, 1108.73), (27.5, 1318.51),
    ], "cottagecore_warm", 1.0),

    ("ep04", "cc_flora_ep04_carried_home.py", 30.0, [
        (0.1, 880), (3.0, 1108.73), (6.0, 1318.51), (8.5, 880),
        (13.5, 880), (15.5, 1108.73), (18.0, 1318.51), (22.0, 880), (27.0, 1108.73),
    ], "cottagecore_warm", 1.0),

    ("ep05", "cc_flora_ep05_same_frame.py", 30.0, [
        (0.1, 880), (3.0, 1108.73), (6.0, 1318.51), (9.0, 880),
        (16.5, 880), (19.0, 1108.73), (21.5, 1318.51), (24.0, 880),
        (26.5, 1108.73), (29.0, 1318.51),
    ], "cottagecore_warm", 1.0),

    ("ep06", "cc_flora_ep06_three_centimeters.py", 30.0, [
        (0.1, 880), (3.0, 1108.73), (6.0, 1318.51), (9.0, 880),
        (12.0, 1108.73), (15.0, 1318.51), (18.0, 880), (21.0, 1108.73),
        (22.5, 1108.73), (24.0, 1318.51), (27.0, 880),
    ], "cottagecore_warm", 1.0),

    ("ep07", "cc_flora_ep07_ping_pong.py", 30.0, [
        (0.1, 880), (3.0, 1108.73), (6.0, 1318.51), (9.0, 880),
        (12.0, 1108.73), (15.5, 1318.51), (18.5, 880), (21.5, 1108.73),
        (24.5, 1318.51), (27.5, 880),
    ], "cottagecore_warm", 1.0),

    ("ep08", "cc_flora_ep08_the_threshold.py", 30.0, [
        (0.1, 880), (3.0, 1108.73), (6.0, 1318.51), (9.0, 880),
        (12.0, 1108.73), (16.0, 1318.51), (19.0, 880), (22.0, 1108.73),
        (25.0, 1318.51), (28.0, 880),
    ], "cottagecore_warm", 1.0),

    ("ep09", "cc_flora_ep09_the_hallway.py", 30.0, [
        (0.1, 880), (3.0, 1108.73), (6.0, 1318.51), (9.0, 880),
        (12.0, 1108.73), (15.0, 1318.51), (18.0, 880), (20.0, 1108.73),
        (22.0, 1318.51),
    ], "cottagecore_warm", 1.0),

    ("ep10", "cc_flora_ep10_the_patience_of_rooms.py", 30.0, [
        (0.1, 880), (3.0, 1108.73), (5.5, 880), (8.0, 1318.51),
        (10.5, 880), (13.5, 1108.73), (16.0, 1318.51), (19.0, 880),
        (22.0, 1108.73), (25.5, 880),
    ], "cottagecore_warm", 1.0),

    ("flora_30s", "cc_flora_30s.py", 30.0, [
        (0.1, 880), (2.5, 1108.73), (5.0, 1318.51), (7.5, 880),
        (10.0, 1108.73), (12.5, 1318.51), (15.0, 880), (17.5, 1108.73),
        (20.0, 1318.51), (22.5, 880), (25.0, 1108.73), (27.5, 1318.51),
        (29.0, 880),
    ], "cottagecore_warm", 1.0),

    ("masterpiece", "cc_flora_masterpiece.py", 30.0, [
        (3.0, 880), (8.0, 1108.73), (15.0, 1318.51), (22.0, 880), (27.0, 1108.73),
    ], "cottagecore_masterpiece", 1.0),
]

CC_HOOKSHOT_EPISODES = [
    ("cc_hookshot", "cc_hookshot.py", 30.0,
     [(3.0, 880), (7.5, 1046.5), (12.0, 1318.5), (16.5, 880),
      (21.0, 1318.5), (25.5, 1046.5)],
     "hookshot_attention", 1.0, True),

    ("cc_hookshot_faith", "cc_hookshot_faith.py", 30.0,
     [(5.0, 587.33), (12.0, 698.46), (20.0, 880), (28.0, 587.33)],
     "hookshot_grief", 1.0, True),

    ("cc_hookshot_toast", "cc_hookshot_toast.py", 30.0,
     [(4.0, 880), (9.0, 1046.5), (15.0, 1318.5), (21.0, 880), (27.0, 1046.5)],
     "hookshot_attention", 1.0, False),  # toast: no octave on chimes
]


# --------------------------------------------------------------------------- #
# Extract `generate_ambient_pad` from a script and run it in isolation
# --------------------------------------------------------------------------- #

def extract_function_source(script_path: Path, fn_name: str) -> str:
    """Pull a top-level function definition's source from a script file."""
    src = script_path.read_text(encoding="utf-8")
    tree = ast.parse(src)
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == fn_name:
            return ast.get_source_segment(src, node)
    raise LookupError(f"{fn_name} not found in {script_path.name}")


def extract_helper_functions(script_path: Path,
                              skip: set[str] = frozenset({"generate_ambient_pad"})) -> str:
    """Extract every top-level function definition from a script EXCEPT
    those in `skip`. Used to make helper functions like ease_out_np
    available when we exec the pad function in isolation."""
    src = script_path.read_text(encoding="utf-8")
    tree = ast.parse(src)
    chunks = []
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name not in skip:
            chunks.append(ast.get_source_segment(src, node))
    return "\n\n".join(chunks)


def run_inline_pad(script_path: Path, duration: float) -> np.ndarray:
    """Execute the script's generate_ambient_pad in a clean namespace
    and return the pad as float32 numpy array (no WAV writing).

    Patches OUTPUT_DIR + the wave-write block by monkey-replacing
    the function body to return the array before writing.
    """
    helpers_src = extract_helper_functions(script_path)
    fn_src = extract_function_source(script_path, "generate_ambient_pad")
    # Strip the WAV-writing tail; just keep the synth + return the array.
    # Simpler hack: exec in a namespace where `wave.open(...)` becomes a
    # no-op, then re-extract `pad` from the local namespace by editing
    # the function to return `pad` after the normalization step.
    #
    # Even simpler: inject a sentinel — replace the `out = OUTPUT_DIR /...`
    # line and everything after with `return pad`. Use a regex-style
    # split on the OUTPUT_DIR write block.
    src_lines = fn_src.split("\n")
    cut = None
    # Find the first line that references OUTPUT_DIR or wave.open (start of WAV-write tail)
    for i, line in enumerate(src_lines):
        stripped = line.lstrip()
        if stripped.startswith("#"):
            continue
        if "OUTPUT_DIR" in line or "wave.open" in line:
            cut = i
            break
    if cut is None:
        raise RuntimeError(f"Couldn't find WAV-write marker in {script_path.name}")
    fn_src = "\n".join(src_lines[:cut]) + "\n    return pad\n"

    # Build the namespace.
    ns: dict = {
        "np": np,
        "scipy": scipy,
        "scipy.signal": scipy.signal,
        "wave": wave,
    }
    # Define helpers (ease_out_np, etc.) before the pad function.
    if helpers_src:
        try:
            exec(helpers_src, ns)
        except Exception:
            pass  # Some helpers reference unimported deps; we only need pad's deps.
    # The function source uses `scipy.signal` directly, which works
    # because we put scipy in the namespace.
    exec(fn_src, ns)
    fn = ns["generate_ambient_pad"]
    # Some scripts (masterpiece) use `sample_rate`; others use `sr`.
    import inspect
    params = inspect.signature(fn).parameters
    sr_kwarg = "sr" if "sr" in params else "sample_rate"
    pad = fn(duration, **{sr_kwarg: SR})
    return np.asarray(pad, dtype=np.float64)


# --------------------------------------------------------------------------- #
# Canonical render
# --------------------------------------------------------------------------- #

def run_canonical(
    duration: float,
    schedule,
    mood: str,
    *,
    drone_gain_scale: float = 1.0,
    apply_lowpass: bool = True,
) -> np.ndarray:
    """Same shape as cc_flora's `generate_ambient_pad`, no editorial."""
    return cottagecore_pad_canonical(
        duration, schedule, mood=mood, sr=SR,
        drone_gain_scale=drone_gain_scale, apply_lowpass=apply_lowpass,
    )


def run_hookshot_canonical(
    duration: float,
    schedule,
    mood: str,
    *,
    chime_octave: bool = True,
) -> np.ndarray:
    """Hookshot pad: sting + ambient_pad (no envelope) + chime_layer
    + lowpass on whole mix + master normalize."""
    pad = ambient_pad(duration, mood=mood, sr=SR, apply_envelope=False)
    chimes = chime_layer(
        duration, schedule, mood=mood, sr=SR,
        octave_gain_override=None if chime_octave else 0.0,
    )
    s = sting(duration, mood=mood, t_start=0.0, sr=SR)
    # Hookshot envelope: linspace shape
    from cvs_lib._audio_canonical_draft import pad_envelope
    env = pad_envelope(duration, sr=SR, variant="hookshot_linspace")
    pad = (pad + chimes) * env + s

    sos = scipy.signal.butter(
        MOODS[mood].lowpass_order,
        MOODS[mood].lowpass_hz,
        "low", fs=SR, output="sos",
    )
    pad = scipy.signal.sosfilt(sos, pad)
    pad = pad / (np.max(np.abs(pad)) + 1e-8) * 0.7  # hookshot peak ceiling
    return pad


# --------------------------------------------------------------------------- #
# WAV writers
# --------------------------------------------------------------------------- #

def write_wav(arr: np.ndarray, path: Path, *, sr: int = SR) -> None:
    arr = np.asarray(arr, dtype=np.float64)
    arr = arr / (np.max(np.abs(arr)) + 1e-8) * 0.95  # peak normalize
    int16 = (arr * 32767).astype(np.int16)
    with wave.open(str(path), "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(int16.tobytes())


def stitch_ab(a: np.ndarray, b: np.ndarray, *, gap_s: float = 0.5,
              sr: int = SR) -> np.ndarray:
    gap = np.zeros(int(gap_s * sr), dtype=np.float64)
    return np.concatenate([a, gap, b])


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #

def main():
    print(f"Rendering Phase 1 A/B fixtures into {OUT_DIR}")
    print()

    for slug, script_name, dur, schedule, mood, drone_scale in CC_FLORA_EPISODES:
        path = SCRIPTS_DIR / script_name
        print(f"=== {slug} ({script_name}, {dur}s, mood={mood}) ===")
        try:
            a = run_inline_pad(path, dur)
        except Exception as e:
            print(f"  [skip A] {type(e).__name__}: {e}")
            continue
        b = run_canonical(dur, schedule, mood, drone_gain_scale=drone_scale)
        write_wav(a, OUT_DIR / f"{slug}_A_inline.wav")
        write_wav(b, OUT_DIR / f"{slug}_B_canonical.wav")
        write_wav(stitch_ab(a, b), OUT_DIR / f"{slug}_AB.wav")
        # Compute base similarity: Pearson correlation A vs B as float64
        # If editorial inserts are absent in B, the residual A-B is them.
        a64 = a.astype(np.float64) / (np.max(np.abs(a)) + 1e-8)
        b64 = b.astype(np.float64) / (np.max(np.abs(b)) + 1e-8)
        n = min(len(a64), len(b64))
        corr = float(np.corrcoef(a64[:n], b64[:n])[0, 1])
        residual_rms = float(np.sqrt(np.mean((a64[:n] - b64[:n]) ** 2)))
        print(f"  A peak {np.max(np.abs(a)):.4f}  B peak {np.max(np.abs(b)):.4f}  "
              f"corr {corr:.4f}  residual_rms {residual_rms:.4f}")

    print()
    for slug, script_name, dur, schedule, mood, drone_scale, chime_oct \
            in CC_HOOKSHOT_EPISODES:
        path = SCRIPTS_DIR / script_name
        print(f"=== {slug} ({script_name}, {dur}s, mood={mood}) ===")
        # cc_hookshot's audio fn is generate_bed_audio, returns stereo
        # — different shape. Skip A capture for now and just emit B.
        b = run_hookshot_canonical(dur, schedule, mood, chime_octave=chime_oct)
        write_wav(b, OUT_DIR / f"{slug}_B_canonical.wav")
        print(f"  B peak {np.max(np.abs(b)):.4f}")
        print(f"  B WAV: {(OUT_DIR / f'{slug}_B_canonical.wav').name}")

    print()
    print("Sign-off: listen to *_AB.wav per cc_flora episode.")
    print("First half = existing inline pad. After 0.5s gap = canonical primitive.")
    print("They should be ~indistinguishable EXCEPT for per-episode editorial events")
    print("(act tensions, ep04 battery-death, ep05 freeze) that are absent in B by")
    print("design — those go in via Phase 4 callers, not the primitive.")


if __name__ == "__main__":
    main()
