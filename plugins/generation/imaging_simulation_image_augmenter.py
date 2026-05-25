from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from ._image_io import read_image, write_image


PARAMETERS = [
    {
        "name": 'shot_noise',
        "type": 'float',
        "label": '散粒噪声强度',
        "default": 0.0,
        "min": 0.0,
        "max": 0.5,
        "options": [],
        "description": '泊松分布散粒噪声强度',
        "required": False,
    },
    {
        "name": 'read_noise',
        "type": 'float',
        "label": '读出噪声标准差',
        "default": 0.0,
        "min": 0.0,
        "max": 0.1,
        "options": [],
        "description": '高斯分布读出噪声标准差',
        "required": False,
    },
    {
        "name": 'blur_kernel',
        "type": 'int',
        "label": '模糊核大小',
        "default": 0,
        "min": 0,
        "max": 15,
        "options": [],
        "description": '传感器模糊核大小，0表示不模糊',
        "required": False,
    },
    {
        "name": 'downsample',
        "type": 'float',
        "label": '下采样比例',
        "default": 1.0,
        "min": 0.1,
        "max": 1.0,
        "options": [],
        "description": '下采样比例，1.0表示不变',
        "required": False,
    },
]


def run(payload: dict, context) -> dict:
    """成像模拟增强：传感器噪声、下采样、光学模糊模拟。"""
    parameters = payload.get("parameters", {}) or {}
    output_dir = Path(payload.get("output", {}).get("output_dir") or ".")
    output_dir.mkdir(parents=True, exist_ok=True)

    samples = payload.get("input", {}).get("samples", []) or []
    if not samples:
        return {"ok": False, "error_code": "NO_INPUT_SAMPLES", "message": "未提供源样本。"}

    target_count = max(1, int(payload.get("target_count") or len(samples)))
    shot_strength = float(parameters.get("shot_strength", parameters.get("散粒噪声强度", 0.0)) or 0.0)
    read_noise_sigma = float(parameters.get("read_noise", parameters.get("读出噪声sigma", 0.0)) or 0.0)
    blur_kernel = int(parameters.get("blur_kernel", parameters.get("成像模糊核大小", 0)) or 0)
    downsample = float(parameters.get("downsample", parameters.get("下采样比例", 1.0)) or 1.0)

    outputs = []
    for index in range(target_count):
        if context.is_cancel_requested():
            return {"ok": False, "error_code": "CANCELLED", "message": "任务已取消"}

        sample = samples[index % len(samples)]
        source_path = Path(sample.get("sample_path") or sample.get("path") or "")
        img = read_image(source_path)
        if img is None:
            continue

        if len(img.shape) == 2:
            img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)

        out = img.astype(np.float32) / 255.0

        # 光学低通模糊
        if blur_kernel and blur_kernel > 1:
            k = blur_kernel
            if k % 2 == 0:
                k += 1
            out = cv2.GaussianBlur(out, (k, k), 0)

        # 下采样模拟链路分辨率损失
        if 0 < downsample < 1.0:
            h, w = out.shape[:2]
            nh = max(1, int(h * downsample))
            nw = max(1, int(w * downsample))
            small = cv2.resize(out, (nw, nh), interpolation=cv2.INTER_AREA)
            out = cv2.resize(small, (w, h), interpolation=cv2.INTER_LINEAR)

        # 散粒噪声（shot noise）
        if shot_strength > 0:
            shot_std = np.sqrt(np.clip(out, 0, 1)) * shot_strength
            out = out + np.random.normal(0, shot_std, size=out.shape).astype(np.float32)

        # 读出噪声
        if read_noise_sigma > 0:
            out = out + np.random.normal(0, read_noise_sigma, size=out.shape).astype(np.float32)

        out = np.clip(out, 0.0, 1.0)
        augmented = (out * 255.0).astype(np.uint8)

        output_path = output_dir / f"{source_path.stem}_imaging_{index:04d}{source_path.suffix or '.jpg'}"
        if not write_image(output_path, augmented):
            return {"ok": False, "error_code": "IMAGE_WRITE_ERROR", "message": f"Cannot write image: {output_path}"}

        outputs.append({
            "source_sample_id": sample.get("id"),
            "output_path": str(output_path),
            "relative_path": output_path.name,
            "metadata": {
                "method": "imaging_simulation",
                "algorithm_key": payload.get("algorithm_key", "generation.image.imaging_simulation"),
                "parameters": {"shot_strength": shot_strength, "read_noise_sigma": read_noise_sigma, "blur_kernel": blur_kernel, "downsample": downsample},
            },
            "status": "created",
        })
        context.set_progress((index + 1) * 100 / target_count, f"成像模拟 {index + 1}/{target_count}")

    return {"ok": True, "outputs": outputs, "logs": []}
