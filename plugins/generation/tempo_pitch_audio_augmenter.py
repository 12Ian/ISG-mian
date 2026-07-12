from __future__ import annotations

import hashlib
from collections import defaultdict
from fractions import Fraction
from pathlib import Path

import numpy as np

from utils.audio_io import load_audio


PARAMETERS = [
    {"name": "time_stretch", "type": "float", "label": "语速倍率", "default": 1.0, "min": 0.5, "max": 2.0, "options": [], "description": "语速变化中心值，每条会在附近随机扰动", "required": False},
    {"name": "pitch_shift_semitones", "type": "float", "label": "音调半音偏移", "default": 0.0, "min": -12.0, "max": 12.0, "options": [], "description": "音调变化中心值，每条会在附近随机扰动", "required": False},
    {"name": "max_variants_per_source", "type": "int", "label": "单源最大变体数", "default": 20, "min": 1, "max": 100, "options": [], "description": "限制每个源音频的语速音调变体数量", "required": False},
]


def run(payload: dict, context) -> dict:
    try:
        import soundfile as sf
        from scipy.signal import resample_poly
    except ImportError:
        return {"ok": False, "error_code": "MISSING_DEPENDENCY"}
    parameters = payload.get("parameters", {}) or {}
    output_dir = Path(payload.get("output", {}).get("output_dir") or "."); output_dir.mkdir(parents=True, exist_ok=True)
    samples = payload.get("input", {}).get("samples", []) or []
    if not samples: return {"ok": False, "error_code": "NO_INPUT_SAMPLES"}
    requested_count = max(1, int(payload.get("target_count") or len(samples)))
    base_rate = _clamp_float(parameters.get("time_stretch", 1.0), 0.5, 2.0)
    base_pitch = _clamp_float(parameters.get("pitch_shift_semitones", 0.0), -12.0, 12.0)
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
        for _attempt in range(12):
            rate = _clamp_float(base_rate * rng.uniform(0.9, 1.1), 0.5, 2.0)
            pitch = _clamp_float(base_pitch + rng.uniform(-2.0, 2.0), -12.0, 12.0)
            if abs(rate - 1.0) < 0.02 and abs(pitch) < 0.2: pitch = 0.5 if rng.random() < 0.5 else -0.5
            signature = (round(rate, 3), round(pitch, 2))
            if signature in signatures_by_source[cache_key]: duplicate_retries += 1; continue
            combined_ratio = rate * (2.0 ** (pitch / 12.0))
            ratio_fraction = Fraction(combined_ratio).limit_denominator(1000)
            effective_ratio = ratio_fraction.numerator / ratio_fraction.denominator
            audio = resample_poly(
                np.asarray(source_audio, dtype=np.float32),
                ratio_fraction.denominator,
                ratio_fraction.numerator,
            )
            audio = _match_len(audio, len(source_audio))
            pcm_hash = hashlib.sha256(audio.tobytes()).hexdigest()
            if pcm_hash in hashes_by_source[cache_key]: duplicate_retries += 1; continue
            accepted = audio, signature, pcm_hash, rate, pitch, effective_ratio
            break
        if accepted is None: continue
        audio, signature, pcm_hash, rate, pitch, effective_ratio = accepted
        output_path = output_dir / f"{source_path.stem}_tempo_{index:04d}.wav"; sf.write(str(output_path), audio, sample_rate)
        variants_by_source[cache_key] += 1; signatures_by_source[cache_key].add(signature); hashes_by_source[cache_key].add(pcm_hash)
        outputs.append({"source_sample_id": sample.get("id"), "output_path": str(output_path), "relative_path": output_path.name, "metadata": {"method": "tempo_pitch", "time_stretch": rate, "pitch_shift_semitones": pitch, "effective_resample_ratio": effective_ratio, "pcm_sha256": pcm_hash}, "status": "created"})
        context.set_progress(len(outputs) * 100 / target_count, f"Tempo/pitch {len(outputs)}/{target_count}")
    if not outputs and read_errors: return {"ok": False, "error_code": "AUDIO_READ_FAILED", "message": read_errors[0], "outputs": [], "logs": read_errors}
    logs = list(read_errors)
    if requested_count > target_count: logs.append(f"Requested {requested_count}, limited to {target_count} by max_variants_per_source={max_per_source}.")
    if duplicate_retries: logs.append(f"Rejected {duplicate_retries} duplicate candidates.")
    return {"ok": True, "outputs": outputs, "logs": logs}


def _match_len(audio, target):
    if len(audio) >= target: return np.asarray(audio[:target], dtype=np.float32)
    return np.pad(audio, (0, target - len(audio)), mode="constant").astype(np.float32)


def _clamp_float(value, low, high):
    try: parsed = float(value)
    except (TypeError, ValueError): parsed = low
    return max(low, min(parsed, high))


def _clamp_int(value, low, high):
    try: parsed = int(value)
    except (TypeError, ValueError): parsed = low
    return max(low, min(parsed, high))
