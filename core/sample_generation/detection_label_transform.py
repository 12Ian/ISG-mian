from __future__ import annotations

import math
from copy import deepcopy

import numpy as np


DEFAULT_MIN_VISIBILITY = 0.2
NORMALIZED_BBOX_FORMATS = {"cxcywh_normalized", "yolo", "normalized"}


class DetectionLabelTransformError(ValueError):
    pass


def has_detection_labels(labels) -> bool:
    return any(
        isinstance(label, dict)
        and (label.get("type") == "detection" or isinstance(label.get("bbox"), (list, tuple)))
        for label in (labels or [])
    )


def transform_crop_labels(
    labels,
    *,
    image_width: int,
    image_height: int,
    crop_x: int,
    crop_y: int,
    crop_width: int,
    crop_height: int,
    min_visibility: float = DEFAULT_MIN_VISIBILITY,
) -> list[dict]:
    """裁剪检测框；非检测标签保持不变。"""
    _validate_size(image_width, image_height)
    _validate_size(crop_width, crop_height)
    crop_left = float(crop_x)
    crop_top = float(crop_y)
    crop_right = crop_left + float(crop_width)
    crop_bottom = crop_top + float(crop_height)
    transformed = []

    for label in labels or []:
        if not _is_detection_label(label):
            transformed.append(deepcopy(label))
            continue

        left, top, right, bottom = _label_to_xyxy(label, image_width, image_height)
        original_area = max(0.0, right - left) * max(0.0, bottom - top)
        clipped_left = max(left, crop_left)
        clipped_top = max(top, crop_top)
        clipped_right = min(right, crop_right)
        clipped_bottom = min(bottom, crop_bottom)
        visible_area = max(0.0, clipped_right - clipped_left) * max(0.0, clipped_bottom - clipped_top)
        if original_area <= 0.0 or visible_area / original_area < min_visibility:
            continue

        new_label = deepcopy(label)
        new_label["bbox"] = _xyxy_to_normalized(
            clipped_left - crop_left,
            clipped_top - crop_top,
            clipped_right - crop_left,
            clipped_bottom - crop_top,
            crop_width,
            crop_height,
        )
        new_label["bbox_format"] = "cxcywh_normalized"
        transformed.append(new_label)

    return transformed


def transform_affine_labels(
    labels,
    *,
    image_width: int,
    image_height: int,
    matrix,
    output_width: int | None = None,
    output_height: int | None = None,
    min_visibility: float = DEFAULT_MIN_VISIBILITY,
) -> list[dict]:
    """按最终的二维仿射矩阵变换检测框，输出裁剪后的最小外接框。"""
    _validate_size(image_width, image_height)
    output_width = int(output_width or image_width)
    output_height = int(output_height or image_height)
    _validate_size(output_width, output_height)
    affine = np.asarray(matrix, dtype=np.float64)
    if affine.shape == (2, 3):
        affine = np.vstack([affine, [0.0, 0.0, 1.0]])
    if affine.shape != (3, 3) or not np.isfinite(affine).all():
        raise DetectionLabelTransformError("仿射变换矩阵必须是有效的 2x3 或 3x3 矩阵。")

    transformed = []
    for label in labels or []:
        if not _is_detection_label(label):
            transformed.append(deepcopy(label))
            continue

        left, top, right, bottom = _label_to_xyxy(label, image_width, image_height)
        corners = np.asarray(
            [[left, top, 1.0], [right, top, 1.0], [right, bottom, 1.0], [left, bottom, 1.0]],
            dtype=np.float64,
        )
        polygon = (affine @ corners.T).T[:, :2].tolist()
        transformed_area = _polygon_area(polygon)
        clipped = _clip_polygon_to_image(polygon, float(output_width), float(output_height))
        visible_area = _polygon_area(clipped)
        if transformed_area <= 0.0 or visible_area / transformed_area < min_visibility or not clipped:
            continue

        xs = [point[0] for point in clipped]
        ys = [point[1] for point in clipped]
        new_label = deepcopy(label)
        new_label["bbox"] = _xyxy_to_normalized(
            min(xs), min(ys), max(xs), max(ys), output_width, output_height
        )
        new_label["bbox_format"] = "cxcywh_normalized"
        transformed.append(new_label)

    return transformed


def transform_remap_labels(
    labels,
    *,
    image_width: int,
    image_height: int,
    map_x,
    map_y,
    min_visibility: float = DEFAULT_MIN_VISIBILITY,
) -> list[dict]:
    """根据 OpenCV remap 的目标像素到源像素映射重算检测框。"""
    _validate_size(image_width, image_height)
    source_x = np.asarray(map_x, dtype=np.float32)
    source_y = np.asarray(map_y, dtype=np.float32)
    if source_x.shape != (image_height, image_width) or source_y.shape != source_x.shape:
        raise DetectionLabelTransformError("remap 映射尺寸必须与输出图像一致。")
    if not np.isfinite(source_x).all() or not np.isfinite(source_y).all():
        raise DetectionLabelTransformError("remap 映射包含无效坐标。")

    transformed = []
    for label in labels or []:
        if not _is_detection_label(label):
            transformed.append(deepcopy(label))
            continue

        left, top, right, bottom = _label_to_xyxy(label, image_width, image_height)
        destination_mask = (
            (source_x >= left)
            & (source_x < right)
            & (source_y >= top)
            & (source_y < bottom)
        )
        ys, xs = np.nonzero(destination_mask)
        original_area = max(0.0, right - left) * max(0.0, bottom - top)
        visible_ratio = min(1.0, float(len(xs)) / max(original_area, 1.0))
        if len(xs) == 0 or visible_ratio < min_visibility:
            continue

        new_label = deepcopy(label)
        new_label["bbox"] = _xyxy_to_normalized(
            float(xs.min()),
            float(ys.min()),
            float(xs.max() + 1),
            float(ys.max() + 1),
            image_width,
            image_height,
        )
        new_label["bbox_format"] = "cxcywh_normalized"
        transformed.append(new_label)

    return transformed


def _is_detection_label(label) -> bool:
    return isinstance(label, dict) and (
        label.get("type") == "detection" or isinstance(label.get("bbox"), (list, tuple))
    )


def _label_to_xyxy(label: dict, image_width: int, image_height: int) -> tuple[float, float, float, float]:
    bbox = label.get("bbox")
    if not isinstance(bbox, (list, tuple)) or len(bbox) < 4:
        raise DetectionLabelTransformError("检测标签缺少有效 bbox。")
    bbox_format = str(label.get("bbox_format") or "cxcywh_normalized").strip().lower()
    if bbox_format not in NORMALIZED_BBOX_FORMATS:
        raise DetectionLabelTransformError(f"暂不支持 bbox 格式：{bbox_format}")
    try:
        center_x, center_y, width, height = [float(value) for value in bbox[:4]]
    except (TypeError, ValueError) as exc:
        raise DetectionLabelTransformError("检测框坐标必须是数字。") from exc
    values = (center_x, center_y, width, height)
    if not all(math.isfinite(value) for value in values) or width <= 0.0 or height <= 0.0:
        raise DetectionLabelTransformError("检测框坐标无效。")

    left = (center_x - width / 2.0) * image_width
    top = (center_y - height / 2.0) * image_height
    right = (center_x + width / 2.0) * image_width
    bottom = (center_y + height / 2.0) * image_height
    return left, top, right, bottom


def _xyxy_to_normalized(left, top, right, bottom, image_width, image_height) -> list[float]:
    left = max(0.0, min(float(image_width), float(left)))
    top = max(0.0, min(float(image_height), float(top)))
    right = max(0.0, min(float(image_width), float(right)))
    bottom = max(0.0, min(float(image_height), float(bottom)))
    width = right - left
    height = bottom - top
    if width <= 0.0 or height <= 0.0:
        raise DetectionLabelTransformError("变换后的检测框无效。")
    return [
        ((left + right) / 2.0) / image_width,
        ((top + bottom) / 2.0) / image_height,
        width / image_width,
        height / image_height,
    ]


def _clip_polygon_to_image(polygon, width: float, height: float):
    clipped = list(polygon)
    clipped = _clip_polygon(clipped, axis=0, boundary=0.0, keep_greater=True)
    clipped = _clip_polygon(clipped, axis=0, boundary=width, keep_greater=False)
    clipped = _clip_polygon(clipped, axis=1, boundary=0.0, keep_greater=True)
    return _clip_polygon(clipped, axis=1, boundary=height, keep_greater=False)


def _clip_polygon(polygon, *, axis: int, boundary: float, keep_greater: bool):
    if not polygon:
        return []

    def inside(point):
        return point[axis] >= boundary if keep_greater else point[axis] <= boundary

    def intersection(start, end):
        delta = end[axis] - start[axis]
        if abs(delta) < 1e-12:
            return [float(start[0]), float(start[1])]
        ratio = (boundary - start[axis]) / delta
        return [
            float(start[0] + ratio * (end[0] - start[0])),
            float(start[1] + ratio * (end[1] - start[1])),
        ]

    result = []
    previous = polygon[-1]
    previous_inside = inside(previous)
    for current in polygon:
        current_inside = inside(current)
        if current_inside:
            if not previous_inside:
                result.append(intersection(previous, current))
            result.append([float(current[0]), float(current[1])])
        elif previous_inside:
            result.append(intersection(previous, current))
        previous = current
        previous_inside = current_inside
    return result


def _polygon_area(polygon) -> float:
    if len(polygon) < 3:
        return 0.0
    area = 0.0
    for index, point in enumerate(polygon):
        next_point = polygon[(index + 1) % len(polygon)]
        area += point[0] * next_point[1] - next_point[0] * point[1]
    return abs(area) / 2.0


def _validate_size(width: int, height: int) -> None:
    if int(width) <= 0 or int(height) <= 0:
        raise DetectionLabelTransformError("图像尺寸必须大于零。")
