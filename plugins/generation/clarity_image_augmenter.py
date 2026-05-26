from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from ._image_io import read_image, write_image


PARAMETERS = [
    {
        "name": 'blur_strength',
        "type": 'float',
        "label": '模糊强度',
        "default": 0.0,
        "min": 0.0,
        "max": 10.0,
        "options": [],
        "description": '高斯模糊sigma值',
        "required": False,
    },
    {
        "name": 'blur_kernel',
        "type": 'int',
        "label": '模糊核大小',
        "default": 5,
        "min": 3,
        "max": 31,
        "options": [],
        "description": '高斯模糊卷积核尺寸（奇数）',
        "required": False,
    },
    {
        "name": 'sharpen_strength',
        "type": 'float',
        "label": '锐化强度',
        "default": 0.0,
        "min": 0.0,
        "max": 5.0,
        "options": [],
        "description": '反锐化掩模锐化强度',
        "required": False,
    },
    {
        "name": 'sharpen_amount',
        "type": 'float',
        "label": '锐化叠加比例',
        "default": 0.5,
        "min": 0.0,
        "max": 1.0,
        "options": [],
        "description": '锐化叠加比例',
        "required": False,
    },
]


def run(payload: dict, context) -> dict:
    """清晰度变换增强：高斯模糊与反锐化掩模锐化。"""
    parameters = payload.get("parameters", {}) or {}
    output_dir = Path(payload.get("output", {}).get("output_dir") or ".")
    output_dir.mkdir(parents=True, exist_ok=True)

    samples = payload.get("input", {}).get("samples", []) or []
    if not samples:
        return {"ok": False, "error_code": "NO_INPUT_SAMPLES", "message": "未提供源样本。"}

    target_count = max(1, int(payload.get("target_count") or len(samples)))
    blur_strength = float(parameters.get("blur_strength", parameters.get("模糊强度", 0.0)) or 0.0)
    blur_kernel = int(parameters.get("blur_kernel", parameters.get("模糊核大小", 5)) or 5)
    sharp_strength = float(parameters.get("sharp_strength", parameters.get("锐化强度", 0.0)) or 0.0)
    sharp_amount = float(parameters.get("sharp_amount", parameters.get("锐化量", 0.5)) or 0.5)

    outputs = []
    for index in range(target_count):
        if context.is_cancel_requested():
            return {"ok": False, "error_code": "CANCELLED", "message": "任务已取消"}

        sample = samples[index % len(samples)]
        source_path = Path(sample.get("sample_path") or sample.get("path") or sample.get("file_path") or "")
        img = read_image(source_path)
        if img is None:
            continue

        if len(img.shape) == 2:
            img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)

        out = img

        # 高斯模糊：根据强度增大核大小
        if blur_strength > 0:
            k = max(3, blur_kernel)
            if k % 2 == 0:
                k += 1
            k = int(min(k + int(blur_strength * 10), 31))
            if k % 2 == 0:
                k += 1
            out = cv2.GaussianBlur(out, (k, k), 0)

        # 反锐化掩模锐化：out + amount * (out - blurred)
        if sharp_strength > 0:
            amount = max(0.0, sharp_amount)
            blurred = cv2.GaussianBlur(out, (3, 3), 1.0)
            out = cv2.addWeighted(out, 1.0 + amount, blurred, -amount, 0)

        output_path = output_dir / f"{source_path.stem}_clarity_{index:04d}{source_path.suffix or '.jpg'}"
        if not write_image(output_path, out):
            return {"ok": False, "error_code": "IMAGE_WRITE_ERROR", "message": f"Cannot write image: {output_path}"}

        outputs.append({
            "source_sample_id": sample.get("id"),
            "output_path": str(output_path),
            "relative_path": output_path.name,
            "metadata": {
                "method": "clarity",
                "algorithm_key": payload.get("algorithm_key", "generation.image.clarity"),
                "parameters": {
                    "blur_strength": blur_strength, "blur_kernel": blur_kernel,
                    "sharp_strength": sharp_strength, "sharp_amount": sharp_amount,
                },
            },
            "status": "created",
        })
        context.set_progress((index + 1) * 100 / target_count, f"清晰度变换 {index + 1}/{target_count}")

    return {"ok": True, "outputs": outputs, "logs": []}
