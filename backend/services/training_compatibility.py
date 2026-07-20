from __future__ import annotations

import csv
from collections import Counter, defaultdict
from pathlib import Path

from core.data_management.detection_annotations import sanitize_normalized_bbox
from core.data_management.dataset_requirements import normalize_dataset_requirements
from core.data_management.multimodal_association import sample_group_id, sample_path, sample_role


IMAGE_EXTENSIONS = {".bmp", ".jpeg", ".jpg", ".png", ".tif", ".tiff", ".webp"}


def analyze_training_compatibility(dataset, samples, algorithm, parameters: dict | None = None) -> dict:
    key = str(algorithm.key or "")
    params = dict(parameters or {})
    active_samples = [sample for sample in samples if getattr(sample, "status", "") != "deleted"]
    if not active_samples:
        return _result(False, "数据集没有可用样本")

    try:
        declared_requirements = normalize_dataset_requirements(
            (algorithm.validation_rules_json or {}).get("dataset_requirements")
            if getattr(algorithm, "validation_rules_json", None)
            else {}
        )
    except ValueError as exc:
        return _result(False, f"算法的数据集要求配置无效：{exc}")
    if declared_requirements:
        return _analyze_declared_requirements(
            dataset, active_samples, declared_requirements, str(algorithm.modality or "")
        )

    if key == "training.demo_classifier":
        return _result(True, "演示算法接受任意非空数据集")
    if key == "training.ship_classifier":
        images = _image_samples(active_samples)
        if len(images) < 2:
            return _result(False, f"至少需要 2 张可读取图片，当前 {len(images)} 张")
        if any(_detection_labels(sample) for sample in images):
            return _result(False, "舰船分类算法不能把目标检测框当作图片分类标签")
        labeled_names = [name for sample in images for name in _classification_names(sample)[:1]]
        if labeled_names and len(set(labeled_names)) < 2:
            return _result(False, "监督分类至少需要 2 个类别；无标签数据可使用聚类模式")
        return _result(True, f"找到 {len(images)} 张可读取图片")
    if key == "training.image.sonar_oltr_classifier":
        labeled = [sample for sample in _image_samples(active_samples) if _classification_names(sample)]
        if len(labeled) < 10:
            return _result(False, f"至少需要 10 张有分类标签的图片，当前 {len(labeled)} 张")
        counts = Counter(name for sample in labeled for name in _classification_names(sample)[:1])
        if len(counts) < 2:
            return _result(False, "声呐分类至少需要 2 个类别")
        if min(counts.values()) < 2:
            return _result(False, "声呐分类每个类别至少需要 2 张图片")
        return _result(True, f"{len(labeled)} 张有标签图片，{len(counts)} 个类别")
    if key == "training.image.yolov5_detector":
        detected = [sample for sample in _image_samples(active_samples) if _detection_labels(sample)]
        if len(detected) < 2:
            return _result(False, f"YOLOv5 至少需要 2 张带有效检测框的图片，当前 {len(detected)} 张")
        return _result(True, f"{len(detected)} 张图片包含有效检测框")
    if key == "training.multimodal.seg":
        groups = _multimodal_groups(active_samples)
        paired = sum(1 for roles in groups.values() if roles["image"] and roles["mask"])
        return _minimum(paired, 10, "至少需要 10 组同名图片和分割 mask")
    if key == "training.multimodal.fusion_detector":
        groups = _multimodal_groups(active_samples)
        paired = 0
        for roles in groups.values():
            if roles["radar"] and any(_detection_labels(sample) for sample in roles["image"]):
                paired += 1
        return _minimum(paired, 10, "至少需要 10 组图片、检测框和雷达数据")
    if key == "training.timeseries.hyfd_fault_diagnosis":
        csv_path = _first_csv(active_samples)
        if not csv_path:
            return _result(False, "需要包含 CSV 文件")
        header, _ = _csv_shape(csv_path)
        if "MEAN TEMP" not in header or "label" not in header:
            return _result(False, "CSV 必须包含 MEAN TEMP 和 label 列")
        return _result(True, "CSV 包含故障诊断所需列")
    if key == "training.timeseries.ship_predictor":
        csv_path = _first_csv(active_samples)
        if not csv_path:
            return _result(False, "需要包含 AIS CSV 文件")
        header, row_count = _csv_shape(csv_path)
        lookback = int(params.get("lookback_window", 20))
        prediction = int(params.get("prediction_window", 10))
        minimum_rows = max(40, (lookback + prediction) * 7)
        if len(header) < 4:
            return _result(False, "AIS CSV 至少需要 4 个特征列")
        if row_count < minimum_rows:
            return _result(False, f"AIS CSV 至少需要约 {minimum_rows} 行，当前 {row_count} 行")
        return _result(True, f"AIS CSV 包含 {row_count} 行数据")

    expected = str(algorithm.modality or "")
    actual = str(dataset.modality or "")
    if expected not in {actual, "multimodal"}:
        return _result(False, f"算法需要 {expected} 数据，当前数据集为 {actual}")
    return _result(True, "数据集模态与算法匹配")


def build_dataset_summary(dataset, samples) -> dict:
    active_samples = [sample for sample in samples if getattr(sample, "status", "") != "deleted"]
    extensions = Counter(Path(sample_path(sample)).suffix.casefold() for sample in active_samples)
    roles = Counter(sample_role(sample) for sample in active_samples)
    groups = _multimodal_groups(active_samples)
    class_counts = _class_counts(active_samples, {"classification", "detection"})
    csv_path = _first_csv(active_samples)
    csv_header, csv_rows = _csv_shape(csv_path) if csv_path else ([], 0)
    return {
        "dataset_id": getattr(dataset, "id", 0),
        "modality": str(getattr(dataset, "modality", "") or ""),
        "sample_count": len(active_samples),
        "extensions": dict(extensions),
        "label_types": sorted(_available_label_types(active_samples)),
        "class_distribution": dict(class_counts),
        "multimodal_role_counts": dict(roles),
        "multimodal_group_count": len(groups),
        "csv_columns": csv_header,
        "csv_row_count": csv_rows,
    }


def _analyze_declared_requirements(dataset, samples, requirements: dict, fallback_modality: str) -> dict:
    modalities = set(requirements.get("modalities") or [])
    if modalities and str(dataset.modality or "") not in modalities:
        return _result(False, f"算法要求数据模态 {sorted(modalities)}，当前为 {dataset.modality}")
    if not modalities and fallback_modality not in {str(dataset.modality or ""), "multimodal"}:
        return _result(False, f"算法需要 {fallback_modality} 数据，当前数据集为 {dataset.modality}")

    label_types = set(requirements.get("label_types") or [])
    primary_samples = _primary_samples(samples, label_types)
    minimum_samples = int(requirements.get("min_samples") or 0)
    if len(primary_samples) < minimum_samples:
        return _result(False, f"至少需要 {minimum_samples} 个主样本，当前 {len(primary_samples)} 个")

    extensions = {Path(sample_path(sample)).suffix.casefold() for sample in samples}
    missing_extensions = set(requirements.get("required_extensions") or []) - extensions
    if missing_extensions:
        return _result(False, f"缺少必需文件类型: {sorted(missing_extensions)}")

    required_columns = list(requirements.get("required_columns") or [])
    if required_columns:
        csv_path = _first_csv(samples)
        if not csv_path:
            return _result(False, "算法要求 CSV 文件")
        header, _ = _csv_shape(csv_path)
        missing_columns = [column for column in required_columns if column not in header]
        if missing_columns:
            return _result(False, f"CSV 缺少必需列: {missing_columns}")

    required_roles = set(requirements.get("required_companion_roles") or [])
    if required_roles:
        required_roles.add("image")
        groups = _multimodal_groups(samples)
        complete_groups = sum(
            1
            for roles in groups.values()
            if all(roles.get(role) for role in required_roles)
        )
        minimum_groups = max(1, int(requirements.get("min_complete_groups") or 1))
        if complete_groups < minimum_groups:
            return _result(
                False,
                f"至少需要 {minimum_groups} 个包含 {sorted(required_roles)} 的完整组，当前 {complete_groups} 个",
            )

    available_label_types = _available_label_types(samples)
    if label_types and not label_types.intersection(available_label_types):
        return _result(
            False,
            f"算法要求标签类型 {sorted(label_types)}，当前为 {sorted(available_label_types)}",
        )

    if requirements.get("bbox_required") and "detection" not in available_label_types:
        return _result(False, "算法要求有效的归一化检测框")

    class_counts = _class_counts(samples, label_types)
    minimum_classes = int(requirements.get("min_classes") or 0)
    if len(class_counts) < minimum_classes:
        return _result(False, f"至少需要 {minimum_classes} 个类别，当前 {len(class_counts)} 个")
    minimum_per_class = int(requirements.get("min_samples_per_class") or 0)
    if minimum_per_class and class_counts and min(class_counts.values()) < minimum_per_class:
        return _result(False, f"每个类别至少需要 {minimum_per_class} 个标注样本")

    if requirements.get("allow_unlabeled") is False:
        if "segmentation" in label_types:
            groups = _multimodal_groups(samples)
            unlabeled_groups = [
                group_id
                for group_id, roles in groups.items()
                if roles.get("image") and not roles.get("mask")
            ]
            if unlabeled_groups:
                return _result(False, "算法不允许存在缺少分割 mask 的图片")
            return _result(True, "满足算法声明的数据集要求")
        labeled_ids = {
            id(sample)
            for sample in primary_samples
            if _sample_matches_label_types(sample, label_types)
        }
        if len(labeled_ids) < len(primary_samples):
            return _result(False, "算法不允许存在无标签主样本")

    return _result(True, "满足算法声明的数据集要求")


def _result(compatible: bool, reason: str) -> dict:
    return {"compatible": compatible, "reason": reason}


def _minimum(count: int, minimum: int, message: str) -> dict:
    if count < minimum:
        return _result(False, f"{message}，当前 {count} 组")
    return _result(True, f"找到 {count} 组有效数据")


def _image_samples(samples) -> list:
    return [
        sample
        for sample in samples
        if Path(sample_path(sample)).suffix.casefold() in IMAGE_EXTENSIONS
    ]


def _labels(sample) -> list[dict]:
    values = getattr(sample, "labels_json", None) or []
    return [value for value in values if isinstance(value, dict)]


def _classification_names(sample) -> list[str]:
    result = []
    for label in _labels(sample):
        if label.get("type") == "detection" or label.get("bbox"):
            continue
        class_name = str(label.get("class_name") or label.get("name") or "").strip()
        if class_name:
            result.append(class_name)
    return result


def _detection_labels(sample) -> list[dict]:
    result = []
    for label in _labels(sample):
        bbox = sanitize_normalized_bbox(label.get("bbox") or [])
        class_name = str(label.get("class_name") or label.get("name") or "").strip()
        if bbox is not None and class_name:
            result.append(label)
    return result


def _available_label_types(samples) -> set[str]:
    result = set()
    if any(_classification_names(sample) for sample in samples):
        result.add("classification")
    if any(_detection_labels(sample) for sample in samples):
        result.add("detection")
    if any(sample_role(sample) == "mask" for sample in samples):
        result.add("segmentation")
    if not result:
        result.add("none")
    return result


def _primary_samples(samples, label_types: set[str]) -> list:
    if "segmentation" in label_types:
        return [sample for sample in samples if sample_role(sample) == "image"]
    if label_types.intersection({"classification", "detection"}):
        return _image_samples(samples)
    return [sample for sample in samples if sample_role(sample) not in {"annotation", "auxiliary"}]


def _sample_matches_label_types(sample, label_types: set[str]) -> bool:
    if not label_types or "none" in label_types:
        return True
    if "classification" in label_types and _classification_names(sample):
        return True
    if "detection" in label_types and _detection_labels(sample):
        return True
    if "segmentation" in label_types:
        return sample_role(sample) == "image"
    return False


def _class_counts(samples, label_types: set[str]) -> Counter:
    counts = Counter()
    for sample in samples:
        if not label_types or "classification" in label_types:
            for class_name in _classification_names(sample)[:1]:
                counts[class_name] += 1
        if "detection" in label_types:
            for label in _detection_labels(sample):
                class_name = str(label.get("class_name") or label.get("name") or "").strip()
                if class_name:
                    counts[class_name] += 1
    return counts


def _multimodal_groups(samples) -> dict:
    groups = defaultdict(lambda: defaultdict(list))
    for sample in samples:
        groups[sample_group_id(sample)][sample_role(sample)].append(sample)
    return groups


def _first_csv(samples) -> Path | None:
    for sample in samples:
        path = Path(sample_path(sample))
        if path.suffix.casefold() == ".csv" and path.is_file():
            return path
    return None


def _csv_shape(path: Path) -> tuple[list[str], int]:
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.reader(handle)
            header = next(reader, [])
            row_count = sum(1 for row in reader if row)
        return header, row_count
    except OSError:
        return [], 0
