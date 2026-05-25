from __future__ import annotations

from pathlib import Path

import numpy as np


PARAMETERS = [
    {
        "name": 'downsample_ratio',
        "type": 'float',
        "label": '降采样比例',
        "default": 0.8,
        "min": 0.1,
        "max": 1.0,
        "options": [],
        "description": '降采样/升采样比例',
        "required": False,
    },
    {
        "name": 'quantize_bits',
        "type": 'int',
        "label": '量化位深',
        "default": 8,
        "min": 2,
        "max": 32,
        "options": [],
        "description": '量化比特深度',
        "required": False,
    },
    {
        "name": 'distortion_drive',
        "type": 'float',
        "label": '失真驱动量',
        "default": 0.0,
        "min": 0.0,
        "max": 1.0,
        "options": [],
        "description": 'tanh饱和失真驱动量',
        "required": False,
    },
]


def run(payload: dict, context) -> dict:
    try:
        import librosa
        import soundfile as sf
    except ImportError:
        return {"ok": False, "error_code": "MISSING_DEPENDENCY"}

    parameters = payload.get("parameters", {}) or {}
    output_dir = Path(payload.get("output", {}).get("output_dir") or ".")
    output_dir.mkdir(parents=True, exist_ok=True)

    samples = payload.get("input", {}).get("samples", []) or []
    if not samples:
        return {"ok": False, "error_code": "NO_INPUT_SAMPLES"}

    target_count = max(1, int(payload.get("target_count") or len(samples)))
    ds_ratio = max(0.2, min(float(parameters.get("ds_ratio", parameters.get("降采样比例", 0.8)) or 0.8), 1.0))
    bits = max(2, min(int(parameters.get("bits", parameters.get("量化位深", 8)) or 8), 16))
    drive = max(0.0, float(parameters.get("drive", parameters.get("失真驱动强度", 0.0)) or 0.0))

    outputs = []
    for index in range(target_count):
        if context.is_cancel_requested():
            return {"ok": False, "error_code": "CANCELLED"}
        sample = samples[index % len(samples)]
        sp = Path(sample.get("sample_path") or sample.get("path") or "")
        try:
            y, sr = librosa.load(str(sp), sr=None, mono=True)
        except Exception:
            continue
        T = len(y)
        yc = y.astype(np.float32)

        if ds_ratio < 0.999:
            new_sr = max(8000, int(sr * ds_ratio))
            yc_ds = librosa.resample(yc, orig_sr=sr, target_sr=new_sr)
            yc = librosa.resample(yc_ds, orig_sr=new_sr, target_sr=sr)
            yc = _match_len(yc, T)

        levels = (2 ** bits) - 1
        yc = np.round(yc * levels) / levels

        if drive > 0.0:
            yc = np.tanh(drive * yc) / (np.tanh(drive) + 1e-6)

        out = output_dir / f"{sp.stem}_distort_{index:04d}.wav"
        sf.write(str(out), yc, sr)
        outputs.append({
            "source_sample_id": sample.get("id"),
            "output_path": str(out),
            "relative_path": out.name,
            "metadata": {"method": "quality_distortion", "bits": bits, "ds_ratio": ds_ratio},
            "status": "created",
        })
        context.set_progress((index + 1) * 100 / target_count, f"Distort {index+1}/{target_count}")

    return {"ok": True, "outputs": outputs, "logs": []}


def _match_len(y, target):
    if len(y) == target:
        return y
    if len(y) > target:
        return y[:target]
    return np.pad(y, (0, target - len(y)), mode="constant")
