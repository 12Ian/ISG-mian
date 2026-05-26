from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from ._image_io import read_image, write_image


PARAMETERS = [
    {
        "name": 'brightness',
        "type": 'float',
        "label": '亮度增量',
        "default": 0.0,
        "min": -1.0,
        "max": 1.0,
        "options": [],
        "description": '亮度调整增量',
        "required": False,
    },
    {
        "name": 'contrast',
        "type": 'float',
        "label": '对比度系数',
        "default": 1.0,
        "min": 0.0,
        "max": 3.0,
        "options": [],
        "description": '对比度缩放系数',
        "required": False,
    },
    {
        "name": 'saturation',
        "type": 'float',
        "label": '饱和度系数',
        "default": 1.0,
        "min": 0.0,
        "max": 3.0,
        "options": [],
        "description": '饱和度缩放系数',
        "required": False,
    },
    {
        "name": 'hue',
        "type": 'float',
        "label": '色相偏移',
        "default": 0.0,
        "min": -180.0,
        "max": 180.0,
        "options": [],
        "description": '色相偏移量',
        "required": False,
    },
    {
        "name": 'pca_jitter',
        "type": 'float',
        "label": 'PCA颜色抖动',
        "default": 0.0,
        "min": 0.0,
        "max": 1.0,
        "options": [],
        "description": 'PCA颜色抖动强度',
        "required": False,
    },
]


def run(payload: dict, context) -> dict:
    """色域变换增强：亮度/对比度/饱和度抖动与 PCA Lighting。"""
    parameters = payload.get("parameters", {}) or {}
    output_dir = Path(payload.get("output", {}).get("output_dir") or ".")
    output_dir.mkdir(parents=True, exist_ok=True)

    samples = payload.get("input", {}).get("samples", []) or []
    if not samples:
        return {"ok": False, "error_code": "NO_INPUT_SAMPLES", "message": "未提供源样本。"}

    target_count = max(1, int(payload.get("target_count") or len(samples)))
    brightness_delta = float(parameters.get("brightness", parameters.get("亮度调整值", 0.0)) or 0.0)
    contrast_alpha = float(parameters.get("contrast", parameters.get("对比度缩放", 1.0)) or 1.0)
    sat_scale = float(parameters.get("saturation", parameters.get("饱和度缩放", 1.0)) or 1.0)
    hue_delta = float(parameters.get("hue", parameters.get("色相偏移", 0.0)) or 0.0)
    pca_strength = float(parameters.get("pca_strength", parameters.get("PCA抖动强度", 0.0)) or 0.0)

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

        img_f = img.astype(np.float32)

        # 亮度/对比度调整
        img_f = img_f * contrast_alpha + brightness_delta

        # 饱和度与色相调整（在 HSV 空间操作）
        hsv = cv2.cvtColor(np.clip(img_f, 0, 255).astype(np.uint8), cv2.COLOR_BGR2HSV).astype(np.float32)
        hsv[..., 1] = np.clip(hsv[..., 1] * sat_scale, 0, 255)
        hsv[..., 0] = (hsv[..., 0] + hue_delta) % 180
        img_f = cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2BGR).astype(np.float32)

        # PCA Lighting（AlexNet 风格颜色增强）
        if pca_strength != 0.0:
            pixels = img_f.reshape(-1, 3)
            mean = np.mean(pixels, axis=0, keepdims=True)
            centered = pixels - mean
            cov = np.cov(centered, rowvar=False)
            eigvals, eigvecs = np.linalg.eigh(cov)
            order = np.argsort(eigvals)[::-1]
            eigvals = eigvals[order]
            eigvecs = eigvecs[:, order]
            alpha = np.random.normal(0, 1, size=(3,)).astype(np.float32)
            lighting = eigvecs @ (np.sqrt(np.maximum(eigvals, 0)) * alpha)
            img_f = img_f + lighting.astype(np.float32) * pca_strength

        augmented = np.clip(img_f, 0, 255).astype(np.uint8)
        output_path = output_dir / f"{source_path.stem}_color_{index:04d}{source_path.suffix or '.jpg'}"
        if not write_image(output_path, augmented):
            return {"ok": False, "error_code": "IMAGE_WRITE_ERROR", "message": f"Cannot write image: {output_path}"}

        outputs.append({
            "source_sample_id": sample.get("id"),
            "output_path": str(output_path),
            "relative_path": output_path.name,
            "metadata": {
                "method": "color_space",
                "algorithm_key": payload.get("algorithm_key", "generation.image.color_space"),
                "parameters": {
                    "brightness_delta": brightness_delta,
                    "contrast_alpha": contrast_alpha,
                    "sat_scale": sat_scale,
                    "hue_delta": hue_delta,
                    "pca_strength": pca_strength,
                },
            },
            "status": "created",
        })
        context.set_progress((index + 1) * 100 / target_count, f"色域变换 {index + 1}/{target_count}")

    return {"ok": True, "outputs": outputs, "logs": []}
