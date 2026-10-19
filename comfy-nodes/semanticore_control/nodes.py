"""Measurement nodes: turn a graph's output into numbers any verifier can re-run.

These exist because the workshop's rule is that claims must be re-derivable text,
not impressions (docs/verification-protocol.md). A restoration that "looks
sharper" is a hunch; a restoration whose ink coverage, tonal histogram and edge
energy moved in a measured way is a claim.
"""

import json

import numpy as np

MAX_SAMPLES = 4096  # bounded, strided summary so reruns of one file agree


def _as_batch(image):
    """Normalise a ComfyUI IMAGE tensor (or array-like) to float32 [B,H,W,C]."""
    data = image
    for attr in ("detach", "cpu"):
        if hasattr(data, attr):
            data = getattr(data, attr)()
    arr = np.asarray(data, dtype=np.float32)
    if arr.ndim == 2:
        arr = arr[None, ..., None]
    elif arr.ndim == 3:
        arr = arr[None, ...]
    elif arr.ndim != 4:
        raise ValueError("expected a 2D/3D/4D image, got shape %r" % (arr.shape,))
    if arr.shape[-1] not in (1, 3, 4):
        raise ValueError("expected channel count 1/3/4 last, got shape %r" % (arr.shape,))
    return np.nan_to_num(arr, nan=0.0, posinf=1.0, neginf=0.0)


def _luma(arr):
    if arr.shape[-1] == 1:
        return arr[..., 0]
    return (0.2126 * arr[..., 0] + 0.7152 * arr[..., 1] + 0.0722 * arr[..., 2])


def _hist(lum, bins=16):
    counts = np.histogram(lum, bins=bins, range=(0.0, 1.0))[0]
    total = float(counts.sum()) or 1.0
    return [round(float(c) / total, 5) for c in counts]


def stats(frame):
    """Deterministic region statistics for one HxWxC frame, as JSON-safe numbers."""
    lum = _luma(frame)
    flat = lum.reshape(-1)
    if flat.size > MAX_SAMPLES:  # fixed stride: same input, same sample set
        flat = flat[:: flat.size // MAX_SAMPLES + 1]
    ink = lum < 0.5
    rows, cols = ink.any(axis=1), ink.any(axis=0)
    dy = np.diff(lum, axis=0) if lum.shape[0] > 1 else np.zeros((0,) + lum.shape[1:])
    dx = np.diff(lum, axis=1) if lum.shape[1] > 1 else np.zeros_like(lum)
    return {
        "shape": list(frame.shape),
        "luma_mean": round(float(lum.mean()), 6),
        "luma_p05": round(float(np.percentile(lum, 5)), 6),
        "luma_p50": round(float(np.percentile(lum, 50)), 6),
        "luma_p95": round(float(np.percentile(lum, 95)), 6),
        "luma_hist16": _hist(lum),
        "ink_coverage": round(float(ink.mean()), 6),
        "bbox_ink": ([int(np.argmax(rows)), int(len(rows) - np.argmax(rows[::-1])),
                      int(np.argmax(cols)), int(len(cols) - np.argmax(cols[::-1]))]
                     if ink.any() else None),
        "edge_energy": round(float(np.abs(dy).mean() + np.abs(dx).mean()) / 2.0, 6),
        "saturation_mean": round(float((frame.max(axis=-1) - frame.min(axis=-1)).mean()), 6),
        "pure_white_frac": round(float((lum > 0.98).mean()), 6),
        "pure_black_frac": round(float((lum < 0.02).mean()), 6),
        "sample_pixels": int(flat.size),
    }


class SemanticoreImageStats:
    """Measure an image batch and emit the numbers as a string.

    Wire it after LoadImage, or after any restoration round, and read the value
    from the prompt's history: one graph then yields both the picture (for the
    eyes) and the metric (for the ledger).
    """

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"image": ("IMAGE",)}}

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("stats_json",)
    FUNCTION = "measure"
    CATEGORY = "semanticore/measurement"
    DESCRIPTION = ("Deterministic luma/ink/edge/saturation statistics for an "
                   "image batch, as JSON text.")

    def measure(self, image):
        batch = _as_batch(image)
        frames = [stats(batch[i]) for i in range(batch.shape[0])]
        payload = frames[0] if len(frames) == 1 else frames
        return (json.dumps(payload, sort_keys=True),)
