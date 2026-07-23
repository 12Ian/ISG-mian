from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from ._image_io import read_image, write_image


PARAMETERS = [
    {
        "name": "blur_kernel",
        "type": "int",
        "label": "模糊核大小",
        "default": 5,
        "min": 0,
        "max": 15,
        "options": [],
        "description": "传感器/光学模糊核大小，默认产生可见成像退化",
        "required": False,
    },
    {
        "name": "downsample",
        "type": "float",
        "label": "下采样比例",
        "default": 0.5,
        "min": 0.1,
        "max": 1.0,
        "options": [],
        "description": "先降采样再放回原尺寸，默认产生低清成像效果",
        "required": False,
    },
    {
        "name": "noise_std",
        "type": "float",
        "label": "噪声强度",
        "default": 0.03,
        "min": 0.0,
        "max": 0.2,
        "options": [],
        "description": "归一化像素单位的高斯传感器噪声标准差",
        "required": False,
    },
    {
        "name": "brightness_shift",
        "type": "float",
        "label": "亮度变化",
        "default": 0.05,
        "min": 0.0,
        "max": 0.3,
        "options": [],
        "description": "归一化像素单位的最大随机亮度偏移",
        "required": False,
    },
    {
        "name": "color_shift",
        "type": "float",
        "label": "色彩退化",
        "default": 0.05,
        "min": 0.0,
        "max": 0.3,
        "options": [],
        "description": "各颜色通道的最大随机增益变化",
        "required": False,
    },
]


def run(payload: dict, context) -> dict:
    parameters = payload.get("parameters", {}) or {}
    output_dir = Path(payload.get("output", {}).get("output_dir") or ".")
    output_dir.mkdir(parents=True, exist_ok=True)

    samples = payload.get("input", {}).get("samples", []) or []
    if not samples:
        return {"ok": False, "error_code": "NO_INPUT_SAMPLES", "message": "未提供源样本。"}

    target_count = max(1, int(payload.get("target_count") or len(samples)))
    blur_kernel = _clamp_int(parameters.get("blur_kernel", 5), 0, 15)
    downsample = _clamp_float(parameters.get("downsample", 0.5), 0.1, 1.0)
    noise_std = _clamp_float(parameters.get("noise_std", 0.03), 0.0, 0.2)
    brightness_shift = _clamp_float(parameters.get("brightness_shift", 0.05), 0.0, 0.3)
    color_shift = _clamp_float(parameters.get("color_shift", 0.05), 0.0, 0.3)
    task_seed = int(payload.get("task_id") or 0)
    output_offset = max(0, int(payload.get("output_index") or 0))

    outputs = []
    for index in range(target_count):
        if context.is_cancel_requested():
            return {"ok": False, "error_code": "CANCELLED", "message": "任务已取消。"}

        sample = samples[index % len(samples)]
        source_path = Path(sample.get("sample_path") or sample.get("path") or sample.get("file_path") or "")
        img = read_image(source_path)
        if img is None:
            continue
        if len(img.shape) == 2:
            img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)

        out = img.astype(np.float32) / 255.0
        if blur_kernel > 1:
            kernel = blur_kernel if blur_kernel % 2 == 1 else blur_kernel + 1
            out = cv2.GaussianBlur(out, (kernel, kernel), 0)

        if downsample < 1.0:
            h, w = out.shape[:2]
            nh = max(1, int(h * downsample))
            nw = max(1, int(w * downsample))
            small = cv2.resize(out, (nw, nh), interpolation=cv2.INTER_AREA)
            out = cv2.resize(small, (w, h), interpolation=cv2.INTER_LINEAR)

        rng = np.random.default_rng((task_seed * 1000003 + output_offset + index) & 0xFFFFFFFF)
        if color_shift > 0:
            channel_gains = rng.uniform(1.0 - color_shift, 1.0 + color_shift, size=(1, 1, 3))
            out *= channel_gains
        if brightness_shift > 0:
            out += rng.uniform(-brightness_shift, brightness_shift)
        if noise_std > 0:
            out += rng.normal(0.0, noise_std, size=out.shape).astype(np.float32)

        augmented = np.clip(out * 255.0, 0, 255).astype(np.uint8)
        output_path = output_dir / f"{source_path.stem}_imaging_{index:04d}{source_path.suffix or '.jpg'}"
        if not write_image(output_path, augmented):
            return {"ok": False, "error_code": "IMAGE_WRITE_ERROR", "message": f"Cannot write image: {output_path}"}

        outputs.append(
            {
                "source_sample_id": sample.get("id"),
                "output_path": str(output_path),
                "relative_path": output_path.name,
                "metadata": {
                    "method": "imaging_simulation",
                    "algorithm_key": payload.get("algorithm_key", "generation.image.imaging_simulation"),
                    "parameters": {
                        "blur_kernel": blur_kernel,
                        "downsample": downsample,
                        "noise_std": noise_std,
                        "brightness_shift": brightness_shift,
                        "color_shift": color_shift,
                    },
                },
                "status": "created",
            }
        )
        context.set_progress((index + 1) * 100 / target_count, f"成像模拟 {index + 1}/{target_count}")

    return {"ok": True, "outputs": outputs, "logs": []}


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
