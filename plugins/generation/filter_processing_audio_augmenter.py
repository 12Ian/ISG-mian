from __future__ import annotations

import hashlib
from collections import defaultdict
from pathlib import Path

import numpy as np

from utils.audio_io import load_audio


PARAMETERS = [
    {"name": "filter_type", "type": "select", "label": "滤波类型", "default": "bandpass", "min": None, "max": None, "options": ["bandpass", "lowpass", "highpass", "bandstop"], "description": "滤波器类型", "required": False},
    {"name": "low_cutoff_hz", "type": "float", "label": "低截止频率(Hz)", "default": 300.0, "min": 20.0, "max": 20000.0, "options": [], "description": "低端截止频率", "required": False},
    {"name": "high_cutoff_hz", "type": "float", "label": "高截止频率(Hz)", "default": 3000.0, "min": 20.0, "max": 20000.0, "options": [], "description": "高端截止频率", "required": False},
    {"name": "randomize_parameters", "type": "bool", "label": "随机扰动截止频率", "default": True, "min": None, "max": None, "options": [], "description": "开启后每条样本随机调整截止频率；关闭时固定参数只生成一条", "required": False},
    {"name": "max_variants_per_source", "type": "int", "label": "单源最大变体数", "default": 20, "min": 1, "max": 100, "options": [], "description": "限制每个源音频的滤波变体数量", "required": False},
]


def run(payload: dict, context) -> dict:
    try:
        import soundfile as sf
        from scipy.signal import butter, sosfiltfilt
    except ImportError:
        return {"ok": False, "error_code": "MISSING_DEPENDENCY"}

    parameters = payload.get("parameters", {}) or {}
    output_dir = Path(payload.get("output", {}).get("output_dir") or ".")
    output_dir.mkdir(parents=True, exist_ok=True)
    samples = payload.get("input", {}).get("samples", []) or []
    if not samples:
        return {"ok": False, "error_code": "NO_INPUT_SAMPLES"}

    requested_count = max(1, int(payload.get("target_count") or len(samples)))
    filter_type = str(parameters.get("filter_type", "bandpass") or "bandpass").lower()
    if filter_type not in {"bandpass", "lowpass", "highpass", "bandstop"}:
        filter_type = "bandpass"
    base_low = _clamp_float(parameters.get("low_cutoff_hz", 300.0), 20.0, 20000.0)
    base_high = _clamp_float(parameters.get("high_cutoff_hz", 3000.0), 20.0, 20000.0)
    if base_low > base_high:
        base_low, base_high = base_high, base_low
    randomize = _as_bool(parameters.get("randomize_parameters", True))
    max_per_source = _clamp_int(parameters.get("max_variants_per_source", 20), 1, 100) if randomize else 1
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
            if randomize:
                low = base_low * rng.uniform(0.82, 1.18)
                high = base_high * rng.uniform(0.82, 1.18)
            else:
                low, high = base_low, base_high
            nyquist = sample_rate * 0.5
            low = _clamp_float(low, 10.0, nyquist * 0.95)
            high = _clamp_float(high, 10.0, nyquist * 0.99)
            if low > high:
                low, high = high, low
            if high - low < 10.0:
                high = min(nyquist * 0.99, low + 10.0)
            signature = (filter_type, round(low, 1), round(high, 1))
            if signature in signatures_by_source[cache_key]:
                duplicate_retries += 1
                continue

            if filter_type == "lowpass":
                sos = butter(4, high, btype="lowpass", fs=sample_rate, output="sos")
            elif filter_type == "highpass":
                sos = butter(4, low, btype="highpass", fs=sample_rate, output="sos")
            else:
                sos = butter(4, [low, high], btype=filter_type, fs=sample_rate, output="sos")
            audio = sosfiltfilt(sos, np.asarray(source_audio, dtype=np.float32)).astype(np.float32)
            pcm_hash = hashlib.sha256(audio.tobytes()).hexdigest()
            if pcm_hash in hashes_by_source[cache_key]:
                duplicate_retries += 1
                continue
            accepted = (audio, low, high, signature, pcm_hash)
            break
        if accepted is None:
            continue

        audio, low, high, signature, pcm_hash = accepted
        output_path = output_dir / f"{source_path.stem}_filter_{index:04d}.wav"
        sf.write(str(output_path), audio, sample_rate)
        variants_by_source[cache_key] += 1
        signatures_by_source[cache_key].add(signature)
        hashes_by_source[cache_key].add(pcm_hash)
        outputs.append({
            "source_sample_id": sample.get("id"),
            "output_path": str(output_path),
            "relative_path": output_path.name,
            "metadata": {"method": "filter_processing", "filter_type": filter_type, "low_cutoff_hz": low, "high_cutoff_hz": high, "randomized": randomize, "pcm_sha256": pcm_hash},
            "status": "created",
        })
        context.set_progress(len(outputs) * 100 / target_count, f"Filter {len(outputs)}/{target_count}")

    if not outputs and read_errors:
        return {"ok": False, "error_code": "AUDIO_READ_FAILED", "message": read_errors[0], "outputs": [], "logs": read_errors}
    logs = list(read_errors)
    if requested_count > target_count:
        reason = f"max_variants_per_source={max_per_source}" if randomize else "fixed filter parameters"
        logs.append(f"Requested {requested_count}, limited to {target_count} by {reason}.")
    if duplicate_retries:
        logs.append(f"Rejected {duplicate_retries} duplicate candidates.")
    return {"ok": True, "outputs": outputs, "logs": logs}


def _as_bool(value):
    if isinstance(value, str):
        return value.strip().lower() not in {"", "0", "false", "no", "off"}
    return bool(value)


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
