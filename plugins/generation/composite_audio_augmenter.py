from __future__ import annotations

from collections import defaultdict
from pathlib import Path

import numpy as np

from utils.audio_io import load_audio


PARAMETERS = [
    {"name": "combination_count", "type": "int", "label": "组合次数", "default": 3, "min": 1, "max": 10, "options": [], "description": "每条样本应用的增强策略数量", "required": False},
    {"name": "include_specaugment", "type": "bool", "label": "包含SpecAugment", "default": True, "min": None, "max": None, "options": [], "description": "是否启用频谱遮挡重建", "required": False},
    {"name": "include_spatial", "type": "bool", "label": "包含空间声学", "default": True, "min": None, "max": None, "options": [], "description": "是否启用回声与混响", "required": False},
    {"name": "max_variants_per_source", "type": "int", "label": "单源最大变体数", "default": 20, "min": 1, "max": 100, "options": [], "description": "限制单个源音频的扩增数量，降低近重复率", "required": False},
]

LIGHT_OPS = ("energy", "timeseries", "noise", "filter", "channel")
EXPENSIVE_OPS = ("tempo", "distort", "specaugment", "spatial")


def run(payload: dict, context) -> dict:
    try:
        import librosa
        import soundfile as sf
        from scipy.signal import fftconvolve, istft, stft
    except ImportError:
        return {"ok": False, "error_code": "MISSING_DEPENDENCY"}

    parameters = payload.get("parameters", {}) or {}
    output_dir = Path(payload.get("output", {}).get("output_dir") or ".")
    output_dir.mkdir(parents=True, exist_ok=True)
    samples = payload.get("input", {}).get("samples", []) or []
    if not samples:
        return {"ok": False, "error_code": "NO_INPUT_SAMPLES"}

    requested_count = max(1, int(payload.get("target_count") or len(samples)))
    combo = max(1, min(int(parameters.get("combination_count", 3) or 3), 10))
    include_spec = _as_bool(parameters.get("include_specaugment", True))
    include_spatial = _as_bool(parameters.get("include_spatial", True))
    max_per_source = max(1, min(int(parameters.get("max_variants_per_source", 20) or 20), 100))
    target_count = min(requested_count, len(samples) * max_per_source)

    # 同一源文件只解码一次，后续变体复制缓存波形。
    audio_cache: dict[str, tuple[np.ndarray, int]] = {}
    valid_samples = []
    read_errors = []
    for sample in samples:
        path = Path(sample.get("sample_path") or sample.get("path") or sample.get("file_path") or "")
        key = str(path.resolve())
        if key not in audio_cache:
            try:
                y, sr = load_audio(path, mono=True)
                audio_cache[key] = (np.asarray(y, dtype=np.float32), int(sr))
            except Exception as exc:
                read_errors.append(str(exc))
                continue
        valid_samples.append((sample, path, key))
    if not valid_samples:
        return {"ok": False, "error_code": "AUDIO_READ_FAILED", "message": read_errors[0] if read_errors else "Cannot read source audio"}

    target_count = min(target_count, len(valid_samples) * max_per_source)
    rng = np.random.default_rng()
    outputs = []
    variants_by_source = defaultdict(int)
    signatures_by_source = defaultdict(set)
    fingerprints_by_source = defaultdict(list)
    duplicate_retries = 0

    for index in range(target_count):
        if context.is_cancel_requested():
            return {"ok": False, "error_code": "CANCELLED"}
        candidates = [item for item in valid_samples if variants_by_source[item[2]] < max_per_source]
        if not candidates:
            break
        sample, source_path, cache_key = candidates[index % len(candidates)]
        source_audio, sr = audio_cache[cache_key]

        accepted = None
        for _attempt in range(6):
            ops = _choose_ops(rng, combo, include_spec, include_spatial, signatures_by_source[cache_key])
            y_out, descriptors = _apply_ops(source_audio.copy(), sr, ops, rng, librosa, fftconvolve, stft, istft)
            signature = tuple(sorted(descriptors))
            fingerprint = _spectral_fingerprint(y_out)
            if signature in signatures_by_source[cache_key] or _is_near_duplicate(fingerprint, fingerprints_by_source[cache_key]):
                duplicate_retries += 1
                continue
            accepted = (y_out, signature, fingerprint, ops)
            break
        if accepted is None:
            continue

        y_out, signature, fingerprint, ops = accepted
        out = output_dir / f"{source_path.stem}_composite_{index:04d}.wav"
        sf.write(str(out), y_out, sr)
        signatures_by_source[cache_key].add(signature)
        fingerprints_by_source[cache_key].append(fingerprint)
        variants_by_source[cache_key] += 1
        outputs.append({
            "source_sample_id": sample.get("id"),
            "output_path": str(out),
            "relative_path": out.name,
            "metadata": {"method": "composite", "ops": ops, "strategy_signature": list(signature)},
            "status": "created",
        })
        context.set_progress(len(outputs) * 100 / target_count, f"Composite {len(outputs)}/{target_count}")

    logs = list(read_errors)
    if requested_count > target_count:
        logs.append(f"Requested {requested_count}, limited to {target_count} by max_variants_per_source={max_per_source}.")
    if duplicate_retries:
        logs.append(f"Rejected {duplicate_retries} near-duplicate candidates.")
    return {"ok": True, "outputs": outputs, "logs": logs}


def _choose_ops(rng, combo: int, include_spec: bool, include_spatial: bool, used_signatures: set) -> list[str]:
    light = list(LIGHT_OPS)
    expensive = ["tempo", "distort"]
    if include_spec:
        expensive.append("specaugment")
    if include_spatial:
        expensive.append("spatial")
    count = min(combo, len(light) + (1 if expensive else 0))
    # 每条最多一个昂贵策略，其余优先使用轻量策略。
    expensive_count = 1 if expensive and count > 1 and rng.random() < 0.45 else 0
    light_count = min(count - expensive_count, len(light))
    ops = list(rng.choice(light, size=light_count, replace=False))
    if expensive_count:
        ops.append(str(rng.choice(expensive)))
    rng.shuffle(ops)
    return ops


def _apply_ops(y_out, sr, ops, rng, librosa, fftconvolve, stft, istft):
    target_len = len(y_out)
    descriptors = []
    for op in ops:
        if op == "tempo":
            rate = float(rng.uniform(0.88, 1.12)); pitch = float(rng.uniform(-2.5, 2.5))
            y_out = _mlen(librosa.effects.time_stretch(y_out, rate=rate), target_len)
            y_out = _mlen(librosa.effects.pitch_shift(y_out, sr=sr, n_steps=pitch), target_len)
            descriptors.append(f"tempo:{round(rate, 2)}:{round(pitch * 2) / 2}")
        elif op == "energy":
            gain = float(rng.uniform(0.65, 1.35)); y_out *= gain
            descriptors.append(f"energy:{round(gain, 1)}")
        elif op == "timeseries":
            shift = int(rng.uniform(-0.25, 0.25) * sr)
            y_out = np.roll(y_out, shift)
            if shift > 0: y_out[:shift] = 0
            elif shift < 0: y_out[shift:] = 0
            descriptors.append(f"shift:{round(shift / sr, 2)}")
        elif op == "channel":
            descriptors.append("channel:mono")
        elif op == "noise":
            snr = float(rng.uniform(3.0, 22.0)); noise = rng.standard_normal(target_len).astype(np.float32)
            scale = np.sqrt((np.mean(y_out ** 2) + 1e-8) / (10 ** (snr / 10) * (np.mean(noise ** 2) + 1e-8)))
            y_out += scale * noise
            descriptors.append(f"noise:{round(snr / 2) * 2}")
        elif op == "filter":
            lo, hi = float(rng.uniform(120, 900)), float(rng.uniform(1800, 6000))
            spectrum = np.fft.rfft(y_out); freqs = np.fft.rfftfreq(target_len, 1 / sr)
            spectrum[(freqs < lo) | (freqs > hi)] = 0
            y_out = np.fft.irfft(spectrum, n=target_len).astype(np.float32)
            descriptors.append(f"filter:{round(lo / 100) * 100}:{round(hi / 500) * 500}")
        elif op == "distort":
            ratio = float(rng.uniform(0.62, 0.94)); reduced_sr = max(8000, int(sr * ratio))
            y_out = librosa.resample(y_out, orig_sr=sr, target_sr=reduced_sr)
            y_out = _mlen(librosa.resample(y_out, orig_sr=reduced_sr, target_sr=sr), target_len)
            descriptors.append(f"distort:{round(ratio, 1)}")
        elif op == "specaugment":
            n_fft, hop = 1024, 256
            _, _, spectrum = stft(y_out, fs=sr, nperseg=n_fft, noverlap=n_fft - hop, boundary="zeros")
            width = int(rng.integers(4, 25)); start = int(rng.integers(0, max(1, spectrum.shape[0] - width + 1)))
            spectrum[start:start + width, :] = 0
            _, reconstructed = istft(spectrum, fs=sr, nperseg=n_fft, noverlap=n_fft - hop, input_onesided=True)
            y_out = _mlen(reconstructed, target_len)
            descriptors.append(f"spec:{start // 4}:{width // 2}")
        elif op == "spatial":
            length = max(1, int(0.3 * sr)); t = np.arange(length, dtype=np.float32) / sr
            ir = rng.standard_normal(length).astype(np.float32) * np.exp(-t / float(rng.uniform(0.08, 0.25)))
            ir[0] += 1.0; ir /= np.sum(np.abs(ir)) + 1e-8
            y_out = fftconvolve(y_out, ir, mode="full")[:target_len].astype(np.float32)
            descriptors.append(f"spatial:{round(length / sr, 1)}")
    peak = float(np.max(np.abs(y_out))) if y_out.size else 0.0
    if peak > 1.0: y_out = y_out / peak * 0.999
    return y_out.astype(np.float32), descriptors


def _spectral_fingerprint(audio: np.ndarray) -> np.ndarray:
    if audio.size == 0:
        return np.zeros(32, dtype=np.float32)
    step = max(1, audio.size // 32768)
    reduced = audio[::step][:32768]
    spectrum = np.log1p(np.abs(np.fft.rfft(reduced, n=32768)))
    bands = np.array_split(spectrum, 32)
    fingerprint = np.asarray([float(np.mean(band)) for band in bands], dtype=np.float32)
    norm = float(np.linalg.norm(fingerprint))
    return fingerprint / norm if norm > 0 else fingerprint


def _is_near_duplicate(fingerprint: np.ndarray, existing: list[np.ndarray], threshold: float = 0.9995) -> bool:
    return any(float(np.dot(fingerprint, previous)) >= threshold for previous in existing)


def _as_bool(value) -> bool:
    if isinstance(value, str):
        return value.strip().lower() not in {"", "0", "false", "no", "off"}
    return bool(value)


def _mlen(audio, target):
    if len(audio) >= target:
        return np.asarray(audio[:target], dtype=np.float32)
    return np.pad(audio, (0, target - len(audio)), mode="constant").astype(np.float32)
