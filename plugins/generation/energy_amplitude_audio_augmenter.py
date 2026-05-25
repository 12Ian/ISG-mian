from __future__ import annotations

from pathlib import Path

import numpy as np


PARAMETERS = [
    {
        "name": 'volume_scale',
        "type": 'float',
        "label": '音量缩放',
        "default": 1.0,
        "min": 0.0,
        "max": 5.0,
        "options": [],
        "description": '线性音量缩放系数',
        "required": False,
    },
    {
        "name": 'mute_probability',
        "type": 'float',
        "label": '静音触发概率',
        "default": 0.5,
        "min": 0.0,
        "max": 1.0,
        "options": [],
        "description": '每个静音段的触发概率',
        "required": False,
    },
    {
        "name": 'mute_count',
        "type": 'int',
        "label": '静音段数量',
        "default": 1,
        "min": 0,
        "max": 10,
        "options": [],
        "description": '随机插入的静音段数量',
        "required": False,
    },
    {
        "name": 'min_sec',
        "type": 'float',
        "label": '最短静音(秒)',
        "default": 0.05,
        "min": 0.01,
        "max": 1.0,
        "options": [],
        "description": '单个静音段最短时长',
        "required": False,
    },
    {
        "name": 'max_sec',
        "type": 'float',
        "label": '最长静音(秒)',
        "default": 0.2,
        "min": 0.05,
        "max": 2.0,
        "options": [],
        "description": '单个静音段最长时长',
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
    gain = max(0.0, float(parameters.get("gain", parameters.get("音量缩放", 1.0)) or 1.0))
    sil_prob = float(parameters.get("sil_prob", parameters.get("静音概率", 0.5)) or 0.5)
    sil_times = max(1, int(parameters.get("sil_times", parameters.get("静音次数", 1)) or 1))
    sil_min = float(parameters.get("sil_min", parameters.get("静音最短秒", 0.05)) or 0.05)
    sil_max = float(parameters.get("sil_max", parameters.get("静音最长秒", 0.2)) or 0.2)

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

        y_out = y * gain

        if np.random.rand() < sil_prob:
            for _ in range(sil_times):
                seg = int(np.random.uniform(sil_min, sil_max) * sr)
                seg = max(1, min(seg, T))
                start = int(np.random.randint(0, max(1, T - seg)))
                y_out[start:start + seg] = 0.0

        out = output_dir / f"{sp.stem}_energy_{index:04d}.wav"
        sf.write(str(out), y_out, sr)
        outputs.append({
            "source_sample_id": sample.get("id"),
            "output_path": str(out),
            "relative_path": out.name,
            "metadata": {"method": "energy_amplitude", "gain": gain},
            "status": "created",
        })
        context.set_progress((index + 1) * 100 / target_count, f"Energy/amp {index+1}/{target_count}")

    return {"ok": True, "outputs": outputs, "logs": []}
