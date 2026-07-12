from __future__ import annotations

import hashlib
from collections import defaultdict
from pathlib import Path

import numpy as np

from utils.audio_io import load_audio


PARAMETERS = [
    {"name": "target_channel", "type": "select", "label": "目标声道", "default": "auto", "min": None, "max": None, "options": ["auto", "mono", "stereo"], "description": "目标声道配置", "required": False},
    {"name": "mix_strategy", "type": "select", "label": "混合策略", "default": "avg", "min": None, "max": None, "options": ["avg", "max", "min", "random_weight"], "description": "多声道转单声道时的混合策略", "required": False},
    {"name": "dither", "type": "float", "label": "抖动幅度", "default": 0.002, "min": 0.0, "max": 0.1, "options": [], "description": "声道抖动噪声幅度", "required": False},
    {"name": "swap_probability", "type": "float", "label": "声道交换概率", "default": 0.2, "min": 0.0, "max": 1.0, "options": [], "description": "左右声道交换概率", "required": False},
    {"name": "max_variants_per_source", "type": "int", "label": "单源最大变体数", "default": 20, "min": 1, "max": 100, "options": [], "description": "限制每个源音频的声道配置变体数量", "required": False},
]


def run(payload: dict, context) -> dict:
    try:
        import soundfile as sf
    except ImportError:
        return {"ok": False, "error_code": "MISSING_DEPENDENCY"}
    parameters = payload.get("parameters", {}) or {}
    output_dir = Path(payload.get("output", {}).get("output_dir") or ".")
    output_dir.mkdir(parents=True, exist_ok=True)
    samples = payload.get("input", {}).get("samples", []) or []
    if not samples: return {"ok": False, "error_code": "NO_INPUT_SAMPLES"}

    requested_count = max(1, int(payload.get("target_count") or len(samples)))
    target_channel = str(parameters.get("target_channel", "auto") or "auto").lower()
    if target_channel not in {"auto", "mono", "stereo"}: target_channel = "auto"
    mix_strategy = str(parameters.get("mix_strategy", "avg") or "avg").lower()
    dither = _clamp_float(parameters.get("dither", 0.002), 0.0, 0.1)
    swap_probability = _clamp_float(parameters.get("swap_probability", 0.2), 0.0, 1.0)
    max_per_source = _clamp_int(parameters.get("max_variants_per_source", 20), 1, 100)
    target_count = min(requested_count, len(samples) * max_per_source)

    outputs = []; read_errors = []; audio_cache = {}; rng = np.random.default_rng()
    variants_by_source = defaultdict(int); signatures_by_source = defaultdict(set); hashes_by_source = defaultdict(set)
    duplicate_retries = 0
    for index in range(target_count):
        if context.is_cancel_requested(): return {"ok": False, "error_code": "CANCELLED"}
        candidates = []
        for item in samples:
            path = Path(item.get("sample_path") or item.get("path") or item.get("file_path") or "")
            if variants_by_source[str(path.resolve())] < max_per_source: candidates.append((item, path))
        if not candidates: break
        sample, source_path = candidates[index % len(candidates)]; cache_key = str(source_path.resolve())
        try:
            if cache_key not in audio_cache: audio_cache[cache_key] = load_audio(source_path, mono=False)
            source_audio, sample_rate = audio_cache[cache_key]
        except Exception as exc:
            read_errors.append(f"{source_path}: {exc}"); continue
        source_audio = np.asarray(source_audio, dtype=np.float32)
        if source_audio.ndim == 1: source_audio = source_audio[np.newaxis, :]

        accepted = None
        for _attempt in range(6):
            resolved_channel = target_channel
            if resolved_channel == "auto": resolved_channel = "mono" if rng.random() < 0.5 else "stereo"
            gain_left = float(rng.uniform(0.82, 1.18)); gain_right = float(rng.uniform(0.82, 1.18))
            delay_samples = int(rng.integers(-max(1, int(sample_rate * 0.012)), max(2, int(sample_rate * 0.012))))
            invert_channel = int(rng.integers(-1, 2))
            swapped = bool(rng.random() < swap_probability)
            signature = (resolved_channel, mix_strategy, round(gain_left, 2), round(gain_right, 2), delay_samples, invert_channel, swapped)
            if signature in signatures_by_source[cache_key]: duplicate_retries += 1; continue

            if source_audio.shape[0] == 1:
                left = source_audio[0].copy(); right = source_audio[0].copy()
            else:
                left = source_audio[0].copy(); right = source_audio[1].copy()
            left *= gain_left; right *= gain_right
            if invert_channel == 0: left *= -1.0
            elif invert_channel == 1: right *= -1.0
            if delay_samples > 0:
                right = np.pad(right[:-delay_samples], (delay_samples, 0))
            elif delay_samples < 0:
                shift = -delay_samples; left = np.pad(left[:-shift], (shift, 0))
            if swapped: left, right = right, left
            if dither > 0:
                left += rng.normal(0.0, dither, len(left)).astype(np.float32)
                right += rng.normal(0.0, dither, len(right)).astype(np.float32)

            if resolved_channel == "mono":
                if mix_strategy == "max": output_audio = np.maximum(left, right)
                elif mix_strategy == "min": output_audio = np.minimum(left, right)
                elif mix_strategy == "random_weight":
                    weight = float(rng.uniform(0.2, 0.8)); output_audio = weight * left + (1.0 - weight) * right
                else: output_audio = (left + right) * 0.5
            else:
                output_audio = np.stack([left, right], axis=1)
            peak = float(np.max(np.abs(output_audio))) if output_audio.size else 0.0
            if peak > 1.0: output_audio = output_audio / peak * 0.999
            output_audio = np.asarray(output_audio, dtype=np.float32)
            pcm_hash = hashlib.sha256(output_audio.tobytes()).hexdigest()
            if pcm_hash in hashes_by_source[cache_key]: duplicate_retries += 1; continue
            accepted = output_audio, signature, pcm_hash, resolved_channel, gain_left, gain_right, delay_samples, invert_channel, swapped
            break
        if accepted is None: continue
        output_audio, signature, pcm_hash, resolved_channel, gain_left, gain_right, delay_samples, invert_channel, swapped = accepted
        output_path = output_dir / f"{source_path.stem}_ch_{index:04d}.wav"; sf.write(str(output_path), output_audio, sample_rate)
        variants_by_source[cache_key] += 1; signatures_by_source[cache_key].add(signature); hashes_by_source[cache_key].add(pcm_hash)
        outputs.append({"source_sample_id": sample.get("id"), "output_path": str(output_path), "relative_path": output_path.name, "metadata": {"method": "channel_config", "target_channel": resolved_channel, "mix_strategy": mix_strategy, "left_gain": gain_left, "right_gain": gain_right, "delay_samples": delay_samples, "inverted_channel": invert_channel, "swapped": swapped, "pcm_sha256": pcm_hash}, "status": "created"})
        context.set_progress(len(outputs) * 100 / target_count, f"Channel cfg {len(outputs)}/{target_count}")

    if not outputs and read_errors: return {"ok": False, "error_code": "AUDIO_READ_FAILED", "message": read_errors[0], "outputs": [], "logs": read_errors}
    logs = list(read_errors)
    if requested_count > target_count: logs.append(f"Requested {requested_count}, limited to {target_count} by max_variants_per_source={max_per_source}.")
    if duplicate_retries: logs.append(f"Rejected {duplicate_retries} duplicate candidates.")
    return {"ok": True, "outputs": outputs, "logs": logs}


def _clamp_float(value, low, high):
    try: parsed = float(value)
    except (TypeError, ValueError): parsed = low
    return max(low, min(parsed, high))


def _clamp_int(value, low, high):
    try: parsed = int(value)
    except (TypeError, ValueError): parsed = low
    return max(low, min(parsed, high))
