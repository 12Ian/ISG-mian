from __future__ import annotations

import hashlib
from collections import defaultdict
from pathlib import Path

import numpy as np

from utils.audio_io import load_audio


PARAMETERS = [
    {"name": "effect_type", "type": "select", "label": "效果类型", "default": "echo", "min": None, "max": None, "options": ["echo", "reverb", "both"], "description": "空间声学效果类型", "required": False},
    {"name": "probability", "type": "float", "label": "触发概率", "default": 0.8, "min": 0.0, "max": 1.0, "options": [], "description": "效果作用概率；未命中时仍会保证至少应用一种效果", "required": False},
    {"name": "count", "type": "int", "label": "回声次数", "default": 3, "min": 1, "max": 10, "options": [], "description": "回声重复次数", "required": False},
    {"name": "delay", "type": "float", "label": "延迟(秒)", "default": 0.3, "min": 0.05, "max": 2.0, "options": [], "description": "回声或混响延迟时间", "required": False},
    {"name": "decay", "type": "float", "label": "衰减系数", "default": 0.6, "min": 0.0, "max": 1.0, "options": [], "description": "回声衰减系数", "required": False},
    {"name": "tau", "type": "float", "label": "混响时间常数", "default": 0.5, "min": 0.1, "max": 5.0, "options": [], "description": "指数衰减混响的时间常数", "required": False},
    {"name": "max_variants_per_source", "type": "int", "label": "单源最大变体数", "default": 20, "min": 1, "max": 100, "options": [], "description": "限制每个源音频的空间声学变体数量", "required": False},
]


def run(payload: dict, context) -> dict:
    try:
        import soundfile as sf
        from scipy.signal import fftconvolve
    except ImportError:
        return {"ok": False, "error_code": "MISSING_DEPENDENCY"}

    parameters = payload.get("parameters", {}) or {}
    output_dir = Path(payload.get("output", {}).get("output_dir") or ".")
    output_dir.mkdir(parents=True, exist_ok=True)
    samples = payload.get("input", {}).get("samples", []) or []
    if not samples:
        return {"ok": False, "error_code": "NO_INPUT_SAMPLES"}

    requested_count = max(1, int(payload.get("target_count") or len(samples)))
    effect_type = str(parameters.get("effect_type", "echo") or "echo").lower()
    if effect_type not in {"echo", "reverb", "both"}:
        effect_type = "echo"
    probability = _clamp_float(parameters.get("probability", 0.8), 0.0, 1.0)
    base_count = _clamp_int(parameters.get("count", 3), 1, 10)
    base_delay = _clamp_float(parameters.get("delay", 0.3), 0.05, 2.0)
    base_decay = _clamp_float(parameters.get("decay", 0.6), 0.0, 1.0)
    base_tau = _clamp_float(parameters.get("tau", 0.5), 0.1, 5.0)
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
        sample, source_path = candidates[index % len(candidates)]
        cache_key = str(source_path.resolve())
        try:
            if cache_key not in audio_cache:
                audio_cache[cache_key] = load_audio(source_path, mono=True)
            source_audio, sample_rate = audio_cache[cache_key]
        except Exception as exc:
            read_errors.append(f"{source_path}: {exc}")
            continue

        accepted = None
        for _attempt in range(6):
            count = _clamp_int(base_count + int(rng.integers(-1, 2)), 1, 10)
            delay = _clamp_float(base_delay * rng.uniform(0.75, 1.25), 0.05, 2.0)
            decay = _clamp_float(base_decay + rng.uniform(-0.12, 0.12), 0.05, 0.95)
            tau = _clamp_float(base_tau * rng.uniform(0.75, 1.25), 0.1, 5.0)
            apply_echo = effect_type in {"echo", "both"} and rng.random() < probability
            apply_reverb = effect_type in {"reverb", "both"} and rng.random() < probability
            if not apply_echo and not apply_reverb:
                if effect_type == "reverb":
                    apply_reverb = True
                elif effect_type == "both" and rng.random() < 0.5:
                    apply_reverb = True
                else:
                    apply_echo = True
            signature = (apply_echo, apply_reverb, count, round(delay, 3), round(decay, 2), round(tau, 2))
            if signature in signatures_by_source[cache_key]:
                duplicate_retries += 1
                continue

            audio = np.asarray(source_audio, dtype=np.float32).copy()
            target_len = len(audio)
            applied_effects = []
            if apply_echo:
                dry = audio.copy()
                for echo_index in range(1, count + 1):
                    delay_samples = int(delay * echo_index * sample_rate)
                    if 0 < delay_samples < target_len:
                        audio[delay_samples:] += (decay ** echo_index) * dry[:target_len - delay_samples]
                applied_effects.append("echo")
            if apply_reverb:
                impulse_len = max(1, int(min(2.0, delay * count) * sample_rate))
                time_axis = np.arange(impulse_len, dtype=np.float32) / sample_rate
                impulse = rng.standard_normal(impulse_len).astype(np.float32) * np.exp(-time_axis / tau)
                impulse[0] += 1.0
                impulse /= np.sum(np.abs(impulse)) + 1e-8
                audio = fftconvolve(audio, impulse, mode="full")[:target_len].astype(np.float32)
                applied_effects.append("reverb")
            peak = float(np.max(np.abs(audio))) if audio.size else 0.0
            if peak > 1.0:
                audio = audio / peak * 0.999
            pcm_hash = hashlib.sha256(np.asarray(audio, dtype=np.float32).tobytes()).hexdigest()
            if pcm_hash in hashes_by_source[cache_key]:
                duplicate_retries += 1
                continue
            accepted = (audio, signature, pcm_hash, applied_effects, count, delay, decay, tau)
            break
        if accepted is None:
            continue

        audio, signature, pcm_hash, applied_effects, count, delay, decay, tau = accepted
        output_path = output_dir / f"{source_path.stem}_spatial_{index:04d}.wav"
        sf.write(str(output_path), audio, sample_rate)
        variants_by_source[cache_key] += 1
        signatures_by_source[cache_key].add(signature)
        hashes_by_source[cache_key].add(pcm_hash)
        outputs.append({
            "source_sample_id": sample.get("id"),
            "output_path": str(output_path),
            "relative_path": output_path.name,
            "metadata": {"method": "spatial_acoustics", "effect_type": effect_type, "applied_effects": applied_effects, "count": count, "delay": delay, "decay": decay, "tau": tau, "pcm_sha256": pcm_hash},
            "status": "created",
        })
        context.set_progress(len(outputs) * 100 / target_count, f"Spatial {len(outputs)}/{target_count}")

    if not outputs and read_errors:
        return {"ok": False, "error_code": "AUDIO_READ_FAILED", "message": read_errors[0], "outputs": [], "logs": read_errors}
    logs = list(read_errors)
    if requested_count > target_count:
        logs.append(f"Requested {requested_count}, limited to {target_count} by max_variants_per_source={max_per_source}.")
    if duplicate_retries:
        logs.append(f"Rejected {duplicate_retries} duplicate candidates.")
    return {"ok": True, "outputs": outputs, "logs": logs}


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
