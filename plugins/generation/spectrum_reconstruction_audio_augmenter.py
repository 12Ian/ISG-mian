from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from pathlib import Path

import numpy as np

from utils.audio_io import load_audio


PARAMETERS = [
    {"name": "freq_range", "type": "string", "label": "频谱范围(Hz)", "default": "[0, 4000]", "min": None, "max": None, "options": [], "description": "保留的频率范围，格式为[low, high]", "required": False},
    {"name": "randomize_parameters", "type": "bool", "label": "随机扰动频率范围", "default": True, "min": None, "max": None, "options": [], "description": "开启后每条随机调整频率上下限；关闭时固定参数只生成一条", "required": False},
    {"name": "max_variants_per_source", "type": "int", "label": "单源最大变体数", "default": 20, "min": 1, "max": 100, "options": [], "description": "限制每个源音频的频谱重构变体数量", "required": False},
]


def run(payload: dict, context) -> dict:
    try:
        import soundfile as sf
        from scipy.signal import butter, sosfiltfilt
    except ImportError:
        return {"ok": False, "error_code": "MISSING_DEPENDENCY", "message": "Missing scipy/soundfile"}
    parameters = payload.get("parameters", {}) or {}
    output_dir = Path(payload.get("output", {}).get("output_dir") or "."); output_dir.mkdir(parents=True, exist_ok=True)
    samples = payload.get("input", {}).get("samples", []) or []
    if not samples: return {"ok": False, "error_code": "NO_INPUT_SAMPLES"}

    requested_count = max(1, int(payload.get("target_count") or len(samples)))
    min_freq, max_freq = _parse_freq_range(parameters.get("freq_range", [0, 4000]))
    randomize = _as_bool(parameters.get("randomize_parameters", True)) and max_freq > min_freq
    max_per_source = _clamp_int(parameters.get("max_variants_per_source", 20), 1, 100) if randomize else 1
    target_count = min(requested_count, len(samples) * max_per_source)

    outputs = []; read_errors = []; audio_cache = {}; filter_cache = {}
    variants_by_source = defaultdict(int); signatures_by_source = defaultdict(set); hashes_by_source = defaultdict(set)
    duplicate_retries = 0; rng = np.random.default_rng()
    for index in range(target_count):
        if context.is_cancel_requested(): return {"ok": False, "error_code": "CANCELLED"}
        candidates = []
        for item in samples:
            item_path = Path(item.get("sample_path") or item.get("path") or item.get("file_path") or "")
            if variants_by_source[str(item_path.resolve())] < max_per_source: candidates.append((item, item_path))
        if not candidates: break
        sample, source_path = candidates[index % len(candidates)]
        cache_key = str(source_path.resolve())
        try:
            if cache_key not in audio_cache: audio_cache[cache_key] = load_audio(source_path, mono=True)
            source_audio, sample_rate = audio_cache[cache_key]
        except Exception as exc:
            read_errors.append(f"{source_path}: {exc}"); continue

        accepted = None
        for _attempt in range(8):
            if randomize:
                low = min_freq * rng.uniform(0.8, 1.2) if min_freq > 0 else rng.uniform(0.0, min(200.0, max_freq * 0.05))
                high = max_freq * rng.uniform(0.8, 1.2)
            else: low, high = min_freq, max_freq
            nyquist = sample_rate * 0.5
            low = _clamp_float(low, 0.0, nyquist * 0.95); high = _clamp_float(high, 10.0, nyquist * 0.99)
            if low > high: low, high = high, low
            if high - low < 10.0: high = min(nyquist * 0.99, low + 10.0)
            signature = (round(low, 1), round(high, 1))
            if signature in signatures_by_source[cache_key]: duplicate_retries += 1; continue
            filter_key = (sample_rate, *signature)
            if filter_key not in filter_cache:
                if low <= 10.0: filter_cache[filter_key] = butter(6, high, btype="lowpass", fs=sample_rate, output="sos")
                elif high >= nyquist * 0.98: filter_cache[filter_key] = butter(6, low, btype="highpass", fs=sample_rate, output="sos")
                else: filter_cache[filter_key] = butter(6, [low, high], btype="bandpass", fs=sample_rate, output="sos")
            output_audio = sosfiltfilt(filter_cache[filter_key], np.asarray(source_audio, dtype=np.float32)).astype(np.float32)
            pcm_hash = hashlib.sha256(output_audio.tobytes()).hexdigest()
            if pcm_hash in hashes_by_source[cache_key]: duplicate_retries += 1; continue
            accepted = output_audio, low, high, signature, pcm_hash; break
        if accepted is None: continue
        output_audio, low, high, signature, pcm_hash = accepted

        output_path = output_dir / f"{source_path.stem}_spectrum_{index:04d}.wav"
        sf.write(str(output_path), output_audio, sample_rate)
        variants_by_source[cache_key] += 1; signatures_by_source[cache_key].add(signature); hashes_by_source[cache_key].add(pcm_hash)
        outputs.append({"source_sample_id": sample.get("id"), "output_path": str(output_path), "relative_path": output_path.name, "metadata": {"method": "spectrum_reconstruction", "freq_range": [low, high], "filter": "butterworth_sos", "randomized": randomize, "pcm_sha256": pcm_hash}, "status": "created"})
        context.set_progress(len(outputs) * 100 / target_count, f"Spectrum recon {len(outputs)}/{target_count}")
    if not outputs and read_errors: return {"ok": False, "error_code": "AUDIO_READ_FAILED", "message": read_errors[0], "outputs": [], "logs": read_errors}
    logs = list(read_errors)
    if requested_count > target_count:
        reason = f"max_variants_per_source={max_per_source}" if randomize else "fixed spectrum parameters"
        logs.append(f"Requested {requested_count}, limited to {target_count} by {reason}.")
    if duplicate_retries: logs.append(f"Rejected {duplicate_retries} duplicate candidates.")
    return {"ok": True, "outputs": outputs, "logs": logs}


def _parse_freq_range(value):
    if isinstance(value, str):
        text = value.strip()
        try: value = json.loads(text)
        except (TypeError, ValueError, json.JSONDecodeError): value = [part.strip() for part in text.strip("[]()").split(",")]
    if not isinstance(value, (list, tuple)) or len(value) < 2: value = [0, 4000]
    low = _clamp_float(value[0], 0.0, 100000.0); high = _clamp_float(value[1], 0.0, 100000.0)
    return (low, high) if low <= high else (high, low)


def _as_bool(value):
    if isinstance(value, str): return value.strip().lower() not in {"", "0", "false", "no", "off"}
    return bool(value)


def _clamp_float(value, low, high):
    try: parsed = float(value)
    except (TypeError, ValueError): parsed = low
    return max(low, min(parsed, high))


def _clamp_int(value, low, high):
    try: parsed = int(value)
    except (TypeError, ValueError): parsed = low
    return max(low, min(parsed, high))
