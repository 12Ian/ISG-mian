from __future__ import annotations

import hashlib
from collections import defaultdict
from pathlib import Path

import numpy as np

from utils.audio_io import load_audio


PARAMETERS = [
    {"name": "volume_scale", "type": "float", "label": "音量缩放", "default": 1.35, "min": 0.0, "max": 5.0, "options": [], "description": "音量缩放中心值，每条会在附近随机扰动", "required": False},
    {"name": "mute_probability", "type": "float", "label": "静音触发概率", "default": 0.9, "min": 0.0, "max": 1.0, "options": [], "description": "每条样本插入静音段的概率", "required": False},
    {"name": "mute_count", "type": "int", "label": "静音段数量", "default": 2, "min": 0, "max": 10, "options": [], "description": "随机插入的静音段数量", "required": False},
    {"name": "min_sec", "type": "float", "label": "最短静音秒数", "default": 0.05, "min": 0.01, "max": 1.0, "options": [], "description": "单个静音段最短时长", "required": False},
    {"name": "max_sec", "type": "float", "label": "最长静音秒数", "default": 0.35, "min": 0.05, "max": 2.0, "options": [], "description": "单个静音段最长时长", "required": False},
    {"name": "max_variants_per_source", "type": "int", "label": "单源最大变体数", "default": 20, "min": 1, "max": 100, "options": [], "description": "限制每个源音频的能量幅度变体数量", "required": False},
]


def run(payload: dict, context) -> dict:
    try:
        import soundfile as sf
    except ImportError:
        return {"ok": False, "error_code": "MISSING_DEPENDENCY"}
    parameters = payload.get("parameters", {}) or {}
    output_dir = Path(payload.get("output", {}).get("output_dir") or "."); output_dir.mkdir(parents=True, exist_ok=True)
    samples = payload.get("input", {}).get("samples", []) or []
    if not samples: return {"ok": False, "error_code": "NO_INPUT_SAMPLES"}

    requested_count = max(1, int(payload.get("target_count") or len(samples)))
    base_gain = _clamp_float(parameters.get("volume_scale", 1.35), 0.0, 5.0)
    mute_probability = _clamp_float(parameters.get("mute_probability", 0.9), 0.0, 1.0)
    mute_count = _clamp_int(parameters.get("mute_count", 2), 0, 10)
    min_sec = _clamp_float(parameters.get("min_sec", 0.05), 0.01, 1.0)
    max_sec = _clamp_float(parameters.get("max_sec", 0.35), 0.05, 2.0)
    if min_sec > max_sec: min_sec, max_sec = max_sec, min_sec
    max_per_source = _clamp_int(parameters.get("max_variants_per_source", 20), 1, 100)
    target_count = min(requested_count, len(samples) * max_per_source)

    outputs = []; read_errors = []; audio_cache = {}; rng = np.random.default_rng()
    variants_by_source = defaultdict(int); signatures_by_source = defaultdict(set); hashes_by_source = defaultdict(set); duplicate_retries = 0
    for index in range(target_count):
        if context.is_cancel_requested(): return {"ok": False, "error_code": "CANCELLED"}
        candidates = []
        for item in samples:
            path = Path(item.get("sample_path") or item.get("path") or item.get("file_path") or "")
            if variants_by_source[str(path.resolve())] < max_per_source: candidates.append((item, path))
        if not candidates: break
        sample, source_path = candidates[index % len(candidates)]; cache_key = str(source_path.resolve())
        try:
            if cache_key not in audio_cache: audio_cache[cache_key] = load_audio(source_path, mono=True)
            source_audio, sample_rate = audio_cache[cache_key]
        except Exception as exc:
            read_errors.append(f"{source_path}: {exc}"); continue

        accepted = None
        for _attempt in range(6):
            gain_range = max(0.08, abs(base_gain) * 0.15)
            gain = _clamp_float(base_gain + rng.uniform(-gain_range, gain_range), 0.0, 5.0)
            apply_mute = mute_count > 0 and rng.random() < mute_probability
            # 未触发静音时，保证音量与原音频有可见差异。
            if not apply_mute and abs(gain - 1.0) < 0.03:
                gain = _clamp_float(1.0 + (0.05 if rng.random() < 0.5 else -0.05), 0.0, 5.0)
            audio = np.clip(np.asarray(source_audio, dtype=np.float32) * gain, -1.0, 1.0)
            mute_segments = []
            if apply_mute:
                for _ in range(mute_count):
                    duration = float(rng.uniform(min_sec, max_sec)); length = max(1, min(int(duration * sample_rate), len(audio)))
                    start = int(rng.integers(0, max(1, len(audio) - length + 1))); audio[start:start + length] = 0.0
                    mute_segments.append({"start": start, "length": length, "duration_sec": duration})
            signature = (round(gain, 4), tuple((x["start"], x["length"]) for x in mute_segments))
            if signature in signatures_by_source[cache_key]: duplicate_retries += 1; continue
            pcm_hash = hashlib.sha256(audio.tobytes()).hexdigest()
            if pcm_hash in hashes_by_source[cache_key]: duplicate_retries += 1; continue
            accepted = audio, signature, pcm_hash, gain, mute_segments
            break
        if accepted is None: continue
        audio, signature, pcm_hash, gain, mute_segments = accepted
        output_path = output_dir / f"{source_path.stem}_energy_{index:04d}.wav"; sf.write(str(output_path), audio, sample_rate)
        variants_by_source[cache_key] += 1; signatures_by_source[cache_key].add(signature); hashes_by_source[cache_key].add(pcm_hash)
        outputs.append({"source_sample_id": sample.get("id"), "output_path": str(output_path), "relative_path": output_path.name, "metadata": {"method": "energy_amplitude", "volume_scale": gain, "mute_applied": bool(mute_segments), "mute_segments": mute_segments, "pcm_sha256": pcm_hash}, "status": "created"})
        context.set_progress(len(outputs) * 100 / target_count, f"Energy/amp {len(outputs)}/{target_count}")

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
