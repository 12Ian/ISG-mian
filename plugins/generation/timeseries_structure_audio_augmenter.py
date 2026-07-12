from __future__ import annotations

import hashlib
from collections import defaultdict
from pathlib import Path

import numpy as np

from utils.audio_io import load_audio


PARAMETERS = [
    {"name": "operation", "type": "select", "label": "操作类型", "default": "mix", "min": None, "max": None, "options": ["mix", "shift", "crop", "concat", "reverse"], "description": "时序变换操作类型", "required": False},
    {"name": "shift_sec", "type": "float", "label": "偏移量(秒)", "default": 0.2, "min": 0.01, "max": 5.0, "options": [], "description": "最大时间偏移量", "required": False},
    {"name": "crop_ratio", "type": "float", "label": "裁剪保留比例", "default": 0.9, "min": 0.1, "max": 0.99, "options": [], "description": "随机裁剪保留比例", "required": False},
    {"name": "concat_segments", "type": "int", "label": "拼接段数", "default": 2, "min": 2, "max": 10, "options": [], "description": "随机拼接的音频段数量", "required": False},
    {"name": "reverse_probability", "type": "float", "label": "反转概率", "default": 0.5, "min": 0.0, "max": 1.0, "options": [], "description": "混合模式下反转操作的触发概率", "required": False},
    {"name": "max_variants_per_source", "type": "int", "label": "单源最大变体数", "default": 20, "min": 1, "max": 100, "options": [], "description": "限制每个源音频的时序结构变体数量", "required": False},
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
    operation = str(parameters.get("operation", "mix") or "mix").lower()
    if operation not in {"mix", "shift", "crop", "concat", "reverse"}: operation = "mix"
    shift_sec = _clamp_float(parameters.get("shift_sec", 0.2), 0.01, 5.0)
    crop_ratio = _clamp_float(parameters.get("crop_ratio", 0.9), 0.1, 0.99)
    concat_segments = _clamp_int(parameters.get("concat_segments", 2), 2, 10)
    reverse_probability = _clamp_float(parameters.get("reverse_probability", 0.5), 0.0, 1.0)
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
            selected = list(rng.choice(["shift", "crop", "concat", "reverse"], size=2, replace=False)) if operation == "mix" else [operation]
            audio = np.asarray(source_audio, dtype=np.float32).copy(); target_len = len(audio); actual_ops = []; op_params = {}
            for action in selected:
                if action == "shift":
                    shift = int(rng.uniform(-shift_sec, shift_sec) * sample_rate)
                    if shift == 0: shift = 1
                    audio = np.roll(audio, shift)
                    if shift > 0: audio[:shift] = 0
                    else: audio[shift:] = 0
                    actual_ops.append("shift"); op_params["shift_samples"] = shift
                elif action == "crop":
                    varied_ratio = _clamp_float(crop_ratio + rng.uniform(-0.08, 0.03), 0.1, 0.99)
                    length = max(1, min(int(target_len * varied_ratio), target_len - 1)); start = int(rng.integers(0, max(1, target_len - length + 1)))
                    audio = _match_len(audio[start:start + length], target_len)
                    actual_ops.append("crop"); op_params.update({"crop_ratio": varied_ratio, "crop_start": start})
                elif action == "concat":
                    parts = _clamp_int(concat_segments + int(rng.integers(-1, 2)), 2, 10); part_len = max(1, target_len // parts); starts = [] ; segments = []
                    for _ in range(parts):
                        start = int(rng.integers(0, max(1, target_len - part_len + 1))); starts.append(start); segments.append(audio[start:start + part_len])
                    audio = _match_len(np.concatenate(segments), target_len)
                    actual_ops.append("concat"); op_params.update({"concat_segments": parts, "concat_starts": starts})
                elif action == "reverse" and (operation == "reverse" or rng.random() < reverse_probability):
                    audio = audio[::-1].copy()
                    reverse_shift = int(rng.uniform(-shift_sec, shift_sec) * sample_rate)
                    if reverse_shift != 0:
                        audio = np.roll(audio, reverse_shift)
                        if reverse_shift > 0: audio[:reverse_shift] = 0
                        else: audio[reverse_shift:] = 0
                    actual_ops.append("reverse"); op_params.update({"reversed": True, "reverse_shift_samples": reverse_shift})
            if not actual_ops:
                shift = max(1, int(rng.uniform(0.01, shift_sec) * sample_rate)); audio = np.roll(audio, shift); audio[:shift] = 0
                actual_ops.append("shift"); op_params["shift_samples"] = shift
            signature = (tuple(actual_ops), repr(op_params))
            if signature in signatures_by_source[cache_key]: duplicate_retries += 1; continue
            pcm_hash = hashlib.sha256(audio.tobytes()).hexdigest()
            if pcm_hash in hashes_by_source[cache_key]: duplicate_retries += 1; continue
            accepted = audio, signature, pcm_hash, actual_ops, op_params
            break
        if accepted is None: continue
        audio, signature, pcm_hash, actual_ops, op_params = accepted
        output_path = output_dir / f"{source_path.stem}_ts_{index:04d}.wav"; sf.write(str(output_path), audio, sample_rate)
        variants_by_source[cache_key] += 1; signatures_by_source[cache_key].add(signature); hashes_by_source[cache_key].add(pcm_hash)
        outputs.append({"source_sample_id": sample.get("id"), "output_path": str(output_path), "relative_path": output_path.name, "metadata": {"method": "timeseries_structure", "requested_operation": operation, "applied_operations": actual_ops, "operation_parameters": op_params, "pcm_sha256": pcm_hash}, "status": "created"})
        context.set_progress(len(outputs) * 100 / target_count, f"TS structure {len(outputs)}/{target_count}")

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
