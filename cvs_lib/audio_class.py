"""Audio segment classifier — speech / chant / song / ambient / silence.

Sliding-window AudioSet tagging via PANNs (CNN14, AudioSet-pretrained).
Each window's 527-class score vector is collapsed into our 5 editorial
classes by summing across hand-picked label groups; adjacent same-class
windows are merged into segments.

Why PANNs and not YAMNet:
- The plan called for YAMNet, which lives in the TensorFlow ecosystem.
  The repo already runs PyTorch (faster-whisper, CUDA), so installing
  TF would have ~1GB of new wheels for a model that's functionally
  equivalent to PANNs CNN14 on AudioSet ontology.
- PANNs is `pip install panns_inference`, ~330 MB checkpoint, runs on
  the existing torch/CUDA install. AudioSet labels are identical
  (527 vs YAMNet's 521 same-ontology classes).
- First-run note: panns_inference uses `wget` to fetch the checkpoint
  and labels CSV; on Windows we manually placed both at
  `~/panns_data/{Cnn14_mAP=0.431.pth, class_labels_indices.csv}`.

5-class mapping (editorial taxonomy):
    speech   — solo vocal language, prose form. Election speech,
               narration, conversation. Excludes group "hubbub" babble.
    chant    — rhythmic group vocalization without melody. "ABOLISH
               ICE!" call-and-response. Excludes singing.
    song     — melodic group vocalization. The "We are locked inside"
               rally song; choir, a capella, vocal music.
    ambient  — crowd noise, applause, room tone, footsteps, traffic.
               Default for "audio is happening but no salient class."
    silence  — Silence label dominant, OR all four other classes
               below threshold (rare on phone-mic outdoor recordings).
"""

from __future__ import annotations

import os
import warnings
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple, Union

import numpy as np

PathLike = Union[str, Path]

# AudioSet label IDs grouped into our 5 editorial classes.
# IDs from the AudioSet ontology (class_labels_indices.csv); these are
# stable across PANNs / YAMNet / other AudioSet-pretrained models.
LABEL_GROUPS: Dict[str, List[int]] = {
    "speech": [
        0,    # Speech
        1,    # Male speech, man speaking
        2,    # Female speech, woman speaking
        3,    # Child speech, kid speaking
        4,    # Conversation
        5,    # Narration, monologue
        7,    # Speech synthesizer
    ],
    "chant": [
        8,    # Shout
        13,   # Children shouting
        14,   # Screaming
        30,   # Chant
        31,   # Mantra (acoustically identical to call/response chant)
    ],
    "song": [
        27,   # Singing
        28,   # Choir
        32,   # Male singing
        33,   # Female singing
        34,   # Child singing
        35,   # Synthetic singing
        36,   # Rapping
        137,  # Music
        254,  # Vocal music
        255,  # A capella
        266,  # Song
    ],
    "ambient": [
        66,   # Cheering
        67,   # Applause
        69,   # Crowd
        70,   # Hubbub, speech noise, speech babble
        506,  # Inside, small room
        507,  # Inside, large room or hall
        508,  # Inside, public space
    ],
    "silence": [
        500,  # Silence
    ],
}

CLASSES: Tuple[str, ...] = tuple(LABEL_GROUPS.keys())

# Below this summed-confidence floor, we call it `ambient` rather than
# whichever raw class won — most rally clips have *some* signal in
# every group; only true silence drops below 0.05 across all four
# foreground classes.
AMBIENT_FALLBACK_THRESHOLD = 0.05

# Editorial override: if AudioSet's "Chant" label fires above this
# floor in a window, the window is `chant` regardless of which class
# group summed higher. Rationale: rally chants ("ABOLISH ICE!")
# trigger Music + Choir + Singing strongly because they're rhythmic
# group vocalization, but the Chant label specifically separates them
# from melodic song. On Phase 2 validation, this single rule moved
# 170030 (pure ABOLISH ICE chant) from misclassified-as-song to
# correctly chant without affecting any other clip — Chant on the
# melodic 170245 was 0.10 (below threshold), Chant on 170030 mid-chant
# was 0.27.
CHANT_PRIORITY_LABEL = 30   # AudioSet "Chant"
CHANT_PRIORITY_THRESHOLD = 0.20


# --------------------------------------------------------------------------- #
# Model loader (cached singleton)
# --------------------------------------------------------------------------- #

_MODEL = None


def load_model(device: str = "cuda"):
    """Load CNN14 once and cache. Subsequent calls return the same object."""
    global _MODEL
    if _MODEL is not None:
        return _MODEL
    # panns_inference prints a `wget` not-found error on first run when
    # the checkpoint is already present; suppress noisy stderr.
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        from panns_inference import AudioTagging
        _MODEL = AudioTagging(checkpoint_path=None, device=device)
    return _MODEL


# --------------------------------------------------------------------------- #
# Audio loading
# --------------------------------------------------------------------------- #

def load_audio_32k_mono(path: PathLike) -> np.ndarray:
    """Load any media file as 32 kHz mono float32 — PANNs' native input rate."""
    import librosa
    y, _ = librosa.load(str(path), sr=32000, mono=True)
    return y.astype(np.float32)


# --------------------------------------------------------------------------- #
# Per-window classification
# --------------------------------------------------------------------------- #

def _summed_class_scores(clipwise: np.ndarray) -> Dict[str, float]:
    """Sum AudioSet scores within each editorial class group."""
    return {
        cls: float(sum(clipwise[i] for i in ids))
        for cls, ids in LABEL_GROUPS.items()
    }


def _pick_class(scores: Dict[str, float]) -> Tuple[str, float]:
    """Pick winning editorial class with the ambient fallback."""
    # If silence is the highest, return silence directly.
    if scores["silence"] > max(scores["speech"], scores["chant"],
                                scores["song"], scores["ambient"]):
        return "silence", scores["silence"]
    # Otherwise pick the highest of the foreground classes; if none
    # clear the floor, call it ambient.
    fg = {k: v for k, v in scores.items() if k != "silence"}
    cls, conf = max(fg.items(), key=lambda kv: kv[1])
    if conf < AMBIENT_FALLBACK_THRESHOLD and cls != "ambient":
        return "ambient", scores["ambient"]
    return cls, conf


def classify_window(audio_32k: np.ndarray, model) -> Tuple[str, float, Dict[str, float]]:
    """Classify one audio window. Returns (class, confidence, all_scores).

    `audio_32k` must be 32 kHz mono float32. Empty/silent windows
    return ('silence', 1.0, {...}) without invoking the model.
    """
    if len(audio_32k) == 0 or float(np.max(np.abs(audio_32k))) < 1e-4:
        return "silence", 1.0, {c: 0.0 for c in CLASSES}
    clipwise, _embed = model.inference(audio_32k[None, :])
    scores = _summed_class_scores(clipwise[0])
    # Chant priority: rally chants trigger Singing/Music/Choir hard
    # because they're harmonic group vocalization. The Chant label is
    # the cleanest separator from melodic song.
    chant_score = float(clipwise[0][CHANT_PRIORITY_LABEL])
    if chant_score >= CHANT_PRIORITY_THRESHOLD:
        return "chant", scores["chant"], scores
    cls, conf = _pick_class(scores)
    return cls, conf, scores


# --------------------------------------------------------------------------- #
# Sliding-window classification + segment merging
# --------------------------------------------------------------------------- #

def classify_clip(path: PathLike, *,
                  window_s: float = 1.5,
                  hop_s: float = 0.75,
                  device: str = "cuda",
                  model=None) -> List[Dict]:
    """Sliding-window classify a media file. Returns merged segments:

        [{t0, t1, class, confidence, scores}, ...]

    `scores` is the per-window summed scores for all 5 classes — keep
    it for downstream tuning. `confidence` is the winning class's
    summed score on the window that voted it (max across the merged
    span — represents the strongest evidence for the call).

    Default window/hop = 1.5/0.75s ⇒ 50% overlap, ~1.3 calls per
    second of source. Tune `window_s` up for more stable calls on
    speech, down for tighter chant/song boundary resolution.
    """
    if model is None:
        model = load_model(device)
    y = load_audio_32k_mono(path)
    sr = 32000
    win_n = int(window_s * sr)
    hop_n = int(hop_s * sr)

    # Per-window calls.
    calls: List[Tuple[float, float, str, float]] = []
    pos = 0
    while pos < len(y):
        end = min(pos + win_n, len(y))
        # Skip windows under 0.4s to avoid degenerate inference at
        # tail-end (CNN14 expects >~1s of audio).
        if end - pos >= int(0.4 * sr):
            cls, conf, _ = classify_window(y[pos:end], model)
            t0 = pos / sr
            t1 = end / sr
            calls.append((t0, t1, cls, conf))
        if end == len(y):
            break
        pos += hop_n

    # Merge adjacent same-class windows into one segment.
    if not calls:
        return []
    segments: List[Dict] = []
    cur_t0, cur_t1, cur_cls, cur_conf = calls[0]
    for t0, t1, cls, conf in calls[1:]:
        if cls == cur_cls:
            cur_t1 = max(cur_t1, t1)
            cur_conf = max(cur_conf, conf)
        else:
            segments.append({
                "t0": round(cur_t0, 3), "t1": round(cur_t1, 3),
                "class": cur_cls, "confidence": round(cur_conf, 3),
            })
            cur_t0, cur_t1, cur_cls, cur_conf = t0, t1, cls, conf
    segments.append({
        "t0": round(cur_t0, 3), "t1": round(cur_t1, 3),
        "class": cur_cls, "confidence": round(cur_conf, 3),
    })

    # Drop sub-0.5s segments by absorbing them into the next neighbour.
    # Tiny flips between speech↔ambient on transitions are noise; we
    # want segments that downstream readers can meaningfully filter on.
    return _absorb_short_segments(segments, min_dur=0.5)


def _absorb_short_segments(segments: List[Dict], min_dur: float) -> List[Dict]:
    """Fold segments shorter than `min_dur` into the next (or previous)
    neighbour. Stabilizes the boundary noise."""
    if len(segments) <= 1:
        return segments
    cleaned: List[Dict] = []
    for s in segments:
        dur = s["t1"] - s["t0"]
        if dur < min_dur and cleaned:
            # Extend previous segment to swallow this short one.
            cleaned[-1]["t1"] = s["t1"]
        else:
            cleaned.append(dict(s))
    # Second pass: if the FIRST segment is short, absorb it into the
    # second (which is now cleaned[0]) — handled by re-extending t0 down.
    if len(cleaned) > 1 and (cleaned[0]["t1"] - cleaned[0]["t0"]) < min_dur:
        cleaned[1]["t0"] = cleaned[0]["t0"]
        cleaned = cleaned[1:]
    return cleaned


# --------------------------------------------------------------------------- #
# Summary helpers (one tag per clip, dominant class + dominant fraction)
# --------------------------------------------------------------------------- #

def dominant_class(segments: Sequence[Dict]) -> Tuple[str, float]:
    """Return (class_name, fraction) for the editorial class covering
    the most clip seconds. Used by downstream search ('show me the
    song clips')."""
    if not segments:
        return "ambient", 0.0
    by_class: Dict[str, float] = {c: 0.0 for c in CLASSES}
    total = 0.0
    for s in segments:
        dur = float(s["t1"]) - float(s["t0"])
        by_class[s["class"]] = by_class.get(s["class"], 0.0) + dur
        total += dur
    if total <= 0:
        return "ambient", 0.0
    cls = max(by_class.items(), key=lambda kv: kv[1])[0]
    return cls, by_class[cls] / total


def salient_classes(segments: Sequence[Dict],
                    min_fraction: float = 0.05) -> List[str]:
    """Return all classes that cover at least `min_fraction` of the
    clip's segmented duration.

    AudioSet can't reliably separate group-singing from group-chanting
    on every window — a rally chant clip will have segments labelled
    as both `chant` and `song`. Tagging with every class that fires
    above the floor (rather than only `dominant_class`) means the
    chant clip surfaces in both 'find chant clips' and 'find song
    clips' searches, which matches editorial reality (a rally chant
    *is* group singing in audio terms; the user picks the framing).
    """
    if not segments:
        return []
    by_class: Dict[str, float] = {c: 0.0 for c in CLASSES}
    total = 0.0
    for s in segments:
        dur = float(s["t1"]) - float(s["t0"])
        by_class[s["class"]] = by_class.get(s["class"], 0.0) + dur
        total += dur
    if total <= 0:
        return []
    return sorted(c for c, d in by_class.items() if d / total >= min_fraction)
