from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from core.sample_generation.detection_label_transform import transform_affine_labels


PARAMETERS = [
    {
        "name": 'rotation_degrees',
        "type": 'float',
        "label": '旋转角度',
        "default": 15.0,
        "min": -360.0,
        "max": 360.0,
        "options": [],
        "description": '围绕图像中心旋转的角度',
        "required": False,
    },
    {
        "name": 'scale',
        "type": 'float',
        "label": '缩放比例',
        "default": 0.92,
        "min": 0.1,
        "max": 5.0,
        "options": [],
        "description": '几何变换缩放比例',
        "required": False,
    },
    {
        "name": 'translate_x_pct',
        "type": 'float',
        "label": '水平平移百分比',
        "default": 6.0,
        "min": -100.0,
        "max": 100.0,
        "options": [],
        "description": '相对图像宽度的水平平移百分比',
        "required": False,
    },
    {
        "name": 'translate_y_pct',
        "type": 'float',
        "label": '垂直平移百分比',
        "default": -4.0,
        "min": -100.0,
        "max": 100.0,
        "options": [],
        "description": '相对图像高度的垂直平移百分比',
        "required": False,
    },
    {
        "name": 'flip_horizontal',
        "type": 'bool',
        "label": '水平翻转',
        "default": False,
        "min": None,
        "max": None,
        "options": [],
        "description": '是否执行水平翻转',
        "required": False,
    },
    {
        "name": 'flip_vertical',
        "type": 'bool',
        "label": '垂直翻转',
        "default": False,
        "min": None,
        "max": None,
        "options": [],
        "description": '是否执行垂直翻转',
        "required": False,
    },
    {
        "name": 'border_value',
        "type": 'int',
        "label": '边界填充值',
        "default": 0,
        "min": 0,
        "max": 255,
        "options": [],
        "description": '仿射变换边界填充像素值',
        "required": False,
    },
]


def run(payload: dict, context) -> dict:
    parameters = payload.get("parameters", {}) or {}
    output_dir = Path(payload.get("output", {}).get("output_dir") or ".")
    output_dir.mkdir(parents=True, exist_ok=True)

    samples = payload.get("input", {}).get("samples", []) or []
    if not samples:
        return {"ok": False, "error_code": "NO_INPUT_SAMPLES", "message": "No source samples provided."}

    target_count = max(1, int(payload.get("target_count") or parameters.get("target_count") or len(samples)))
    rotation = _as_float(parameters.get("rotation_degrees", parameters.get("angle", 15.0)), 15.0)
    scale = _as_float(parameters.get("scale", 0.92), 0.92)
    translate_x_pct = _as_float(parameters.get("translate_x_pct", 6.0), 6.0)
    translate_y_pct = _as_float(parameters.get("translate_y_pct", -4.0), -4.0)
    flip_horizontal = _as_bool(parameters.get("flip_horizontal", False))
    flip_vertical = _as_bool(parameters.get("flip_vertical", False))
    border_value = int(parameters.get("border_value", 0) or 0)

    outputs = []
    for index in range(target_count):
        if context.is_cancel_requested():
            return {"ok": False, "error_code": "CANCELLED", "message": "Generation cancelled."}

        sample = samples[index % len(samples)]
        source_path = Path(sample.get("sample_path") or sample.get("path") or sample.get("file_path") or "")
        image = _read_image(source_path)
        if image is None:
            return {"ok": False, "error_code": "IMAGE_READ_ERROR", "message": f"Cannot read image: {source_path}"}

        h, w = image.shape[:2]
        matrix = _build_affine_matrix(
            width=w,
            height=h,
            rotation_degrees=rotation,
            scale=scale,
            translate_x_pct=translate_x_pct,
            translate_y_pct=translate_y_pct,
        )
        augmented = _transform_image(
            image,
            matrix=matrix,
            flip_horizontal=flip_horizontal,
            flip_vertical=flip_vertical,
            border_value=border_value,
        )
        label_matrix = _compose_flip_matrix(matrix, w, h, flip_horizontal, flip_vertical)
        labels = transform_affine_labels(
            sample.get("labels") or sample.get("labels_json") or [],
            image_width=w,
            image_height=h,
            matrix=label_matrix,
        )
        output_path = output_dir / f"{source_path.stem}_geo_{index:04d}{source_path.suffix or '.jpg'}"
        if not _write_image(output_path, augmented):
            return {"ok": False, "error_code": "IMAGE_WRITE_ERROR", "message": f"Cannot write image: {output_path}"}

        metadata = {
            "method": "geometric_transform",
            "algorithm_key": payload.get("algorithm_key", "generation.image.geometric_transform"),
            "source_sample_id": sample.get("id"),
            "source_sample_path": str(source_path),
            "augmented_sample_path": str(output_path),
            "parameters": {
                "rotation_degrees": rotation,
                "scale": scale,
                "translate_x_pct": translate_x_pct,
                "translate_y_pct": translate_y_pct,
                "flip_horizontal": flip_horizontal,
                "flip_vertical": flip_vertical,
                "border_value": border_value,
            },
        }
        outputs.append(
            {
                "source_sample_id": sample.get("id"),
                "output_path": str(output_path),
                "relative_path": output_path.name,
                "labels": labels,
                "label_policy": "transformed",
                "metadata": metadata,
                "status": "created",
            }
        )
        context.set_progress((index + 1) * 100 / target_count, f"generated {index + 1}/{target_count}")

    return {"ok": True, "outputs": outputs, "logs": []}


def _transform_image(
    image,
    *,
    matrix,
    flip_horizontal: bool,
    flip_vertical: bool,
    border_value: int,
):
    height, width = image.shape[:2]
    transformed = cv2.warpAffine(
        image,
        matrix,
        (width, height),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=_border_value_for(image, border_value),
    )
    if flip_horizontal and flip_vertical:
        transformed = cv2.flip(transformed, -1)
    elif flip_horizontal:
        transformed = cv2.flip(transformed, 1)
    elif flip_vertical:
        transformed = cv2.flip(transformed, 0)
    return transformed


def _build_affine_matrix(
    *,
    width: int,
    height: int,
    rotation_degrees: float,
    scale: float,
    translate_x_pct: float,
    translate_y_pct: float,
):
    matrix = cv2.getRotationMatrix2D((width / 2.0, height / 2.0), rotation_degrees, scale)
    matrix[0, 2] += width * translate_x_pct / 100.0
    matrix[1, 2] += height * translate_y_pct / 100.0
    return matrix


def _compose_flip_matrix(matrix, width: int, height: int, flip_horizontal: bool, flip_vertical: bool):
    result = np.vstack([np.asarray(matrix, dtype=np.float64), [0.0, 0.0, 1.0]])
    if flip_horizontal:
        result = np.asarray([[-1.0, 0.0, float(width)], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]) @ result
    if flip_vertical:
        result = np.asarray([[1.0, 0.0, 0.0], [0.0, -1.0, float(height)], [0.0, 0.0, 1.0]]) @ result
    return result


def _border_value_for(image, value: int):
    channels = 1 if len(image.shape) == 2 else image.shape[2]
    if channels == 1:
        return value
    return tuple([value] * channels)


def _as_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y", "是"}


def _as_float(value, default: float) -> float:
    if value in (None, ""):
        return float(default)
    return float(value)


def _read_image(path: Path):
    data = np.frombuffer(path.read_bytes(), dtype=np.uint8)
    return cv2.imdecode(data, cv2.IMREAD_UNCHANGED)


def _write_image(path: Path, image) -> bool:
    ext = path.suffix or ".jpg"
    ok, encoded = cv2.imencode(ext, image)
    if not ok:
        return False
    path.write_bytes(encoded.tobytes())
    return True
