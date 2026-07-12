from __future__ import annotations

import hashlib
from collections import defaultdict
from pathlib import Path

import numpy as np

from utils.audio_io import load_audio


PARAMETERS = [
    {"name": "mel_bins", "type": "int", "label": "频带数", "default": 64, "min": 16, "max": 256, "options": [], "description": "用于换算频率遮挡宽度", "required": False},
    {"name": "n_fft", "type": "int", "label": "FFT点数", "default": 1024, "min": 256, "max": 4096, "options": [], "description": "STFT窗口大小", "required": False},
    {"name": "hop", "type": "int", "label": "帧移", "default": 256, "min": 64, "max": 1024, "options": [], "description": "STFT帧移", "required": False},
    {"name": "freq_mask_param", "type": "int", "label": "频率遮挡宽度", "default": 8, "min": 1, "max": 32, "options": [], "description": "最大频率遮挡宽度", "required": False},
    {"name": "time_mask_param", "type": "int", "label": "时间遮挡宽度", "default": 8, "min": 1, "max": 32, "options": [], "description": "最大时间帧遮挡宽度", "required": False},
    {"name": "inversion_iterations", "type": "int", "label": "反演迭代次数", "default": 1, "min": 1, "max": 1, "options": [], "description": "保留原相位快速反演，无需Griffin-Lim迭代", "required": False},
    {"name": "max_variants_per_source", "type": "int", "label": "单源最大变体数", "default": 20, "min": 1, "max": 100, "options": [], "description": "限制每个源音频的频谱遮挡变体数量", "required": False},
]


def run(payload: dict, context) -> dict:
    try:
        import soundfile as sf
        from scipy.signal import istft, stft
    except ImportError:
        return {"ok": False, "error_code": "MISSING_DEPENDENCY"}
    parameters = payload.get("parameters", {}) or {}
    output_dir = Path(payload.get("output", {}).get("output_dir") or ".")
    output_dir.mkdir(parents=True, exist_ok=True)
    samples = payload.get("input", {}).get("samples", []) or []
    if not samples:
        return {"ok": False, "error_code": "NO_INPUT_SAMPLES"}

    requested_count = max(1, int(payload.get("target_count") or len(samples)))
    n_fft = _clamp_int(parameters.get("n_fft", 1024), 256, 4096)
    hop = _clamp_int(parameters.get("hop", parameters.get("hop_length", 256)), 64, n_fft)
    mel_bins = _clamp_int(parameters.get("mel_bins", parameters.get("n_mels", 64)), 16, 256)
    freq_mask = _clamp_int(parameters.get("freq_mask_param", 8), 1, 32)
    time_mask = _clamp_int(parameters.get("time_mask_param", 8), 1, 32)
    max_per_source = _clamp_int(parameters.get("max_variants_per_source", 20), 1, 100)
    target_count = min(requested_count, len(samples) * max_per_source)

    outputs = []
    read_errors = []
    audio_cache = {}
    variants_by_source = defaultdict(int)
    signatures_by_source = defaultdict(set)
    hashes_by_source = defaultdict(set)
    rng = np.random.default_rng()

    for index in range(target_count):
        if context.is_cancel_requested(): return {"ok": False, "error_code": "CANCELLED"}
        candidates = []
        for item in samples:
            path = Path(item.get("sample_path") or item.get("path") or item.get("file_path") or "")
            if variants_by_source[str(path.resolve())] < max_per_source: candidates.append((item, path))
        if not candidates: break
        sample, source_path = candidates[index % len(candidates)]
        cache_key = str(source_path.resolve())
        try:
            if cache_key not in audio_cache: audio_cache[cache_key] = load_audio(source_path, mono=True)
            source_audio, sample_rate = audio_cache[cache_key]
        except Exception as exc:
            read_errors.append(f"{source_path}: {exc}"); continue

        accepted = None
        for _attempt in range(6):
            audio = np.asarray(source_audio, dtype=np.float32)
            overlap = max(0, n_fft - hop)
            _, _, spectrum = stft(audio, fs=sample_rate, nperseg=n_fft, noverlap=overlap, boundary="zeros")
            freq_width = max(1, int(rng.integers(1, freq_mask + 1) * spectrum.shape[0] / mel_bins))
            time_width = max(1, int(rng.integers(1, time_mask + 1)))
            freq_start = int(rng.integers(0, max(1, spectrum.shape[0] - freq_width + 1)))
            time_start = int(rng.integers(0, max(1, spectrum.shape[1] - time_width + 1)))
            signature = (freq_start, freq_width, time_start, time_width)
            if signature in signatures_by_source[cache_key]: continue
            masked = spectrum.copy()
            masked[freq_start:freq_start + freq_width, :] = 0
            masked[:, time_start:time_start + time_width] = 0
            _, output_audio = istft(masked, fs=sample_rate, nperseg=n_fft, noverlap=overlap, input_onesided=True)
            output_audio = _match_len(output_audio, len(audio)).astype(np.float32)
            pcm_hash = hashlib.sha256(output_audio.tobytes()).hexdigest()
            if pcm_hash in hashes_by_source[cache_key]: continue
            accepted = output_audio, signature, pcm_hash, freq_start, freq_width, time_start, time_width
            break
        if accepted is None: continue
        output_audio, signature, pcm_hash, freq_start, freq_width, time_start, time_width = accepted
        output_path = output_dir / f"{source_path.stem}_specaug_{index:04d}.wav"
        sf.write(str(output_path), output_audio, sample_rate)
        variants_by_source[cache_key] += 1; signatures_by_source[cache_key].add(signature); hashes_by_source[cache_key].add(pcm_hash)
        outputs.append({"source_sample_id": sample.get("id"), "output_path": str(output_path), "relative_path": output_path.name, "metadata": {"method": "specaugment", "freq_start": freq_start, "freq_width": freq_width, "time_start": time_start, "time_width": time_width, "pcm_sha256": pcm_hash}, "status": "created"})
        context.set_progress(len(outputs) * 100 / target_count, f"SpecAugment {len(outputs)}/{target_count}")

    if not outputs and read_errors: return {"ok": False, "error_code": "AUDIO_READ_FAILED", "message": read_errors[0], "outputs": [], "logs": read_errors}
    logs = list(read_errors)
    if requested_count > target_count: logs.append(f"Requested {requested_count}, limited to {target_count} by max_variants_per_source={max_per_source}.")
    return {"ok": True, "outputs": outputs, "logs": logs}


def _match_len(audio, target):
    if len(audio) >= target: return audio[:target]
    return np.pad(audio, (0, target - len(audio)), mode="constant")


def _clamp_int(value, low, high):
    try: parsed = int(value)
    except (TypeError, ValueError): parsed = low
    return max(low, min(parsed, high))
