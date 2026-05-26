from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from ._image_io import read_image, write_image


PARAMETERS = [
    {
        "name": "fog_intensity",
        "type": "float",
        "label": "雾气浓度",
        "default": 0.0,
        "min": 0.0,
        "max": 1.0,
        "options": [],
        "description": "大气散射模拟强度",
        "required": False,
    },
    {
        "name": "snow_intensity",
        "type": "float",
        "label": "雪花强度",
        "default": 0.0,
        "min": 0.0,
        "max": 1.0,
        "options": [],
        "description": "雪花叠加强度",
        "required": False,
    },
    {
        "name": "shadow_intensity",
        "type": "float",
        "label": "阴影强度",
        "default": 0.0,
        "min": 0.0,
        "max": 1.0,
        "options": [],
        "description": "随机阴影块强度",
        "required": False,
    },
]


def run(payload: dict, context) -> dict:
    """环境模拟增强：雾、雪、阴影效果叠加。"""
    parameters = payload.get("parameters", {}) or {}
    output_dir = Path(payload.get("output", {}).get("output_dir") or ".")
    output_dir.mkdir(parents=True, exist_ok=True)

    samples = payload.get("input", {}).get("samples", []) or []
    if not samples:
        return {"ok": False, "error_code": "NO_INPUT_SAMPLES", "message": "未提供源样本。"}

    target_count = max(1, int(payload.get("target_count") or len(samples)))
    fog_strength = float(parameters.get("fog_intensity", parameters.get("fog", parameters.get("雾气浓度", 0.0))) or 0.0)
    snow_strength = float(parameters.get("snow_intensity", parameters.get("snow", parameters.get("雪强度", 0.0))) or 0.0)
    shadow_strength = float(parameters.get("shadow_intensity", parameters.get("shadow", parameters.get("阴影强度", 0.0))) or 0.0)

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

        h, w = img.shape[:2]
        out = img.astype(np.float32)

        if fog_strength > 0:
            depth = np.random.rand(h, w).astype(np.float32)
            depth = cv2.GaussianBlur(depth, (51, 51), 0)
            depth = depth - depth.min()
            depth = depth / (depth.max() + 1e-6)
            trans = np.exp(-fog_strength * 2.0 * depth)
            trans = trans[..., None]
            airlight = np.array([200, 200, 200], dtype=np.float32)
            out = out * trans + airlight * (1.0 - trans)

        if snow_strength > 0:
            snow = np.zeros((h, w), dtype=np.uint8)
            n_snow = int((h * w) * 0.00005 * snow_strength + 30 * snow_strength)
            n_snow = max(10, n_snow)
            for _ in range(n_snow):
                x = int(np.random.randint(0, w))
                y = int(np.random.randint(0, h))
                r = int(np.random.randint(1, 3 + int(3 * snow_strength)))
                cv2.circle(snow, (x, y), r, 255, -1)
            snow_f = cv2.GaussianBlur(snow, (9, 9), 0).astype(np.float32) / 255.0
            out = out * (1.0 - 0.5 * snow_strength) + 255.0 * snow_f[..., None] * (0.5 * snow_strength)

        if shadow_strength > 0:
            mask = np.ones((h, w), dtype=np.float32)
            n_ell = 1 + int(shadow_strength > 0.2)
            for _ in range(n_ell):
                cx = int(np.random.randint(0, w))
                cy = int(np.random.randint(0, h))
                ax = int(w * np.random.uniform(0.3, 0.8))
                ay = int(h * np.random.uniform(0.3, 0.8))
                angle = float(np.random.uniform(0, 180))
                ellipse = np.zeros((h, w), dtype=np.uint8)
                cv2.ellipse(ellipse, (cx, cy), (ax, ay), angle, 0, 360, 255, -1)
                ellipse_f = cv2.GaussianBlur(ellipse.astype(np.float32), (31, 31), 0) / 255.0
                mask = mask * (1.0 - ellipse_f * 0.6 * shadow_strength)
            out = out * mask[..., None]

        augmented = np.clip(out, 0, 255).astype(np.uint8)
        output_path = output_dir / f"{source_path.stem}_env_{index:04d}{source_path.suffix or '.jpg'}"
        if not write_image(output_path, augmented):
            return {"ok": False, "error_code": "IMAGE_WRITE_ERROR", "message": f"Cannot write image: {output_path}"}

        outputs.append(
            {
                "source_sample_id": sample.get("id"),
                "output_path": str(output_path),
                "relative_path": output_path.name,
                "metadata": {
                    "method": "environment_simulation",
                    "algorithm_key": payload.get("algorithm_key", "generation.image.environment_simulation"),
                    "parameters": {
                        "fog": fog_strength,
                        "snow": snow_strength,
                        "shadow": shadow_strength,
                    },
                },
                "status": "created",
            }
        )
        context.set_progress((index + 1) * 100 / target_count, f"环境模拟 {index + 1}/{target_count}")

    return {"ok": True, "outputs": outputs, "logs": []}
