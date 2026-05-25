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
]


def run(payload: dict, context) -> dict:
    parameters = payload.get("parameters", {}) or {}
    samples = payload.get("input", {}).get("samples", []) or []
    output_dir = Path(payload.get("output", {}).get("output_dir", "."))
    blur_threshold = float(parameters.get("blur_threshold", 100))
    apply_changes = bool(parameters.get("apply", True))

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
                output_path = _deblur_and_save(sample_path, output_dir)
            suggestions.append({
                "sample_id": sample["id"],
                "issue_type": "image_blur",
                "suggested_action": "repair",
                "confidence": confidence,
                "message": f"Laplacian blur score {score:.1f} < threshold {blur_threshold:.0f}",
                "details": {"blur_score": score, "blur_threshold": blur_threshold,
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
        import numpy as np
    except Exception:
        return None
    try:
        img = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
        if img is None:
            return None
        return float(cv2.Laplacian(img, cv2.CV_64F).var())
    except Exception:
        return None


def _deblur_and_save(path: Path, output_dir: Path) -> str:
    try:
        import cv2
        import numpy as np
    except Exception:
        return ""
    try:
        img = cv2.imread(str(path))
        if img is None:
            return ""
        blurred = cv2.GaussianBlur(img, (0, 0), 3)
        sharpened = cv2.addWeighted(img, 1.6, blurred, -0.6, 0)
        output_dir.mkdir(parents=True, exist_ok=True)
        out_path = output_dir / f"deblurred_{path.name}"
        cv2.imwrite(str(out_path), sharpened)
        return str(out_path)
    except Exception:
        return ""


def _clamp(v: float) -> float:
    return round(max(0.0, min(1.0, v)), 4)
