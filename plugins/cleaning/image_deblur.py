"""Image deblur cleaning plugin. Uses Laplacian variance to detect blur and sharpens via unsharp masking."""

from pathlib import Path
from typing import Optional


PARAMETERS = [
    {
        "name": 'blur_threshold',
        "type": 'int',
        "label": '模糊阈值',
        "default": 100,
        "min": 1,
        "max": 1000,
        "options": [],
        "description": 'Laplacian方差低于此值时判定为模糊',
        "required": False,
    },
    {
        "name": 'apply',
        "type": 'bool',
        "label": '写入修复结果',
        "default": True,
        "min": None,
        "max": None,
        "options": [],
        "description": '是否将去模糊后的图像写入磁盘',
        "required": False,
    },
    {
        "name": 'sharpen_amount',
        "type": 'float',
        "label": '锐化强度',
        "default": 1.2,
        "min": 0.1,
        "max": 3.0,
        "options": [],
        "description": '反锐化掩模强度，值越大边缘增强越明显',
        "required": False,
    },
]


def run(payload: dict, context) -> dict:
    parameters = payload.get("parameters", {}) or {}
    samples = payload.get("input", {}).get("samples", []) or []
    output_dir = Path(payload.get("output", {}).get("output_dir", "."))
    blur_threshold = float(parameters.get("blur_threshold", 100))
    apply_changes = bool(parameters.get("apply", True))
    sharpen_amount = max(0.1, min(float(parameters.get("sharpen_amount", 1.2)), 3.0))

    if not samples:
        return {"ok": True, "suggestions": [], "logs": []}

    total = max(len(samples), 1)
    suggestions = []

    for idx, sample in enumerate(samples):
        if context.is_cancel_requested():
            return {"ok": False, "error_code": "CANCELLED", "message": "任务已取消", "details": {}}
        context.set_progress((idx + 1) * 100 / total, f"去模糊检测 {idx + 1}/{total}")

        sample_path = _sample_path(sample)
        if not sample_path or not sample_path.is_file():
            continue

        score = _blur_score(sample_path)
        if score is None:
            continue

        if score < blur_threshold:
            confidence = _clamp(1.0 - score / max(blur_threshold, 1.0))
            output_path = ""
            if apply_changes:
                output_path = _deblur_and_save(sample_path, output_dir, sharpen_amount)
            suggestions.append({
                "sample_id": sample["id"],
                "issue_type": "image_blur",
                "suggested_action": "repair",
                "confidence": confidence,
                "message": f"Laplacian blur score {score:.1f} < threshold {blur_threshold:.0f}",
                "details": {"blur_score": score, "blur_threshold": blur_threshold,
                            "sharpen_amount": sharpen_amount,
                            "output_file_path": output_path, "processing_result": "deblurred"},
            })

    return {"ok": True, "suggestions": suggestions, "logs": []}


def _sample_path(sample: dict):
    path = sample.get("sample_path") or sample.get("path") or sample.get("file_path")
    if not path:
        return None
    return Path(path)


def _blur_score(path: Path) -> Optional[float]:
    try:
        import cv2
    except Exception:
        return None
    try:
        img = _read_image(path, cv2.IMREAD_GRAYSCALE)
        if img is None:
            return None
        return float(cv2.Laplacian(img, cv2.CV_64F).var())
    except Exception:
        return None


def _deblur_and_save(path: Path, output_dir: Path, sharpen_amount: float) -> str:
    try:
        import cv2
    except Exception:
        return ""
    try:
        img = _read_image(path, cv2.IMREAD_COLOR)
        if img is None:
            return ""
        blurred = cv2.GaussianBlur(img, (0, 0), 3)
        sharpened = cv2.addWeighted(img, 1.0 + sharpen_amount, blurred, -sharpen_amount, 0)
        output_dir.mkdir(parents=True, exist_ok=True)
        out_path = output_dir / f"deblurred_{path.name}"
        _write_image(out_path, sharpened)
        return str(out_path)
    except Exception:
        return ""


def _read_image(path: Path, flags):
    try:
        import cv2
        import numpy as np
        data = np.fromfile(str(path), dtype=np.uint8)
        if data.size == 0:
            return None
        return cv2.imdecode(data, flags)
    except Exception:
        return None


def _write_image(path: Path, image) -> bool:
    try:
        import cv2
        success, encoded = cv2.imencode(path.suffix or ".jpg", image)
        if not success:
            return False
        path.write_bytes(encoded.tobytes())
        return True
    except Exception:
        return False


def _clamp(v: float) -> float:
    return round(max(0.0, min(1.0, v)), 4)
