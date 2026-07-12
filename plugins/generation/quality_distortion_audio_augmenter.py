from __future__ import annotations

import hashlib
from collections import defaultdict
from pathlib import Path

import numpy as np

from utils.audio_io import load_audio


PARAMETERS = [
    {
        "name": "downsample_ratio",
        "type": "float",
        "label": "降采样比例",
        "default": 0.6,
        "min": 0.1,
        "max": 1.0,
        "options": [],
        "description": "降采样后再升采样的比例",
        "required": False,
    },
    {
        "name": "quantize_bits",
        "type": "int",
        "label": "量化位深",
        "default": 6,
        "min": 2,
        "max": 32,
        "options": [],
        "description": "量化比特深度，越低失真越明显",
        "required": False,
    },
    {
        "name": "distortion_drive",
        "type": "float",
        "label": "失真驱动量",
        "default": 0.45,
        "min": 0.0,
        "max": 1.0,
        "options": [],
        "description": "tanh 饱和失真驱动量",
        "required": False,
    },
    {
        "name": "max_variants_per_source",
        "type": "int",
        "label": "单源最大变体数",
        "default": 20,
        "min": 1,
        "max": 100,
        "options": [],
        "description": "限制每个源音频的增强数量，避免产生大量近重复样本",
        "required": False,
    },
]


def run(payload: dict, context) -> dict:
    try:
        import soundfile as sf
        from scipy.signal import resample_poly
    except ImportError:
        return {"ok": False, "error_code": "MISSING_DEPENDENCY"}

    parameters = payload.get("parameters", {}) or {}
    output_dir = Path(payload.get("output", {}).get("output_dir") or ".")
    output_dir.mkdir(parents=True, exist_ok=True)

    samples = payload.get("input", {}).get("samples", []) or []
    if not samples:
        return {"ok": False, "error_code": "NO_INPUT_SAMPLES"}

    requested_count = max(1, int(payload.get("target_count") or len(samples)))
    base_ds_ratio = _clamp_float(parameters.get("downsample_ratio", parameters.get("ds_ratio", 0.6)), 0.1, 1.0)
    base_bits = _clamp_int(parameters.get("quantize_bits", parameters.get("bits", 6)), 2, 16)
    base_drive = _clamp_float(parameters.get("distortion_drive", parameters.get("drive", 0.45)), 0.0, 1.0)
    max_per_source = _clamp_int(parameters.get("max_variants_per_source", 20), 1, 100)
    target_count = min(requested_count, len(samples) * max_per_source)

    outputs = []
    read_errors = []
    audio_cache = {}
    variants_by_source = defaultdict(int)
    signatures_by_source = defaultdict(set)
    hashes_by_source = defaultdict(set)
    duplicate_retries = 0
    rng = np.random.default_rng()
    for index in range(target_count):
        if context.is_cancel_requested():
            return {"ok": False, "error_code": "CANCELLED"}
        candidates = []
        for item in samples:
            item_path = Path(item.get("sample_path") or item.get("path") or item.get("file_path") or "")
            if variants_by_source[str(item_path.resolve())] < max_per_source:
                candidates.append((item, item_path))
        if not candidates:
            break
        sample, sp = candidates[index % len(candidates)]
        try:
            cache_key = str(sp.resolve())
            if cache_key not in audio_cache:
                audio_cache[cache_key] = load_audio(sp, mono=True)
            y, sr = audio_cache[cache_key]
        except Exception as exc:
            read_errors.append(f"{sp}: {exc}")
            continue

        accepted = None
        for _attempt in range(6):
            ds_ratio = _clamp_float(base_ds_ratio + rng.uniform(-0.15, 0.15), 0.1, 1.0)
            bits = _clamp_int(base_bits + int(rng.integers(-3, 4)), 2, 16)
            drive = _clamp_float(base_drive + rng.uniform(-0.25, 0.25), 0.0, 1.0)
            signature = (round(ds_ratio, 2), bits, round(drive, 2))
            if signature in signatures_by_source[cache_key]:
                duplicate_retries += 1
                continue

            target_len = len(y)
            y_out = y.astype(np.float32).copy()
            if ds_ratio < 0.999:
                ratio_steps = max(1, min(100, int(round(ds_ratio * 100))))
                y_ds = resample_poly(y_out, ratio_steps, 100)
                y_out = resample_poly(y_ds, 100, ratio_steps)
                y_out = _match_len(y_out, target_len)

            levels = float((2 ** bits) - 1)
            y_out = np.round(y_out * levels) / levels
            if drive > 0:
                drive_gain = 1.0 + drive * 8.0
                y_out = np.tanh(drive_gain * y_out) / (np.tanh(drive_gain) + 1e-6)
            y_out = np.asarray(y_out, dtype=np.float32)
            pcm_hash = hashlib.sha256(y_out.tobytes()).hexdigest()
            if pcm_hash in hashes_by_source[cache_key]:
                duplicate_retries += 1
                continue
            accepted = (y_out, ds_ratio, bits, drive, signature, pcm_hash)
            break
        if accepted is None:
            continue
        y_out, ds_ratio, bits, drive, signature, pcm_hash = accepted

        out = output_dir / f"{sp.stem}_distort_{index:04d}.wav"
        sf.write(str(out), y_out, sr)
        variants_by_source[cache_key] += 1
        signatures_by_source[cache_key].add(signature)
        hashes_by_source[cache_key].add(pcm_hash)
        outputs.append(
            {
                "source_sample_id": sample.get("id"),
                "output_path": str(out),
                "relative_path": out.name,
                "metadata": {
                    "method": "quality_distortion",
                    "downsample_ratio": ds_ratio,
                    "quantize_bits": bits,
                    "distortion_drive": drive,
                    "pcm_sha256": pcm_hash,
                },
                "status": "created",
            }
        )
        context.set_progress((index + 1) * 100 / target_count, f"Distort {index + 1}/{target_count}")

    if not outputs and read_errors:
        return {
            "ok": False,
            "error_code": "AUDIO_READ_FAILED",
            "message": read_errors[0],
            "outputs": [],
            "logs": read_errors,
        }
    logs = list(read_errors)
    if requested_count > target_count:
        logs.append(f"Requested {requested_count}, limited to {target_count} by max_variants_per_source={max_per_source}.")
    if duplicate_retries:
        logs.append(f"Rejected {duplicate_retries} duplicate or near-duplicate candidates.")
    return {"ok": True, "outputs": outputs, "logs": logs}


def _match_len(y, target):
    if len(y) == target:
        return y
    if len(y) > target:
        return y[:target]
    return np.pad(y, (0, target - len(y)), mode="constant")


def _clamp_float(value, low, high):
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        parsed = low
    return max(low, min(parsed, high))


def _clamp_int(value, low, high):
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = low
    return max(low, min(parsed, high))
