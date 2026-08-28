from __future__ import annotations

import json
import math
import re
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path

import yaml
from PIL import Image


IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".gif", ".webp", ".tif", ".tiff"}
SUPPORTED_FORMATS = ("yolo", "coco", "voc", "labelme")
NORMALIZED_BBOX_TOLERANCE = 1e-4


class AnnotationFormatError(ValueError):
    pass


def scan_detection_dataset(folder: str | Path, default_split: str = "train") -> dict | None:
    """扫描目录并把检测标注统一为归一化 cx/cy/w/h。"""
    root = Path(folder).expanduser().resolve()
    if not root.is_dir():
        return None

    image_index = _build_image_index(root)
    coco_files: list[tuple[Path, dict]] = []
    labelme_files: list[tuple[Path, dict]] = []
    voc_files: list[tuple[Path, ET.Element]] = []
    unreadable_annotations = []

    for path in sorted(root.rglob("*.json")):
        if path.name == "dataset_manifest.json":
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            if _looks_like_json_annotation(path):
                unreadable_annotations.append(path)
            continue
        if _is_coco_payload(payload):
            coco_files.append((path, payload))
        elif _is_labelme_payload(payload):
            labelme_files.append((path, payload))

    for path in sorted(root.rglob("*.xml")):
        try:
            xml_root = ET.parse(path).getroot()
        except (OSError, ET.ParseError):
            if path.parent.name.casefold() == "annotations":
                unreadable_annotations.append(path)
            continue
        if _xml_tag(xml_root) == "annotation":
            voc_files.append((path, xml_root))

    yolo_pairs = _find_yolo_pairs(root)
    detected = []
    if yolo_pairs:
        detected.append("yolo")
    if coco_files:
        detected.append("coco")
    if voc_files:
        detected.append("voc")
    if labelme_files:
        detected.append("labelme")

    if unreadable_annotations:
        names = ", ".join(path.name for path in unreadable_annotations[:3])
        raise AnnotationFormatError(f"标注文件无法解析：{names}")
    if not detected:
        return None
    if len(detected) > 1:
        raise AnnotationFormatError(
            f"检测到多种目标检测标注格式：{', '.join(detected)}。请只保留一套标注后重新导入。"
        )

    annotation_format = detected[0]
    report = {
        "format": annotation_format,
        "annotation_files": [],
        "image_count": 0,
        "box_count": 0,
        "class_names": [],
        "warnings": [],
        "errors": [],
    }
    if annotation_format == "yolo":
        records = _parse_yolo(root, yolo_pairs, report, default_split)
    elif annotation_format == "coco":
        records = _parse_coco(root, coco_files, image_index, report, default_split)
    elif annotation_format == "voc":
        records = _parse_voc(root, voc_files, image_index, report, default_split)
    else:
        records = _parse_labelme(root, labelme_files, image_index, report, default_split)

    records = _deduplicate_records(records, report)
    if not records:
        _add_error(report, root, f"{annotation_format.upper()} 标注中没有找到可用图片")
    class_names = sorted(
        {
            str(label.get("class_name") or "").strip()
            for record in records
            for label in record.get("labels", [])
            if str(label.get("class_name") or "").strip()
        },
        key=str.casefold,
    )
    report["image_count"] = len(records)
    report["box_count"] = sum(len(record.get("labels", [])) for record in records)
    report["class_names"] = class_names
    if records and not class_names:
        _add_error(report, root, "标注中没有找到任何有效目标类别")
    return {"format": annotation_format, "records": records, "report": report}


def summarize_annotation_errors(report: dict, limit: int = 3) -> str:
    errors = list(report.get("errors") or [])
    if not errors:
        return ""
    messages = [str(item.get("message") or item) for item in errors[:limit]]
    remaining = len(errors) - len(messages)
    if remaining > 0:
        messages.append(f"另有 {remaining} 个错误")
    return "；".join(messages)


def _build_image_index(root: Path) -> dict:
    images = sorted(path for path in root.rglob("*") if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS)
    by_relative = {}
    by_name: dict[str, list[Path]] = defaultdict(list)
    by_stem: dict[str, list[Path]] = defaultdict(list)
    for image_path in images:
        relative = image_path.relative_to(root).as_posix().casefold()
        by_relative[relative] = image_path
        by_name[image_path.name.casefold()].append(image_path)
        by_stem[image_path.stem.casefold()].append(image_path)
    return {
        "images": images,
        "by_relative": by_relative,
        "by_name": by_name,
        "by_stem": by_stem,
    }


def _is_coco_payload(payload) -> bool:
    return (
        isinstance(payload, dict)
        and isinstance(payload.get("images"), list)
        and isinstance(payload.get("annotations"), list)
        and isinstance(payload.get("categories"), list)
    )


def _is_labelme_payload(payload) -> bool:
    return isinstance(payload, dict) and isinstance(payload.get("shapes"), list) and "imagePath" in payload


def _looks_like_json_annotation(path: Path) -> bool:
    stem = path.stem.casefold()
    return "annotation" in stem or stem.startswith("instances") or path.parent.name.casefold() == "annotations"


def _parse_coco(root, files, image_index, report, default_split):
    records = []
    for annotation_path, payload in files:
        report["annotation_files"].append(_path_text(annotation_path))
        category_names = {
            item.get("id"): str(item.get("name") or "").strip()
            for item in payload.get("categories", [])
            if item.get("id") is not None and str(item.get("name") or "").strip()
        }
        images_by_id = {
            item.get("id"): item for item in payload.get("images", []) if item.get("id") is not None
        }
        annotations_by_image: dict[object, list[dict]] = defaultdict(list)
        for annotation in payload.get("annotations", []):
            annotations_by_image[annotation.get("image_id")].append(annotation)

        for image_id, image_info in images_by_id.items():
            file_name = str(image_info.get("file_name") or "").strip()
            image_path = _resolve_image(file_name, annotation_path.parent, root, image_index)
            if image_path is None:
                _add_error(report, annotation_path, f"COCO 图片不存在：{file_name or image_id}")
                continue
            width, height = _image_size(image_path, image_info.get("width"), image_info.get("height"))
            if width <= 0 or height <= 0:
                _add_error(report, annotation_path, f"无法读取图片尺寸：{image_path}")
                continue

            split = _infer_split(
                default_split,
                _relative_text(root, annotation_path),
                _relative_text(root, image_path),
                file_name,
            )
            labels = []
            for annotation in annotations_by_image.get(image_id, []):
                category_id = annotation.get("category_id")
                class_name = category_names.get(category_id, "")
                if not class_name:
                    _add_error(report, annotation_path, f"COCO category_id 无对应类别：{category_id}")
                    continue
                bbox = annotation.get("bbox")
                normalized = _normalize_absolute_xywh(bbox, width, height)
                if normalized is None:
                    _add_error(report, annotation_path, f"COCO bbox 无效：{bbox}")
                    continue
                labels.append(
                    _detection_label(
                        class_name,
                        normalized,
                        annotation_path,
                        "coco",
                        split,
                        source_class_id=category_id,
                    )
                )
            records.append(_record(root, image_path, labels, split, "coco", annotation_path))
    return records


def _parse_voc(root, files, image_index, report, default_split):
    records = []
    split_map = _load_voc_split_map(root)
    for annotation_path, xml_root in files:
        report["annotation_files"].append(_path_text(annotation_path))
        file_name = _xml_text(xml_root, "filename")
        path_value = _xml_text(xml_root, "path")
        image_path = _resolve_image(path_value or file_name or annotation_path.stem, annotation_path.parent, root, image_index)
        if image_path is None:
            _add_error(report, annotation_path, f"VOC 图片不存在：{file_name or annotation_path.stem}")
            continue

        size_node = xml_root.find("size")
        width_value = _xml_text(size_node, "width") if size_node is not None else ""
        height_value = _xml_text(size_node, "height") if size_node is not None else ""
        width, height = _image_size(image_path, width_value, height_value)
        if width <= 0 or height <= 0:
            _add_error(report, annotation_path, f"无法读取图片尺寸：{image_path}")
            continue

        split = split_map.get(annotation_path.stem) or _infer_split(
            default_split, _relative_text(root, annotation_path), _relative_text(root, image_path)
        )
        labels = []
        for object_node in xml_root.findall("object"):
            class_name = _xml_text(object_node, "name").strip()
            bbox_node = object_node.find("bndbox")
            if not class_name or bbox_node is None:
                _add_error(report, annotation_path, "VOC object 缺少类别或 bndbox")
                continue
            try:
                xmin = float(_xml_text(bbox_node, "xmin"))
                ymin = float(_xml_text(bbox_node, "ymin"))
                xmax = float(_xml_text(bbox_node, "xmax"))
                ymax = float(_xml_text(bbox_node, "ymax"))
            except (TypeError, ValueError):
                _add_error(report, annotation_path, "VOC bndbox 包含非数字坐标")
                continue
            normalized = _normalize_absolute_xyxy([xmin, ymin, xmax, ymax], width, height)
            if normalized is None:
                _add_error(report, annotation_path, f"VOC bndbox 无效：{xmin}, {ymin}, {xmax}, {ymax}")
                continue
            labels.append(_detection_label(class_name, normalized, annotation_path, "voc", split))
        records.append(_record(root, image_path, labels, split, "voc", annotation_path))
    return records


def _parse_labelme(root, files, image_index, report, default_split):
    records = []
    for annotation_path, payload in files:
        report["annotation_files"].append(_path_text(annotation_path))
        image_value = str(payload.get("imagePath") or annotation_path.stem).strip()
        image_path = _resolve_image(image_value, annotation_path.parent, root, image_index)
        if image_path is None:
            _add_error(report, annotation_path, f"LabelMe 图片不存在：{image_value}")
            continue
        width, height = _image_size(image_path, payload.get("imageWidth"), payload.get("imageHeight"))
        if width <= 0 or height <= 0:
            _add_error(report, annotation_path, f"无法读取图片尺寸：{image_path}")
            continue

        split = _infer_split(
            default_split, _relative_text(root, annotation_path), _relative_text(root, image_path)
        )
        labels = []
        for shape in payload.get("shapes", []):
            class_name = str(shape.get("label") or "").strip()
            points = shape.get("points") or []
            bounds = _labelme_bounds(points, str(shape.get("shape_type") or "polygon"))
            if not class_name or bounds is None:
                _add_error(report, annotation_path, "LabelMe shape 缺少有效类别或区域坐标")
                continue
            normalized = _normalize_absolute_xyxy(bounds, width, height)
            if normalized is None:
                _add_error(report, annotation_path, f"LabelMe shape 区域无效：{points}")
                continue
            labels.append(_detection_label(class_name, normalized, annotation_path, "labelme", split))
        records.append(_record(root, image_path, labels, split, "labelme", annotation_path))
    return records


def _parse_yolo(root, pairs, report, default_split):
    records = []
    name_map = _load_yolo_names(root)
    matched_labels: set[Path] = set()
    all_label_files: set[Path] = set()

    for _, label_dir in pairs:
        all_label_files.update(path.resolve() for path in label_dir.rglob("*.txt") if path.is_file())

    for image_dir, label_dir in pairs:
        for image_path in sorted(path for path in image_dir.rglob("*") if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS):
            image_width, image_height = _image_size(image_path)
            relative = image_path.relative_to(image_dir)
            label_path = (label_dir / relative).with_suffix(".txt")
            split = _infer_split(
                default_split, _relative_text(root, image_dir), relative.as_posix()
            )
            labels = []
            if label_path.is_file():
                matched_labels.add(label_path.resolve())
                report["annotation_files"].append(_path_text(label_path))
                try:
                    label_lines = label_path.read_text(encoding="utf-8-sig").splitlines()
                except (OSError, UnicodeError):
                    _add_error(report, label_path, "YOLO 标注文件无法读取")
                    label_lines = []
                for line_number, line in enumerate(label_lines, start=1):
                    parts = line.strip().split()
                    if not parts:
                        continue
                    if len(parts) != 5:
                        _add_error(report, label_path, f"YOLO 第 {line_number} 行不是五列检测标注")
                        continue
                    try:
                        class_id = int(parts[0])
                        bbox = [float(value) for value in parts[1:5]]
                    except (TypeError, ValueError):
                        _add_error(report, label_path, f"YOLO 第 {line_number} 行包含非数字字段")
                        continue
                    normalized = _normalize_yolo_bbox(bbox, image_width, image_height)
                    if class_id < 0 or normalized is None:
                        _add_error(report, label_path, f"YOLO 第 {line_number} 行类别或 bbox 无效")
                        continue
                    class_name = name_map.get(class_id, f"class_{class_id}")
                    labels.append(
                        _detection_label(
                            class_name,
                            normalized,
                            label_path,
                            "yolo",
                            split,
                            source_class_id=class_id,
                        )
                    )
            records.append(_record(root, image_path, labels, split, "yolo", label_path if label_path.is_file() else None))

    for orphan in sorted(all_label_files - matched_labels):
        _add_error(report, orphan, "YOLO 标注文件没有对应图片")
    return records


def _find_yolo_pairs(root: Path) -> list[tuple[Path, Path]]:
    direct_images = root / "images"
    direct_labels = root / "labels"
    if direct_images.is_dir() and direct_labels.is_dir():
        return [(direct_images, direct_labels)]

    pairs = []
    seen = set()
    for image_dir in sorted(path for path in root.rglob("images") if path.is_dir()):
        label_dir = image_dir.parent / "labels"
        if not label_dir.is_dir():
            continue
        key = (str(image_dir.resolve()).casefold(), str(label_dir.resolve()).casefold())
        if key not in seen:
            pairs.append((image_dir, label_dir))
            seen.add(key)
    return pairs


def _load_yolo_names(root: Path) -> dict[int, str]:
    mappings = []
    yaml_paths = sorted(
        {path for name in ("data.yaml", "data.yml") for path in root.rglob(name)},
        key=lambda path: (len(path.parts), str(path).casefold()),
    )
    for yaml_path in yaml_paths:
        try:
            payload = yaml.safe_load(yaml_path.read_text(encoding="utf-8-sig")) or {}
        except (OSError, UnicodeError, yaml.YAMLError):
            continue
        names = payload.get("names")
        mapping = _names_mapping(names)
        if mapping:
            mappings.append(mapping)

    if not mappings:
        for name in ("classes.txt", "obj.names"):
            for path in sorted(root.rglob(name)):
                try:
                    values = [line.strip() for line in path.read_text(encoding="utf-8-sig").splitlines() if line.strip()]
                except (OSError, UnicodeError):
                    continue
                if values:
                    mappings.append({index: value for index, value in enumerate(values)})

    if not mappings:
        return {}
    first = mappings[0]
    if any(mapping != first for mapping in mappings[1:]):
        raise AnnotationFormatError("检测到多份互相冲突的 YOLO 类别名称配置。")
    return first


def _names_mapping(names) -> dict[int, str]:
    if isinstance(names, list):
        return {index: str(value) for index, value in enumerate(names)}
    if isinstance(names, dict):
        result = {}
        for key, value in names.items():
            try:
                result[int(key)] = str(value)
            except (TypeError, ValueError):
                continue
        return result
    return {}


def _resolve_image(reference, annotation_dir, root, image_index) -> Path | None:
    raw = str(reference or "").strip().replace("\\", "/")
    candidates = []
    if raw:
        reference_path = Path(raw)
        if reference_path.is_absolute():
            candidates.append(reference_path)
        candidates.extend((annotation_dir / reference_path, root / reference_path, root / "images" / reference_path))
    for candidate in candidates:
        if candidate.is_file() and candidate.suffix.lower() in IMAGE_EXTENSIONS:
            return candidate.resolve()

    normalized = raw.lstrip("./").casefold()
    if normalized in image_index["by_relative"]:
        return image_index["by_relative"][normalized]
    if normalized:
        suffix_matches = [
            path for relative, path in image_index["by_relative"].items()
            if relative == normalized or relative.endswith(f"/{normalized}")
        ]
        if len(suffix_matches) == 1:
            return suffix_matches[0]
        name_matches = image_index["by_name"].get(Path(normalized).name.casefold(), [])
        if len(name_matches) == 1:
            return name_matches[0]
        stem_matches = image_index["by_stem"].get(Path(normalized).stem.casefold(), [])
        if len(stem_matches) == 1:
            return stem_matches[0]
    return None


def _image_size(image_path: Path, width_value=None, height_value=None) -> tuple[int, int]:
    try:
        width = int(float(width_value))
        height = int(float(height_value))
        if width > 0 and height > 0:
            return width, height
    except (TypeError, ValueError):
        pass
    try:
        with Image.open(image_path) as image:
            return int(image.width), int(image.height)
    except (OSError, ValueError):
        return 0, 0


def _normalize_absolute_xywh(bbox, image_width, image_height):
    if not isinstance(bbox, (list, tuple)) or len(bbox) < 4:
        return None
    try:
        x, y, width, height = [float(value) for value in bbox[:4]]
    except (TypeError, ValueError):
        return None
    return _normalize_absolute_xyxy([x, y, x + width, y + height], image_width, image_height)


def _normalize_yolo_bbox(bbox, image_width: int, image_height: int):
    """兼容标准归一化 YOLO 与像素级 cx/cy/w/h 标签。"""
    try:
        values = [float(value) for value in bbox[:4]]
    except (TypeError, ValueError, IndexError):
        return None
    if all(0.0 <= value <= 1.0 for value in values):
        return sanitize_normalized_bbox(values, tolerance=0.01)
    if image_width <= 0 or image_height <= 0:
        return None
    converted = [
        values[0] / image_width,
        values[1] / image_height,
        values[2] / image_width,
        values[3] / image_height,
    ]
    return sanitize_normalized_bbox(converted, tolerance=0.01)


def _normalize_absolute_xyxy(bbox, image_width, image_height):
    if image_width <= 0 or image_height <= 0:
        return None
    try:
        xmin, ymin, xmax, ymax = [float(value) for value in bbox[:4]]
    except (TypeError, ValueError):
        return None
    if not all(math.isfinite(value) for value in (xmin, ymin, xmax, ymax)):
        return None
    xmin = min(max(xmin, 0.0), float(image_width))
    ymin = min(max(ymin, 0.0), float(image_height))
    xmax = min(max(xmax, 0.0), float(image_width))
    ymax = min(max(ymax, 0.0), float(image_height))
    if xmax <= xmin or ymax <= ymin:
        return None
    normalized = [
        ((xmin + xmax) / 2.0) / image_width,
        ((ymin + ymax) / 2.0) / image_height,
        (xmax - xmin) / image_width,
        (ymax - ymin) / image_height,
    ]
    return normalized if _valid_normalized_bbox(normalized) else None


def sanitize_normalized_bbox(bbox, tolerance: float = NORMALIZED_BBOX_TOLERANCE) -> list[float] | None:
    """修正由小数舍入造成的轻微越界，明显错误仍返回 None。"""
    if not isinstance(bbox, (list, tuple)) or len(bbox) < 4:
        return None
    try:
        cx, cy, width, height = [float(value) for value in bbox[:4]]
    except (TypeError, ValueError):
        return None
    if not all(math.isfinite(value) for value in (cx, cy, width, height)) or width <= 0 or height <= 0:
        return None

    xmin = cx - width / 2.0
    ymin = cy - height / 2.0
    xmax = cx + width / 2.0
    ymax = cy + height / 2.0
    if xmin < -tolerance or ymin < -tolerance or xmax > 1.0 + tolerance or ymax > 1.0 + tolerance:
        return None

    xmin = min(max(xmin, 0.0), 1.0)
    ymin = min(max(ymin, 0.0), 1.0)
    xmax = min(max(xmax, 0.0), 1.0)
    ymax = min(max(ymax, 0.0), 1.0)
    if xmax <= xmin or ymax <= ymin:
        return None
    return [
        (xmin + xmax) / 2.0,
        (ymin + ymax) / 2.0,
        xmax - xmin,
        ymax - ymin,
    ]


def _valid_normalized_bbox(bbox) -> bool:
    return sanitize_normalized_bbox(bbox) is not None


def _labelme_bounds(points, shape_type):
    if not isinstance(points, list) or len(points) < 2:
        return None
    try:
        coords = [(float(point[0]), float(point[1])) for point in points if len(point) >= 2]
    except (TypeError, ValueError):
        return None
    if len(coords) < 2:
        return None
    if shape_type.casefold() == "circle":
        center_x, center_y = coords[0]
        edge_x, edge_y = coords[1]
        radius = math.hypot(edge_x - center_x, edge_y - center_y)
        return [center_x - radius, center_y - radius, center_x + radius, center_y + radius]
    xs = [point[0] for point in coords]
    ys = [point[1] for point in coords]
    return [min(xs), min(ys), max(xs), max(ys)]


def _record(root, image_path, labels, split, annotation_format, annotation_path):
    try:
        relative_path = image_path.relative_to(root).as_posix()
    except ValueError:
        relative_path = image_path.name
    return {
        "source_path": image_path,
        "relative_path": relative_path,
        "labels": labels,
        "metadata": {
            "source_path": _path_text(image_path),
            "label_source": _path_text(annotation_path) if annotation_path else "",
            "annotation_format": annotation_format,
            "split": split,
        },
        "split": split,
        "sample_modality": "image",
        "import_format": f"{annotation_format}_detection",
    }


def _detection_label(class_name, bbox, source, source_format, split, source_class_id=None):
    label = {
        "type": "detection",
        "class_name": str(class_name),
        "bbox": [float(value) for value in bbox[:4]],
        "bbox_format": "cxcywh_normalized",
        "source": _path_text(source),
        "source_format": source_format,
        "split": split,
    }
    if source_class_id is not None:
        label["source_class_id"] = source_class_id
    return label


def _infer_split(default_split, *values) -> str:
    tokens = []
    for value in values:
        text = str(value or "").replace("\\", "/").casefold()
        for part in (part for part in text.split("/") if part):
            tokens.extend(token for token in re.split(r"[_.-]+", part) if token)
    if any(_matches_split_token(token, "test") for token in tokens):
        return "test"
    if any(
        _matches_split_token(token, "val")
        or _matches_split_token(token, "valid")
        or token == "validation"
        for token in tokens
    ):
        return "val"
    if any(_matches_split_token(token, "train") or token == "training" for token in tokens):
        return "train"
    return _normalize_split(default_split)


def _normalize_split(value) -> str:
    split = str(value or "train").strip().casefold()
    if split in {"valid", "validation"}:
        return "val"
    return split if split in {"train", "val", "test"} else "train"


def _matches_split_token(token: str, prefix: str) -> bool:
    if token == prefix:
        return True
    suffix = token[len(prefix):] if token.startswith(prefix) else ""
    return bool(suffix and suffix[0].isdigit())


def _relative_text(root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(root).as_posix()
    except ValueError:
        return path.name


def _load_voc_split_map(root: Path) -> dict[str, str]:
    result = {}
    main_dirs = [path for path in root.rglob("Main") if path.is_dir() and path.parent.name.casefold() == "imagesets"]
    for split in ("test", "val", "train"):
        for main_dir in main_dirs:
            for path in sorted(main_dir.glob(f"{split}*.txt")):
                if path.stem.casefold() == "trainval":
                    continue
                try:
                    lines = path.read_text(encoding="utf-8-sig").splitlines()
                except (OSError, UnicodeError):
                    continue
                for line in lines:
                    stem = line.strip().split()[0] if line.strip() else ""
                    if stem and stem not in result:
                        result[stem] = split
    return result


def _deduplicate_records(records, report):
    unique = {}
    for record in records:
        key = str(Path(record["source_path"]).resolve()).casefold()
        if key in unique:
            _add_error(report, record["source_path"], "同一图片存在多份标注")
            continue
        unique[key] = record
    return list(unique.values())


def _add_error(report, path, message):
    report["errors"].append({"path": _path_text(path), "message": str(message)})


def _path_text(path) -> str:
    return Path(path).expanduser().resolve().as_posix()


def _xml_tag(node) -> str:
    return str(node.tag).rsplit("}", 1)[-1].casefold()


def _xml_text(node, child_name) -> str:
    if node is None:
        return ""
    child = node.find(child_name)
    return str(child.text or "").strip() if child is not None else ""
