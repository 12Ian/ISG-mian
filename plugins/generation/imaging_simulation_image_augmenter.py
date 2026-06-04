from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from ._image_io import read_image, write_image


PARAMETERS = [
    {
        "name": "noise_type",
        "type": "select",
        "label": "噪声类型",
        "default": "none",
        "min": None,
        "max": None,
        "options": ["none", "gaussian", "salt_pepper", "multiplicative"],
        "description": "选择注入的噪声类型",
        "required": False,
    },
    {
        "name": "noise_intensity",
        "type": "float",
        "label": "噪声强度",
        "default": 0.1,
        "min": 0.0,
        "max": 1.0,
        "options": [],
        "description": "通用噪声强度参数",
        "required": False,
    },
    {
        "name": "salt_pepper_ratio",
        "type": "float",
        "label": "椒盐比例",
        "default": 0.5,
        "min": 0.0,
        "max": 1.0,
        "options": [],
        "description": "椒盐噪声中盐噪声所占比例",
        "required": False,
    },
    {
        "name": "shot_noise",
        "type": "float",
        "label": "散粒噪声强度",
        "default": 0.0,
        "min": 0.0,
        "max": 0.5,
        "options": [],
        "description": "泊松分布散粒噪声强度",
        "required": False,
    },
    {
        "name": "read_noise",
        "type": "float",
        "label": "读出噪声标准差",
        "default": 0.0,
        "min": 0.0,
        "max": 0.1,
        "options": [],
        "description": "高斯分布读出噪声标准差",
        "required": False,
    },
    {
        "name": "blur_kernel",
        "type": "int",
        "label": "模糊核大小",
        "default": 0,
        "min": 0,
        "max": 15,
        "options": [],
        "description": "传感器模糊核大小，0表示不模糊",
        "required": False,
    },
    {
        "name": "downsample",
        "type": "float",
        "label": "下采样比例",
        "default": 1.0,
        "min": 0.1,
        "max": 1.0,
        "options": [],
        "description": "下采样比例，1.0表示不变",
        "required": False,
    },
]


def run(payload: dict, context) -> dict:
    """成像模拟及噪声注入：传感器噪声、下采样、光学模糊模拟。"""
    parameters = payload.get("parameters", {}) or {}
    output_dir = Path(payload.get("output", {}).get("output_dir") or ".")
    output_dir.mkdir(parents=True, exist_ok=True)

    samples = payload.get("input", {}).get("samples", []) or []
    if not samples:
        return {"ok": False, "error_code": "NO_INPUT_SAMPLES", "message": "未提供源样本。"}

    target_count = max(1, int(payload.get("target_count") or len(samples)))
    noise_type = str(parameters.get("noise_type", parameters.get("噪声类型", "none")) or "none").lower()
    noise_intensity = float(parameters.get("noise_intensity", parameters.get("噪声强度", 0.1)) or 0.1)
    salt_pepper_ratio = float(parameters.get("salt_pepper_ratio", parameters.get("椒盐比例", 0.5)) or 0.5)
    shot_strength = float(parameters.get("shot_noise", parameters.get("散粒噪声强度", 0.0)) or 0.0)
    read_noise_sigma = float(parameters.get("read_noise", parameters.get("读出噪声sigma", 0.0)) or 0.0)
    blur_kernel = int(parameters.get("blur_kernel", parameters.get("成像模糊核大小", 0)) or 0)
    downsample = float(parameters.get("downsample", parameters.get("下采样比例", 1.0)) or 1.0)

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

        if blur_kernel and blur_kernel > 1:
            k = blur_kernel if blur_kernel % 2 == 1 else blur_kernel + 1
            out = cv2.GaussianBlur(out, (k, k), 0)

        if 0 < downsample < 1.0:
            h, w = out.shape[:2]
            nh = max(1, int(h * downsample))
            nw = max(1, int(w * downsample))
            small = cv2.resize(out, (nw, nh), interpolation=cv2.INTER_AREA)
            out = cv2.resize(small, (w, h), interpolation=cv2.INTER_LINEAR)

        if noise_type == "gaussian":
            out = out + np.random.normal(0, noise_intensity, size=out.shape).astype(np.float32)
        elif noise_type == "salt_pepper":
            out = _apply_salt_pepper_noise(out, noise_intensity, salt_pepper_ratio)
        elif noise_type == "multiplicative":
            out = out * (1.0 + np.random.normal(0, noise_intensity, size=out.shape).astype(np.float32))
        else:
            if shot_strength > 0:
                shot_std = np.sqrt(np.clip(out, 0, 1)) * shot_strength
                out = out + np.random.normal(0, shot_std, size=out.shape).astype(np.float32)

            if read_noise_sigma > 0:
                out = out + np.random.normal(0, read_noise_sigma, size=out.shape).astype(np.float32)

        out = np.clip(out, 0.0, 1.0)
        augmented = (out * 255.0).astype(np.uint8)

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
                        "noise_type": noise_type,
                        "noise_intensity": noise_intensity,
                        "salt_pepper_ratio": salt_pepper_ratio,
                        "shot_noise": shot_strength,
                        "read_noise": read_noise_sigma,
                        "blur_kernel": blur_kernel,
                        "downsample": downsample,
                    },
                },
                "status": "created",
            }
        )
        context.set_progress((index + 1) * 100 / target_count, f"成像模拟及噪声注入 {index + 1}/{target_count}")

    return {"ok": True, "outputs": outputs, "logs": []}


def _apply_salt_pepper_noise(out, intensity: float, salt_ratio: float):
    noisy = out.copy()
    if intensity <= 0:
        return noisy

    intensity = float(max(0.0, min(intensity, 1.0)))
    salt_ratio = float(max(0.0, min(salt_ratio, 1.0)))
    total = noisy.shape[0] * noisy.shape[1]
    num_pixels = max(1, int(total * intensity))
    num_salt = int(num_pixels * salt_ratio)

    ys = np.random.randint(0, noisy.shape[0], size=num_pixels)
    xs = np.random.randint(0, noisy.shape[1], size=num_pixels)
    if noisy.ndim == 2:
        noisy[ys[:num_salt], xs[:num_salt]] = 1.0
        noisy[ys[num_salt:], xs[num_salt:]] = 0.0
    else:
        noisy[ys[:num_salt], xs[:num_salt], :] = 1.0
        noisy[ys[num_salt:], xs[num_salt:], :] = 0.0
    return noisy
